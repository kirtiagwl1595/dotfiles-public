# Shared Claude Code rules (dotfiles-public)

Imported by `install.py` at the top of `~/.claude/CLAUDE.md`. Put your own rules below the imports in that file.

## Ask first
- Ask before a machine-wide install (`brew`, `apt`, `winget`, `choco`, `scoop`, `uv tool install`, `npm -g`), any delete, or anything outward-facing (push, PR, repo create, publishing an artifact, sending through a connector).
- `uv add` into the project `.venv` needs no question.
- Outside the sandbox, run one specific command per call, so each one gets its own approval. The compound-command guard denies a chain there; a pipe into a filter that reads only stdin (`| head -8`) is fine.

## When rules pull apart
Order:
1. Data rules (credentials, secrets, company and customer data). A casual request does not override them; if a request would break one, ask once.
2. The user's words in this message. An explicit request counts as approval for that one ask-first action.
3. Ask-first rules.
4. The repo's own guidelines (its CLAUDE.md, CONTRIBUTING, tooling), for committed work.
5. Answer first, then style rules.

## Secrets and the sandbox
- The guards block reads of SSH keys, cloud and git credentials, keychains and `.env` files. Ask the user for only the part you need, for example the variable names.
- In the sandbox, "Operation not permitted" or "token missing from keyring" is a sandbox denial, not a logout. Run the command alone outside the sandbox (it asks the user). Keep `gh auth login` and token files out of it.
- Native Windows has no sandbox: every command asks the user. macOS and Linux: a sandboxed command runs without a question; an escape from the sandbox asks.

## Git
- Work on a branch (`git switch -c feature/...`) and merge by PR. The main-branch guard blocks commits and pushes on `main`; a repo can opt out with `git config claude.allowMain true`.
- Commit or push only when the user asks.

## Python
- One local `.venv` per project with uv: `uv add`, `uv run`. The pip guard blocks `pip install`.
- Tests with pytest in `tests/`; ruff formats and lints.
- For a code change, write a failing test first.

## Token cost
- Answer first. A yes/no or fact question gets the answer in the first line and at most 3 sentences.
- Read only the part of a file you need (offset and limit, or a search) when you know where it is.
- In a repo with `graphify-out/`, answer code and architecture questions with `graphify query`, `graphify path` or `graphify explain` first, then read only the files the graph names.
- Start a subagent only when the user asks for one: each one starts cold and reads the context again.
- When the conversation is long and the old part no longer matters, suggest `/compact`.
- Suggest a lower effort level for simple, mechanical work.
- `/cost` and `/usage` show the spend of this session; the `token-report` skill shows the last 7 days.
