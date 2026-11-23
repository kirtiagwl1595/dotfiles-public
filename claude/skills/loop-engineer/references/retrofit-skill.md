# Retrofit a skill

Use this for `skill <name>`: a skill of an own plugin with an eval case in that plugin's `evals/` folder: `claude/evals/` for safe-lean, and an `evals/` folder in `claude/plugins/writing-skills/` for writing-skills (the first case creates it). The goal is a skill whose behavior an eval shows, improved only where a grader fails (R13).

## Where it runs

- Only in this repo (or a fork that holds the loop engine): the verifier runs `claude/evals/run.sh`.
- Only in the personal profile: confirm refuses a skill target in the work profile, because the eval runs outside the sandbox.

## The eval

1. Find the case: a folder in the plugin's `evals/` whose files name the skill (`loopctl audit` lists it under the skill's `eval`). If there is none, write one in step 3, before confirm, in that `evals/` folder, in the shape of `claude/evals/step-back-on-patches/`: `case.yaml` or `prompt.md`, and `graders/<grader>.md`. After confirm, `evals/**` is protected.
2. In the LOOP.md frontmatter, add `eval_case: <case folder>`.
3. In `.loop/loop-features.json`, write one check for each grader: `{"id": "...", "category": "behavior", "description": "...", "steps": [...], "grader": "<grader file name without .md>", "passes": false}`. A grader check has no `verify`. Shell checks can sit next to it, for example a line count of the SKILL.md.
4. In the skill, add a short `## Verification` section in step 3: the eval case and what it checks. It goes in the setup commit, so the gate does not count it as skill growth.

## How a grader passes

- One verify runs the eval once for all graders: 3 runs, the `with` arm only (`--ablation none`), in a new folder under `.loop/eval/`.
- A grader passes when it passes in 2 of the 3 runs: one run is noisy.
- A run that ended in an error counts as a fail.
- If verify cannot read a new result, it exits 2 and prints no evidence line. A partial result (the cost cap stopped it) is the same. Do not run it again at once: stop, and the Stop hook asks for a new run. If it happens twice in a row, tell the operator.

## Cost: ask first

Each verify costs model calls on the operator's plan. Each verify has a cap of $3 (`EVAL_MAX_USD`), and one verify takes about 2 minutes. Nothing caps the number of verify runs: a loop runs the baseline, one verify for each iteration, and one more each time a verify must run again. In step 4, show the operator the expected cost, `(max_iterations + 2) × $3`, and say that only each verify is capped, not the total. The typed confirm approves that spend. Keep `max_iterations` at 3, and run verify again only when the hook asks. The bundle shows the real spend: `Eval spend` adds up the eval's own `costUsd` over every verify.

## The verifier call

Run `python3 -B .loop/bin/loopctl.py verify` with `dangerouslyDisableSandbox: true` and a Bash timeout of 600000. The eval needs `claude` and the network. The guard allows the flag only for this exact command, only in a personal skill loop.

## Scope

- **may change:** the skill's `SKILL.md`: its description, and the text that a failing grader needs.
- **must not change:** `claude/skills/<other skill>/` for each skill that the change could touch. The eval case and `plugin.json` are protected anyway. The debrief must say: "bump the plugin version when you apply this".
- Do not add text for a grader that already passes. The gate rejects skill text that grows when no check failed at baseline.
