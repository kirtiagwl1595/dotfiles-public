#!/usr/bin/env python3
"""PreToolUse Skill|Agent: EGM (Elephant-Goldfish Model) is for design work only; the user approves each start.

Acts only when an EGM plugin is installed: its skills and agents live in the `egm:` namespace,
so a session without that plugin never makes such a call, and this hook stays silent.

- An `egm:` skill always asks. A skill the user types (/egm:...) is no tool call, so it runs as is.
- An `egm:` reviewer agent runs without a prompt once an EGM skill ran in this session
  (user-typed, or a Skill call that was approved). Otherwise it asks too.
- No transcript, or one we cannot read: ask.
"""

import json

from _common import run_guard

REASON = "EGM is for design work only. Approve to start `{}`."


def egm_started(transcript_path):
    """True if this session already ran an EGM skill: typed by the user, or an approved Skill call."""
    calls, done = set(), set()
    try:
        with open(transcript_path, errors="ignore") as f:
            for line in f:
                if "egm:" not in line and "tool_result" not in line:
                    continue
                if "<command-name>/egm:" in line:
                    return True
                content = json.loads(line).get("message", {}).get("content", [])
                for c in content if isinstance(content, list) else []:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and c.get("name") == "Skill":
                        if str(c.get("input", {}).get("skill", "")).startswith("egm:"):
                            calls.add(c.get("id"))
                    elif c.get("type") == "tool_result" and not c.get("is_error"):
                        done.add(c.get("tool_use_id"))
    except (OSError, TypeError, ValueError):
        return False
    return bool(calls & done)


def check(data):
    tool, args = data.get("tool_name"), data.get("tool_input", {})
    if tool == "Skill":
        name = str(args.get("skill", ""))
        if not name.startswith("egm:"):
            return None
    elif tool == "Agent":
        name = str(args.get("subagent_type", ""))
        if not name.startswith("egm:") or egm_started(
            data.get("transcript_path") or ""
        ):
            return None
    else:
        return None
    return "ask", REASON.format(name)


if __name__ == "__main__":
    run_guard(check)
