#!/usr/bin/env python3
"""PostToolUse Edit|Write|MultiEdit|Skill: nudge a step back when one file keeps changing in a session.

Band-aid fixes pass their tests, so a failure count never notices them. Edits that pile up on
one file do, also when the new cases arrive one user prompt at a time: the count spans the session.
It sees only Edit, Write and MultiEdit tool calls: a file changed through Bash is not counted.
Files outside the repo (plans, memory, scratch notes) change often by design and are skipped.

Each nudge and each step-back skill call goes to a local log, so `churn_watch.py report` can show
whether a nudge leads to a step back. The log holds file paths only, never file content.
"""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

NUDGE_AT = {4, 8}


def log_path():
    state = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(state) / "safe-lean" / "churn.jsonl"


def log(event, session, repo, **fields):
    entry = {"ts": int(time.time()), "event": event, "session": session, "repo": repo}
    try:
        log_path().parent.mkdir(parents=True, exist_ok=True)
        with log_path().open("a") as f:
            f.write(json.dumps({**entry, **fields}) + "\n")
    except OSError:
        pass  # the log is for review later; it must never disturb the edit


def watch(data):
    session = re.sub(r"[^\w-]", "_", data["session_id"])
    if data.get("tool_name") == "Skill":
        if data["tool_input"].get("skill", "").split(":")[-1] == "step-back":
            log("step-back", session, data.get("cwd"))
        return
    path = data["tool_input"]["file_path"]
    if not Path(path).is_relative_to(data["cwd"]):
        return
    state = Path(tempfile.gettempdir()) / f"claude-churn-{session}.json"
    try:
        counts = json.loads(state.read_text())
    except (OSError, ValueError):
        counts = {}
    counts[path] = counts.get(path, 0) + 1
    state.write_text(json.dumps(counts))
    if counts[path] in NUDGE_AT:
        log("nudge", session, data["cwd"], file=path, edits=counts[path])
        text = (
            f"You edited {path} {counts[path]} times in this session. Before the next edit, "
            "stop and check whether these edits are patches on one idea (a step-back skill, if you have one). "
            "If they are, rewrite the code to one general rule and delete the earlier patches."
        )
        out = {"hookEventName": "PostToolUse", "additionalContext": text}
        print(json.dumps({"hookSpecificOutput": out}))


def sessions(n):
    return f"{n} session" + ("" if n == 1 else "s")


def report():
    try:
        lines = log_path().read_text().splitlines()
    except OSError:
        print("No churn_watch events logged yet.")
        return
    nudged, after, without, nudges = set(), set(), set(), 0
    for line in lines:  # appended in time order, so "after" is the line order
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "nudge":
            nudges += 1
            nudged.add(e["session"])
        elif e.get("event") == "step-back":
            (after if e["session"] in nudged else without).add(e["session"])
    print(f"Log: {log_path()}")
    print(f"nudges: {nudges} in {sessions(len(nudged))}")
    print(f"step-back after a nudge: {len(after)} of {sessions(len(nudged))}")
    print(f"step-back without a nudge: {sessions(len(without))}")


def main():
    if sys.argv[1:] == ["report"]:
        return report()
    try:
        data = json.load(sys.stdin)
        watch(data)
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        return  # a nudge is optional: bad input must never disturb the edit


if __name__ == "__main__":
    main()
