"""guard_loop: what the agent may not do during a loop, in both profiles (§13.1)."""

import json

import _loop
import pytest
from loop_fixtures import (
    HOOKS,
    LOOP_MARKS,
    VERIFY,
    confirm,
    git,
    run_hook,
)

pytestmark = LOOP_MARKS

GUARD = HOOKS / "guard_loop.py"
BASH = HOOKS / "guard_bash.py"


def call(env, tool, cwd=None, hook=None, mode=None, **tool_input):
    """The hook Claude Code runs: guard_bash for Bash, guard_loop for the file tools."""
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(cwd or env.wt)}
    if mode:
        payload["permission_mode"] = mode
    hook = hook or (BASH if tool == "Bash" else GUARD)
    code, out, err = run_hook(hook, payload)
    assert code == 0, err
    return out.get("hookSpecificOutput", {})


def denied(out):
    return out.get("permissionDecision") == "deny"


def asked(out):
    return out.get("permissionDecision") == "ask"


def with_baseline(env, profile="personal"):
    confirm(env)
    s = _loop.load_state(env.wt)
    s["baseline"] = {"prints-ok": 1, "runs": 0}
    s["profile"] = profile
    _loop.save_state(s)


# ── outside a loop the guard says nothing ───────────────────────────────────
@pytest.mark.parametrize("where", ["no state", "root", "missing", "not git"])
def test_quiet_outside_a_loop(loop_env, where):
    cwd = {
        "no state": loop_env.wt,
        "root": "/",
        "missing": loop_env.tmp / "missing",
        "not git": loop_env.tmp,
    }[where]
    out = call(loop_env, "Write", cwd=cwd, file_path=str(loop_env.wt / "tests/x.py"))
    assert out == {}
    # guard_loop alone: through guard_bash, guard_compound asks for `reset --hard` anyway
    assert call(loop_env, "Bash", cwd=cwd, hook=GUARD, command="git reset --hard") == {}


def test_quiet_after_the_loop_is_done(loop_env):
    with_baseline(loop_env)
    s = _loop.load_state(loop_env.wt)
    s["status"] = "done"
    _loop.save_state(s)
    assert (
        call(loop_env, "Edit", file_path=str(loop_env.wt / "tests/test_tool.py")) == {}
    )


# ── baseline first ──────────────────────────────────────────────────────────
def test_no_edit_before_the_baseline(loop_env):
    confirm(loop_env)
    out = call(loop_env, "Edit", file_path=str(loop_env.wt / "tool.sh"))
    assert denied(out) and "baseline" in out["permissionDecisionReason"]
    progress = loop_env.wt / ".loop/loop-progress.md"
    assert not denied(call(loop_env, "Write", file_path=str(progress)))


# ── protected paths ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "rel",
    [
        "tests/test_tool.py",
        "sub/conftest.py",
        "ruff.toml",
        ".loop/LOOP.md",
        ".loop/loop-features.json",
        ".loop/run.json",
        ".loop/bin/loopctl.py",
        "keep.txt",
    ],
)
def test_protected_file_writes_are_denied(loop_env, rel):
    with_baseline(loop_env)
    for tool in ("Edit", "Write", "MultiEdit"):
        assert denied(call(loop_env, tool, file_path=str(loop_env.wt / rel)))
    assert denied(call(loop_env, "NotebookEdit", notebook_path=str(loop_env.wt / rel)))


def test_target_and_progress_writes_pass(loop_env):
    with_baseline(loop_env)
    for rel in ("tool.sh", ".loop/loop-progress.md", ".loop/bundle.md"):
        assert not denied(call(loop_env, "Write", file_path=str(loop_env.wt / rel)))


def test_state_file_is_denied(loop_env):
    with_baseline(loop_env)
    path = _loop.state_path(loop_env.wt)
    assert denied(call(loop_env, "Write", file_path=str(path)))
    assert denied(call(loop_env, "Bash", command=f"echo x > {path}"))


def test_the_running_plugin_code_is_denied(loop_env):
    # The judge must not be editable from inside the loop, wherever the plugin copy lives
    with_baseline(loop_env)
    for rel in ("hooks/loop_hook.py", "loopctl.py", "templates/loop/LOOP.md"):
        path = HOOKS.parent / rel
        assert denied(call(loop_env, "Edit", file_path=str(path)))
    assert denied(call(loop_env, "Bash", command=f"echo x >> {HOOKS / 'x.py'}"))


