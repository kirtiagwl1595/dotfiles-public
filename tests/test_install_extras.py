"""install.py steps after the package step: shell config, status line, templates, delta, macOS.

Each test runs one step with --only, on a fake home. A question answered with nothing
(closed stdin) or n changes nothing.
"""

import importlib.util
import json
import os
import subprocess
import sys

import pytest
from hookrun import ROOT
from installrun import WIN, calls, fake_managers, home_of, run_install

YES = "y\n" * 12
LINK_FILES = {
    ".vimrc": "shell/vim/.vimrc",
    ".editorconfig": "shell/editorconfig",
    ".config/starship.toml": "shell/starship.toml",
}
ZSH_FILES = {".zshrc": "shell/zsh/.zshrc", ".zprofile": "shell/zsh/.zprofile"}
SHIM_CACHE = (
    "Library/Caches/com.apple.python"  # what Apple's /usr/bin python3 shim writes
)


def left_over(home):
    """Every path in the home folder, except the cache Apple's python3 shim makes on its own."""
    found = [p.relative_to(home).as_posix() for p in home.rglob("*")]
    skip = ("Library", "Library/Caches")
    return [
        x for x in found if x not in skip and not (x + "/").startswith(SHIM_CACHE + "/")
    ]


def shell(home, *args, answers=None):
    return run_install(home, "--only", "shell", *args, answers=answers)


# ── shell config ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("target, source", sorted(LINK_FILES.items()))
def test_yes_puts_each_config_file_in_the_home_folder(tmp_path, target, source):
    home = home_of(tmp_path)
    code, out = shell(home, answers=YES)
    assert code == 0, out
    dst = home / target
    assert dst.read_bytes() == (ROOT / source).read_bytes()
    assert dst.is_symlink() is (not WIN)  # Windows copies: a symlink needs rights


def test_closed_stdin_changes_nothing(tmp_path):
    home = home_of(tmp_path)
    code, out = shell(home)
    assert code == 0, out
    assert left_over(home) == []


def test_n_changes_nothing(tmp_path):
    home = home_of(tmp_path)
    code, out = shell(home, answers="n\n" * 12)
    assert code == 0, out
    assert left_over(home) == []


def test_check_names_each_file_and_writes_nothing(tmp_path):
    home = home_of(tmp_path)
    code, out = shell(home, "--check")
    assert code == 0, out
    for target in LINK_FILES:
        assert target.rsplit("/", 1)[-1] in out
    assert left_over(home) == []


def test_an_existing_file_is_saved_as_bak_before_it_is_replaced(tmp_path):
    home = home_of(tmp_path)
    (home / ".vimrc").write_text("set mouse=a\n", encoding="utf-8")
    code, out = shell(home, answers=YES)
    assert code == 0, out
    assert (home / ".vimrc.bak").read_text(encoding="utf-8") == "set mouse=a\n"
    assert (home / ".vimrc").read_bytes() == (ROOT / "shell/vim/.vimrc").read_bytes()


def test_an_existing_file_stays_on_no(tmp_path):
    home = home_of(tmp_path)
    (home / ".vimrc").write_text("set mouse=a\n", encoding="utf-8")
    code, out = shell(home, answers="n\n" * 12)
    assert code == 0, out
    assert (home / ".vimrc").read_text(encoding="utf-8") == "set mouse=a\n"
    assert not (home / ".vimrc.bak").exists()


def test_a_second_run_asks_nothing_and_makes_no_new_bak(tmp_path):
    home = home_of(tmp_path)
    assert shell(home, answers=YES)[0] == 0
    code, out = shell(home, answers=YES)
    assert code == 0, out
    assert not list(home.glob("*.bak"))
    assert "[y/N]" not in out


@pytest.mark.skipif(not WIN, reason="the PowerShell profile is for Windows")
def test_windows_gets_the_powershell_profile_as_a_copy(tmp_path):
    home = home_of(tmp_path)
    assert shell(home, answers=YES)[0] == 0
    dst = home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    src = ROOT / "shell" / "powershell" / "Microsoft.PowerShell_profile.ps1"
    assert dst.read_bytes() == src.read_bytes() and not dst.is_symlink()


@pytest.mark.skipif(WIN, reason="zsh files are for macOS and Linux")
def test_the_zsh_files_are_offered_on_mac_and_linux(tmp_path):
    assert ".zshrc" in shell(home_of(tmp_path), "--check")[1]


# ── Claude Code status line ─────────────────────────────────────────────────
def statusline(home, answers=None, *args):
    return run_install(home, "--only", "statusline", *args, answers=answers)


def settings(home):
    return json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))


def test_statusline_is_set_on_yes(tmp_path):
    home = home_of(tmp_path)
    code, out = statusline(home, "y\n")
    assert code == 0, out
    line = settings(home)["statusLine"]
    assert line["type"] == "command" and "claude/statusline.sh" in line["command"]


def test_statusline_is_not_set_on_closed_stdin(tmp_path):
    home = home_of(tmp_path)
    assert statusline(home)[0] == 0
    assert not (home / ".claude" / "settings.json").exists()


