#!/usr/bin/env python3
"""PreToolUse: what the agent may not do while a loop runs (docs/loop-engineering.md §13).

Outside a loop it returns at once: no state file for this worktree, no opinion. It runs
alone for the file tools and inside guard_bash for Bash. One ordered table (RULES) holds
the rules of both profiles; the work profile adds its own (R18). The Bash word checks
only warn early; Stop row 7 and loop_gate enforce (§13.1).
"""

import fnmatch
import json
import os
import sys
from collections import namedtuple
from pathlib import Path

if __name__ == "__main__" and sys.platform == "win32":
    # The loop needs the OS sandbox: no loop runs on native Windows. Return before any import
    # from the guards, so that this hook can never block normal work there. Elsewhere a failed
    # import below is not caught: a PreToolUse guard must not run on without its rules.
    sys.exit(0)

import _loop
from _common import run_guard
from guard_compound import in_rules, parts_of, settings_files, trusted_forge
from guard_main_branch import TREE_WRITES, WRITES, git_writes
from guard_secrets import GLOB_BRACE, SHELL_SPLIT, alternatives, written

FILE_WRITES = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# The running plugin (installed or a frozen pilot copy): the judge must not change mid-loop
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
# Only hooks write git during a loop (§7): these change the work tree or history
LOOP_GIT_VERBS = {*WRITES, *TREE_WRITES, "update-ref"}
DELETERS = {"rm", "rmdir", "mv", "unlink"}
NULL_DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"}
FIND_EXPRESSION = ("-", "(", "!", "\\(")
# Key and credential files (R19). `*.key` is left out: Keynote files use it too
KEY_FILES = (
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "credentials*.json",
    "*service-account*.json",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "kubeconfig",
)
# No push, PR or repo creation by the loop, in any profile (non-goal; G4). Push is a git verb
OUTWARD = ("*forge.sh pr-create*", "*forge.sh repo-create*")
WORK_DENY = ("claude mcp add:*",)
WORK_ASK = (
    "curl:*",
    "wget:*",
    "git clone:*",
    "uv add:*",
    "npm install:*",
    "npm i:*",
    "brew install:*",
)


def loop_state(cwd):
    if sys.platform == "win32":
        return None  # the loop needs the OS sandbox: no loop runs on native Windows
    wt = _loop.worktree_root(cwd)
    state = _loop.load_state(wt) if wt else None
    return state if state and state.get("status") in _loop.ACTIVE else None


def inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(str(folder))
    return path == folder or path.startswith(folder + os.sep)


def protected(state, path):
    """A reason when the agent must not write `path`, else None."""
    if os.path.realpath(path) in NULL_DEVICES:
        return None
    if inside(path, PLUGIN_ROOT):
        return "the loop's own hooks and tools are read-only during a loop"
    wt = state["worktree"]
    if not inside(path, wt):
        # The state folder, the main checkout and lessons too: the bundle step writes .loop/lesson.md
        return f"{path} is outside the worktree; during a loop the agent writes only inside it"
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(wt))
    hit = _loop.is_protected(
        rel,
        state.get("scope_protected") or (),
        state.get("approved_paths") or (),
        state.get("self_protect"),
    )
    return (
        f"{rel} is protected during the loop; the operator can approve it with `/safe-lean:loop-engineer allow {rel}`"
        if hit
        else None
    )


def target_path(c):
    path = c.inp.get("file_path") or c.inp.get("notebook_path")
    return os.path.join(c.cwd, os.path.expanduser(path)) if path else None


def baseline_first(c):
    path = target_path(c)
    if not path or c.state.get("baseline"):
        return None
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(c.state["worktree"]))
    return (
        None
        if rel == ".loop/loop-progress.md"
        else f"run `{_loop.VERIFY_CMD}` for the baseline before any edit"
    )


def protected_file(c):
    path = target_path(c)
    return protected(c.state, path) if path else None


def operands(norm):
    if norm[0] == "find":
        out = []
        for w in norm[1:]:
            if w.startswith(FIND_EXPRESSION):
                break
            out.append(w)
        return out if "-delete" in norm else []
    return [w for w in norm[1:] if not w.startswith("-")]


def delete_outside(c):
    folder = c.cwd
    for _raw, norm in c.parts:
        if norm[0] == "cd" and len(norm) > 1:
            folder = os.path.join(folder, os.path.expanduser(norm[1]))
        elif norm[0] in DELETERS or norm[0] == "find":
            for word in operands(norm):
                path = os.path.join(folder, os.path.expanduser(word))
                if "$" in word or not inside(path, c.state["worktree"]):
                    return f"{word} is outside the worktree; the loop deletes or moves files only inside it"
    return None


def sandbox_flag(c):
    # A skill eval needs `claude` and the API, so its verifier may leave the sandbox (§7)
    skill_eval = (
        c.cmd == _loop.VERIFY_CMD
        and c.state.get("target_type") == "skill"
        and c.state.get("profile") == "personal"
    )
    if c.inp.get("dangerouslyDisableSandbox") and not skill_eval:
        return "commands stay in the sandbox during a loop"
    return None


def changed_bin(c):
    if c.cmd == _loop.VERIFY_CMD and _loop.bin_sha(c.state["worktree"]) != c.state.get(
        "bin_sha"
    ):
        return ".loop/bin changed; stop, and the Stop hook restores it"
    return None


def git_write(c):
    try:
        writes = git_writes(c.cmd, c.cwd, LOOP_GIT_VERBS)
    except ValueError:
        return None  # guard_compound asks for a command it cannot split
    return (
        writes
        and f"git {writes[0][1]}: only the loop hooks write git; the Stop hook commits or reverts"
    )