@pytest.mark.parametrize("where", ["main checkout", "lessons", "home", "tmp"])
def test_every_write_outside_the_worktree_is_denied(loop_env, where):
    # File tools run outside the sandbox: during a loop they may write only in the worktree
    with_baseline(loop_env)
    path = {
        "main checkout": loop_env.main / "tool.sh",
        "lessons": loop_env.main / ".claude/lessons/x.md",
        "home": loop_env.home / "notes.md",
        "tmp": loop_env.tmp / "scratch.txt",
    }[where]
    for tool in ("Write", "Edit", "MultiEdit"):
        out = call(loop_env, tool, file_path=str(path))
        assert denied(out) and "outside the worktree" in out["permissionDecisionReason"]
    assert denied(call(loop_env, "Bash", command=f"echo x > {path}"))


def test_null_devices_and_the_loop_lesson_stay_allowed(loop_env):
    with_baseline(loop_env)
    for cmd in ("ls > /dev/null", "ls 2>/dev/null", "echo x >&2"):
        assert not denied(call(loop_env, "Bash", command=cmd)), cmd
    lesson = loop_env.wt / ".loop/lesson.md"
    assert not denied(call(loop_env, "Write", file_path=str(lesson)))


def test_approved_path_passes(loop_env):
    with_baseline(loop_env)
    s = _loop.load_state(loop_env.wt)
    s["approved_paths"] = ["tests/test_tool.py"]
    _loop.save_state(s)
    path = str(loop_env.wt / "tests/test_tool.py")
    assert not denied(call(loop_env, "Edit", file_path=path))


@pytest.mark.parametrize(
    "cmd",
    [
        "echo x > tests/test_tool.py",
        "echo x >> .loop/LOOP.md",
        "printf x | tee .loop/loop-features.json",
        "cd tests && echo x > test_tool.py",
    ],
)
def test_bash_writes_to_protected_paths_are_denied(loop_env, cmd):
    with_baseline(loop_env)
    assert denied(call(loop_env, "Bash", command=cmd))


# ── git writes ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -qm x",
        "git reset --hard HEAD~1",
        "git checkout -- tool.sh",
        "git switch main",
        "git stash",
        "git clean -fd",
        "git restore tool.sh",
        "cd .. && git -C wt revert HEAD",
        "git push",
        "cd .. && git push origin loop/demo",
        "git -C wt push",
    ],
)
def test_agent_git_writes_are_denied(loop_env, cmd):
    with_baseline(loop_env)
    out = call(loop_env, "Bash", command=cmd)
    assert denied(out), out


def test_git_reads_pass(loop_env):
    with_baseline(loop_env)
    reads = ("git log --oneline -5", "git status", "git diff HEAD", "git stash list")
    for cmd in reads:
        assert not denied(call(loop_env, "Bash", command=cmd))


def test_switch_on_main_stays_allowed_outside_a_loop(loop_env):
    # guard_main_branch must not learn the loop-only verbs: `git switch -c` is the workflow
    p = call(loop_env, "Bash", cwd=loop_env.main, command="git switch -c feature/x")
    assert p == {}


# ── deletes outside the worktree ────────────────────────────────────────────
@pytest.mark.parametrize(
    "cmd, bad",
    [
        ("rm -f ../main/keep.txt", True),
        ("rm -rf $HOME/x", True),
        ("rmdir /tmp/x", True),
        ("mv tool.sh ../elsewhere.sh", True),
        ("cd .. && rm main/keep.txt", True),
        ("find .. -name '*.pyc' -delete", True),
        ("rm -f build/out.txt", False),
        ("find . -name '*.pyc' -delete", False),
        ("mv a.txt b.txt", False),
    ],
)
def test_deletes_outside_the_worktree(loop_env, cmd, bad):
    with_baseline(loop_env)
    assert denied(call(loop_env, "Bash", command=cmd)) is bad


# ── the sandbox flag and the verifier ───────────────────────────────────────
def test_sandbox_flag_is_denied(loop_env):
    with_baseline(loop_env)
    out = call(loop_env, "Bash", command="ls", dangerouslyDisableSandbox=True)
    assert denied(out) and "sandbox" in out["permissionDecisionReason"]
    out = call(loop_env, "Bash", command=VERIFY, dangerouslyDisableSandbox=True)
    assert denied(out)  # a script target: the verifier runs in the sandbox


def test_skill_verifier_may_leave_the_sandbox_in_the_personal_profile(loop_env):
    with_baseline(loop_env)
    s = _loop.load_state(loop_env.wt)
    s["target_type"] = "skill"
    _loop.save_state(s)
    out = call(loop_env, "Bash", command=VERIFY, dangerouslyDisableSandbox=True)
    assert not denied(out)


