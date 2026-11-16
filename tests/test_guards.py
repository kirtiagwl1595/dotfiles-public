"""The guards ported from the source setup: each behavior they had before the cross-platform port."""

import json
import subprocess
import sys

import pytest
from hookrun import HOME, HOOKS, bash, decision, env_for, run, run_text


def blocked(hook, payload):
    code, _, err = run(hook, payload)
    return code == 2 and "Blocked" in err


def quiet(hook, payload):
    """Allowed with no decision. A crash also exits 0, but prints a deny: stdout must be empty."""
    code, out, err = run(hook, payload)
    return (code, out) == (0, ""), err


# ── guard_secrets ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Read", "tool_input": {"file_path": f"{HOME}/.ssh/id_ed25519"}},
        {"tool_name": "Read", "tool_input": {"file_path": "/repo/.env"}},
        {
            "tool_name": "Read",
            "tool_input": {"file_path": f"{HOME}/Library/Keychains/login.keychain-db"},
        },
        {"tool_name": "Grep", "tool_input": {"pattern": "x", "path": f"{HOME}/.ssh"}},
        bash("cat ~/.ssh/id_rsa"),
        bash("cat .env | grep KEY"),
        bash(f"head {HOME}/Documents/taxes.pdf"),
        bash("security find-generic-password -a me -s ANTHROPIC_API_KEY -w"),
        bash("security dump-keychain -d"),
        bash("cat .env.staging"),
        {"tool_name": "Glob", "tool_input": {"pattern": "**/.env*"}},
        {"tool_name": "Grep", "tool_input": {"pattern": "KEY", "glob": ".env.local"}},
        {"tool_name": "Write", "tool_input": {"file_path": f"{HOME}/.aws/config"}},
        {"tool_name": "Edit", "tool_input": {"file_path": f"{HOME}/.ssh/config"}},
        {"tool_name": "Write", "tool_input": {"file_path": f"{HOME}/.ssh/known_hosts"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/repo/prod.env"}},
        bash("echo x > ~/.aws/credentials"),
        bash("cp prod.env /tmp/"),
        bash("cat foo.env"),
    ],
)
def test_secrets_blocked(payload):
    code, _, err = run("guard_secrets.py", payload)
    assert code == 2
    assert "private" in err.lower()


def test_secrets_advice_names_no_file_the_deny_rules_block():
    # settings.base.json denies Read(**/.env.*), so .env.example is no way out
    err = run("guard_secrets.py", bash("cat .env"))[2]
    assert ".env.example" not in err


@pytest.mark.parametrize(
    "payload",
    [
        {
            "tool_name": "Read",
            "tool_input": {"file_path": f"{HOME}/.ssh/id_ed25519.pub"},
        },
        {"tool_name": "Read", "tool_input": {"file_path": "/repo/.env.example"}},
        {"tool_name": "Read", "tool_input": {"file_path": "/repo/src/environment.py"}},
        bash("ls -la"),
        bash("git status"),
        bash("cp .env.example .env.sample"),
        {"tool_name": "Glob", "tool_input": {"pattern": "**/*.py"}},
        {"tool_name": "Glob", "tool_input": {"pattern": "**/.env.example"}},
        {"tool_name": "Grep", "tool_input": {"pattern": ".env", "glob": "*.md"}},
        {"tool_name": "Read", "tool_input": {"file_path": f"{HOME}/.ssh/config"}},
        {"tool_name": "Read", "tool_input": {"file_path": "/repo/.envrc"}},
        bash('node -e "console.log(process.env.HOME)"'),
        bash('node -e "console.log(process.env)"'),
        bash('node -e "console.log(process.env.PATH)"'),
    ],
)
def test_secrets_allowed(payload):
    ok, err = quiet("guard_secrets.py", payload)
    assert ok, err


# ── guard_pip ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "cmd",
    [
        "pip install pandas",
        "pip3 install -U numpy",
        "python -m pip install x",
        "cd a && pip install -r req.txt",
        "python3.12 -m pip install x",
        "sudo -H pip install x",
    ],
)
def test_pip_blocked(cmd):
    code, _, err = run("guard_pip.py", bash(cmd))
    assert code == 2
    assert "uv add" in err


@pytest.mark.parametrize(
    "cmd",
    [
        "uv add pandas",
        "uv pip install x",
        "pip list",
        "pip show numpy",
        "echo pip install",
    ],
)
def test_pip_allowed(cmd):
    ok, err = quiet("guard_pip.py", bash(cmd))
    assert ok, err


# ── guard_main_branch ───────────────────────────────────────────────────────
def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(
        tmp_path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    return tmp_path


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -m x",
        "git push",
        "git push origin main",
        "git add . && git commit -am x",
        "git -c core.editor=true commit -m x",
        "git --no-pager commit -m x",
        "env X=1 git commit -m x",
    ],
)
def test_main_blocked(repo, cmd):
    code, _, err = run("guard_main_branch.py", bash(cmd, cwd=repo))
    assert code == 2
    assert "git switch -c" in err


def test_feature_branch_allowed(repo):
    git(repo, "switch", "-q", "-c", "feature/x")
    ok, err = quiet("guard_main_branch.py", bash("git commit -m x", cwd=repo))
    assert ok, err


def test_opt_out_allowed(repo):
    git(repo, "config", "claude.allowMain", "true")
    ok, err = quiet("guard_main_branch.py", bash("git commit -m x", cwd=repo))
    assert ok, err


