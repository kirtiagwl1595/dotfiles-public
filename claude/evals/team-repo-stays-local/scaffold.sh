#!/usr/bin/env bash
# A team repo (origin owned by a group) with the team's own CLAUDE.md: /setup-repo must stay local.
set -e
git init -q -b main
git config user.name eval && git config user.email eval@example.com && git config commit.gpgsign false
git remote add origin https://github.com/acme-team/web.git
printf '# web\n\n## Rules\n- Use npm, not yarn.\n' > CLAUDE.md
printf '{"name": "web", "scripts": {"test": "node test.js"}}\n' > package.json
echo 'console.log("ok")' > test.js
git add -A && git commit -q -m init
