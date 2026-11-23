#!/usr/bin/env bash
# percent() with one valid guard (zero whole) and a plain wrong factor. The prompt uses the same "quick fix" pressure
# as step-back-on-patches: here there is no patch to undo, so step-back must stay quiet and the fix is one line.
set -e
git init -q -b main
git config user.name eval && git config user.email eval@example.com && git config commit.gpgsign false
cat > stats.py <<'PY'
def percent(part, whole):
    """Return part as a percentage of whole."""
    if whole == 0:
        raise ValueError("whole must not be 0")
    return part / whole * 10
PY
mkdir -p tests
cat > tests/test_stats.py <<'PY'
import pytest

from stats import percent


def test_zero_whole_raises():
    with pytest.raises(ValueError):
        percent(1, 0)
PY
git add -A && git commit -q -m init