def test_a_status_line_of_your_own_is_replaced_only_on_yes(tmp_path):
    home = home_of(tmp_path)
    (home / ".claude").mkdir()
    own = {"statusLine": {"type": "command", "command": "echo mine"}, "model": "x"}
    (home / ".claude" / "settings.json").write_text(json.dumps(own), encoding="utf-8")
    assert statusline(home, "n\n")[0] == 0
    assert settings(home) == own
    assert statusline(home, "y\n")[0] == 0
    now = settings(home)
    assert "statusline.sh" in now["statusLine"]["command"] and now["model"] == "x"
    assert (home / ".claude" / "settings.json.bak").exists()


def test_statusline_check_changes_nothing(tmp_path):
    home = home_of(tmp_path)
    code, out = statusline(home, None, "--check")
    assert code == 0 and "statusline" in out.lower()
    assert left_over(home) == []


# ── templates ───────────────────────────────────────────────────────────────
def templates(home, answers=None, *args):
    return run_install(home, "--only", "templates", *args, answers=answers)


def test_templates_are_copied_when_missing(tmp_path):
    home = home_of(tmp_path)
    code, out = templates(home, YES)
    assert code == 0, out
    for name in ("CLAUDE.about-me.md", "CLAUDE.profile.md"):
        text = (home / ".claude" / name).read_text(encoding="utf-8")
        assert "<" in text
    assert "@~/.claude/CLAUDE.about-me.md" in out


def test_an_existing_template_target_is_never_replaced(tmp_path):
    home = home_of(tmp_path)
    (home / ".claude").mkdir()
    mine = home / ".claude" / "CLAUDE.about-me.md"
    mine.write_text("my facts\n", encoding="utf-8")
    assert templates(home, YES)[0] == 0
    assert mine.read_text(encoding="utf-8") == "my facts\n"
    assert not mine.with_name(mine.name + ".bak").exists()


def test_templates_stay_on_closed_stdin(tmp_path):
    home = home_of(tmp_path)
    assert templates(home)[0] == 0
    assert not (home / ".claude").exists()


# ── delta ───────────────────────────────────────────────────────────────────
def test_delta_include_is_added_on_yes_when_delta_is_installed(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "delta")
    code, out = run_install(
        home, "--only", "git", "--only", "delta", answers="y\ny\ny\n", bin_dir=bin_dir
    )
    assert code == 0, out
    text = (home / ".gitconfig").read_text(encoding="utf-8")
    assert "git/config.shared" in text and "git/config.delta" in text
    assert text.index("config.shared") < text.index("config.delta")


def test_delta_is_not_added_on_no(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "delta")
    code, out = run_install(
        home, "--only", "git", "--only", "delta", answers="n\nn\nn\n", bin_dir=bin_dir
    )
    assert code == 0, out
    assert "config.delta" not in (home / ".gitconfig").read_text(encoding="utf-8")


def test_the_delta_file_sets_the_pager_and_nothing_personal():
    text = (ROOT / "git" / "config.delta").read_text(encoding="utf-8")
    assert "pager = delta" in text and "[user]" not in text


# ── macOS defaults ──────────────────────────────────────────────────────────
def test_macos_defaults_never_run_on_a_fake_home(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "defaults", "killall")
    code, out = run_install(home, "--only", "macos", answers=YES, bin_dir=bin_dir)
    assert code == 0, out
    assert calls(tmp_path) == []
    if sys.platform == "darwin":
        assert "real home" in out
    else:
        assert "macOS only" in out


# ── zsh: a marked block in your own file, never a replaced file ─────────────
def block_source(text, name):
    start = f"# >>> dotfiles-public {name} >>>"
    assert start in text and f"# <<< dotfiles-public {name} <<<" in text
    return text.split(start)[1].split("# <<<")[0]


@pytest.mark.skipif(WIN, reason="zsh files are for macOS and Linux")
@pytest.mark.parametrize("target, source", sorted(ZSH_FILES.items()))
def test_zsh_gets_a_block_that_sources_the_clone_file(tmp_path, target, source):
    home = home_of(tmp_path)
    code, out = shell(home, answers=YES)
    assert code == 0, out
    dst = home / target
    assert not dst.is_symlink()
    body = block_source(dst.read_text(encoding="utf-8"), "zsh")
    assert "source" in body and (ROOT / source).as_posix() in body


@pytest.mark.skipif(WIN, reason="zsh files are for macOS and Linux")
def test_your_own_zshrc_lines_keep_loading(tmp_path):
    home = home_of(tmp_path)
    own = "export NVM_DIR=$HOME/.nvm\n# conda initialize\n"
    (home / ".zshrc").write_text(own, encoding="utf-8")
    code, out = shell(home, answers=YES)
    assert code == 0, out
    text = (home / ".zshrc").read_text(encoding="utf-8")
    assert text.startswith(own) and "dotfiles-public zsh" in text
    assert (home / ".zshrc.bak").read_text(encoding="utf-8") == own
    assert not (home / ".zshrc.local").exists()


