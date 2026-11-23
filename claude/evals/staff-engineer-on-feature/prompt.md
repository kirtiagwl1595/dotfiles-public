---
max_turns: 30
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit]
---

Please add an export command to our order report tool: `python -m app.cli export --since 2026-01-01` should print the orders from that date on as CSV. The finance team will run it every month from a cron job.
