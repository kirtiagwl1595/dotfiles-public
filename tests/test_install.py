"""install.py on a fake home: it adds, never removes the user's own values, and asks before
it replaces a weaker safety value. --check changes nothing."""

import json
import os
import subprocess
import sys

import pytest
from hookrun import ROOT, env_for

INSTALL = ROOT / "install.py"
SANDBOX_OS = sys.platform != "win32"


def install(home, *args, answers="", path_prefix=None):
    env = env_for(home=home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    if path_prefix:
        env["PATH"] = str(path_prefix) + os.pathsep + env["PATH"]
    p = subprocess.run(
        [sys.executable, str(INSTALL), *args],
        input=answers,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def full(home, answers=""):
    return install(home, "--skip-plugin", answers=answers)


def settings(home):
    return json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))


def write_settings(home, data):
    (home / ".claude").mkdir(exist_ok=True)
    (home / ".claude" / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def files_in(home):
    return sorted(p.relative_to(home).as_posix() for p in home.rglob("*"))


# ── --check ─────────────────────────────────────────────────────────────────
def test_check_changes_nothing(tmp_path):
    code, out = install(tmp_path, "--check", "--skip-plugin")
    assert code == 0, out
    # Only what install.py manages: Apple's /usr/bin shims cache to ~/Library on their own
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".gitconfig").exists()
    assert "CLAUDE.md" in out and "settings.json" in out and ".gitconfig" in out


def test_check_reports_a_weaker_value_and_keeps_it(tmp_path):
    write_settings(tmp_path, {"permissions": {"defaultMode": "auto"}})
    code, out = install(tmp_path, "--check", "--skip-plugin")
    assert code == 0, out
    assert "permissions.defaultMode" in out
    assert settings(tmp_path) == {"permissions": {"defaultMode": "auto"}}


def test_check_names_each_tool_and_a_fix(tmp_path):
    out = install(tmp_path, "--check", "--skip-plugin")[1]
    for tool in ("git", "bash", "python", "claude"):
        assert tool in out.lower()


# ── CLAUDE.md ───────────────────────────────────────────────────────────────
def test_rules_are_imported_at_the_top_and_own_text_stays(tmp_path):
    (tmp_path / ".claude").mkdir()
    own = tmp_path / ".claude" / "CLAUDE.md"
    own.write_text("# My rules\nBe brief.\n", encoding="utf-8")
    assert full(tmp_path)[0] == 0
    lines = own.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("@") and lines[0].endswith("claude/CLAUDE.md")
    assert lines[1].startswith("@") and lines[1].endswith("claude/CLAUDE.style.md")
    assert "Be brief." in lines
    for line in lines[:2]:
        assert os.path.isfile(os.path.expanduser(line[1:])), line


def test_second_run_changes_nothing(tmp_path):
    assert full(tmp_path)[0] == 0
    before = {
        p: (tmp_path / p).read_bytes()
        for p in files_in(tmp_path)
        if (tmp_path / p).is_file()
    }
    assert full(tmp_path)[0] == 0
    after = {
        p: (tmp_path / p).read_bytes()
        for p in files_in(tmp_path)
        if (tmp_path / p).is_file()
    }
    assert before == after


# ── settings ────────────────────────────────────────────────────────────────
def test_settings_merge_keeps_own_values_and_adds_the_baseline(tmp_path):
    write_settings(
        tmp_path, {"model": "x", "permissions": {"allow": ["Read(./docs/**)"]}}
    )
    assert full(tmp_path)[0] == 0
    s = settings(tmp_path)
    assert s["model"] == "x"
    assert "Read(./docs/**)" in s["permissions"]["allow"]
    assert s["permissions"]["defaultMode"] == "default"
    assert "disableAutoMode" not in s["permissions"]
    assert "Read(~/.ssh/**)" in s["permissions"]["deny"]
    assert ("sandbox" in s) is SANDBOX_OS


