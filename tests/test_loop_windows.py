"""The loop needs the OS sandbox, so on native Windows its hooks do nothing: exit 0, no output.

These tests run on every OS. They fake sys.platform in a child process, so the Windows path
is checked on macOS and Linux too. A copy of guard_loop.py alone in a folder (no _loop.py, no
guards) proves that the Windows path returns before the imports from the guards.
"""

import json
import shutil
import subprocess
import sys

import pytest
from hookrun import ROOT

HOOKS = ROOT / "claude" / "hooks"
PAYLOAD = json.dumps(
    {
        "tool_name": "Write",
        "tool_input": {"file_path": "x"},
        "cwd": str(ROOT),
        "session_id": "s",
    }
)
# Fake the platform, then run the script as __main__ with the given arguments
RUNNER = (
    "import runpy, sys, subprocess, tempfile, shutil, fnmatch, hashlib, datetime, pathlib, collections, re, json, time, os\n"
    "sys.platform = 'win32'\n"
    "script = sys.argv[1]\n"
    "sys.path.insert(0, os.path.dirname(script))\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def run(script, *args, faked=True, cwd=None):
    cmd = [sys.executable, "-B"]
    cmd += ["-c", RUNNER, str(script), *args] if faked else [str(script), *args]
    return subprocess.run(
        cmd,
        input=PAYLOAD,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=cwd,
    )


@pytest.mark.parametrize("mode", ["record", "stop", "prompt"])
def test_loop_hook_does_nothing_on_windows(mode):
    p = run(HOOKS / "loop_hook.py", mode)
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")


def test_guard_loop_returns_before_the_guard_imports_on_windows(tmp_path):
    lone = tmp_path / "guard_loop.py"
    shutil.copy(
        HOOKS / "guard_loop.py", lone
    )  # no _loop.py, _common.py or guards beside it
    p = run(lone)
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="on native Windows guard_loop exits 0 before its imports by design; the faked-win32 tests above cover that side",
)
def test_a_failed_import_is_not_swallowed_off_windows(tmp_path):
    # Not on Windows, the same lone copy must fail on its missing imports: no try/except hides it
    lone = tmp_path / "guard_loop.py"
    shutil.copy(HOOKS / "guard_loop.py", lone)
    p = run(lone, faked=False)
    assert p.returncode != 0 and "ModuleNotFoundError" in p.stderr