def protected_redirect(c):
    # A redirect target is a whole path: its tails (`/null` of `/dev/null`) are not
    for target in written(os.path.expandvars(c.cmd)):
        why = protected(c.state, os.path.join(c.cwd, os.path.expanduser(target)))
        if why:
            return why
    return None


def excluded_patterns(cwd):
    """sandbox.excludedCommands from the settings files: these run outside the sandbox."""
    found = []
    for f in settings_files(cwd):
        try:
            found += (
                json.loads(f.read_text()).get("sandbox", {}).get("excludedCommands", [])
            )
        except (OSError, ValueError, AttributeError):
            continue
    return found


def part_rule(patterns, why):
    """A rule that hits the first part matching a pattern, as text or normalized, so
    `cd x && git clone` and `bash path/forge.sh pr-create` are found too."""

    def test(c):
        hit = next(
            (
                " ".join(norm)
                for raw, norm in c.parts
                if in_rules(patterns, " ".join(raw), " ".join(norm))
            ),
            None,
        )
        return hit and f"`{hit}`: {why}"

    return test


def forge_part(norm):
    # `forge.sh x`, or a shell that runs it (`bash path/forge.sh x`)
    return any(os.path.basename(w) == "forge.sh" for w in norm[:2])


def excluded_command(c):
    rules = excluded_patterns(c.cwd)
    for raw, norm in c.parts:
        if not in_rules(rules, " ".join(raw), " ".join(norm)):
            continue
        if forge_part(norm) and trusted_forge(raw, norm, c.cwd):
            continue  # its outward subcommands are OUTWARD's part
        return f"`{' '.join(norm)}` runs outside the sandbox; a loop runs only sandboxed commands"
    return None


def key_name(word):
    # Plain fnmatch, not the shell rule: `*.pem` must also match `.deploy.pem`
    name = os.path.basename(word.rstrip("/")).lower()
    return any(fnmatch.fnmatchcase(name, p) for p in KEY_FILES)


def key_words(c):
    """The paths and globs that a call names. A Grep pattern is a regex, not a path."""
    if c.tool == "Bash":
        for word in c.cmd.split():
            for alt in alternatives(word) or [word]:
                yield from SHELL_SPLIT.split(alt)
        return
    for k in ("file_path", "notebook_path", "path", "glob"):
        yield c.inp.get(k) or ""
    if c.tool == "Glob":
        yield from alternatives(c.inp.get("pattern") or "", GLOB_BRACE) or []


def key_file(c):
    word = next((w for w in key_words(c) if w and key_name(w)), None)
    return word and f"{word} names a key file; a loop does not read or write keys"


def auto_mode(c):
    mode = c.mode
    if mode is None or mode in _loop.AUTO_MODES:
        return f"permission mode is {mode or 'unknown'}: switch to manual or acceptEdits mode"
    return None


# What every rule sees. parts: (raw words, normalized words) of a Bash command; empty
# when the command cannot be split (guard_compound asks for it then)
Call = namedtuple("Call", "state tool inp cwd cmd parts mode")

BASH = {"Bash"}
KEY_TOOLS = FILE_WRITES | {"Read", "Grep", "Glob", "Bash"}
# Every tool that reaches guard_loop: its hooks.json matcher, and Bash through guard_bash
SEEN = KEY_TOOLS | {"WebFetch"}
BOTH, WORK = "both", "work"
# (profile, decision, tools, test). A test returns its reason or a false value. The first
# hit decides, and every deny comes before every ask.
RULES = (
    (WORK, "deny", SEEN, auto_mode),
    (BOTH, "deny", BASH, sandbox_flag),
    (BOTH, "deny", BASH, changed_bin),
    (BOTH, "deny", KEY_TOOLS, key_file),
    (BOTH, "deny", FILE_WRITES, baseline_first),
    (BOTH, "deny", FILE_WRITES, protected_file),
    (BOTH, "deny", BASH, git_write),
    (BOTH, "deny", BASH, delete_outside),
    (BOTH, "deny", BASH, protected_redirect),
    (
        BOTH,
        "deny",
        BASH,
        part_rule(OUTWARD, "the loop never pushes or opens a PR or a repo"),
    ),
    (BOTH, "deny", BASH, excluded_command),
    (
        WORK,
        "deny",
        BASH,
        part_rule(WORK_DENY, "it changes this machine; not in a work loop"),
    ),
    (WORK, "ask", {"WebFetch"}, lambda c: "a work loop asks before network access"),
    (
        WORK,
        "ask",
        BASH,
        part_rule(WORK_ASK, "it uses the network or installs; a work loop asks first"),
    ),
)


def call_of(state, data, cwd):
    tool, inp = data.get("tool_name", ""), data.get("tool_input") or {}
    cmd = str(inp.get("command", "")) if tool == "Bash" else ""
    try:
        parts = parts_of(cmd)
    except ValueError:
        parts = []
    return Call(state, tool, inp, cwd, cmd.strip(), parts, data.get("permission_mode"))


def check(data):
    cwd = data.get("cwd") or os.getcwd()
    state = loop_state(cwd)
    if not state:
        return None
    c = call_of(state, data, cwd)
    work = (
        state.get("profile") != "personal"
    )  # an unknown profile gets the strict rules
    for profile, kind, tools, test in RULES:
        if c.tool in tools and (profile == BOTH or work):
            why = test(c)
            if why:
                return kind, f"Loop guard: {why}"
    return None


if __name__ == "__main__":
    run_guard(check)