def test_verifier_with_a_changed_bin_is_denied(loop_env):
    with_baseline(loop_env)
    (loop_env.wt / ".loop/bin/json.py").write_text("x", encoding="utf-8")
    out = call(loop_env, "Bash", command=VERIFY)
    assert denied(out) and ".loop/bin" in out["permissionDecisionReason"]


def test_guard_bash_still_loads_with_guard_loop(loop_env):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "cwd": str(loop_env.wt),
    }
    code, out, err = run_hook(BASH, payload)
    assert (code, err) == (0, "")
    assert json.dumps(out).count("deny") == 0
    assert git(loop_env.wt, "status", "--short") == ""


# ── commands that run outside the sandbox (sandbox.excludedCommands) ───────
FORGE = HOOKS.parent / "forge.sh"


@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr view 3",
        "gh pr view 3 | head",
        "cd sub && glab mr create",
        "bash -c 'gh api user'",
        "/opt/homebrew/bin/gh repo list",
    ],
)
def test_excluded_commands_are_denied(loop_env, cmd):
    with_baseline(loop_env)
    out = call(loop_env, "Bash", hook=GUARD, command=cmd)
    assert denied(out) and "sandbox" in out["permissionDecisionReason"], out


def test_the_trusted_forge_may_read(loop_env):
    with_baseline(loop_env)
    for cmd in (f"bash {FORGE} whoami", f"{FORGE} kind"):
        assert not denied(call(loop_env, "Bash", hook=GUARD, command=cmd)), cmd


def test_a_forge_that_is_not_ours_is_denied(loop_env):
    """The public sandbox settings exclude only the plugin-cache forge.sh from the sandbox. A
    forge.sh elsewhere runs inside the sandbox, so there is nothing to deny. But a file at a
    plugin-cache path that is not this plugin's own copy matches the exclusion, leaves the
    sandbox, and is not the trusted forge.sh: the guard must deny it."""
    with_baseline(loop_env)
    fake = (
        loop_env.tmp / ".claude/plugins/cache/dotfiles-public/safe-lean/9.9.9/forge.sh"
    )
    fake.parent.mkdir(parents=True)
    fake.write_text("echo hi\n", encoding="utf-8")
    assert denied(call(loop_env, "Bash", hook=GUARD, command=f"bash {fake} whoami"))


@pytest.mark.parametrize("profile", ["personal", "work"])
@pytest.mark.parametrize(
    "cmd",
    [
        f"bash {FORGE} pr-create --fill",
        f"cd sub && {FORGE} repo-create x",
        "forge.sh pr-create",
    ],
)
def test_the_loop_never_opens_a_pr_or_a_repo(loop_env, profile, cmd):
    # No push, PR or repo creation by the loop, in any profile (non-goal, G4)
    with_baseline(loop_env, profile)
    out = call(loop_env, "Bash", hook=GUARD, mode="acceptEdits", command=cmd)
    assert denied(out), out


# ── key files ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "tool, tool_input",
    [
        ("Read", {"file_path": "deploy.pem"}),
        ("Read", {"file_path": ".deploy.pem"}),
        ("Read", {"file_path": "certs/ID_RSA"}),
        ("Edit", {"file_path": "conf/credentials-prod.json"}),
        ("Write", {"file_path": ".npmrc"}),
        ("Grep", {"pattern": "x", "path": "kubeconfig"}),
        ("Grep", {"pattern": "x", "glob": "*.p12"}),
        ("Glob", {"pattern": "**/*.pem"}),
        ("Glob", {"pattern": "*", "path": "keys/app.keystore"}),
        ("Bash", {"command": "cat deploy.pem"}),
        ("Bash", {"command": "cat certs/{a,b}.pem"}),
        ("Bash", {"command": "openssl x509 -in './my-service-account.json'"}),
    ],
)
def test_key_files_are_denied(loop_env, tool, tool_input):
    with_baseline(loop_env)
    out = call(loop_env, tool, hook=GUARD, **tool_input)
    assert denied(out) and "key file" in out["permissionDecisionReason"], out


@pytest.mark.parametrize(
    "tool, tool_input",
    [
        ("Read", {"file_path": "README.md"}),
        ("Read", {"file_path": "presentation.key"}),
        ("Grep", {"pattern": "pem"}),
        ("Grep", {"pattern": "x", "path": "src"}),
        ("Glob", {"pattern": "**/*.py"}),
        ("Glob", {"pattern": "**/*"}),
        ("Bash", {"command": "grep -rn pem src"}),
    ],
)
def test_other_files_pass_the_key_file_rule(loop_env, tool, tool_input):
    with_baseline(loop_env)
    assert not denied(call(loop_env, tool, hook=GUARD, **tool_input))


