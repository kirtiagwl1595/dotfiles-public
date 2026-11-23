# A task in a repo

Use this for `task "<goal>"`: a change in any repo, with that repo's own commands (R15).

## The repo's own commands

- `loopctl discover` reads the repo's CLAUDE.md `## Commands` lines, `pyproject.toml`, `package.json` and `Makefile`. It runs each Test, Lint, Format and Type command once and writes `.loop/discovery.json`.
- Use only those commands in the checks. Add no files, configs or scripts of this plugin to the repo. The `.loop/` folder never enters a commit: the hooks leave it out.
- If `discover` finds nothing, ask the operator for the test command. Do not guess one.

## The checks

- **Behavior:** one check for each part of the goal, on the real path: a command, a CLI call, or a test you write in step 3 that calls the public entry point. Name the test id in `verify`, so that one check runs one test.
- **Baseline:** each discovered command that passed, scoped to the files the goal touches. A full suite that takes minutes goes in the debrief as "run before merge".
- Write the goal as the outcome for the people who use the repo, in one sentence.

## Reads outside the worktree

The loop worktree lies inside the repo, under `.claude/worktrees/`. A tool that searches parent folders reads the main checkout. uv does this: it looks for a workspace root, finds the main checkout's `pyproject.toml`, and the sandbox denies the read. The command exits 2 in under a second, and no test runs. `discover` prints each denied path outside the worktree and records it as `outside_reads` in `.loop/discovery.json`.

Stop, and give the operator these choices:

| Choice | Effect |
|---|---|
| Allow sandbox reads of the main checkout (`/sandbox`) | The commands run. The loop can then also read the main checkout's untracked files, such as data folders. The hooks commit only the worktree. |
| No loop for this repo | Nothing changes. |

Do not run the command outside the sandbox: a check must run where the loop runs.

## Work profile

A repo under collaboration gets the work profile:

- The operator must switch to manual or acceptEdits mode before confirm.
- A network call or an install asks first. `claude mcp add` is denied.
- No customer names, customer data, credentials or internal URLs in `.loop/LOOP.md`, the progress file, the bundle or the lesson. These files leave the worktree when the operator approves.
- The repo's tracked CLAUDE.md belongs to the team. Put a proposed CLAUDE.md change in the debrief, not in the repo.

## Scope

- **may change:** the files the goal needs, and the docs that describe them.
- **must not change:** CI files and `pyproject.toml` are protected anyway. Add lock files and generated files: the guard does not know them. Write path patterns only (`uv.lock`, `src/gen/`); put a reason in the goal, not in the list.
