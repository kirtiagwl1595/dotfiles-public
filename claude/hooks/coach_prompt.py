#!/usr/bin/env python3
"""UserPromptSubmit: add a one-line tip for risky prompt habits, and a hint when a disabled plugin fits the prompt."""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

BIG_ASK = 1200  # characters of the user's own words (pastes excluded)
PASTED = re.compile(
    r'<pasted_content id="([^"]+)">.*?</pasted_content id="\1">', re.DOTALL
)  # pasted logs/files are evidence, not the ask

TIPS = [
    (
        r"\b(just )?quickly\b|\bquick (fix|hack)\b",
        "Coach: even quick fixes go faster with a failing test first; add it as a row to an existing test table if one fits.",
    ),
    (
        r"\bskip(ping)? (the )?tests?\b|\bno tests?\b",
        "Coach: keep the tests; if they are slow, run only the one test that covers this change.",
    ),
]


# A disabled plugin's skills leave Claude's listing, so Claude cannot know they fit a
# prompt. A hint names a plugin that is installed but off: settings must list it with
# `false`. Plugin name (before the @) to the words that make it fit. Only plugins that
# this repo ships; to hint about another one, add a line.
DORMANT = {
    "ecc-picks": r"\bpass@k\b|\beval(s| harness)\b",
    "hf-picks": r"\bhugging ?face\b|\bhf (hub|upload|download|jobs|spaces?)\b",
    "addy-picks": r"\bdoubt[- ]driven\b|\badversarial review\b|\bcross-examine\b",
    "writing-skills": r"\bwinston\b|\bhow to speak\b|\bpresentation (skills?|coach)\b",
}
# Plugins that are off by default, so that they are turned on for one repo only
PER_REPO = {"hf-picks", "ecc-picks", "addy-picks"}


def coach_tip(prompt):
    if len(prompt) > BIG_ASK:
        return "Coach: this is a big task. Suggest plan mode (Shift+Tab) and split it into steps before editing."
    for pattern, tip in TIPS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return tip
    return None


def enabled_plugins(cwd):
    """enabledPlugins from user, then project, then local settings; the later file wins."""
    user = Path(
        os.environ.get("COACH_SETTINGS", Path.home() / ".claude" / "settings.json")
    )
    try:
        enabled = json.loads(user.read_text()).get("enabledPlugins") or {}
    except (OSError, ValueError, AttributeError):
        return None
    if cwd:
        for name in ("settings.json", "settings.local.json"):
            try:
                repo = json.loads((Path(cwd) / ".claude" / name).read_text())
                enabled = {**enabled, **(repo.get("enabledPlugins") or {})}
            except (OSError, ValueError, AttributeError):
                continue  # no repo file: the user value stands
    return enabled


def dormant_hints(prompt, session_id, cwd=None):
    enabled = enabled_plugins(cwd)
    if enabled is None:
        return []  # no readable settings: stay quiet rather than guess
    # Once per session, so a recurring topic does not nag every prompt.
    safe_id = re.sub(r"[^\w-]", "_", session_id)
    seen_file = Path(tempfile.gettempdir()) / f"coach-dormant-{safe_id}"
    seen = set(seen_file.read_text().split()) if seen_file.exists() else set()
    hints = []
    for name, pattern in DORMANT.items():
        # The key is `name@marketplace`: the marketplace is whatever the user installed from
        key = next((k for k in enabled if k.split("@")[0] == name), None)
        if (
            key
            and enabled[key] is False
            and key not in seen
            and re.search(pattern, prompt, re.IGNORECASE)
        ):
            seen.add(key)
            scope, where = (
                (" --scope local", ".claude/settings.local.json")
                if name in PER_REPO
                else ("", "~/.claude/settings.json")
            )
            hints.append(
                f"Dormant: {name} is off but may fit this prompt. Ask the user first; "
                f"then run `claude plugin enable {key}{scope}` (it writes {where}, "
                "so it needs a sandbox bypass), then `/reload-plugins`."
            )
    if hints:
        seen_file.write_text("\n".join(sorted(seen)))
    return hints


def main():
    payload = json.load(sys.stdin)
    prompt = payload.get("prompt", "")
    if prompt.lstrip().startswith("<task-notification>"):
        return  # a background agent finished; not the user's ask
    prompt = PASTED.sub("", prompt)
    tip = coach_tip(prompt)
    for line in ([tip] if tip else []) + dormant_hints(
        prompt, str(payload.get("session_id", "none")), payload.get("cwd")
    ):
        print(line)


if __name__ == "__main__":
    main()
