"""test_gate (Stop), after_python_edit (PostToolUse) and notify (Notification, Stop): the shell hooks.

Each runs with bash, as Claude Code runs it (Git Bash on Windows). No bash: skipped.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from hookrun import HOOKS, env_for

PY = [sys.executable, "-B"]


def run(cmd, payload, env=None):
    p = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env if env is not None else env_for(),
        check=False,
    )
    return p.returncode, p.stdout, p.stderr


BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH, reason="no bash")


# ── test_gate ───────────────────────────────────────────────────────────────
@pytest.fixture
def project(tmp_path, monkeypatch):
    # The gate is off until the user opts in with this file
    optin = tmp_path.parent / f"{tmp_path.name}-test-gate"
    optin.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_TEST_GATE", str(optin))

    def sh(*a):
        subprocess.run(a, cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="p"\nversion="0"\nrequires-python=">=3.9"\n', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    sh("git", "init", "-q", "-b", "main")
    sh("git", "add", "-A")
    sh(
        "git",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "i",
    )
    return tmp_path


GATE = [BASH, str(HOOKS / "test_gate.sh")]


def test_gate_quiet_without_python_changes(project):
    assert run(GATE, {"cwd": str(project)})[0] == 0


def test_gate_passes_green_tests(project):
    (project / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert 1 == 1\n", encoding="utf-8"
    )
    assert run(GATE, {"cwd": str(project)})[0] == 0


def test_gate_blocks_red_tests(project):
    (project / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    code, _, err = run(GATE, {"cwd": str(project)})
    assert code == 2
    assert "failed" in err.lower()


def test_gate_never_runs_a_skipped_clone(project, tmp_path_factory):
    # CLAUDE_TEST_GATE_SKIP names repos you only read: their conftest must not run outside the sandbox
    base = tmp_path_factory.mktemp("home")
    clone = base / "external" / "theirs"
    shutil.copytree(project, clone)
    (clone / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
    env = {**env_for(), "CLAUDE_TEST_GATE_SKIP": str(base / "external")}
    assert run(GATE, {"cwd": str(clone)}, env) == (0, "", "")


def test_gate_no_loop(project):
    (project / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    assert run(GATE, {"cwd": str(project), "stop_hook_active": True})[0] == 0


def test_gate_checks_again_after_a_fix_attempt(project, tmp_path_factory):
    # After a block, a new edit is checked again; an unchanged tree lets Claude stop
    env = {**env_for(), "TMPDIR": str(tmp_path_factory.mktemp("state"))}
    bad = project / "tests" / "test_bad.py"
    bad.write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    payload = {"cwd": str(project), "session_id": "s"}
    assert run(GATE, payload, env)[0] == 2
    again = {**payload, "stop_hook_active": True}
    assert run(GATE, again, env)[0] == 0
    bad.write_text("def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
    assert run(GATE, again, env)[0] == 2


def test_gate_skips_changes_made_before_the_session(project, tmp_path_factory):
    env_tmp = str(tmp_path_factory.mktemp("state"))
    (project / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    payload = {"cwd": str(project), "session_id": "s1"}
    env = {**env_for(), "TMPDIR": env_tmp}
    assert run(GATE + ["snapshot"], payload, env)[0] == 0
    # dirty before the session: not this session's work
    assert run(GATE, payload, env)[0] == 0
    (project / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert 0\n", encoding="utf-8"
    )
    assert run(GATE, payload, env)[0] == 2  # changed in this session: tests run


@pytest.mark.skip(reason="needs loop engine (agent B)")
def test_gate_skips_while_a_loop_of_this_session_runs():
    """Ported with the loop engine: the gate steps aside for a running loop."""


@pytest.mark.skip(reason="needs loop engine (agent B)")
def test_gate_runs_when_the_loop_check_crashes():
    """Ported with the loop engine: a crash in the loop check means the gate runs as before."""


# ── after_python_edit ───────────────────────────────────────────────────────
EDIT = [BASH, str(HOOKS / "after_python_edit.sh")]


# CI has no ruff on PATH (it runs ruff through uvx): the hook then does nothing, by design
needs_ruff = pytest.mark.skipif(
    not shutil.which("ruff"), reason="no ruff on PATH: the hook stays silent"
)


@needs_ruff
def test_ruff_formats_file(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x=1\n", encoding="utf-8")
    assert run(EDIT, {"tool_input": {"file_path": str(f)}})[0] == 0
    assert f.read_text(encoding="utf-8") == "x = 1\n"


def test_ruff_skips_scratchpad(tmp_path):
    f = tmp_path / "scratchpad" / "m.py"
    f.parent.mkdir()
    f.write_text("x=1\n", encoding="utf-8")
    assert run(EDIT, {"tool_input": {"file_path": str(f)}})[0] == 0
    assert f.read_text(encoding="utf-8") == "x=1\n"


@needs_ruff
def test_ruff_reports_errors(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("print(undefined_name)\n", encoding="utf-8")
    code, _, err = run(EDIT, {"tool_input": {"file_path": str(f)}})
    assert code == 2 and "F821" in err


def test_no_ruff_is_silent_and_exit_0(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x=1\nprint(undefined_name)\n", encoding="utf-8")
    # An empty HOME and a PATH without ruff: neither `command -v` nor ~/.local/bin finds it
    path = os.pathsep.join(
        {str(Path(BASH).parent), str(Path(sys.executable).parent), "/usr/bin", "/bin"}
    )
    if shutil.which("ruff", path=path):
        pytest.skip("ruff sits beside bash or python: cannot hide it")
    env = env_for(tmp_path, PATH=path)
    code, out, err = run(EDIT, {"tool_input": {"file_path": str(f)}}, env)
    assert (code, out, err) == (0, "", "")
    assert f.read_text(encoding="utf-8") == "x=1\nprint(undefined_name)\n"


def test_ruff_ignores_other_files(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("x=1\n", encoding="utf-8")
    assert run(EDIT, {"tool_input": {"file_path": str(f)}})[0] == 0


# ── notify ──────────────────────────────────────────────────────────────────
def notify(payload, front="Safari"):
    env = {**env_for(), "NOTIFY_DRY_RUN": "1", "NOTIFY_FRONT_APP": front}
    code, out, _ = run([BASH, str(HOOKS / "notify.sh")], payload, env)  # decodes UTF-8
    return code, out


def test_notify_when_claude_waits():
    code, out = notify(
        {
            "hook_event_name": "Notification",
            "message": 'Needs "Bash"',
            "cwd": "/x/churn",
        }
    )
    assert code == 0 and "Needs" in out and "Claude Code · churn" in out


def test_notify_finished_only_when_away():
    assert (
        "Claude finished"
        in notify({"hook_event_name": "Stop", "cwd": "/x/p"}, front="Safari")[1]
    )
    assert notify({"hook_event_name": "Stop", "cwd": "/x/p"}, front="iTerm2")[1] == ""
    assert (
        notify({"hook_event_name": "Stop", "stop_hook_active": True, "cwd": "/x/p"})[1]
        == ""
    )


def test_py_helper_finds_python_and_hashes_stdin():
    out = subprocess.run(
        [
            BASH,
            "-c",
            '. "$1"; pyrun -c "print(6*7)"; echo x | sha | cut -c1-8',
            "_",
            str(HOOKS / "_py.sh"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        out.returncode == 0
        and out.stdout.split()[0] == "42"
        and len(out.stdout.split()[1]) == 8
    )


def test_py_helper_returns_127_without_python(tmp_path):
    out = subprocess.run(
        [
            BASH,
            "-c",
            '. "$1"; PATH=/nonexistent; pyrun -c 1; echo $?',
            "_",
            str(HOOKS / "_py.sh"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout.split()[-1] == "127"


def test_gate_is_off_without_the_opt_in_file(project, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_TEST_GATE", str(tmp_path / "missing"))
    (project / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    assert run(GATE, {"cwd": str(project)}) == (0, "", "")


def test_gate_default_opt_in_file_is_in_the_home_config(project, monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_TEST_GATE")
    (project / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    home = tmp_path / "h"
    (home / ".config" / "claude").mkdir(parents=True)
    env = {**env_for(home)}
    assert run(GATE, {"cwd": str(project)}, env) == (0, "", "")  # no file: off
    (home / ".config" / "claude" / "test-gate").write_text("", encoding="utf-8")
    assert run(GATE, {"cwd": str(project)}, env)[0] == 2  # opted in: runs


def test_notify_on_windows_returns_at_once(tmp_path):
    # The toast sleeps in the background; a Stop hook that waits for it would stay busy
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in {
        "uname": "echo MINGW64_NT-10.0",
        "powershell.exe": "sleep 8",
    }.items():
        f = stubs / name
        f.write_bytes(f"#!/bin/sh\n{body}\n".encode())
        f.chmod(0o755)
    env = {**env_for(), "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"}
    start = time.monotonic()
    code, _, _ = run(
        [BASH, str(HOOKS / "notify.sh")],
        {"hook_event_name": "Notification", "message": "x", "cwd": "/x/p"},
        env,
    )
    assert code == 0 and time.monotonic() - start < 5


# ── Windows forms, proven on any OS ─────────────────────────────────────────
def test_pyrun_strips_crlf_and_keeps_the_exit_status(tmp_path):
    # Windows Python prints CRLF; a stub python3 does the same here
    stub = tmp_path / "python3"
    stub.write_bytes(
        b'#!/bin/sh\n[ "$1" = -c ] && case "$2" in *version_info*) exit 0;; esac\n'
        b'printf "True\\r\\n"; exit 3\n'
    )
    stub.chmod(0o755)
    env = env_for(PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    script = '. "$1"; v=$(pyrun -c x); echo "[$v]"; pyrun -c x >/dev/null; echo $?'
    out = subprocess.run(
        [BASH, "-c", script, "_", str(HOOKS / "_py.sh")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert out.stdout.split() == ["[True]", "3"]


def test_fwd_gives_one_path_form():
    out = subprocess.run(
        [BASH, "-c", '. "$1"; fwd "C:\\Users\\x\\repo"', "_", str(HOOKS / "_py.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout == "C:/Users/x/repo"


def test_gate_skip_list_keeps_drive_letters_and_other_entries(
    project, tmp_path_factory
):
    # "C:\nope" must not swallow the next entry; ";" and ":" both separate entries
    base = tmp_path_factory.mktemp("home")
    clone = base / "external" / "theirs"
    shutil.copytree(project, clone)
    (clone / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
    for sep in (";", ":"):
        skip = f"C:\\nope{sep}{base / 'external'}"
        env = {**env_for(), "CLAUDE_TEST_GATE_SKIP": skip}
        assert run(GATE, {"cwd": str(clone)}, env) == (0, "", "")
