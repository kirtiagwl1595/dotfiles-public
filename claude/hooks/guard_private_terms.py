#!/usr/bin/env python3
"""PreToolUse Edit|Write|MultiEdit|NotebookEdit and the shells: keep private terms (customer
names, internal hosts) out of personal places.

Terms live in ~/.config/claude/private-terms.txt, never in a repo (PRIVATE_TERMS_FILE overrides):
  acme-corp                       blocked in the dotfiles repos, memory, .claude/lessons/ and
                                  the .loop/ files of a running loop
  OldName => NewName              old product name: a warning to Claude on any write
No file: the hook does nothing, so users without one are not affected.
"""

import os
import re
import sys
from pathlib import Path

from _common import HOME, SHELL_TOOLS, norm_path, run_guard

# The loop engine is optional. A failed import exits 1, and exit 1 lets the tool call
# through: only "no such module" is fine, every other failure blocks.
try:
    import _loop
except ModuleNotFoundError as e:
    if e.name != "_loop":
        print("Blocked: the private-terms guard could not load.", file=sys.stderr)
        sys.exit(2)
    _loop = None
except Exception:  # noqa: BLE001 - SyntaxError too, not only ImportError
    print("Blocked: the private-terms guard could not load.", file=sys.stderr)
    sys.exit(2)

TERMS = os.environ.get(
    "PRIVATE_TERMS_FILE", os.path.join(HOME, ".config", "claude", "private-terms.txt")
)
DOTFILES = os.environ.get("DOTFILES", os.path.join(HOME, "dotfiles"))
# Places that are personal, or public: a repo named dotfiles-public is published as a whole
PERSONAL = re.compile(
    r"/\.claude/lessons/|/\.claude/projects/[^/]+/memory/|/dotfiles-public/"
)


def load_terms():
    blocked, renames = [], []
    try:
        lines = Path(TERMS).read_text(encoding="utf-8").splitlines()
    except OSError:
        return blocked, renames
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            old, new = (part.strip() for part in line.split("=>", 1))
            renames.append((old, new))
        else:
            blocked.append(line)
    return blocked, renames


def loop_file(path):
    """A file in the `.loop/` folder of a running loop. Its text travels: Cause lines become
    commit messages, and the bundle and lesson are copied to the main checkout."""
    if _loop is None:
        return False
    p = Path(path)
    wt = _loop.worktree_root(p.parent)
    if not wt or p.relative_to(wt).parts[:1] != (_loop.LOOP_DIR,):
        return False
    state = _loop.load_state(wt)
    return bool(state) and state.get("status") in _loop.ACTIVE


def personal_place(path):
    # realpath: a symlink into ~/dotfiles is still a personal place
    p = norm_path(os.path.realpath(os.path.expanduser(path))) + "/"
    dotfiles = norm_path(os.path.realpath(DOTFILES)) + "/"
    return (
        p.startswith(dotfiles)
        or PERSONAL.search(p) is not None
        or loop_file(os.path.realpath(os.path.expanduser(path)))
    )


def found(term, text):
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)


def written_text(inp):
    """All new text of a Write, Edit, MultiEdit or NotebookEdit call."""
    edits = [e.get("new_string") or "" for e in inp.get("edits") or []]
    parts = [inp.get("content"), inp.get("new_string"), inp.get("new_source"), *edits]
    return "\n".join(p for p in parts if p)


# Where a shell command writes: `> f`, `>> f` (heredocs too), `tee [-a] f`, and the
# PowerShell writers `Out-File`, `Set-Content`, `Add-Content` (with or without -Path)
WRITE_TARGET = re.compile(
    r"(?:>>?|\btee(?:\s+-a)?"
    r"|\b(?:out-file|set-content|add-content)(?:\s+-(?:path|filepath|literalpath))?)"
    r"\s*([^\s;&|<>()]+)",
    re.IGNORECASE,
)


def bash_target(command, cwd):
    """The first personal place a shell command writes to, else None."""
    for raw in WRITE_TARGET.findall(command):
        target = raw.strip("'\"")
        for var in ("$HOME", "$env:USERPROFILE", "%USERPROFILE%"):
            target = target.replace(var, HOME)
        target = os.path.join(cwd or ".", os.path.expanduser(target))
        if personal_place(target):
            return target
    return None


def check(data):
    inp = data.get("tool_input", {})
    if data.get("tool_name") in SHELL_TOOLS:
        command = inp.get("command", "")
        target = bash_target(command, data.get("cwd"))
        if not target:
            return None
        blocked, _ = load_terms()
        hits = [t for t in blocked if found(t, command)]
        if hits:
            return "block", (
                f"Blocked: this command writes {target}, a personal file, and names private terms "
                f"({', '.join(hits)}). Keep customer names and internal hosts in company systems; "
                "write a neutral placeholder instead."
            )
        return None
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    text = written_text(inp)
    if not text:
        return None
    blocked, renames = load_terms()
    if path and personal_place(path):
        hits = [t for t in blocked if found(t, text)]
        if hits:
            why = (
                f"Blocked: {path} is a personal file and the text names private terms "
                f"({', '.join(hits)}). Keep customer names and internal hosts in company systems; "
                "write a neutral placeholder instead."
            )
            return "block", why
    old_names = [f'"{old}" (say "{new}")' for old, new in renames if found(old, text)]
    if old_names:
        return (
            "context",
            "Old product names in this write: "
            + ", ".join(old_names)
            + ". Use the new names unless the text is about the rename itself.",
        )
    return None


if __name__ == "__main__":
    run_guard(check)
