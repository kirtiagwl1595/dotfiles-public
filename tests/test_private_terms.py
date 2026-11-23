"""guard_private_terms keeps listed terms out of personal places (lessons, memory, the
dotfiles repos), on every OS. The terms file lives in the home folder, never in a repo."""

import pytest
from hookrun import bash, decision, powershell

TERM = "acme-corp"


@pytest.fixture
def home(tmp_path):
    terms = tmp_path / ".config" / "claude" / "private-terms.txt"
    terms.parent.mkdir(parents=True)
    terms.write_text(
        f"# one term per line\n{TERM}\nOldName => NewName\n", encoding="utf-8"
    )
    return tmp_path


def write(path, text):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": text}}


@pytest.mark.parametrize(
    "path",
    [
        "/repo/.claude/lessons/2026-01-01-x.md",
        r"C:\repo\.claude\lessons\x.md",
        r"C:\repo\.CLAUDE\Lessons\x.md",
        r"C:\Users\x\.claude\projects\p\memory\m.md",
        "/home/x/.claude/projects/p/memory/m.md",
        "/x/dotfiles-public/README.md",
        r"C:\git\dotfiles-public\claude\CLAUDE.md",
    ],
)
def test_term_in_a_personal_place_blocked(home, path):
    assert (
        decision("guard_private_terms.py", write(path, f"met {TERM} today"), home)
        == "block"
    )


def test_term_in_dotfiles_under_home_blocked(home):
    path = str(home / "dotfiles" / "notes.md")
    assert (
        decision("guard_private_terms.py", write(path, TERM.upper()), home) == "block"
    )


def test_term_elsewhere_allowed(home):
    payload = write("/repo/src/app.py", f"# {TERM}")
    assert decision("guard_private_terms.py", payload, home) is None


def test_old_name_gets_a_hint(home):
    payload = write("/repo/README.md", "Uses OldName.")
    assert decision("guard_private_terms.py", payload, home) == "context"


def test_no_terms_file_allows_everything(tmp_path):
    payload = write("/repo/.claude/lessons/x.md", f"met {TERM}")
    assert decision("guard_private_terms.py", payload, tmp_path) is None


@pytest.mark.parametrize(
    "make, cmd",
    [
        (bash, f"echo {TERM} >> /repo/.claude/lessons/x.md"),
        (bash, f"echo {TERM} | tee -a /repo/.claude/lessons/x.md"),
        (powershell, rf"echo {TERM} > C:\repo\.claude\lessons\x.md"),
        (powershell, rf"'{TERM}' | Out-File C:\repo\.claude\lessons\x.md"),
        (powershell, rf"Set-Content -Path C:\repo\.claude\lessons\x.md -Value {TERM}"),
        (powershell, rf"Add-Content C:\repo\.claude\lessons\x.md '{TERM}'"),
    ],
)
def test_shell_write_of_a_term_to_a_personal_place_blocked(home, make, cmd):
    assert decision("guard_bash.py", make(cmd, cwd=home), home) == "block"


@pytest.mark.parametrize(
    "make, cmd",
    [
        (bash, "echo hello >> /repo/.claude/lessons/x.md"),
        (powershell, r"'hello' | Out-File C:\repo\.claude\lessons\x.md"),
        (powershell, f"Write-Output {TERM}"),
    ],
)
def test_shell_write_without_a_term_allowed(home, make, cmd):
    assert decision("guard_bash.py", make(cmd, cwd=home), home) is None
