---
name: setup-repo
description: Makes an existing repo Claude-forward; writes or improves its project CLAUDE.md (layout, run/test/lint commands, rules) and checks its .gitignore and .claude/settings.json. Use when the user asks to set up, onboard, or prepare a repo or project for Claude.
---

# Set up a repo for Claude

Work in the repo Claude was started in. Never in a read-only clone of someone else's repo.
If a shell step is blocked (permissions, missing tool), skip it, say which, and go on: CLAUDE.md (step 4) needs only Read and Write.

`PY` below means `bash "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" ../repo_setup.py`. It finds a working Python 3.9+ on macOS, Linux and Windows (on Windows, `python3` can be the Microsoft Store stub).

**Sandbox (macOS, Linux):** the sandbox denies writes to `.git/config`, `.git/hooks/` and `.claude/settings.json`. So `PY apply`, `git switch -c` and `git commit` can fail with "Operation not permitted". Then run that one command outside the sandbox: it asks the user. Never chain it with another command.

**First, in every repo (also a team or dirty one): lock the Git hooks.** `PY protect "$PWD"`. Below `~/git` it only says "covered" (the user settings lock those). Elsewhere it writes deny rules to the main checkout's `.claude/settings.local.json`, never committed; on macOS and Linux that write needs the sandbox off, so it asks. If it refuses, show the reason and go on.

0. **Team repo?** `PY team "$PWD"` prints the owner (exit 0) for a team repo, nothing (exit 1) for the user's own repo. A team repo is set up **locally only**: learn it (step 3), then write `CLAUDE.local.md` in the step 4 shape, plus `.claude/settings.local.json` if a permission is worth adding. Both are in the global gitignore (`git/gitignore_global`). A tracked CLAUDE.md is the team's: read it and leave it as is. Skip steps 1, 2, 5 and 6 (no branch, commit, push or PR), then tell the user what was written and that it stays on this machine.
1. Stop if there are uncommitted changes and ask the user. Do not switch branches yet.
2. **Fixed parts first (free):** `PY plan "$PWD"`. It judges the default branch, not the checkout. If it flags tracked personal or secret files, show the warning and let the user decide about `--untrack`.
   - `→`: tell the user, then `PY apply "$PWD"` (managed `.gitignore` block, `.claude/settings.json`, quiet pytest block; one commit on `chore/claude-forward`, made from the default branch in a throwaway worktree). It writes `.git/worktrees` and signs, so on macOS and Linux it needs the sandbox off and asks.
   - `stale` or `no default branch`: show the line and stop. Never merge, rename, rebase or delete that branch, or close its PR, without the user's yes: a PR can use it as its base.
   - Then work on the setup branch, never on one cut from a feature branch: `git switch --no-overwrite-ignore chore/claude-forward`. If there is no such branch: `git switch --no-overwrite-ignore -c chore/claude-forward --no-track <default>` (`<default>`: `origin/HEAD`, else `main` or `master`). If the switch fails, show why and stop.
   **Tracked junk:** `git ls-files -ci --exclude-standard` lists tracked files the gitignore now excludes (`.DS_Store`, Office lock files `~$*`, caches). Also look for build by-products next to their source (`.log`, `.aux`, `.tex` next to an `.Rmd`). Show the list; on the user's yes, `git rm --cached` them (copy what the user needs first: a switch or merge across that commit deletes the files from disk).
3. **Learn the repo cheaply:** `graphify query "<main topic>"` if `graphify-out/` exists; else `git ls-files | head -100`, the README, and the build files (`pyproject.toml`, `package.json`, `DESCRIPTION`, `*.Rproj`). Read only what you need.
4. **CLAUDE.md**: same shape as `${CLAUDE_PLUGIN_ROOT}/templates/project/CLAUDE.md`, under ~60 lines, no personal facts, no imports:
   - `# <repo name>` + one line on what it is
   - `## Layout`: the main folders and what lives where
   - `## Commands`: run, test, lint for this language (Python: `uv run …`; R: `Rscript -e …` / `rmarkdown::render`; Node: `npm run …`). Only commands that exist in the repo. If the language's tool is not installed here (`command -v Rscript`), still write the commands but tell the user they are untested on this computer.
   - `## Rules`: the 2-5 rules this repo really needs (data that must not be committed, generated files not to edit, …)
   - If a CLAUDE.md already exists: **suggest** changes as a diff and let the user choose; do not rewrite it.
5. **LLM projects only:** ask before adding `evals/` from `${CLAUDE_PLUGIN_ROOT}/templates/project/evals/`.
   **Doc rules (repo with `docs/`):** offer `docs/README.md`, `docs/decisions.md` and `tests/test_docs.py` from `${CLAUDE_PLUGIN_ROOT}/templates/project/`. Never overwrite a file: suggest a diff. If `tests/test_docs.py` fails on old docs, show the list and let the user choose.
6. Show the user the CLAUDE.md, then commit everything on `chore/claude-forward`. With no `origin`, stop here: there is nothing to push to, so tell the user to merge it into the default branch. Else **ask** before `git push -u origin chore/claude-forward` and before opening the PR (GitHub) / MR (GitLab), still on the branch: `bash "${CLAUDE_PLUGIN_ROOT}/forge.sh" pr-create --title "…" --body-file <file>`. It picks gh or glab from the `origin` remote and always targets `origin`, never `upstream`. Write the body to a temp file; no AI attribution in it. Then `git switch -` back.
