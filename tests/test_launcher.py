"""hooks/py.sh starts each guard with a working Python 3, and blocks when there is none.

Without it, `python3` on Windows is often the Microsoft Store stub (exit 9009): the hook
fails with a code that is not 2, and Claude Code lets the tool call through.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hookrun import HOOKS, ROOT, bash, env_for

PY_SH = HOOKS / "py.sh"
GIT_BASH = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Git"
    / "bin"
    / "bash.exe"
)


def bash_exe():
    # On Windows, the bash on PATH can be WSL; Claude Code runs hooks in Git Bash
    if os.name == "nt" and GIT_BASH.exists():
        return str(GIT_BASH)
    found = shutil.which("bash")
    if not found:
        pytest.skip("no bash")
    return found


def stub_dir(tmp_path, **programs):
    """A folder for PATH with fake programs: name → shell body."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    for name, body in programs.items():
        f = d / name
        f.write_bytes(f"#!/bin/sh\n{body}\n".encode())  # LF on Windows too
        f.chmod(0o755)
    return d


def launch(guard, payload, path_dir):
    env = env_for()
    env["PATH"] = str(path_dir)
    p = subprocess.run(
        [bash_exe(), str(PY_SH), guard],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return p.returncode, p.stdout, p.stderr


def real_python(tmp_path):
    exe = Path(sys.executable).as_posix()
    return stub_dir(tmp_path, python3=f'exec "{exe}" "$@"')


def test_no_python_blocks(tmp_path):
    code, _, err = launch("guard_bash.py", bash("ls"), stub_dir(tmp_path))
    assert code == 2
    assert "Python" in err


def test_store_stub_is_skipped_and_blocks(tmp_path):
    stubs = stub_dir(tmp_path, python3="exit 9009", python="exit 9009", py="exit 9009")
    assert launch("guard_bash.py", bash("ls"), stubs)[0] == 2


def test_python_too_old_is_skipped(tmp_path):
    old = 'case "$*" in *version_info*) exit 1;; esac; exit 0'
    assert launch("guard_bash.py", bash("ls"), stub_dir(tmp_path, python3=old))[0] == 2


def test_real_python_runs_the_guard(tmp_path):
    path = real_python(tmp_path)
    assert launch("guard_bash.py", bash("ls", cwd=tmp_path), path)[:2] == (0, "")
    code, _, err = launch("guard_bash.py", bash("cat ~/.ssh/id_rsa"), path)
    assert code == 2 and "private" in err


def test_non_ascii_input_passes(tmp_path):
    path = real_python(tmp_path)
    assert launch("guard_bash.py", bash("echo café ü", cwd=tmp_path), path)[:2] == (
        0,
        "",
    )


def test_missing_guard_file_blocks(tmp_path):
    assert launch("guard_nope.py", bash("ls"), real_python(tmp_path))[0] == 2


# ── hooks.json ──────────────────────────────────────────────────────────────
HOOKS_JSON = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
COMMANDS = [
    (entry.get("matcher", ""), hook["command"])
    for entries in HOOKS_JSON["hooks"].values()
    for entry in entries
    for hook in entry["hooks"]
]


@pytest.mark.parametrize("matcher, command", COMMANDS)
def test_every_hook_starts_through_the_launcher(matcher, command):
    prefix = 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" '
    assert command.startswith(prefix)
    assert (HOOKS / command.removeprefix(prefix)).is_file()


def test_shell_tools_and_file_tools_are_guarded():
    by_matcher = {}
    for matcher, command in COMMANDS:
        for tool in matcher.split("|"):
            by_matcher.setdefault(tool, set()).add(command.rsplit(" ", 1)[-1])
    for tool in ("Bash", "PowerShell"):
        assert "guard_bash.py" in by_matcher[tool]
    for tool in ("Read", "Edit", "Write", "MultiEdit", "Grep", "Glob", "NotebookEdit"):
        assert "guard_secrets.py" in by_matcher[tool]
    for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        assert "guard_private_terms.py" in by_matcher[tool]


def test_launcher_has_unix_line_ends():
    # A CRLF checkout breaks bash: `$'\r': command not found`, which is not exit 2
    assert b"\r\n" not in PY_SH.read_bytes()
    assert "*.sh text eol=lf" in (ROOT / ".gitattributes").read_text()


def test_launcher_passes_the_arguments_after_the_script(tmp_path):
    # The setup-repo skill runs `py.sh ../repo_setup.py apply <repo>`: apply must arrive
    # A copy of the plugin layout in tmp_path: a path from the repo to tmp_path can cross
    # drives on Windows (D: to C:), and relpath fails there
    (tmp_path / "hooks").mkdir()
    shutil.copyfile(PY_SH, tmp_path / "hooks" / "py.sh")
    (tmp_path / "show_args.py").write_text(
        "import sys; print(sys.argv[1:])\n", encoding="utf-8"
    )
    env = env_for()
    env["PATH"] = str(real_python(tmp_path))
    p = subprocess.run(
        [
            bash_exe(),
            str(tmp_path / "hooks" / "py.sh"),
            "../show_args.py",
            "apply",
            "a b",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert p.stdout.strip() == "['apply', 'a b']", p.stderr
