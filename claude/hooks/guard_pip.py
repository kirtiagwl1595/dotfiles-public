#!/usr/bin/env python3
"""PreToolUse Bash: no `pip install`: each project has its own uv-managed .venv."""

import re

from _common import run_guard
from guard_compound import parts_of

PIP = re.compile(r"pip3?(\.\d+)?")
PYTHON = re.compile(r"python3?(\.\d+)?")
MESSAGE = (
    "Blocked: pip install. Each project uses its own uv .venv.\n"
    "  add a dependency:   uv add <pkg>        (dev only: uv add --dev <pkg>)\n"
    "  one-off tool:       uvx <tool>  or  uv tool install <tool>\n"
    "  legacy requirements: uv pip install -r requirements.txt"
)


PY_VERSION = re.compile(r"-\d+(\.\d+)?(-\d+)?|-V:\S+")  # the Windows launcher: py -3.12


def pip_install(norm):
    args = norm[1:]
    if norm[0] == "py" and args and PY_VERSION.fullmatch(args[0]):
        args = args[1:]
    if (norm[0] == "py" or PYTHON.fullmatch(norm[0])) and args[:2] == ["-m", "pip"]:
        norm = args[1:]
    return len(norm) > 1 and PIP.fullmatch(norm[0]) and norm[1] == "install"


def check(data):
    try:
        parts = parts_of(data.get("tool_input", {}).get("command", ""))
    except ValueError:
        return None  # guard_compound asks for a command it cannot split
    if any(pip_install(norm) for _, norm in parts):
        return "block", MESSAGE
    return None


if __name__ == "__main__":
    run_guard(check)
