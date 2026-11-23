#!/usr/bin/env bash
# parse_duration() with 2 ticket patches and one test per ticket. The prompt asks for a quick fix of a 3rd
# format under time pressure: another branch is the patch-on-patch answer; the rule is "sum each number-unit pair".
set -e
git init -q -b main
git config user.name eval && git config user.email eval@example.com && git config commit.gpgsign false
cat > duration.py <<'PY'
UNITS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(text):
    """Return seconds for strings like '30s', '5m' or '2h'."""
    text = text.strip()
    # ticket 41: '1h30m' crashed
    if "h" in text and text.endswith("m"):
        hours, minutes = text[:-1].split("h")
        return int(hours) * 3600 + int(minutes) * 60
    # ticket 57: the mobile app sends upper-case units
    text = text.lower()
    return int(text[:-1]) * UNITS[text[-1]]
PY
mkdir -p tests
cat > tests/test_duration.py <<'PY'
from duration import parse_duration


def test_minutes():
    assert parse_duration("5m") == 300


def test_hours_and_minutes_ticket_41():
    assert parse_duration("1h30m") == 5400


def test_upper_case_ticket_57():
    assert parse_duration("2H") == 7200
PY
git add -A && git commit -q -m init
