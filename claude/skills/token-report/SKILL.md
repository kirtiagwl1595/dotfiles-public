---
name: token-report
description: Shows the user's Claude Code token use and cost; today, the last 7 days, and per session. Use when the user asks about tokens, usage, cost, spend, or limits.
---

# Token report

`ccusage` reads only the local logs in `~/.claude/projects`; it sends nothing anywhere.
On macOS and Linux, run each `ccusage` command alone with `dangerouslyDisableSandbox: true` (the user approves it). The sandbox hides `~/.claude/projects`, so an empty report inside it does not mean zero use. On Windows there is no sandbox; run it directly.

1. Find the date 7 days before today and write it as `YYYYMMDD`. Use the date you know; this works on every OS, unlike `date -v` or `date -d`.
2. Run `ccusage daily --since <that date>`.
   If `ccusage` is missing, ask the user to install it (they run it, not you):
   - macOS: `brew install ccusage`
   - Linux, Windows: `npm install -g ccusage`
3. Run `ccusage session --since <today as YYYYMMDD>`.
4. Report in a short table: date, input, output and cache tokens, cost. Name the biggest session today and one way to cut it (for example `graphify query` before reading files, a lower effort level, `/compact`).
5. Tell the user that `/cost` and `/usage` show the current session inside Claude Code.
