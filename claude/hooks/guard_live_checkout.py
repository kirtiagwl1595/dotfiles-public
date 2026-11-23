#!/usr/bin/env python3
"""PreToolUse shell: no sandboxed git that changes the files of a live checkout.

A live checkout is a clone whose files other sessions run, and that the sandbox settings
lock. Git in the sandbox then stops at the first locked file, still says "Switched to
branch", and leaves a mixed tree. Not guard_main_branch: that rule is per branch and
claude.allowMain turns it off.

Which clones are live: the clone this hook runs from (when it is a main checkout, not a
worktree), and each folder listed in ~/.config/claude/live-checkout.txt (one per line,
`~` allowed, `#` starts a comment). LIVE_CHECKOUT adds folders too (a path list for
this OS). With none of them, the hook does nothing.
"""

import os
from pathlib import Path

from _common import HOME, run_guard
from guard_main_branch import TREE_WRITES, git, git_writes

CONFIG = os.path.join(HOME, ".config", "claude", "live-checkout.txt")
WHY = (
    "git {verb} in {live} would change the live copy, and the sandbox would stop it "
    "halfway. Work in a worktree (EnterWorktree). To deploy merged work, run the one git "
    "command outside the sandbox, so that the user is asked."
)


def live_checkouts():
    """The live folders, as written (`~` expanded)."""
    found = [p for p in os.environ.get("LIVE_CHECKOUT", "").split(os.pathsep) if p]
    try:
        lines = Path(CONFIG).read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    found += [s for line in lines if (s := line.strip()) and not s.startswith("#")]
    clone = Path(__file__).resolve().parents[2]
    if (clone / ".git").is_dir():  # a worktree has a .git file: it is not live
        found.append(str(clone))
    return [os.path.expanduser(p) for p in found]


def live_of(repo, live):
    """The live folder that `repo` is the main checkout of, else None."""
    top = git(repo, "rev-parse", "--show-toplevel")
    if not top:
        return None
    # samefile: a symlink or another letter case is the same checkout
    return next(
        (p for p in live if os.path.isdir(p) and os.path.samefile(top, p)), None
    )


def check(data):
    tool_input = data.get("tool_input", {})
    if tool_input.get("dangerouslyDisableSandbox"):
        return None  # git can write there, and the ask rule puts the call to the user
    live = live_checkouts()
    if not live:
        return None
    cwd = data.get("cwd") or os.getcwd()
    try:
        writes = git_writes(tool_input.get("command", ""), cwd, TREE_WRITES)
    except ValueError:
        return None  # guard_compound asks for a command it cannot split
    for repo, verb, _ in writes:
        if where := live_of(repo, live):
            return "deny", WHY.format(verb=verb, live=where)
    return None


if __name__ == "__main__":
    run_guard(check)
