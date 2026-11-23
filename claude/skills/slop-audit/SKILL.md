---
name: slop-audit
description: Audits an existing repo for patch-on-patch code and AI slop (special cases, near-copies, dead code, swallowed errors, one test per scenario), ranks the hot spots and writes a report. Fixes only the findings the user picks, one branch each. Use when the user types /slop-audit.
disable-model-invocation: true
---

# Slop audit

Read-only until the user picks a finding. Run it in the repo root.

## 1. Measure
Run each command alone. Skip a tool that does not fit the repo's language.

```bash
# Churn hot spots: the files changed most often
git log --since=6.months --format= --name-only | sort | uniq -c | sort -rn | head -20
# Python: branches, length, swallowed errors, commented-out code (--output-format concise for locations)
ruff check --select C901,PLR0911,PLR0912,PLR0915,SIM,ERA,BLE,S110 --statistics .
# Python: dead code
uvx vulture . --min-confidence 80 --exclude .venv
# Python: complexity per function, grade C and worse
uvx radon cc -s -n C . -e ".venv/*"
# Leftover band-aid markers (a hit in rule text or docs is not a finding)
git grep -nE "workaround|special case|hack|TODO|FIXME|temporary"
# One rule with 2 sources: a comment that points at a copy
git grep -nE "same (list|rule|set|values?) as"
```

JS/TS: ask first, because the tools (`jscpd`, `fallow`) need npm.
`uvx` runs a tool once from the uv cache. It installs nothing on the machine.
In the Claude Code sandbox, `uvx` cannot write its tools folder: run it as `UV_TOOL_DIR="$TMPDIR/uvtools" uvx ...`.

## 2. Rank
1. Join churn and complexity: a file high on both lists is a hot spot.
2. Read the top 5 hot-spot functions and their tests in full. Count the test rows that pin each function: few rows means high Risk, because a rewrite needs characterization tests first.
3. Check each one against the band-aid smells in `safe-lean:step-back`.
4. Apply the deletion test: if you delete the function, does the complexity go away or move to its callers?
5. For tests, look for near-identical test functions that one parametrized table would cover.

## 3. Report
Write `.claude/audits/YYYY-MM-DD-slop.md` (personal; the global gitignore keeps it out of commits). Put the numbers from step 1 first, then the table below.

| # | File:line | Smell | Evidence | The one rule that replaces it | Risk |
|---|---|---|---|---|---|

End with the top 3 by value (hot spot and simple fix first). Ask which ones to fix. Do not change code before the answer.

## 4. Fix one finding per branch
1. `git switch -c refactor/<finding>`.
2. Pin the current behavior first: characterization tests at the public seam, green before any change.
3. Run `safe-lean:step-back` steps 2 to 6: the rule, 2 designs, rewrite, delete the patches, fold the tests.
   Every existing scenario stays as a row, and no assertion is removed or weakened.
4. Run the full test suite. Report lines added and deleted. Open the PR only after the user says yes.

## 5. Ratchet (ask first)
Stop new slop from coming back: in `pyproject.toml` (or `ruff.toml` when the repo has no `pyproject.toml`), turn on the ruff rules from step 1 that the repo now passes, and set `max-complexity` to today's highest value.
In a team repo, this is a team decision: propose it in the PR, do not push it alone.
