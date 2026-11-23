"""Run install.py on a fake home with fake package managers on PATH.

No test may install a package, change PATH or write to the real home folder: every
manager is a stub that only logs its command line to $FAKE_LOG.
"""

import os
import subprocess
import sys

from hookrun import ROOT, env_for

INSTALL = ROOT / "install.py"
WIN = sys.platform == "win32"

POSIX_STUB = """#!/bin/sh
echo "$(basename "$0") $*" >> "$FAKE_LOG"
if [ -n "$FAKE_FAIL" ]; then
  case "$*" in *"$FAKE_FAIL"*) exit 1 ;; esac
fi
exit 0
"""
WINDOWS_STUB = '@echo off\r\n>>"%FAKE_LOG%" echo %~n0 %*\r\nexit /b 0\r\n'


def fake_tool(bin_dir, name):
    """A program called `name` that logs its arguments and succeeds."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    if WIN:
        path = bin_dir / f"{name}.cmd"
        path.write_bytes(WINDOWS_STUB.encode())
    else:
        path = bin_dir / name
        path.write_text(POSIX_STUB, encoding="utf-8")
        path.chmod(0o755)
    return path


def fake_managers(tmp_path, *names):
    bin_dir = tmp_path / "fakebin"
    for name in names:
        fake_tool(bin_dir, name)
    return bin_dir


def calls(tmp_path):
    log = tmp_path / "fake.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def run_install(
    home, *args, answers=None, bin_dir=None, only_bin=False, extra_env=None
):
    """(exit code, output). answers=None closes stdin, like a CI job."""
    tmp = home.parent
    env = env_for(home=home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    env["FAKE_LOG"] = str(tmp / "fake.log")
    env["DOTFILES_PACKAGES_DIR"] = str(tmp / "pkgdir")
    if bin_dir is not None:
        old = "" if only_bin else os.pathsep + env["PATH"]
        env["PATH"] = str(bin_dir) + old
    env.update(extra_env or {})
    p = subprocess.run(
        [sys.executable, str(INSTALL), "--skip-tools", "--skip-plugin", *args],
        input=answers,
        stdin=subprocess.DEVNULL if answers is None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        timeout=60,
    )
    return p.returncode, p.stdout + p.stderr


def home_of(tmp_path):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return home


# Files a program that install.py starts keeps in the home folder by itself. install.py writes none of them.
SHIM_CACHE = "Library/Caches/com.apple.python"  # Apple's /usr/bin python3 shim (macOS)
# pwsh and powershell write start-up data when install.py asks them for $PROFILE (Windows)
POWERSHELL_CACHES = (
    "AppData/Local/Microsoft/PowerShell/StartupProfileData-NonInteractive",
    "AppData/Local/Microsoft/Windows/PowerShell/StartupProfileData-NonInteractive",
)


def left_over(home):
    """Every path in the home folder, except what a started program caches on its own.

    Only those exact files and the folders that lead to them are skipped: a real write by
    install.py anywhere else, also elsewhere in AppData or Library, still shows."""
    own = set(POWERSHELL_CACHES) | {"AppData/Roaming"}  # PowerShell makes it, empty
    for path in POWERSHELL_CACHES + (SHIM_CACHE,):
        parts = path.split("/")
        own.update("/".join(parts[:i]) for i in range(1, len(parts)))
    found = []
    for p in home.rglob("*"):
        x = p.relative_to(home).as_posix()
        if x not in own and not (x + "/").startswith(SHIM_CACHE + "/"):
            found.append(x)
    return sorted(found)
