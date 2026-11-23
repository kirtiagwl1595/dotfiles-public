"""Shared setup for the loop tests: a throwaway main repo with a linked worktree and HOME in tmp."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CLAUDE = Path(__file__).resolve().parent.parent / "claude"
HOOKS = CLAUDE / "hooks"
SYSTEM_PYTHON = "/usr/bin/python3"
VERIFY = "python3 -B .loop/bin/loopctl.py verify"

sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(CLAUDE))


# The loop needs the OS sandbox: it supports macOS, Linux and WSL2, not native Windows
LOOP_SKIP = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the loop engine needs the OS sandbox: macOS, Linux and WSL2 only",
)

LOOP_MARKS = [LOOP_SKIP, pytest.mark.usefixtures("machine_free_git")]


@pytest.fixture
def machine_free_git(monkeypatch):
    """Throwaway test repos act the same in and out of the sandbox, which hides ~/.ssh and
    ~/.gitignore_global: no signing key, and no global ignore (it lists .loop/ once installed)."""
    pairs = [("commit.gpgsign", "false"), ("core.excludesFile", os.devnull)]
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(pairs)))
    for i, (key, value) in enumerate(pairs):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{i}", key)
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{i}", value)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def python():
    """The hooks run on the system Python (3.9); the tests use it to catch newer syntax."""
    if not Path(SYSTEM_PYTHON).exists():
        pytest.skip("no /usr/bin/python3")
    return SYSTEM_PYTHON


def run_hook(script, payload, *args, cwd=None):
    p = subprocess.run(
        [python(), "-B", str(script), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    out = json.loads(p.stdout) if p.stdout.strip() else {}
    return p.returncode, out, p.stderr


LOOP_MD = """---
slug: demo
target_type: script
target: tool.sh
max_iterations: 3
threshold: all
---
## Goal
Make tool.sh print ok.
## Loop type
goal-based
## Verifier
python3 -B .loop/bin/loopctl.py verify
## Scope
may change: tool.sh; must not change: keep.txt
## Iteration log
"""

FEATURES = [
    {
        "id": "prints-ok",
        "category": "behavior",
        "description": "tool.sh prints ok",
        "steps": ["run tool.sh"],
        "verify": "sh tool.sh | grep -q ok",
        "passes": False,
    },
    {
        "id": "runs",
        "category": "baseline",
        "description": "tool.sh exits 0",
        "steps": ["run tool.sh"],
        "verify": "sh tool.sh",
        "passes": False,
    },
]


@pytest.fixture
def loop_env(tmp_path, monkeypatch, machine_free_git):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_LOOP_OFF", raising=False)
    # forge.sh whoami answers from this, so the profile lookup never calls gh or glab
    monkeypatch.setenv("FORGE_GIT_USER", "me")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "Loop Test")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "loop@example.com")
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    (main / "tool.sh").write_text("echo no\n", encoding="utf-8")
    (main / "keep.txt").write_text("keep\n", encoding="utf-8")
    (main / "tests").mkdir()
    (main / "tests/test_tool.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "init")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "worktree-demo", str(wt))
    return SimpleNamespace(home=home, main=main, wt=wt, tmp=tmp_path)


def team_origin(env):
    """A repo under collaboration: the work profile."""
    git(env.main, "remote", "add", "origin", "git@github.com:team/r.git")


def write_loop_files(wt, loop_md=LOOP_MD, features=FEATURES):
    (wt / ".loop").mkdir(exist_ok=True)
    (wt / ".loop/LOOP.md").write_text(loop_md, encoding="utf-8")
    (wt / ".loop/loop-features.json").write_text(
        json.dumps(features, indent=2), encoding="utf-8"
    )


def personal(home, path):
    """A local profile file that maps this path to personal."""
    cfg = Path(home) / ".config/claude"
    cfg.mkdir(parents=True, exist_ok=True)
    rules = [{"path": str(path), "profile": "personal"}]
    (cfg / "loop-profiles.local.json").write_text(json.dumps(rules), encoding="utf-8")


def own_repos_are_personal(home):
    """A local profile file with the generic rule: a repo that only you can use is personal."""
    cfg = Path(home) / ".config/claude"
    cfg.mkdir(parents=True, exist_ok=True)
    rules = [{"owner": "self", "profile": "personal"}]
    (cfg / "loop-profiles.local.json").write_text(json.dumps(rules), encoding="utf-8")


def copy_bin(dest):
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(CLAUDE / "loopctl.py", dest)
    shutil.copy(HOOKS / "_loop.py", dest)


def loop_running(home, worktree, session="s1"):
    """A running loop's state file for `worktree`, under `home` (for the gate opt-outs)."""
    import _loop

    path = (
        Path(home)
        / ".local/state/claude-safe-lean/loops"
        / f"{_loop.key(worktree)}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    real = str(Path(worktree).resolve())
    path.write_text(
        json.dumps({"worktree": real, "status": "running", "session_id": session}),
        encoding="utf-8",
    )


def broken_hooks(tmp):
    """A copy of the hooks whose _loop.py crashes: the gates must then run as before."""
    copy = Path(tmp) / "broken-hooks"
    shutil.copytree(HOOKS, copy)
    (copy / "_loop.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
    return copy


LOOP_CMD = "/safe-lean:loop-engineer"


def prompt(env, text, mode="default", sid="s1", cwd=None):
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
        "cwd": str(cwd or env.wt),
        "session_id": sid,
        "permission_mode": mode,
    }
    return run_hook(HOOKS / "loop_hook.py", payload, "prompt")


def confirm(env, mode="default", loop_md=LOOP_MD, features=FEATURES):
    """A confirmed loop in the personal profile; returns the hook output."""
    personal(env.home, env.main)
    write_loop_files(env.wt, loop_md, features)
    code, out, err = prompt(env, f"{LOOP_CMD} confirm", mode)
    assert code == 0, err
    assert "decision" not in out, out
    return out


def loopctl(env, *args, timeout=120):
    """Run the copied loopctl from the worktree root, as the agent does."""
    return subprocess.run(
        [python(), "-B", ".loop/bin/loopctl.py", *args],
        cwd=env.wt,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


PROGRESS = (
    "## Iteration {n}\nCause: tool.sh prints the wrong word.\nDecision: print ok.\n"
)


def record(env, stdout, cmd=VERIFY, cwd=None, sid="s1"):
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
        "tool_response": {"stdout": stdout, "stderr": ""},
        "cwd": str(cwd or env.wt),
        "session_id": sid,
    }
    return run_hook(HOOKS / "loop_hook.py", payload, "record")


def stop(env, sid="s1", **extra):
    payload = {
        "hook_event_name": "Stop",
        "cwd": str(env.wt),
        "session_id": sid,
        "stop_hook_active": False,
        "background_tasks": [],
        **extra,
    }
    code, out, err = run_hook(HOOKS / "loop_hook.py", payload, "stop")
    assert code == 0, err
    return out
