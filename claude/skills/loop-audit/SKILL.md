---
name: loop-audit
description: Audits which skills, scripts and repo areas have no verifier (no eval, test or dry run), ranks them by risk and writes a report. Read-only. Use when the user types /safe-lean:loop-audit.
disable-model-invocation: true
---

# Loop audit

Read-only: change no file except the report. Run it at the repo root. A loop can only improve a target that has a verifier, so this list is the loop backlog.

## 1. Measure

Run `python3 -B "${CLAUDE_PLUGIN_ROOT}/loopctl.py" audit`. It runs no repo command and writes nothing. It prints JSON with 4 keys:

| Key | Each item has |
|---|---|
| `skills` | `path`, `eval` (case folders), `tests`, `verifier` (`eval` or null), `churn` (commits in 90 days) |
| `scripts` | `path`, `tests`, `dry_run`, `side_effects`, `verifier` (`test`, `dry-run` or null), `churn` |
| `areas` | top-level folder, `files`, `tests`, `churn` |
| `commands` | the Test, Lint, Format and Type commands that `discover` would run |

A test that only names a skill or a script is not a verifier: the audit counts a test only when it builds the path to the file and runs it.

## 2. Rank

Rank every skill and script with `verifier: null`. Higher first:

1. Side effects: each of deletes, downloads, installs, pushes and writes home counts 1. A script that deletes and downloads with no test is the top risk.
2. Churn: a target that changes often breaks often.
3. No dry run (`dry_run: false`): a first check is harder to write.

Then list the areas with `files` above 0 and `tests` 0, highest churn first.

## 3. Report

Write `.claude/audits/YYYY-MM-DD-loop.md` (personal; the global gitignore keeps it out of commits). Start with the counts: skills, skills without an eval, scripts, scripts without a verifier, the repo commands found. Then this table, one row for each target:

| # | Target | Type | Verifier | Side effects | Churn | Why this rank | Start a loop |
|---|---|---|---|---|---|---|---|

In the last column, write the command: `/safe-lean:loop-engineer script <path>` for a script, `/safe-lean:loop-engineer skill <name>` for a skill.

Below the table, link the newest `.claude/audits/*-slop.md`, or write "No slop audit yet: `/slop-audit`." Slop and missing verifiers are separate risks; a hot spot in both is a strong first pick.

## 4. Ask

Show the top 3 and ask which one to loop on. Do not start a loop.
