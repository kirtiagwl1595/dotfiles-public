"""Rules for the shell config files (zsh, PowerShell, starship, vim, editorconfig, git ignore)."""

import os
import re
import shutil
import subprocess
import sys

import pytest
from hookrun import ROOT

SHELL = ROOT / "shell"
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="needs a Unix shell")


# ── starship ────────────────────────────────────────────────────────────────
def starship_text():
    return (SHELL / "starship.toml").read_text(encoding="utf-8")


def test_every_configured_starship_module_is_in_the_format():
    # A typo such as $node for [nodejs] hides the module without an error
    tables = re.findall(r"^\[([a-z_]+)\]", starship_text(), re.MULTILINE)
    fmt = re.search(
        r'^format = """(.*?)"""', starship_text(), re.MULTILINE | re.DOTALL
    ).group(1)
    assert tables and set(tables) <= set(re.findall(r"\$([a-z_]+)", fmt))


def test_starship_detect_files_are_names_not_globs():
    for line in starship_text().splitlines():
        if line.startswith("detect_files"):
            assert not set("*?") & set(line.split("=", 1)[1]), line


# ── vim and editorconfig ────────────────────────────────────────────────────
MAP = re.compile(r"^\s*[nvixsoc]?(nore)?map\b")


def test_no_vim_mapping_has_a_trailing_comment():
    # After a mapping, `" text` is part of the keys the mapping types
    lines = (SHELL / "vim" / ".vimrc").read_text(encoding="utf-8").splitlines()
    assert not [x for x in lines if MAP.match(x) and re.search(r'\s"\s', x)]


def test_editorconfig_values_have_no_inline_comment():
    # The spec reads `false   # x` as the whole value, so the setting is ignored
    lines = (SHELL / "editorconfig").read_text(encoding="utf-8").splitlines()
    bad = [x for x in lines if "=" in x and re.search(r"\s[#;]", x.split("=", 1)[1])]
    assert not bad, bad


# ── git ignore ──────────────────────────────────────────────────────────────
def ignore_lines():
    return (ROOT / "git" / "gitignore_global").read_text(encoding="utf-8").splitlines()


def test_global_gitignore_keeps_secret_files_out_of_every_repo():
    for pattern in [".env", ".env.*", "*.env", ".envrc", "*.pem", "!.env.example"]:
        assert pattern in ignore_lines(), pattern
    # .key is also Keynote: a global ignore would drop decks from every repo with no warning
    assert "*.key" not in ignore_lines()


def test_global_gitignore_keeps_loop_and_lesson_files_out_of_every_repo():
    assert {".loop/", ".claude/loop-runs/", ".claude/lessons/"} <= set(ignore_lines())


# ── zsh ─────────────────────────────────────────────────────────────────────
ZSH = shutil.which("zsh")


@POSIX_ONLY
@pytest.mark.skipif(not ZSH, reason="no zsh here")
@pytest.mark.parametrize("name", [".zshrc", ".zprofile"])
def test_zsh_files_have_no_syntax_error(name):
    p = subprocess.run(
        [ZSH, "-n", str(SHELL / "zsh" / name)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("name", [".zshrc", ".zprofile"])
def test_zsh_files_name_no_private_helper(name):
    text = (SHELL / "zsh" / name).read_text(encoding="utf-8")
    for word in ("home.zsh", "DOTFILES_PROFILE", "Brewfile", "HOMEBREW_BUNDLE_FILE"):
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE), word


@POSIX_ONLY
@pytest.mark.skipif(not ZSH, reason="no zsh here")
def test_brewup_updates_and_upgrades_through_brew(tmp_path):
    log, stub = tmp_path / "brew.log", tmp_path / "bin"
    stub.mkdir()
    (stub / "brew").write_text(f'#!/bin/sh\necho "$*" >> {log}\n', encoding="utf-8")
    (stub / "brew").chmod(0o755)
    fn = re.search(
        r"^brewup\(\) \{.*?^\}",
        (SHELL / "zsh" / ".zshrc").read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    env = {"PATH": f"{stub}:/usr/bin:/bin", "HOME": str(tmp_path)}
    subprocess.run([ZSH, "-fc", fn.group(0) + "\nbrewup"], env=env, check=True)
    got = log.read_text(encoding="utf-8").splitlines()
    assert got[0] == "update" and "upgrade" in got


@POSIX_ONLY
@pytest.mark.skipif(not ZSH, reason="no zsh here")
def test_zshrc_loads_in_an_interactive_shell_with_no_error(tmp_path):
    # A copy of the home folder layout: the file must start clean without any tool installed
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "TERM": "dumb"}
    p = subprocess.run(
        [ZSH, "-fic", f"source {SHELL / 'zsh' / '.zshrc'}; echo loaded"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert "loaded" in p.stdout, p.stderr
    assert "command not found" not in p.stderr


# ── PowerShell profile ──────────────────────────────────────────────────────
PROFILE = SHELL / "powershell" / "Microsoft.PowerShell_profile.ps1"
PWSH = shutil.which("pwsh")


def test_the_powershell_profile_sets_up_the_same_tools_as_zsh():
    text = PROFILE.read_text(encoding="utf-8")
    for needle in ("starship init powershell", "zoxide init powershell", "PSReadLine"):
        assert needle in text
    assert "Get-Command" in text  # every tool is optional


def test_the_powershell_profile_is_plain_ascii():
    # PowerShell 5.1 reads a file without a BOM as the ANSI code page
    PROFILE.read_text(encoding="ascii")


@pytest.mark.skipif(not PWSH, reason="no pwsh here")
@pytest.mark.parametrize(
    "path",
    [PROFILE, ROOT / "scripts" / "install-jena.ps1"],
    ids=lambda p: p.name,
)
def test_powershell_files_parse(path):
    cmd = (
        "$e = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$null, [ref]$e) | Out-Null; "
        "if ($e) { $e | ForEach-Object { $_.ToString() }; exit 1 }"
    )
    p = subprocess.run(
        [PWSH, "-NoProfile", "-Command", cmd],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "NO_COLOR": "1"},
    )
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.skipif(not PWSH, reason="no pwsh here")
def test_the_powershell_profile_loads_with_none_of_the_tools(tmp_path):
    empty = tmp_path / "bin"
    empty.mkdir()
    p = subprocess.run(
        [PWSH, "-NoProfile", "-Command", f". '{PROFILE}'; 'loaded'"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": str(empty) + os.pathsep + "/usr/bin:/bin"},
    )
    assert "loaded" in p.stdout, p.stdout + p.stderr
