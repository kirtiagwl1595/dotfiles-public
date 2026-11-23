#!/usr/bin/env bash
# A small order report tool (3 modules, 1 test file, production-style: finance reads it). The prompt asks for a
# new export command: a feature that spans several files, which is when the staff-engineer skill should fire.
set -e
git init -q -b main
git config user.name eval && git config user.email eval@example.com && git config commit.gpgsign false
mkdir -p app tests data
touch app/__init__.py
# An empty conftest.py at the root puts the root on sys.path, so `pytest` finds `app`
touch conftest.py
cat > data/orders.json <<'JSON'
[
  {"id": 1, "date": "2025-12-30", "total_cents": 1250, "status": "paid"},
  {"id": 2, "date": "2026-01-04", "total_cents": 9900, "status": "paid"},
  {"id": 3, "date": "2026-01-19", "total_cents": 4500, "status": "refunded"}
]
JSON
cat > app/store.py <<'PY'
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "orders.json"


def load_orders(path=DATA):
    """All orders, oldest first. Dates are ISO strings, totals are integer cents."""
    return sorted(json.loads(Path(path).read_text()), key=lambda o: o["date"])
PY
cat > app/report.py <<'PY'
def summary(orders):
    """Count and revenue of the paid orders; a refunded order does not count."""
    paid = [o for o in orders if o["status"] == "paid"]
    return {"orders": len(paid), "revenue_cents": sum(o["total_cents"] for o in paid)}
PY
cat > app/cli.py <<'PY'
import argparse

from app.report import summary
from app.store import load_orders


def main(argv=None):
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary", help="count and revenue of paid orders")
    args = parser.parse_args(argv)
    if args.command == "summary":
        print(summary(load_orders()))


if __name__ == "__main__":
    main()
PY
cat > tests/test_report.py <<'PY'
from app.report import summary


def test_a_refunded_order_does_not_count():
    orders = [
        {"id": 1, "date": "2026-01-04", "total_cents": 100, "status": "paid"},
        {"id": 2, "date": "2026-01-05", "total_cents": 900, "status": "refunded"},
    ]
    assert summary(orders) == {"orders": 1, "revenue_cents": 100}
PY
git add -A && git commit -q -m init
