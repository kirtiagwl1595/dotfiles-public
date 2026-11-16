"""install.py finds a tool that is installed but not on PATH and, on a yes, adds its folder to
PATH. A tool that is not installed: on a yes, it runs the install command. --check and a
"no" change nothing, and no install runs unasked."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hookrun import ROOT, env_for

sys.path.insert(0, str(ROOT))
import install

POSIX = os.name != "nt"
posix_only = pytest.mark.skipif(not POSIX, reason="the stubs are shell scripts")


def stubs(tmp_path, **programs):
    """A PATH folder with only these programs, plus git and bash that call the real ones."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    real = {"git": shutil.which("git"), "bash": shutil.which("bash")}
    bodies = {name: f'exec "{path}" "$@"' for name, path in real.items() if path}
    bodies.update(programs)
    for name, body in bodies.items():
        f = d / name
        f.write_bytes(f"#!/bin/sh\n{body}\n".encode())
        f.chmod(0o755)
    return d


def recorder(log):
    # Builtins only: PATH holds just the stubs
    return f'echo "${{0##*/}} $*" >> "{Path(log).as_posix()}"'


def run(home, path, *args, answers="", shell="/bin/zsh"):
    env = env_for(home=home, PATH=str(path), SHELL=shell)
    env.pop("GIT_CONFIG_GLOBAL", None)
    p = subprocess.run(
        [sys.executable, str(ROOT / "install.py"), "--skip-plugin", *args],
        input=answers,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def home_with_claude(tmp_path):
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    exe = local_bin / "claude"
    exe.write_bytes(b"#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    return home


# ── installed, not on PATH ──────────────────────────────────────────────────
@posix_only
def test_check_reports_a_tool_off_path_and_writes_nothing(tmp_path):
    home = home_with_claude(tmp_path)
    code, out = run(home, stubs(tmp_path), "--check")
    assert code == 0, out
    assert "not on PATH" in out and "~/.local/bin" in out
    assert not (home / ".zshrc").exists()


@posix_only
def test_folder_is_added_to_the_shell_file_on_yes_once(tmp_path):
    home = home_with_claude(tmp_path)
    path = stubs(tmp_path)
    code, out = run(home, path, answers="y\n")
    assert code == 0, out
    rc = (home / ".zshrc").read_text(encoding="utf-8")
    assert 'export PATH="$HOME/.local/bin:$PATH"' in rc
    # Second run: the block is there; the terminal only needs a restart
    code, out = run(home, path, answers="y\n")
    assert code == 0, out
    assert (home / ".zshrc").read_text(encoding="utf-8") == rc
    assert "new terminal" in out


@posix_only
def test_own_shell_file_lines_stay(tmp_path):
    home = home_with_claude(tmp_path)
    (home / ".zshrc").write_text("alias ll='ls -l'\n", encoding="utf-8")
    run(home, stubs(tmp_path), answers="y\n")
    rc = (home / ".zshrc").read_text(encoding="utf-8")
    assert rc.startswith("alias ll='ls -l'\n")
    assert (home / ".zshrc.bak").exists()


@posix_only
@pytest.mark.parametrize("answer", ["", "n\n"])
def test_folder_is_not_added_without_a_yes(tmp_path, answer):
    home = home_with_claude(tmp_path)
    _code, out = run(home, stubs(tmp_path), answers=answer)
    assert not (home / ".zshrc").exists()
    assert "kept" in out


@posix_only
def test_bash_gets_the_file_its_terminal_reads(tmp_path):
    home = home_with_claude(tmp_path)
    run(home, stubs(tmp_path), answers="y\n", shell="/bin/bash")
    # macOS Terminal starts bash as a login shell: it reads ~/.bash_profile
    expected = ".bash_profile" if sys.platform == "darwin" else ".bashrc"
    assert "dotfiles-public PATH" in (home / expected).read_text(encoding="utf-8")


# ── not installed ───────────────────────────────────────────────────────────
@posix_only
@pytest.mark.parametrize("answer", ["", "n\n"])
def test_no_install_runs_without_a_yes(tmp_path, answer):
    log = tmp_path / "log"
    home = tmp_path / "home"
    home.mkdir()
    _code, out = run(home, stubs(tmp_path, brew=recorder(log)), answers=answer)
    assert "brew install --cask claude-code" in out
    assert not log.exists()


@posix_only
def test_check_shows_the_install_command_and_runs_nothing(tmp_path):
    log = tmp_path / "log"
    home = tmp_path / "home"
    home.mkdir()
    code, out = run(home, stubs(tmp_path, brew=recorder(log)), "--check")
    assert code == 0, out
    assert "install claude: brew install --cask claude-code" in out
    assert not log.exists()


@posix_only
def test_install_runs_on_yes(tmp_path):
    log = tmp_path / "log"
    home = tmp_path / "home"
    home.mkdir()
    _code, _out = run(home, stubs(tmp_path, brew=recorder(log)), answers="y\n")
    assert "brew install --cask claude-code" in log.read_text()


@posix_only
def test_failed_install_is_reported_not_hidden(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _code, out = run(home, stubs(tmp_path, brew="exit 4"), answers="y\n")
    assert "exit code 4" in out


@posix_only
def test_without_a_package_manager_the_native_installer_is_offered(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _code, out = run(home, stubs(tmp_path), "--check")
    assert "https://claude.ai/install.sh" in out


@posix_only
def test_skip_tools_only_reports(tmp_path):
    log = tmp_path / "log"
    home = home_with_claude(tmp_path)
    _code, _out = run(
        home, stubs(tmp_path, brew=recorder(log)), "--skip-tools", answers="y\n" * 3
    )
    assert not log.exists()
    assert not (home / ".zshrc").exists()


# ── Windows user PATH ───────────────────────────────────────────────────────
class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ, KEY_WRITE = 1, 2
    REG_SZ, REG_EXPAND_SZ = 1, 2

    def __init__(self, value=None, kind=2):
        self.value, self.kind = value, kind
        self.writes = []

    def OpenKey(self, root, sub, reserved=0, access=0):
        assert (root, sub) == ("HKCU", "Environment")
        return self

    def QueryValueEx(self, key, name):
        if self.value is None:
            raise FileNotFoundError
        return self.value, self.kind

    def SetValueEx(self, key, name, reserved, kind, value):
        self.writes.append((name, kind, value))
        self.value, self.kind = value, kind

    def CloseKey(self, key):
        pass


def test_windows_path_gets_the_folder_and_keeps_the_rest():
    reg = FakeWinreg(r"%USERPROFILE%\bin;C:\Tools")
    sent = []
    install.add_to_windows_path(r"C:\Users\me\.local\bin", reg, lambda: sent.append(1))
    assert reg.writes == [
        (
            "Path",
            reg.REG_EXPAND_SZ,
            r"%USERPROFILE%\bin;C:\Tools;C:\Users\me\.local\bin",
        )
    ]
    assert sent == [1]  # new terminals see the change without a log-off


def test_windows_path_is_not_changed_twice():
    reg = FakeWinreg(r"C:\Tools;C:\Users\me\.local\bin\\")
    install.add_to_windows_path(r"c:\users\me\.local\bin", reg, lambda: None)
    assert reg.writes == []


def test_windows_path_is_made_when_there_is_none():
    reg = FakeWinreg(None)
    install.add_to_windows_path(r"C:\Users\me\.local\bin", reg, lambda: None)
    assert reg.writes == [("Path", reg.REG_EXPAND_SZ, r"C:\Users\me\.local\bin")]


def test_a_shared_install_command_is_named_once_for_each_tool(monkeypatch, capsys):
    # bwrap and socat come from one apt-get command: one question, a line for each tool
    monkeypatch.setattr(install, "installer", lambda name: ["sudo", "apt-get", "x"])
    report = install.Report(check=True)
    offered = set()
    install.offer_install(report, "bwrap", offered)
    install.offer_install(report, "socat", offered)
    out = capsys.readouterr().out
    assert out.count("sudo apt-get x") == 2
    assert "bwrap" in out and "socat" in out
