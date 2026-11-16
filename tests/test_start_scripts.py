"""install.sh (macOS, Linux, Git Bash) and install.cmd / install.ps1 (Windows) find a Python 3.9+
and start install.py. With no Python they ask before they install one, and never install unasked."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hookrun import ROOT, env_for
from test_launcher import bash_exe, stub_dir

INSTALL_SH = ROOT / "install.sh"
WINDOWS = sys.platform == "win32"


def run_sh(home, path, *args, answers=""):
    env = env_for(home=home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["PATH"] = path
    p = subprocess.run(
        [bash_exe(), str(INSTALL_SH), *args],
        input=answers,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def python_stub_body():
    return f'exec "{Path(sys.executable).as_posix()}" "$@"'


def recorder(log):
    """A fake package manager: it writes its arguments to log."""
    return f'echo "$0 $*" >> "{Path(log).as_posix()}"'


# ── install.sh ──────────────────────────────────────────────────────────────
def test_sh_check_runs_install_py_and_changes_nothing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    stubs = stub_dir(tmp_path, python3=python_stub_body())
    code, out = run_sh(
        home, str(stubs) + os.pathsep + os.environ["PATH"], "--check", "--skip-plugin"
    )
    assert code == 0, out
    assert "Tools" in out and "settings.json" in out
    assert list(home.iterdir()) == []


def test_sh_without_python_and_without_a_package_manager_says_what_to_do(tmp_path):
    code, out = run_sh(tmp_path, str(stub_dir(tmp_path)), "--check")
    assert code == 1
    assert "Python 3.9" in out and "python.org" in out


def test_sh_store_stub_is_not_a_python(tmp_path):
    stubs = stub_dir(tmp_path, python3="exit 9009", python="exit 9009", py="exit 9009")
    assert run_sh(tmp_path, str(stubs), "--check")[0] == 1


@pytest.mark.parametrize("answer", ["", "n\n"])
def test_sh_installs_no_python_without_a_yes(tmp_path, answer):
    log = tmp_path / "log"
    stubs = stub_dir(tmp_path, brew=recorder(log))
    code, out = run_sh(tmp_path, str(stubs), "--check", answers=answer)
    assert code == 1
    assert "brew install python" in out
    assert not log.exists()


def test_sh_installs_python_on_yes_then_runs_install_py(tmp_path):
    log = tmp_path / "log"
    stubs = tmp_path / "bin"
    # The fake brew "installs" Python: it puts a python3 next to itself.
    # PATH has only the stubs, so chmod needs its full path.
    target = f"{stubs.as_posix()}/python3"
    chmod = Path(shutil.which("chmod")).as_posix()
    body = (
        recorder(log)
        + f"\nprintf '#!/bin/sh\\n{python_stub_body()}\\n' > \"{target}\""
        + f'\n"{chmod}" +x "{target}"'
    )
    stub_dir(tmp_path, brew=body)
    # PATH has only the stubs, so no real Python hides the "no Python" case
    code, out = run_sh(tmp_path, str(stubs), "--check", "--skip-plugin", answers="y\n")
    assert "brew install python" in log.read_text()
    # install.py ran: without git on this PATH it reports git as missing
    assert "Tools" in out and "git" in out, (code, out)


def test_sh_apt_install_goes_through_sudo(tmp_path):
    log = tmp_path / "log"
    stubs = stub_dir(tmp_path, **{"apt-get": "exit 0", "sudo": recorder(log)})
    run_sh(tmp_path, str(stubs), answers="y\n")
    assert "apt-get install -y python3" in log.read_text()


def test_sh_failed_python_install_stops_with_a_message(tmp_path):
    stubs = stub_dir(tmp_path, brew="exit 3")
    code, out = run_sh(tmp_path, str(stubs), answers="y\n")
    assert code == 1
    assert "failed" in out


# ── install.cmd and install.ps1 ─────────────────────────────────────────────
def test_cmd_starts_ps1_past_the_execution_policy_and_passes_arguments():
    text = (ROOT / "install.cmd").read_text(encoding="utf-8")
    assert "-ExecutionPolicy Bypass" in text
    assert '"%~dp0install.ps1" %*' in text
    assert "exit /b %ERRORLEVEL%" in text


def test_ps1_asks_before_winget_and_skips_the_store_stub():
    text = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert text.index("Read-Host") < text.index("& winget install")
    assert "sys.version_info < (3, 9)" in text


def test_line_ends_fit_each_shell():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attrs
    assert "*.cmd text eol=crlf" in attrs
    assert "*.ps1 text eol=crlf" in attrs
    assert b"\r\n" not in INSTALL_SH.read_bytes()


def powershell():
    return shutil.which("powershell") or shutil.which("pwsh")


@pytest.mark.parametrize("script", ["install.cmd", "install.ps1"])
def test_windows_scripts_run_install_py_check(tmp_path, script):
    if script.endswith(".cmd") and not WINDOWS:
        pytest.skip("install.cmd runs only on Windows")
    if script.endswith(".ps1") and not powershell():
        pytest.skip("no PowerShell")
    exe = ROOT / script
    cmd = (
        ["cmd", "/c", str(exe)]
        if script.endswith(".cmd")
        else [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(exe),
        ]
    )
    env = env_for(home=tmp_path)
    env.pop("GIT_CONFIG_GLOBAL", None)
    p = subprocess.run(
        [*cmd, "--check", "--skip-plugin"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    out = p.stdout + p.stderr
    assert p.returncode == 0, out
    assert "Tools" in out
    # PowerShell keeps its own cache in the home folder; install.py writes nothing
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".gitconfig").exists()
