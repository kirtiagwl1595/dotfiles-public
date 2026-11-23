"""claude/repo_setup.py (the setup-repo skill): a managed .gitignore block, project settings and
the quiet-pytest block, committed once on chore/claude-forward. Dirty repos, team repos and
tracked secrets are never changed unasked; a failed repo is rolled back."""

import json
import os
import shutil
import subprocess
import sys

import pytest
from hookrun import IDENTITY, ROOT, env_for

SCRIPT = ROOT / "claude" / "repo_setup.py"
BRANCH = "chore/claude-forward"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=env_for(**IDENTITY),
    ).stdout


def make_repo(path, files):
    path.mkdir(parents=True)
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text, encoding="utf-8")
    git(path, "init", "-q", "-b", "main")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")


def run(*args, script=SCRIPT, **extra):
    p = subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env_for(**IDENTITY, PYTHONUTF8="1", **extra),
    )
    assert "Traceback" not in p.stderr, p.stderr
    return p.returncode, p.stdout + p.stderr


def committed(repo, path):
    p = subprocess.run(
        ["git", "-C", str(repo), "show", f"{BRANCH}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return p.stdout if p.returncode == 0 else None


@pytest.fixture
def repos(tmp_path):
    root = tmp_path / "git"
    make_repo(
        root / "py-proj",
        {"pyproject.toml": '[project]\nname = "p"\n', "src/app.py": "x = 1\n"},
    )
    make_repo(root / "r-proj", {"analysis.Rmd": "# hi\n", ".gitignore": ".Rhistory\n"})
    make_repo(root / "group/web", {"package.json": "{}\n", "CLAUDE.md": "# web\n"})
    make_repo(root / "dirty", {"a.py": "x = 1\n"})
    (root / "dirty/a.py").write_text("x = 2\n", encoding="utf-8")
    return root


def test_plan_lists_each_repo_and_changes_nothing(repos):
    code, out = run("plan", repos)
    assert code == 0, out
    assert "py-proj [python]" in out and "r-proj [r]" in out
    assert "web [node]" in out
    assert "dirty: has uncommitted changes, skipped" in out
    assert committed(repos / "py-proj", ".gitignore") is None


def test_one_repo_as_root(repos):
    code, out = run("plan", repos / "py-proj")
    assert code == 0 and "py-proj [python]" in out and "r-proj" not in out


def test_apply_commits_on_the_branch_once(repos):
    run("apply", repos)
    py_ignore = committed(repos / "py-proj", ".gitignore")
    assert ".venv/" in py_ignore and "CLAUDE.local.md" in py_ignore
    assert "node_modules/" not in py_ignore
    assert "addopts" in committed(repos / "py-proj", "pyproject.toml")
    r_ignore = committed(repos / "r-proj", ".gitignore")
    assert r_ignore.startswith(".Rhistory\n") and ".Rproj.user/" in r_ignore
    for repo in ("py-proj", "r-proj", "group/web"):
        assert git(repos / repo, "branch", "--show-current").strip() == "main"
    assert committed(repos / "dirty", ".gitignore") is None
    _, again = run("plan", repos)
    assert "→" not in again and "py-proj: ready on chore/claude-forward" in again
    assert "→" not in run("apply", repos)[1]


def test_bash_allow_rules_only_where_a_sandbox_exists(repos):
    # Native Windows has no sandbox: an allow rule would run the command with no question
    run("apply", repos)
    settings = committed(repos / "group/web", ".claude/settings.json")
    if os.name == "nt":
        assert json.loads(settings)["permissions"]["allow"] == []
    else:
        assert "Bash(npm test:*)" in json.loads(settings)["permissions"]["allow"]


def test_merged_branch_does_not_block_new_changes(repos):
    run("apply", repos)
    py = repos / "py-proj"
    git(py, "merge", "-q", "--ff-only", BRANCH)
    (py / ".gitignore").write_text("only-my-line\n", encoding="utf-8")
    git(py, "commit", "-qam", "drop block")
    _, out = run("plan", repos)
    assert "→ py-proj" in out and "py-proj: ready on" not in out


def test_env_templates_are_not_flagged(repos):
    make_repo(
        repos / "tpl",
        {"app.py": "x = 1\n", ".env.template": "API_KEY=\n", ".env.sample": "A=\n"},
    )
    assert "tpl: personal/secret" not in run("plan", repos)[1]


def test_tracked_secret_is_flagged_and_untracked_only_on_request(repos):
    leaky = repos / "leaky"
    make_repo(leaky, {"app.py": "x = 1\n", ".env": "API_KEY=abc\n"})
    _, out = run("apply", repos)
    assert "leaky: personal/secret files are tracked: .env" in out
    assert "rotate any key" in out and "--untrack" in out
    assert ".env" in git(leaky, "ls-files").split()
    assert ".env" in committed(leaky, ".gitignore")
    run("apply", repos, "--untrack")
    assert ".env" not in git(leaky, "ls-tree", "-r", "--name-only", BRANCH).split()
    assert (leaky / ".env").exists()  # untracked, still on disk


def test_tracked_lessons_are_flagged(repos):
    taught = repos / "taught"
    make_repo(taught, {"app.py": "x = 1\n", ".claude/lessons/2026-01-01-x.md": "# x\n"})
    _, out = run("apply", repos)
    assert "taught: personal/secret files are tracked: .claude/lessons/" in out
    assert ".claude/lessons/" in committed(taught, ".gitignore")


def test_repo_that_ignores_claude_dir_gets_gitignore_only(repos):
    make_repo(repos / "team", {"app.py": "x = 1\n", ".gitignore": ".claude/\n"})
    run("apply", repos)
    assert ".venv/" in committed(repos / "team", ".gitignore")
    assert committed(repos / "team", ".claude/settings.json") is None


def test_failed_repo_is_rolled_back(repos):
    bad = repos / "hooked"
    make_repo(bad, {"app.py": "x = 1\n"})
    hook = bad / ".git" / "hooks" / "pre-commit"
    hook.write_bytes(b"#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    _, out = run("apply", repos)
    assert "hooked: failed, nothing changed" in out
    assert git(bad, "status", "--porcelain", "-b").splitlines() == ["## main"]
    assert git(bad, "branch", "--list", BRANCH) == ""
    assert "py-proj: committed" in out  # the other repos still ran


@pytest.mark.parametrize(
    "url, team",
    [
        ("https://github.com/me/x.git", False),
        ("git@github.com:me/x.git", False),
        ("ssh://git@gitlab.example-corp.com:2222/Me/x.git", False),
        ("https://github.com/acme/x.git", True),
        ("git@gitlab.example-corp.com:group/sub/x.git", True),
    ],
)
def test_team_repos_are_skipped_in_a_folder_scan(repos, url, team):
    r = repos / "remote-case"
    make_repo(r, {"app.py": "x = 1\n"})
    git(r, "remote", "add", "origin", url)
    _, out = run("plan", repos, FORGE_GIT_USER="me")
    assert ("remote-case: team repo" in out) == team
    assert ("→ remote-case [" in out) == (not team)


@pytest.mark.parametrize(
    "url, owner",
    [
        ("https://github.com/me/x.git", None),
        ("git@gitlab.example-corp.com:group/sub/x.git", "group"),
    ],
)
def test_team_subcommand_for_the_skill(repos, url, owner):
    r = repos / "remote-case"
    make_repo(r, {"app.py": "x = 1\n"})
    git(r, "remote", "add", "origin", url)
    code, out = run("team", r, FORGE_GIT_USER="me")
    assert (code, out.strip() or None) == (0 if owner else 1, owner)


def test_runs_from_the_plugin_cache(repos, tmp_path):
    # The plugin cache holds claude/ at its root, with no repo around it
    cache = tmp_path / "cache" / "safe-lean" / "9.9.9"
    shutil.copytree(ROOT / "claude", cache)
    r = repos / "py-proj"
    git(r, "remote", "add", "origin", "https://github.com/me/x")
    script = cache / "repo_setup.py"
    assert run("team", r, script=script, FORGE_GIT_USER="me")[0] == 1
    code, out = run("plan", r, script=script, FORGE_GIT_USER="me")
    assert code == 0 and "pyproject.toml" in out  # the pytest block reads templates/


def test_skill_starts_python_through_the_launcher():
    skill = (ROOT / "claude" / "skills" / "setup-repo" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" ../repo_setup.py' in skill
    assert "python3 " not in skill
    assert "outside the sandbox" in skill
