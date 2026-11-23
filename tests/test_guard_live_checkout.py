"""No halfway git in a live checkout: a sandboxed git write stops at the first locked file.

A live checkout is a folder in ~/.config/claude/live-checkout.txt (or LIVE_CHECKOUT), or the
clone the hook runs from. With none of them, the hook does nothing.
"""

import json
import subprocess
import sys

import pytest
from hookrun import HOOKS, bash, env_for, powershell, run


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def home(tmp_path):
    """A home with a live checkout (listed in the config), a worktree of it, and another repo."""
    live, other = tmp_path / "clone", tmp_path / "other"
    for repo in (live, other):
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.txt").write_text("a\n", encoding="utf-8")
        git(repo, "init", "-q", "-b", "work")
        git(repo, "config", "user.name", "t")
        git(repo, "config", "user.email", "t@example.com")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "init")
    git(live, "worktree", "add", "-q", "-b", "wt", ".claude/worktrees/wt")
    config = tmp_path / ".config" / "claude"
    config.mkdir(parents=True)
    (config / "live-checkout.txt").write_text(
        f"# the live copy\n{live}\n", encoding="utf-8"
    )
    return tmp_path


def decide(home, cmd, cwd, sandbox_off=False, make=bash, hook="guard_live_checkout.py"):
    payload = make(cmd, cwd=home / cwd)
    payload["tool_input"]["dangerouslyDisableSandbox"] = sandbox_off
    code, out, err = run(hook, payload, home)
    assert code == 0, err
    spec = json.loads(out)["hookSpecificOutput"] if out else {}
    return spec.get("permissionDecision"), spec.get("permissionDecisionReason", "")


@pytest.mark.parametrize(
    "cmd, cwd",
    [
        ("git switch main", "clone"),
        ("git checkout -- src/a.txt", "clone"),
        ("git restore src/a.txt", "clone/src"),
        ("git reset --hard HEAD", "clone"),
        ("git stash", "clone"),
        ("git apply fix.patch", "clone"),
        ("git merge wt", "clone"),
        # What looks like a read-only form and is none, or cannot be known from the text
        ("git stash push list", "clone"),
        ("git stash pop", "clone"),
        ("git stash show -p --output=src/a.txt", "clone"),
        ("git apply --check fix.patch --apply", "clone"),
        ("git apply --check $PATCH", "clone"),
        ("git apply --check *", "clone"),
        ("git apply --check {fix.patch,--apply}", "clone"),
        ("git apply --check fix.patch > log --apply", "clone"),
        ("echo --apply | xargs git apply --check fix.patch", "clone"),
        ("git clean -e -n -fd", "clone"),
        ("git clean -fd", "clone"),
        ("git stash list && git switch main", "clone"),
        ("echo '--- stashes'; git stash list", "clone"),  # a read counts only alone
        ("git stash list\ngit switch main", "clone"),
        # Where the parser and the shell read the text differently
        ('git apply --check fix.patch ";" --apply', "clone"),
        ("git apply --check fix.patch '|' --apply", "clone"),
        ("git apply --check fix.patch \\\n --apply", "clone"),
        ("git apply --check a#b --apply", "clone"),
        # Another folder: git -C, cd, and a path that climbs out of a worktree
        ("git -C {home}/clone pull --ff-only", "other"),
        ("cd {home}/clone && git switch main", "other"),
        ('cd "{home}/clone" && git switch main', "other"),
        ('git -C "$HOME/clone" switch main', "other"),
        ('git -C "${HOME}/clone" restore src/a.txt', "clone/.claude/worktrees/wt"),
        ("git -C ../../.. switch main", "clone/.claude/worktrees/wt"),
    ],
)
def test_sandboxed_git_cannot_change_the_live_checkout(home, cmd, cwd):
    decision, why = decide(home, cmd.replace("{home}", str(home)), cwd)
    assert decision == "deny", cmd
    assert "worktree" in why and "sandbox" in why and "clone" in why


@pytest.mark.parametrize(
    "cmd, cwd, sandbox_off",
    [
        ("git switch main", "clone", True),  # the ask rule puts it to the user
        ("git switch -c feature/x", "clone/.claude/worktrees/wt", False),
        ("git restore src/a.txt", "clone/.claude/worktrees/wt", False),
        ("git switch -c feature/x", "other", False),
        ("git status", "clone", False),
        ("git log --oneline -3", "clone", False),
        ("git fetch origin", "clone", False),
        # A read-only form of a verb that can write
        ("git stash list", "clone", False),
        ("git stash show -p stash@{1}", "clone", False),
        ("git apply --check fix.patch", "clone", False),
        ("git apply --stat fix.patch", "clone", False),
        ("git switch main", "no-such-folder", False),
    ],
)
def test_other_git_stays_free(home, cmd, cwd, sandbox_off):
    assert decide(home, cmd, cwd, sandbox_off)[0] is None


@pytest.mark.parametrize(
    "cmd", ["git clean -n", "git clean -nd src", "git clean --dry-run"]
)
def test_a_dry_run_clean_leaves_the_decision_to_the_ask_rule(home, cmd):
    # settings ask before every `git clean`: no deny from this guard, and no free pass either
    assert decide(home, cmd, "clone", hook="guard_bash.py")[0] == "ask"


def test_the_powershell_tool_is_guarded_too(home):
    assert decide(home, "git switch main", "clone", make=powershell)[0] == "deny"
    assert decide(home, "git.exe switch main", "clone", make=powershell)[0] == "deny"


def test_guard_bash_runs_it(home):
    assert decide(home, "git switch main", "clone", hook="guard_bash.py")[0] == "deny"


def test_no_list_no_opinion(tmp_path):
    # Nothing listed: the hook cannot know a live copy. It reads no ~/dotfiles.
    repo = tmp_path / "dotfiles"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "work")
    code, out, _ = run(
        "guard_live_checkout.py", bash("git switch main", cwd=repo), tmp_path
    )
    assert (code, out) == (0, "")


def test_a_folder_in_the_environment_counts(tmp_path):
    repo = tmp_path / "live"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "work")
    p = subprocess.run(
        [
            sys.executable,
            "-B",
            str(HOOKS / "guard_live_checkout.py"),
        ],
        input=json.dumps(bash("git switch main", cwd=repo)),
        capture_output=True,
        text=True,
        env=env_for(tmp_path, LIVE_CHECKOUT=str(repo)),
        check=False,
    )
    assert json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