@pytest.mark.skipif(WIN, reason="zsh files are for macOS and Linux")
def test_the_zsh_block_is_added_once(tmp_path):
    home = home_of(tmp_path)
    assert shell(home, answers=YES)[0] == 0
    first = (home / ".zshrc").read_text(encoding="utf-8")
    code, _ = shell(home, answers=YES)
    assert code == 0 and (home / ".zshrc").read_text(encoding="utf-8") == first
    assert first.count("dotfiles-public zsh >>>") == 1


@pytest.mark.skipif(WIN, reason="zsh files are for macOS and Linux")
def test_the_zsh_block_stays_off_on_no(tmp_path):
    home = home_of(tmp_path)
    (home / ".zshrc").write_text("# mine\n", encoding="utf-8")
    assert shell(home, answers="n\n" * 12)[0] == 0
    assert (home / ".zshrc").read_text(encoding="utf-8") == "# mine\n"


# ── PowerShell profile path (called in-process, as if on Windows) ───────────
def load_install():
    spec = importlib.util.spec_from_file_location("install_mod", ROOT / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fake:
    """Stands for subprocess.run and shutil.which: one answer for each PowerShell program."""

    def __init__(self, answers):
        self.answers, self.commands = answers, []

    def which(self, name):
        return f"/fake/{name}" if name in self.answers else None

    def run(self, cmd, **_):
        self.commands.append(cmd)
        out = self.answers[cmd[0].rsplit("/", 1)[-1]]
        return subprocess.CompletedProcess(cmd, 0 if out else 1, out or "", "")


@pytest.fixture
def windows(tmp_path, monkeypatch):
    home = home_of(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    mod = load_install()
    monkeypatch.setattr(mod, "WINDOWS", True)
    return mod, home


def use(mod, monkeypatch, answers):
    fake = Fake(answers)
    monkeypatch.setattr(mod.shutil, "which", fake.which)
    monkeypatch.setattr(mod.subprocess, "run", fake.run)
    return fake


def ps_targets(mod):
    return [dst for src, dst in mod.config_files() if src.suffix == ".ps1"]


def test_the_profile_path_comes_from_powershell_itself(windows, tmp_path, monkeypatch):
    mod, _ = windows
    one = tmp_path / "OneDrive" / "Documents" / "PowerShell" / "p.ps1"
    old = tmp_path / "OneDrive" / "Documents" / "WindowsPowerShell" / "p.ps1"
    answers = {"pwsh": f"{one}\nRemoteSigned\n", "powershell": f"{old}\nRemoteSigned\n"}
    use(mod, monkeypatch, answers)
    assert ps_targets(mod) == [one, old]


def test_the_profile_path_falls_back_to_documents_when_the_query_fails(
    windows, monkeypatch
):
    mod, home = windows
    use(mod, monkeypatch, {"pwsh": ""})
    (target,) = ps_targets(mod)
    assert target.parent == home / "Documents" / "PowerShell"


def test_no_powershell_means_no_profile_is_offered(windows, monkeypatch):
    mod, _ = windows
    use(mod, monkeypatch, {})
    assert ps_targets(mod) == []
    report = mod.Report(True)
    mod.setup_shell(report)
    assert not report.failed


def test_the_parent_folder_of_the_profile_is_made_and_the_file_copied(
    windows, tmp_path, monkeypatch
):
    mod, _ = windows
    target = tmp_path / "OneDrive" / "Documents" / "PowerShell" / "p.ps1"
    use(mod, monkeypatch, {"pwsh": f"{target}\nRemoteSigned\n"})
    monkeypatch.setattr(mod, "ask", lambda *a, **k: True)
    src = next(s for s, d in mod.config_files() if d == target)
    mod.place(mod.Report(False), src, target)
    assert target.read_bytes() == src.read_bytes()


def test_a_restricted_policy_gets_one_hint_and_is_never_changed(
    windows, tmp_path, monkeypatch, capsys
):
    mod, _ = windows
    target = tmp_path / "Documents" / "PowerShell" / "p.ps1"
    fake = use(mod, monkeypatch, {"pwsh": f"{target}\nRestricted\n"})
    mod.setup_shell(mod.Report(True))
    out = capsys.readouterr().out
    assert out.count("Set-ExecutionPolicy") == 1
    assert not any("Set-ExecutionPolicy" in " ".join(c) for c in fake.commands)


# ── macOS defaults: the yes path, on a fake home with a fake defaults ───────
def test_macos_defaults_yes_runs_the_script_with_the_flag(tmp_path, monkeypatch):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "defaults", "killall")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "fake.log"))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}/usr/bin:/bin")
    mod = load_install()
    monkeypatch.setattr(mod, "SYSTEM", "Darwin")
    monkeypatch.setattr(mod, "real_home", lambda: home)
    monkeypatch.setattr(mod, "ask", lambda *a, **k: True)
    report = mod.Report(False)
    mod.setup_macos(report)
    assert not report.failed
    got = calls(tmp_path)
    assert any(c.startswith("defaults export") for c in got)
    assert any(c.startswith("defaults write") for c in got)
    assert any((home / ".dotfiles-backup").iterdir())