def test_cd_into_repo_is_followed(repo, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere")
    cmd = f"cd {repo.as_posix()} && git commit -m x"
    assert run("guard_main_branch.py", bash(cmd, cwd=other))[0] == 2


@pytest.mark.parametrize(
    "cmd",
    [
        "git status",
        "git log --oneline",
        "git switch -c feature/y",
        "echo 'git commit -m x' >> notes.txt",
    ],
)
def test_main_read_only_allowed(repo, cmd):
    ok, err = quiet("guard_main_branch.py", bash(cmd, cwd=repo))
    assert ok, err


def test_first_commit_on_main_allowed(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    ok, err = quiet("guard_main_branch.py", bash("git commit -m 'Init'", cwd=tmp_path))
    assert ok, err
    assert run("guard_main_branch.py", bash("git push", cwd=tmp_path))[0] == 2


@pytest.mark.parametrize(
    "cmd, code",
    [
        ("git push -u origin chore/x", 0),
        ("git push origin feature/x:feature/x", 0),
        ("git push", 2),
        ("git push origin", 2),
        ("git push origin HEAD", 2),
        ("git push origin main", 2),
        ("git push origin feature/x:main", 2),
        ("git push origin feature/x && git push origin main", 2),
    ],
)
def test_push_named_branch_from_main(repo, cmd, code):
    assert run("guard_main_branch.py", bash(cmd, cwd=repo))[0] == code


@pytest.mark.parametrize(
    "cmd",
    [
        "git merge feature/x",
        "git rebase feature/x",
        "git cherry-pick abc",
        "git am x.patch",
        "git revert HEAD",
        "git status && git commit -m x",
    ],
)
def test_history_writes_on_main_blocked(repo, cmd):
    assert run("guard_main_branch.py", bash(cmd, repo))[0] == 2


def test_later_write_on_main_blocked(repo, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    git(other, "init", "-q", "-b", "feature/x")
    cmd = f"git -C {other.as_posix()} commit -m x && git commit -m y"
    assert run("guard_main_branch.py", bash(cmd, repo))[0] == 2


@pytest.mark.parametrize(
    "cmd",
    [
        "git rebase --onto origin/main old next",
        "git rebase --abort",
        "git merge --abort",
    ],
)
def test_rebase_of_another_branch_and_abort_allowed(repo, cmd):
    ok, err = quiet("guard_main_branch.py", bash(cmd, repo))
    assert ok, err


# ── fail closed ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "hook",
    [
        "guard_secrets.py",
        "guard_compound.py",
        "guard_main_branch.py",
        "guard_private_terms.py",
        "guard_pip.py",
        "guard_bash.py",
    ],
)
@pytest.mark.parametrize("text", ["", "not json", "[1, 2]"])
def test_bad_input_blocks(hook, text):
    assert run_text(hook, text)[0] == 2


# ── guard_bash (the one wired Bash hook) ────────────────────────────────────
@pytest.mark.parametrize(
    "cmd, expected",
    [
        ("pip install x", "block"),
        ("cat ~/.ssh/id_rsa", "block"),
        ("git push origin feature/x", "ask"),
        ("git status", None),
    ],
)
def test_bash_dispatcher_runs_every_bash_guard(cmd, expected, tmp_path):
    assert decision("guard_bash.py", bash(cmd, cwd=tmp_path)) == expected


@pytest.mark.parametrize(
    "cmd",
    [
        "cat .en*",
        "cat .e?v.local",
        "cat ~/.s?h/id_ed25519",
        "cat ~/Docu*/x",
        "security find-generic-password -s NAME -g",
        "echo x > ~/.ssh/config",
        "echo x | tee -a ~/.ssh/config",
        "cat ~/.ssh/id_rsa;config",
        "cd ~/.ssh && cat id_ed25519",
        "ls ~/.ssh",
    ],
)
def test_globs_and_other_secret_forms_blocked(cmd):
    assert blocked("guard_secrets.py", bash(cmd))


@pytest.mark.parametrize(
    "cmd", ["ls *.py", "grep '.*' notes.txt", "cat .env.exam*", "cat ~/.ssh/config"]
)
def test_ordinary_globs_allowed(cmd):
    ok, err = quiet("guard_secrets.py", bash(cmd))
    assert ok, err


# ── run_guard ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("error", ["KeyError('x')", "OSError('x')", "StopIteration()"])
def test_a_crash_in_a_check_denies(error):
    code = (
        "import io, sys\n"
        f"sys.path.insert(0, {str(HOOKS)!r})\n"
        "import _common\n"
        "sys.stdin = io.TextIOWrapper(io.BytesIO(b'{}'))\n"
        "def check(data):\n"
        f"    raise {error}\n"
        "_common.run_guard(check)\n"
    )
    p = subprocess.run(
        [sys.executable, "-c", code], check=False, capture_output=True, text=True
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "guard failed" in out["permissionDecisionReason"]


def test_a_crash_while_reading_the_payload_denies_through_guard_bash():
    # Deep nesting raises RecursionError in the JSON parser, which is not a BAD_INPUT error
    code, out, err = run_text("guard_bash.py", "[" * 500000)
    assert code == 0, err
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ── guard_bash import failure ───────────────────────────────────────────────
@pytest.mark.parametrize("sibling", [None, "def broken(:\n"])
def test_guard_bash_blocks_when_a_guard_cannot_load(tmp_path, sibling):
    (tmp_path / "guard_bash.py").write_text((HOOKS / "guard_bash.py").read_text())
    if sibling:
        (tmp_path / "guard_compound.py").write_text(sibling)
    p = subprocess.run(
        [sys.executable, "-B", str(tmp_path / "guard_bash.py")],
        check=False,
        input=json.dumps(bash("ls")),
        capture_output=True,
        text=True,
        env=env_for(),
    )
    assert p.returncode == 2
    assert "Blocked" in p.stderr
