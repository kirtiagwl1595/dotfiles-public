---
name: loop-engineer
description: Runs a verified improvement loop on one target (a script, a skill, a repo task) in an isolated worktree. Hooks judge each iteration from verifier evidence, commit or revert, and stop on success, the cap or no gain; the operator approves a bundle. Use when the user types /safe-lean:loop-engineer.
disable-model-invocation: true
model: sonnet
effort: medium
argument-hint: "script <path> | skill <name> | task \"<goal>\" | confirm | allow <path> | stop"
---

# Loop engineer

You run one loop on one target. The hooks own the state, the checks, the commits and the stop. You write the cause, edit the target, and run the verifier. Design: `docs/loop-engineering.md` in this repo.

**Platform:** the loop needs the OS sandbox. It runs on macOS, Linux and WSL2. On native Windows the loop hooks do nothing and exit 0, so normal work is never blocked, and `/safe-lean:loop-engineer` cannot start a loop there. Use WSL2.

Never edit tests, evals, lint or type config, or `.loop/LOOP.md`, `.loop/loop-features.json`, `.loop/run.json`, `.loop/bin/`. Never write outside the worktree; scratch files go in `.loop/tmp/`. Never run git writes. Never leave the sandbox. The guard denies these; do not work around a denial. If a check looks wrong, say so in the debrief.

## 0. Which form was typed

- `confirm`, `allow <path>` or `stop`: the loop hook already acted, and its message is in your context. After a confirm, go to step 5. After a refusal, show the reason to the operator and stop.
- `script <path>`, `skill <name>` or `task "<goal>"`: start at step 1.

## 1. Target and slug

- **script:** a file with side effects. Read `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineer/references/retrofit-script.md`.
- **skill:** a skill of an own plugin (safe-lean or writing-skills), checked by its eval; only in this repo (or a fork that holds the loop engine) and only in the personal profile. Read `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineer/references/retrofit-skill.md`.
- **task:** a goal in this repo. Read `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineer/references/repo-task.md`.
- **Slug:** the target name in lower case with hyphens, at most 30 characters. A script uses its file name without the extension; a task uses the first 4 words.

## 2. Worktree

Use the EnterWorktree tool with the name `loop-<slug>`. Every later step runs in that worktree.

## 3. Discover, then write the spec

1. Copy the files: `mkdir -p .loop`, then copy `${CLAUDE_PLUGIN_ROOT}/templates/loop/LOOP.md`, `loop-features.json` and `loop-progress.md` into `.loop/`.
2. Run `python3 -B "${CLAUDE_PLUGIN_ROOT}/loopctl.py" discover` with a Bash timeout of 600000. It runs the repo's Test, Lint, Format and Type commands once and writes `.loop/discovery.json`. If it prints "the sandbox denied a read outside the worktree", stop and give the operator the choices in `repo-task.md`, "Reads outside the worktree". Write no check before the operator chooses.
3. Fill `.loop/LOOP.md`: the slug, `target_type`, `target`, the goal (one sentence: the business outcome), the scope (`may change` is advice; `must not change` takes path patterns only, such as `tests/` or `uv.lock`, and confirm refuses a note in it). Keep `max_iterations` at 3 for a pilot, 5 at most otherwise.
4. Fill `.loop/loop-features.json`: one check for each behavior of the real run path, and `baseline` checks from the discovered commands that passed. Each `verify` is a shell command that exits 0 on a pass; a skill loop uses `grader` checks instead (`retrofit-skill.md`). A unit test alone is not a check of the real path. Scope each baseline check to the target (one test file, one linted file): each check has 300 s, and the whole verify run must end inside the 600 s Bash limit. A full suite that takes minutes goes in the debrief as "run before merge", not in the checks.
5. Write the tests, eval cases and checks that the reference for your target type names now: the setup commit holds them, so the operator approves them with the typed confirm. During the loop they are protected.

## 4. Ask the operator to confirm

Show the operator the goal, the checks and the scope in a short table. In a skill loop, also show the expected cost (`retrofit-skill.md`, Cost): the typed confirm approves that spend. Then say:
- "Type `/safe-lean:loop-engineer confirm` to start."
- In the work profile (any repo that `loop-profiles.json` does not map to personal): "First switch to manual or acceptEdits mode (Shift+Tab). The confirm refuses auto mode."

Then stop. Do not continue until the confirm.

## 5. Baseline

Run `python3 -B .loop/bin/loopctl.py verify` from the worktree root, with a Bash timeout of 600000, in the foreground: never with `run_in_background`. In a skill loop, every verify run also needs `dangerouslyDisableSandbox: true`: the eval needs `claude` and the network. A background run gives the record hook no output, so no evidence is stored. Do not edit any file before it. Then stop: the Stop hook answers with the routine for iteration 1.

Before the first edit of iteration 1, start the `safe-lean:loop-diagnoser` agent. Give it the target, the worktree path, each failed check with its `verify` command and its verify output. Use its most likely cause in step 6.3.

## 6. Each iteration

The Stop hook gives you the routine. Follow it in order:

1. Run `pwd` and `git log --oneline -5`. Read `.loop/loop-progress.md` and `python3 -B .loop/bin/loopctl.py status`.
2. Pick one failed check. Run a smoke test of the target.
3. Find the cause. Use `safe-lean:step-back` thinking: fix the class of bug where it starts, not the one input.
4. In `.loop/loop-progress.md`, write `## Iteration N` with one line `Cause:` (the cause, and the design decision that allowed it) and one line `Decision:`.
5. Edit the target.
6. Run the verifier, then stop. The Stop hook commits a gain and reverts a change with no gain or a regression.

If a protected file must change, do not change it. Tell the operator the path and why; the operator can type `/safe-lean:loop-engineer allow <path>`.

After an iteration with no gain, step back before the next one: start `safe-lean:loop-diagnoser` again, with the earlier `Cause:` and `Decision:` lines too, and name a different cause, not a second patch.

A command with long output (a full test suite, a build log): give it to the `safe-lean:loop-log-reader` agent, which returns only the failures. Never give it the verifier: you run the verifier yourself, so that the hook records its evidence.

## 7. Bundle

When the Stop hook says the loop ends:

1. Run `python3 -B .loop/bin/loopctl.py bundle`. It writes `.loop/bundle.md` and names the sections to fill.
2. **Reviewer answers:** start the `safe-lean:loop-reviewer` agent once, with the brief in `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineer/references/review-brief.md`. It answers 3 questions: is it a root-cause fix or a patch; did a change cheat a check; what breaks next. Copy its answers and its verdict line into the section.
3. **Debrief and lesson:** follow `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineer/references/learning.md`. The debrief covers the goal, result, causes, changes kept and reverted, rules added and open risks, and routes each finding. The lesson goes to `.loop/lesson.md`; `/safe-lean:loop-approve` copies it to the main checkout's `.claude/lessons/`.
4. Replace each `<!-- fill -->` marker, then stop. The Stop hook sets the loop to done when every section is complete.

## 8. Report

Tell the operator: the result, the before and after scores, the iterations, the bundle path. The operator reads the bundle and decides. To accept it, the operator types `/safe-lean:loop-approve <slug>`. Do not push, merge or open a PR.