def test_key_file_rule_is_quiet_outside_a_loop(loop_env):
    assert call(loop_env, "Read", hook=GUARD, file_path="deploy.pem") == {}


# ── work profile (R18) ──────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["auto", "bypassPermissions", "dontAsk", None])
@pytest.mark.parametrize(
    "tool, tool_input",
    [("Read", {"file_path": "tool.sh"}), ("Bash", {"command": "ls"})],
)
def test_work_loop_denies_every_call_in_an_auto_mode(loop_env, mode, tool, tool_input):
    with_baseline(loop_env, "work")
    out = call(loop_env, tool, hook=GUARD, mode=mode, **tool_input)
    assert denied(out) and "manual or acceptEdits" in out["permissionDecisionReason"]


def test_personal_loop_runs_in_auto_mode(loop_env):
    with_baseline(loop_env)
    assert call(loop_env, "Bash", hook=GUARD, mode="auto", command="ls") == {}


@pytest.mark.parametrize("mode", ["default", "acceptEdits"])
def test_work_loop_runs_with_prompts(loop_env, mode):
    with_baseline(loop_env, "work")
    assert call(loop_env, "Bash", hook=GUARD, mode=mode, command="ls") == {}


@pytest.mark.parametrize(
    "cmd", ["claude mcp add x -- npx y", "cd sub && claude mcp add x"]
)
def test_work_loop_denies_mcp_add(loop_env, cmd):
    with_baseline(loop_env, "work")
    assert denied(call(loop_env, "Bash", hook=GUARD, mode="acceptEdits", command=cmd))


@pytest.mark.parametrize(
    "tool, tool_input",
    [
        ("WebFetch", {"url": "https://example.com", "prompt": "x"}),
        ("Bash", {"command": "curl -s https://example.com"}),
        ("Bash", {"command": "cd sub && wget https://example.com"}),
        ("Bash", {"command": "git clone https://example.com/r.git"}),
        ("Bash", {"command": "uv add requests"}),
        ("Bash", {"command": "npm install left-pad"}),
        ("Bash", {"command": "npm i left-pad"}),
        ("Bash", {"command": "brew install jq"}),
    ],
)
def test_work_loop_asks_before_network_and_installs(loop_env, tool, tool_input):
    with_baseline(loop_env, "work")
    out = call(loop_env, tool, hook=GUARD, mode="acceptEdits", **tool_input)
    assert asked(out), out
    s = _loop.load_state(loop_env.wt)
    s["profile"] = "personal"  # the personal profile does not ask
    _loop.save_state(s)
    assert not asked(call(loop_env, tool, hook=GUARD, mode="auto", **tool_input))


# ── guard_private_terms: the .loop files of a running loop ─────────────────
# Their text becomes commit messages (Cause lines), the bundle and the lesson
TERMS = HOOKS / "guard_private_terms.py"


@pytest.fixture
def terms(loop_env, monkeypatch):
    path = loop_env.tmp / "terms.txt"
    path.write_text("acme-corp\n", encoding="utf-8")
    monkeypatch.setenv("PRIVATE_TERMS_FILE", str(path))


def write_call(hook, path, text):
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": text},
        "cwd": str(path.parent),
    }
    return run_hook(hook, payload)[0]


@pytest.mark.parametrize("rel", [".loop/loop-progress.md", ".loop/lesson.md"])
@pytest.mark.usefixtures("terms")
def test_private_terms_are_blocked_in_loop_files(loop_env, rel):
    with_baseline(loop_env)
    assert write_call(TERMS, loop_env.wt / rel, "Cause: acme-corp import") == 2
    assert write_call(TERMS, loop_env.wt / rel, "Cause: the import") == 0


@pytest.mark.usefixtures("terms")
def test_private_terms_are_blocked_in_bash_writes_to_loop_files(loop_env):
    with_baseline(loop_env)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo 'Cause: acme-corp' >> .loop/loop-progress.md"},
        "cwd": str(loop_env.wt),
    }
    assert run_hook(BASH, payload)[0] == 2


@pytest.mark.usefixtures("terms")
def test_private_terms_pass_outside_loop_files(loop_env):
    # The target code of a work repo may name its customer; only the loop's notes travel
    with_baseline(loop_env)
    assert write_call(TERMS, loop_env.wt / "tool.sh", "echo acme-corp") == 0


@pytest.mark.usefixtures("terms")
def test_private_terms_pass_in_loop_files_without_a_loop(loop_env):
    path = loop_env.wt / ".loop/loop-progress.md"
    assert write_call(TERMS, path, "Cause: acme-corp import") == 0
