"""Shared parts of the PreToolUse guards: read the payload, give a decision, fail closed.

A guard's check(data) returns None (no opinion) or a (kind, text) result:
  ("block", message)    exit 2; the message goes to Claude
  ("deny" | "ask", why) a permissionDecision
  ("context", text)     additionalContext for Claude, no decision
"""

import json
import os
import posixpath
import re
import sys

# Bad input must block: exit 1 would let the tool call through.
# UnicodeDecodeError is a ValueError, so bytes that are not UTF-8 block too.
BAD_INPUT = (ValueError, AttributeError, TypeError)

# Tools whose input is a command line, not a file path
SHELL_TOOLS = {"Bash", "PowerShell"}

HOME = os.path.expanduser("~")
_HOME_FWD = HOME.replace("\\", "/").rstrip("/")
_HOME_VARS = re.compile(
    r"\$\{env:userprofile\}|\$env:userprofile\b|%userprofile%|%homedrive%%homepath%"
    r"|\$\{(?:userprofile|home)\}|\$(?:userprofile|home)\b",
    re.IGNORECASE,
)
# Any Windows profile folder, as cmd, Git Bash or WSL write it: another user's secrets are secrets too
_WIN_HOME = re.compile(
    r"(?<![\w.~])(?:[a-z]:|/mnt/[a-z]|/[a-z])/users/[^/\s'\";&|<>()]+"
)
_ABSOLUTE = re.compile(r"/|[a-z]:/", re.IGNORECASE)


def norm(text):
    """Text in one form for matching secret paths: `/` for `\\`, lower case, `~` for each home form.

    Only for matching: matching too much is the safe side. Never pass the result to git or
    any other program; Linux paths are case-sensitive.
    """
    t = _HOME_VARS.sub("~", text.replace("\\", "/")).lower()
    if _HOME_FWD:
        t = re.sub(re.escape(_HOME_FWD.lower()) + r"(?=$|[/\s'\";&|<>()])", "~", t)
    return _WIN_HOME.sub("~", t)


def norm_path(path):
    """norm() for one file path, made absolute and with `..` resolved first."""
    p = _HOME_VARS.sub(lambda _: _HOME_FWD, path.replace("\\", "/"))
    if p == "~" or p.startswith("~/"):
        p = _HOME_FWD + p[1:]
    if not _ABSOLUTE.match(p):
        p = os.getcwd().replace("\\", "/") + "/" + p
    return norm(posixpath.normpath(p))


def emit(result):
    if not result:
        return
    kind, text = result
    if kind == "block":
        print(text, file=sys.stderr)
        sys.exit(2)
    out = {"hookEventName": "PreToolUse"}
    if kind == "context":
        out["additionalContext"] = text
    else:
        out["permissionDecision"] = kind
        out["permissionDecisionReason"] = text
    print(json.dumps({"hookSpecificOutput": out}))


def first(results):
    """The strongest result: block, then deny, then ask, then context."""
    order = ["block", "deny", "ask", "context"]
    found = [r for r in results if r]
    return min(found, key=lambda r: order.index(r[0]), default=None)


def run_guard(*checks):
    """Run checks on the stdin payload in one process and emit the strongest result."""
    try:
        # Bytes, not text: on Windows the text layer decodes as cp1252
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise TypeError("payload is not an object")
        result = first(check(data) for check in checks)
    except BAD_INPUT:
        result = ("block", "Blocked: the guard could not read the tool input.")
    except Exception:  # noqa: BLE001 - a crash exits 1, and exit 1 lets the tool call through
        result = (
            "deny",
            "The guard failed on this call. Report it; do not work around it.",
        )
    emit(result)
