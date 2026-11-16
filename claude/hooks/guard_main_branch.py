#!/usr/bin/env python3
"""PreToolUse Bash: no commit, push or other history write on main: work on a branch, merge by PR.

Opt out per repo:  git config claude.allowMain true
"""

import os
import re
import subprocess

from _common import run_guard
from guard_compound import parts_of, program

WRITES = ("commit", "push", "merge", "rebase", "cherry-pick", "am", "revert")


def git(repo, *args):
    p = subprocess.run(
        ["git", "-C", repo, *args], check=False, capture_output=True, text=True
    )
    return p.stdout.strip() if p.returncode == 0 else ""


def native(path):
    """A path as this OS opens it. Git Bash writes C:\\x as /c/x; Windows Python does not
    know that form, and a path git cannot open would let the write through.
    Not norm(): that lowers the case, and Linux paths are case-sensitive."""
    path = os.path.expanduser(path)
    m = re.match(r"/([a-zA-Z])(?=/|$)", path) if os.name == "nt" else None
    return f"{m[1]}:{path[2:] or '/'}" if m else path


def git_writes(cmd, cwd):
    """(repo, verb, args) for each git write, following cd and git -C."""
    repo, found = cwd, []
    for raw, norm in parts_of(cmd):
        if norm[0] == "cd" and len(norm) > 1:
            repo = os.path.join(repo, native(norm[1]))
        elif norm[:1] == ["git"] and len(norm) > 1 and norm[1] in WRITES:
            target = repo
            start = next(i for i, w in enumerate(raw) if program(w) == "git")
            for i, w in enumerate(raw[start + 1 :], start + 1):
                if not w.startswith("-"):
                    break
                if w == "-C" and i + 1 < len(raw):
                    target = os.path.join(target, native(raw[i + 1]))
            found.append((target, norm[1], norm[2:]))
    return found


def pushes_other_branches(args):
    """True when the push names branches and none of them is main/master/HEAD."""
    words = [w for w in args if not w.startswith("-")]
    refs = [
        w.split(":")[-1].removeprefix("refs/heads/") for w in words[1:]
    ]  # words[0] is the remote
    return bool(refs) and not {"main", "master", "HEAD"} & set(refs)


def rebases_other_branch(args):
    """True for `git rebase [--onto new] old <branch>`: git checks out <branch> first."""
    words = [w for w in args if not w.startswith("-")]
    need = 3 if "--onto" in args else 2
    return len(words) >= need and words[-1] not in ("main", "master")


def allowed(repo, kind, args):
    if kind == "commit" and not git(repo, "rev-parse", "--verify", "HEAD"):
        return True  # first commit of a new repo (new-project skill) goes on main
    if kind == "push" and pushes_other_branches(args):
        return True  # a named branch, e.g. `git push -u origin chore/x` from main
    if kind == "rebase" and rebases_other_branch(args):
        return True
    return "--abort" in args


def check(data):
    cmd = data.get("tool_input", {}).get("command", "")
    try:
        writes = git_writes(cmd, data.get("cwd") or os.getcwd())
    except ValueError:
        return None  # guard_compound asks for a command it cannot split
    branches = {}
    for repo, kind, args in writes:
        if repo not in branches:
            branches[repo] = git(repo, "symbolic-ref", "--short", "HEAD")
        branch = branches[repo]
        if (
            branch not in ("main", "master")
            or git(repo, "config", "--get", "claude.allowMain") == "true"
            or allowed(repo, kind, args)
        ):
            continue
        why = (
            f"Blocked: git {kind} on '{branch}'. Work on a branch instead:\n"
            "  git switch -c feature/<short-name>\n"
            "then commit there and open a PR (gh pr create). "
            "To allow main in this repo: git config claude.allowMain true"
        )
        return "block", why
    return None


if __name__ == "__main__":
    run_guard(check)
