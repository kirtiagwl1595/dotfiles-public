"""Run a hook the way Claude Code does: JSON on stdin, the decision in the exit code and stdout."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "claude" / "hooks"
HOME = os.path.expanduser("~")
# A CI runner has no git identity: a test that commits passes these to env_for
IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def env_for(home=None, **extra):
    """The full environment (Windows needs SYSTEMROOT), with HOME and USERPROFILE moved if asked."""
    # The guards read these; a developer's own values must not change a test result
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DOTFILES", "PRIVATE_TERMS_FILE")
    }
    if home is not None:
        env["HOME"] = env["USERPROFILE"] = str(home)
    env.update(extra)
    return env


def run_text(hook, text, home=None):
    """(exit code, stdout, stderr). Takes a home, not an env: a failed assert prints its arguments."""
    p = subprocess.run(
        [sys.executable, "-B", str(HOOKS / hook)],
        check=False,
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env_for(home),
    )
    return p.returncode, p.stdout, p.stderr


def run(hook, payload, home=None):
    """(exit code, stdout, stderr) of one hook call."""
    return run_text(hook, json.dumps(payload), home)


def decision(hook, payload, home=None):
    """'block' (exit 2), a permissionDecision, 'context', or None. Any other exit code fails."""
    code, out, err = run(hook, payload, home)
    if code == 2:
        return "block"
    assert code == 0, err
    if not out:
        return None
    spec = json.loads(out)["hookSpecificOutput"]
    return spec.get("permissionDecision") or "context"


def bash(cmd, cwd=HOME, **extra):
    return {
        "tool_name": "Bash",
        "tool_input": {"command": cmd, **extra},
        "cwd": str(cwd),
    }


def powershell(cmd, cwd=HOME):
    return {"tool_name": "PowerShell", "tool_input": {"command": cmd}, "cwd": str(cwd)}


def file_tool(tool, path, **extra):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: path, **extra}}