@pytest.mark.parametrize(
    "answer, expected", [("y\n", "default"), ("n\n", "auto"), ("", "auto")]
)
def test_weaker_mode_is_replaced_only_on_yes(tmp_path, answer, expected):
    write_settings(tmp_path, {"permissions": {"defaultMode": "auto"}})
    assert full(tmp_path, answers=answer)[0] == 0
    assert settings(tmp_path)["permissions"]["defaultMode"] == expected


def test_check_reports_auto_mode_off_from_an_old_install_and_keeps_it(tmp_path):
    write_settings(tmp_path, {"permissions": {"disableAutoMode": "disable"}})
    code, out = install(tmp_path, "--check", "--skip-plugin")
    assert code == 0, out
    assert "retired" in out and "disableAutoMode" in out
    assert settings(tmp_path)["permissions"]["disableAutoMode"] == "disable"


@pytest.mark.parametrize(
    "answer, removed", [("y\n", True), ("n\n", False), ("", False)]
)
def test_auto_mode_off_from_an_old_install_is_removed_only_on_yes(
    tmp_path, answer, removed
):
    # The only question in this run: the merged baseline has no weaker value
    write_settings(tmp_path, {"permissions": {"disableAutoMode": "disable"}})
    assert full(tmp_path, answers=answer)[0] == 0
    perms = settings(tmp_path)["permissions"]
    assert ("disableAutoMode" not in perms) is removed


def test_allow_entry_that_skips_a_question_is_removed_on_yes(tmp_path):
    # Mac/Linux: gh runs outside the sandbox. Windows: no sandbox, so every Bash allow
    write_settings(
        tmp_path, {"permissions": {"allow": ["Bash(gh pr view:*)", "Read(x)"]}}
    )
    code, out = full(tmp_path, answers="y\n" * 5)
    assert code == 0, out
    allow = settings(tmp_path)["permissions"]["allow"]
    assert "Bash(gh pr view:*)" not in allow
    assert "Read(x)" in allow


def test_broken_settings_file_stops_with_a_message(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
    code, out = full(tmp_path)
    assert code != 0
    assert "settings.json" in out and "Traceback" not in out


# ── git ─────────────────────────────────────────────────────────────────────
def git_global(home, *args):
    env = env_for(home=home)
    env.pop("GIT_CONFIG_GLOBAL", None)
    p = subprocess.run(
        ["git", "config", "--includes", "--global", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return p.stdout.strip()


def test_git_include_goes_on_top_so_own_values_win(tmp_path):
    (tmp_path / ".gitconfig").write_text("[pull]\n\trebase = false\n", encoding="utf-8")
    assert full(tmp_path)[0] == 0
    text = (tmp_path / ".gitconfig").read_text(encoding="utf-8")
    assert text.lstrip().startswith("[include]")
    assert "rebase = false" in text
    assert git_global(tmp_path, "--get", "pull.rebase") == "false"
    assert git_global(tmp_path, "--get", "init.defaultBranch") == "main"
    assert git_global(tmp_path, "--get", "core.excludesFile").endswith(
        "git/gitignore_global"
    )


def test_git_identity_is_never_set(tmp_path):
    assert full(tmp_path)[0] == 0
    text = (tmp_path / ".gitconfig").read_text(encoding="utf-8")
    assert "[user]" not in text and "credential" not in text


def test_own_excludes_file_is_kept(tmp_path):
    (tmp_path / ".gitconfig").write_text(
        "[core]\n\texcludesFile = ~/my-ignore\n", encoding="utf-8"
    )
    code, out = full(tmp_path)
    assert code == 0
    assert git_global(tmp_path, "--get", "core.excludesFile") == "~/my-ignore"
    assert "excludesFile" in out


# ── plugin ──────────────────────────────────────────────────────────────────
@pytest.mark.skipif(os.name == "nt", reason="the stub claude is a shell script")
def test_plugin_is_added_from_the_clone(tmp_path):
    log = tmp_path / "claude.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "claude"
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    stub.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    code, out = install(home, path_prefix=bin_dir)
    assert code == 0, out
    calls = log.read_text().splitlines()
    assert f"plugin marketplace add {(ROOT / 'claude').as_posix()}" in calls
    assert "plugin install safe-lean@dotfiles-public" in calls
