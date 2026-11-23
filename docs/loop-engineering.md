# Loop engineering

A verified improvement loop for one target: a skill, a script or a repo task. The operator starts it, hooks judge each iteration, and nothing leaves the loop branch until the operator approves. Reader: a person who wants to run the loop, or to change it.

## §1 Status and platforms

The loop is part of the `safe-lean` plugin: the hooks in `claude/hooks/`, `claude/loopctl.py`, `claude/loop_gate.py`, the three agents in `claude/agents/` and the skills `loop-engineer`, `loop-audit` and `loop-approve`.

| Platform | Loop |
|---|---|
| macOS, Linux | Supported. |
| WSL2 | Supported. Run Claude Code inside WSL2. |
| Native Windows | Not supported. The loop needs the OS sandbox, and native Windows has none. The loop hooks exit 0 and do nothing, so normal work is never blocked. The loop tests are skipped there. |

Four things the loop does not do: it does not start by itself (C2), it does not push or open a PR, it does not run unattended in the work profile, and it does not change third-party plugin skills.

The loop commands need the `safe-lean` plugin to be installed. `claude plugin list` shows the copy that a session runs. Check that `/hooks` lists `guard_loop.py` and `loop_hook.py` once.

## §2 Terms

| Term | Meaning |
|---|---|
| Operator | The person who runs the loop. |
| Agent | The Claude Code session that runs the loop. |
| Target | The thing the loop improves: a skill, a script, or a repo task. |
| Iteration | One turn of the agent that ends in a Stop. The Stop hook judges it. |
| Check | One entry in `loop-features.json`. It has a shell command, and exit 0 means pass. |
| Verifier | The command `python3 -B .loop/bin/loopctl.py verify`. It runs every check. |
| Evidence | The last stdout line of the verifier (§8.4). A hook records it. |
| Baseline | The evidence for the content at confirm, before any edit. |
| Content | A sha256 over the files the loop can change (§8.4). |
| Protected path | A path the agent must not change during a loop (§13.1). |
| Mirror | A `.loop/` file whose real copy lives in the state file (§7). |
| Seal | The confirm step that stores the real copies and their sha256 values. |
| Work profile | The strict rules. A repo that no rule maps to personal gets them (§16). |
| Personal profile | The rules for a repo that you mapped to personal in `loop-profiles.local.json` (§16). |
| Bundle | `.loop/bundle.md`: the proposal the operator reads before approval. |
| Design doc | This file. |

Verbs: guard_loop **denies**; the Stop hook **blocks** or **allows**; `loop_gate` **rejects** or **warns**.

## §3 Requirements key

### §3.1 Constraints (C)

| ID | Requirement |
|---|---|
| C1 | Propose, then the operator approves. The loop iterates freely only in an isolated git worktree. |
| C2 | Loops start only from a command the operator runs. No SessionStart hooks, `/schedule` or background tasks. |
| C3 | Two profiles: personal and work. An unknown repo uses the work profile. |
| C4 | Cost control is iteration caps, model, effort and context size. Dollar figures are estimates. |

### §3.2 Requirements (R)

| ID | Requirement |
|---|---|
| R1 | Discover the build, test, lint and type commands. Run each once and record the baseline. |
| R2 | One LOOP.md per run: goal, target, loop type, verifier, stop conditions, scope, iteration log. |
| R3 | Stop on success, the iteration cap (default 5), 2 iterations with no gain, a baseline regression, or the usage warning. |
| R4 | Before an edit, name the cause in one sentence and the design decision that allowed it. Fix the class of bug where it starts. |
| R5 | State on disk: `loop-features.json` (category, description, steps, passes) and `loop-progress.md`. |
| R6 | Each iteration starts with: working directory, git log, state files, one unfinished entry, a smoke test. |
| R7 | Unit tests alone do not set `passes` to true. The real run path must pass. |
| R8 | One commit for each kept iteration. Revert an iteration that does not improve or that regresses. |
| R9 | A slop gate on the diff rejects band-aid patterns, weakened checks, and skill text that grows without a failing eval. |
| R10 | During a loop, a PreToolUse hook blocks edits to tests, evals, lint and type config. Changes need operator approval. |
| R11 | A change to more than 3 files or to a public interface needs a design note in the bundle. |
| R12 | A fresh-context subagent gets only the diff, the goal and the cause. It judges the fix, a cheated check, and what breaks next. |
| R13 | Skill retrofit: find or write an eval, take the baseline, add a short Verification section, improve only where an eval fails. |
| R14 | Script retrofit: tests or a dry run first, a linter, record side effects, check each platform that the script supports. |
| R15 | Repo-code loop: use the repo's own commands, keep state in a worktree, add no files of this plugin to that repo. |
| R16 | A read-only audit lists skills, scripts and repo areas with no verifier, ranked by risk, and proposes retrofits. |
| R17 | `loop-profiles.json` maps repos (remote host or owner, or path) to a profile. An unknown repo is work. |
| R18 | Work profile: no unattended runs, no auto mode, no push or PR, no new MCP or fetch without approval, no customer data. |
| R19 | Both profiles: a worktree or branch only, deny rules kept, secret files blocked, a secret scan of each diff, no outside deletes. |
| R20 | A cheaper model for the main loop. The strongest model only for diagnosis and design check. The cheapest for log and test-output subagents. |
| R21 | Filter test output to failures, send verbose commands to a subagent, prefer CLI tools, compact instructions. |
| R22 | An iteration cap in LOOP.md, lower effort for mechanical steps, a pilot before a full run. |
| R23 | Each bundle shows the tokens used and the iterations used. |
| R24 | After each run, route each lesson: repo fact, workflow, deterministic check, mistake, verifier gap. |
| R25 | A debrief: goal, result, causes, changes kept and reverted, rules added, open risks. |

### §3.3 Non-goals

- Native Windows (§1). The loop needs the OS sandbox.
- Unattended, scheduled or headless loops (C2).
- Push, PR or MR creation by the loop.
- Changes to third-party plugin skills. The loop proposes a fork instead.

## §4 Design principles

| Principle | Effect |
|---|---|
| Gates go in hooks, judgment goes in the skill | The hooks own the state, the checks, the commits and the stop. The agent writes causes and edits the target. |
| Evidence, not claims | `passes` comes only from the verifier's evidence line. The agent never declares success (R7). |
| Protect the judges | An agent that can edit its tests can pass them (a known failure of coding agents). So tests, evals and config are protected, a diff gate runs, and a fresh-context reviewer reads the result. |
| One counter of our own | The built-in Stop block cap counts only blocks with no tool call, so the loop keeps its own counters. |
| No command rewriting | A pipe to `tail` hides the exit code, so `loopctl verify` filters the output itself (§10). |

## §5 Shape

```text
operator: /safe-lean:loop-engineer <target>
  skill: profile -> EnterWorktree loop-<slug> -> loopctl discover -> writes .loop/LOOP.md, loop-features.json
operator: /safe-lean:loop-engineer confirm
  UserPromptSubmit hook: create state -> branch loop/<slug> -> commit #0 setup -> copy loopctl to .loop/bin -> seal
  agent: python3 -B .loop/bin/loopctl.py verify  -> PostToolUse hook stores the baseline
  +- iteration N -----------------------------------------------------+
  | routine -> Cause/Decision in loop-progress.md -> edit (guard_loop)  |
  | -> loopctl verify (sandboxed) -> PostToolUse hook stores evidence   |
  | -> the agent stops -> Stop hook: guards -> judge -> commit or revert|
  +---------- block with the routine for iteration N+1 <---------------+
  status bundling -> loopctl bundle -> loop-reviewer -> debrief and lesson -> status done
operator: /safe-lean:loop-approve <slug> -> hook creates feature/loop-<slug>; no push
```

The agent runs the verifier inside the sandbox. A hook records the evidence, and the Stop hook judges it.

## §6 Names

| Thing | Name |
|---|---|
| Slug | The target name in lower case with hyphens, at most 30 characters. `script scripts/deploy.sh` gives `deploy`. `task "<goal>"` gives the first 4 words. |
| Worktree | `.claude/worktrees/loop-<slug>` (EnterWorktree name `loop-<slug>`). |
| Loop branch | `loop/<slug>`. The confirm hook creates it. |
| Approved branch | `feature/loop-<slug>`. The approve hook creates it. |
| Loop folder | `<worktree>/.loop/`. Every git step leaves it out by pathspec. Add `.loop/` to your global ignore file too, so a later `git add -A` does not pick it up. |
| State file | `~/.local/state/claude-safe-lean/loops/<key>.json`. The key is the first 16 hex characters of the sha256 of the worktree's real path. The path ignores `XDG_STATE_HOME`, so it is the same in every session. No settings deny rule names it: while a loop runs, guard_loop denies file-tool and Bash writes to it (§7, §13.1), and the sandbox does not let the agent write outside the worktree. |
| Statuses | `running`, `bundling`, `done`, `stopped`. |
| Verifier | `python3 -B .loop/bin/loopctl.py verify`, run from the worktree root. |
| Operator commands | `/safe-lean:loop-engineer <target>`, `... confirm`, `... allow <path>`, `... stop`, `/safe-lean:loop-audit`, `/safe-lean:loop-approve <slug>`. The UserPromptSubmit hook gets this raw text. |
| Python | Hook code and `loopctl` use Python 3.9 syntax and the standard library only. |

## §7 Trust model

- **Protects against:** the agent's own tool calls that write or fake evidence, state or approvals.
- **Does not protect against:** code under test that fakes an exit code. `loopctl` and that code share one process tree. Three parts detect it instead: Stop row 7, the `loop_gate` rules, and the reviewer.
- **State:** the state file is outside the sandbox write allowlist. guard_loop denies file-tool writes to it. Only hooks write it, with a temp file and a rename.
- **Mirrors:** the state file holds the real copies of `.loop/LOOP.md`, `.loop/loop-features.json` and `.loop/run.json`. The Stop hook restores a mirror that differs (row 5). The sandbox cannot read the state file, so `run.json` carries what `loopctl` needs: `base`, the approved paths, the scope list, the baseline, the scores, the log, the gate result and the token usage. The code that owns the list is `loop_hook.run_view`.
- **No write through a link:** the hooks run outside the sandbox, and the agent can plant a symlink in the worktree. `_loop.atomic_write` writes each mirror through a fresh `mkstemp` file and `os.replace`, so a planted `<name>.tmp` link is never followed and a link at the mirror itself is replaced. With `root`, it refuses (`_loop.Unsafe`) when `.loop` or a folder below the worktree is a symlink. `copy_bin` checks `.loop/bin` the same way before its `rmtree`, and confirm refuses a symlinked `.loop` before it creates the branch. A refused Stop fails open with the reason in its message.
- **Activation:** guard_loop, the Stop hook and the gate opt-outs act only when a state file exists for the worktree. A `.loop/` file alone does not count.
- **Evidence:** the record hook accepts only the exact verifier command, run from the worktree root. It first checks that `.loop/bin` matches `bin_sha`, a sha256 over the name and content of every file in it: an extra `json.py` there would shadow the standard library. guard_loop runs the same check before the command runs.
- **Sandbox flag:** guard_loop denies `dangerouslyDisableSandbox: true` during a loop. The one exception is the exact verifier command for a skill target in the personal profile, because a skill eval needs `claude` and the API.
- **Unsandboxed commands:** guard_loop denies Bash parts that match `sandbox.excludedCommands` (`gh`, `glab`, `forge.sh`) during a loop.
- **Git writes:** only hooks write to git, with `-c core.hooksPath=/dev/null -c commit.gpgsign=false --no-verify`. Each hook first checks that it is on `loop/<slug>` in a linked worktree. guard_loop denies the agent's git writes.
- **Other Stop hooks:** a test gate or lesson gate that you run at Stop should exit 0 while a loop of the session runs (§14.2). The lesson is written in the bundle step (R24).
- **Self-protection:** in a repo that holds the loop engine (this repo, or a fork), these paths are protected: `claude/hooks/**`, `claude/loopctl.py`, `claude/loop_gate.py`, `claude/gitleaks-gate.toml`, `claude/loop-profiles.json`, `claude/.claude-plugin/plugin.json`, `claude/agents/**`. The check is on content (`loop_hook.holds_engine`), so a clone in any folder counts. In every repo, guard_loop also denies writes under the running plugin's own folder (`guard_loop.PLUGIN_ROOT`), installed or a frozen copy.
- **Pilots:** a pilot can run the hooks from a frozen copy of the plugin. Turn the installed `safe-lean` copy off for the pilot, so the hooks do not run twice.

## §8 File formats

### §8.1 `.loop/LOOP.md`

YAML frontmatter, then the spec, then the log.

```text
---
slug: deploy
target_type: script            # skill | script | task
target: scripts/deploy.sh
max_iterations: 3              # default 5
threshold: all                 # all checks pass, or a number of checks
eval_case: step-back-on-patches  # skill targets: the case folder in <plugin>/evals/
---
## Goal            one sentence: the outcome
## Loop type       goal-based, and why
## Verifier        python3 -B .loop/bin/loopctl.py verify; checks in loop-features.json
## Scope           may change: <paths>; must not change: <paths> (added to the protected list)
## Iteration log   (written only by the Stop hook; outside the seal)
```

The profile, `base` and the baseline live in the state file, not in LOOP.md.

The scope line:
- **must not change:** path patterns only, separated by commas (§9). Confirm refuses an entry with a space or a parenthesis, because a note in an entry makes it match no file.
- **may change:** advice for the agent and the reviewer. No hook enforces it.

### §8.2 `.loop/loop-features.json`

A list of checks. Each check has an `id` and exactly one of these:

- `verify`: a shell command; exit 0 passes.
- `grader`: the name of a grader file in `<plugin>/evals/<eval_case>/graders/`. A skill target has one check for each grader.

The case folder sits in the `evals/` folder of an own plugin: `claude/` (safe-lean) or `claude/plugins/writing-skills/` (`_loop.EVAL_HOMES`). The third-party picks in `claude/plugins/` are left out: the eval runs the plugin's code outside the sandbox (§7), and their skills are not ours to change (§3.3). `_loop.eval_case_dirs` finds it, and `verify` runs the eval against the plugin that holds it, because `claude plugin eval` runs one plugin and reads that plugin's own `evals/`.

A check from `discover` has `category: "baseline"`. The confirm hook and `loopctl` refuse a spec that breaks these rules (`_loop.spec_problem`): a check with both fields or neither, a grader check in a loop whose `target_type` is not `skill` (only a skill loop may run its verifier outside the sandbox, §7), a grader check with no `eval_case`, a case name that is not a folder name, a case name that 2 plugins hold, or a grader with no file.

```json
[{"id": "dry-run", "category": "behavior", "description": "...", "steps": ["..."],
  "verify": "bash scripts/deploy.sh --dry-run | grep -q 'would deploy'", "passes": false},
 {"id": "one-rule", "category": "behavior", "grader": "one-rule", "passes": false}]
```

The hook owns `passes`. The agent changes no field.

### §8.3 `.loop/loop-progress.md` and the state file

`loop-progress.md` has one block for each iteration, `## Iteration N`, with one-line `Cause:` and `Decision:` entries. The Stop hook and `loopctl bundle` read it through `_loop.progress_text`, which drops HTML comments, so the template's hint is never read as a cause.

| State group | Fields |
|---|---|
| Identity | `version`, `slug`, `worktree`, `branch`, `session_id`, `profile`, `target_type`, `confirm_time` |
| Sealed copies | `spec_text`, `spec_sha`, `features`, `features_sha`, `bin_sha` |
| Run | `base`, `base_content` (the content at confirm), `baseline` (check id to exit code), `status`, `iteration`, `best`, `no_improve`, `stuck` |
| Judging | `last_judged`, `evidence`, `approved_paths` |
| Flags | `stop_requested`, `bundle_blocks` |
| Report | `log`, `usage` (summed tokens and the message count, §11.4), `usage_stop` (true when the `rate_limits` snapshot was readable at the last Stop) |

### §8.4 Evidence line

```text
LOOP-EVIDENCE v1 {"content": "<sha>", "spec_sha": "...", "features_sha": "...", "checks": [{"id": "...", "exit": 0}], "score": 3, "total": 4, "truncated": false}
```

- **Content:** a sha256 over the tracked and untracked files that git does not ignore, without `.loop/`. Each entry is a path and the sha256 of that file. Computing it only reads files.
- **Tool output:** a verifier run must not change the content. `loopctl` sets `PYTHONDONTWRITEBYTECODE=1` and passes `-p no:cacheprovider` to pytest. The content, the protected-path check and the commit also skip `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `node_modules/` and `claude/evals/results/`.
- **Score:** the number of checks that exit 0.
- **Skill checks:** a grader check passes when its per-run `passed` is true in at least 2 of 3 runs of the `with` arm (`cases[].arms.with[].graders[]`). A run with an `error` counts as a fail. `loopctl` does not read the case score, which hides the trigger grader (`scored: false`).
- **Regression:** a check with exit 0 in the baseline that now fails.

## §9 Path matching

One matcher in `_loop.py` serves every rule.

- It follows gitignore rules on the path relative to the worktree.
- A pattern with no `/` matches the file name at any depth.
- `dir/**` and `dir/` match that folder at any depth. Case does not count.
- The matcher is `_loop.matches`. It does not import the guards, because `.loop/bin` holds only `loopctl.py` and `_loop.py`.
- Examples: `pkg/tests/test_x.py` matches `tests/**` and `test_*`. `sub/conftest.py` matches `conftest.py`. `src/contest.py` matches nothing.

## §10 loopctl contract

`claude/loopctl.py` is copied to `.loop/bin/` at confirm. It reads only `.loop/` files, never the state file. On bad input it prints a message, never a traceback. The skill passes `timeout: 600000` to the Bash tool for `verify` and `discover`, because one eval run takes about 4 minutes.

| Subcommand | What it does | Exit code |
|---|---|---|
| `discover` | Reads the repo CLAUDE.md `## Commands` bullets. A bullet holds one or more parts separated by `·`; each part starts with `Label: `command``, so a later `(options: `x`)` is not a command. It runs only labels that start with Test, Lint, Format or Type. Then reads `pyproject.toml` section headers, `package.json` scripts `test`, `lint` and `typecheck`, and `Makefile` targets `test` and `lint`. Runs each command once (300 s). Writes `.loop/discovery.json`; a skipped command gets `"skipped": "<reason>"`. A failed command gets `outside_reads`: the paths outside the worktree in its "Operation not permitted" lines. These are sandbox denials, for example uv reading the main checkout's `pyproject.toml` from the nested worktree; `discover` prints each one with a pointer to `repo-task.md`. | 0 found; 1 none found; 2 bad input |
| `verify` | Checks the protected paths against `base`, and stops on a change. Runs each `verify` check. If any check has a `grader`, it runs `claude/evals/run.sh --case <eval_case> --ablation none --runs 3 --plugin <plugin that holds the case> --output-dir .loop/eval/<time_ns>` once for all graders (540 s limit, under the 600 s Bash cap). It reads only that new `aggregate-result.json`, so an old result never counts again. The folders stay, so that the bundle can add up the eval spend. It sets `EVAL_MAX_USD=3` unless the operator set it. A timeout of any check kills its whole process group, so no `claude` process keeps running or spending. Prints the failures (40 lines for each check, and a truncated flag), then the evidence line. | 0 every check ran, whatever its result; 2 could not run, and no evidence line: no new result, a partial result, no such case, not 3 runs, or a grader missing from a run. The evidence line carries the results. |
| `status` | Prints the LOOP.md log and the mirror counters. | 0 |
| `bundle` | Writes `.loop/bundle.md` with the sections below. | 0 complete; 1 a section is missing |
| `audit` | Runs from any repo root, with no loop. It runs no command and writes nothing. It prints JSON with 4 keys. **`skills`** lists each tracked `skills/*/SKILL.md`, with `eval` (the case folders under `evals/` that have the skill's name or name it in their files) and `tests` (the test files that name it). Its `verifier` is `"eval"` or null: a test that names a skill checks its text, not what it does. **`scripts`** lists each tracked `*.sh` file and each file with a `#!` line under a `scripts/` folder, but not test or eval files. Each has `tests`, `dry_run` (`--dry-run` or `--check` in the text) and `side_effects` (deletes, downloads, installs, pushes, writes home). Its `verifier` is `"test"` when a test builds the path to the file, else `"dry-run"`, else null. A test that only lists the name runs nothing. **`areas`** lists each top-level folder with its file count, test count and churn. **`commands`** lists the commands that `discover` would run (Test, Lint, Format, Type); audit does not run them. `churn` counts the commits of the last 90 days. The `loop-audit` skill ranks the result. | 0; 2 not at a repo root |

Bundle sections:

- goal and cause
- `git diff --stat base..HEAD`
- the kept and rejected commits
- the `loop_gate` result, with the secret scan (gitleaks with `--no-banner --redact`) and its `secret_scanner` field
- before and after scores
- iterations and tokens: the four token sums and the message count from the state `usage`, and whether the usage stop could fire (`usage_stop`). The count ends at the last Stop before the bundle, because loopctl cannot read the transcripts; the state file keeps the final count. In a skill loop, the eval's `claude` runs write their own transcripts, so the token count misses them: the line `Eval spend` adds up the `costUsd` of each `.loop/eval/*/aggregate-result.json`. An eval that wrote no result is not counted.
- the reviewer answers
- the bundle design note, when required
- the debrief (R25)
- the lesson path

## §11 Stop hook (`loop_hook.py stop`)

The hook is an ordered list of (condition, action) checks. The first match wins. On any exception it exits 0 with the systemMessage "loop hook failed, loop paused": it **fails open**, so a crash never traps a session.

### §11.1 Part 1: guards

| # | Condition | Action | Result |
|---|---|---|---|
| 0 | No state for this worktree, or `session_id` differs | none | allow |
| 0a | `background_tasks` lists a task with status `running` | none; no counter changes | allow. The task's hand-back starts the next turn. |
| 1 | `CLAUDE_LOOP_OFF=1`, or the file `loops/OFF` in the state folder, or `stop_requested` | status `stopped` | allow, with a systemMessage |
| 2 | Status `done` or `stopped` | none | allow |
| 3 | Status `bundling` | If the bundle has every section: status `done`. If not: `bundle_blocks += 1`, and at 3, status `stopped` | allow when done or stopped; otherwise block, naming the missing sections |
| 4 | `stuck` >= 5 | status `bundling` (reason: stuck) | block: build the bundle with the debrief |
| 5 | A mirror differs from the state copy | restore it; `stuck += 1` | block: the loop files belong to the hook |
| 6 | `.loop/bin` differs from `bin_sha` | restore it; `stuck += 1` | block |
| 7 | A protected path differs from `base` and is not in `approved_paths` | `stuck += 1` | block: undo the change to `<path>` |
| 8 | `baseline` is empty | `stuck += 1` | block: run the verifier before any edit |
| 8a | `last_judged` is empty and the content equals `base_content` | set `last_judged`, so the row fires once | block: the routine for iteration 1 |
| 9 | The content equals `last_judged`, or nothing to commit | `iteration += 1`, `no_improve += 1` | go to Part 3 |
| 10 | No `Cause:` and `Decision:` for iteration N | `stuck += 1` | block: write the cause and the decision |
| 11 | No evidence for the current content | `stuck += 1` | block: run the verifier |

### §11.2 Part 2: judge

1. Check that the worktree is on `loop/<slug>`. If not: `stuck += 1`, and block. Commit with `git add -A -- . ':(exclude).loop'`, message `loop(<slug>) #N: <cause>`. If the commit fails: `stuck += 1`, block, and change no score.
2. If a regression exists, or `score <= best`: run `git revert --no-edit HEAD` with the same `-c` options. If the revert fails, set status `bundling` with that reason, so the operator decides. Set `no_improve += 1`. Set `last_judged` to the content after the revert.
3. If not: set `best = score`, set `passes` true for each check that passed, set `no_improve = 0`, and set `last_judged` to the content.
4. In both cases: set `iteration += 1` and `stuck = 0`, and append a log line. The tokens are counted after every Part (§11.4).

### §11.3 Part 3: decide

| # | Condition | Result |
|---|---|---|
| 12 | `score` reaches the threshold | status `bundling`; block: build the bundle |
| 13 | `iteration >= max_iterations`, or `no_improve >= 2`, or usage at the limit (§11.4) | status `bundling` with the reason; block: build the bundle with the debrief |
| 14 | otherwise | block; the reason holds the routine for iteration N+1 and the failed checks |

Each hook message that names the verifier (the confirm context, rows 8, 11 and 14) builds the call with `loop_hook.verify_step`. In a skill loop, it adds `dangerouslyDisableSandbox: true`, because the eval needs `claude` and the network; guard_loop allows the flag only for that exact command (§13.1).

### §11.4 Usage and tokens

- **Usage limit:** hooks do not get `rate_limits`; only the status line input has it. A status line script can write the `rate_limits` object to `rate_limits.json` in the state folder, with a temp file and a rename. The limits are for the whole account, so one file serves every session. Row 13 fires when `five_hour.used_percentage` or `seven_day.used_percentage` is 90 or more. This repo ships no status line script: with no readable file there is no usage stop, and the bundle says so.
- **Tokens:** the hook sums `message.usage` fields `input_tokens`, `output_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens`, and counts the messages. It counts each `message.id` once: one message has a line for each content block. It reads the main transcript (`transcript_path`) and each subagent transcript in `<transcript without .jsonl>/subagents/agent-<id>.jsonl`.
- **When:** at each Stop that starts with status `running` or `bundling`, after Parts 1 to 3, because row 5 compares the mirrors with the state as the last Stop saved it. A done or stopped loop counts no more. The hook sums every line with a `timestamp` at or after `confirm_time` again each time, so a Stop that runs twice adds nothing. Timestamps end in `Z`; Python 3.9 `fromisoformat` needs `+00:00` in its place.
- **Failure:** a main transcript the hook cannot read keeps the last count. A bad line or an unreadable subagent file is skipped.

## §12 Prompt and record hooks

### §12.1 UserPromptSubmit (`loop_hook.py prompt`)

The hook matches only exact text at the start of the prompt.

| Typed text | What the hook does |
|---|---|
| `... loop-engineer confirm` | Requires a linked worktree with `.loop/LOOP.md` and `.loop/loop-features.json`, and no running loop there. Looks up the profile. The work profile refuses `target_type: skill` and the auto, bypass and dontAsk modes. Then: `git switch -c loop/<slug>`; commit `#0: setup` (the tests and checks the skill wrote); set `base`; copy `loopctl.py` and `_loop.py` to `.loop/bin/` and store `bin_sha`; seal the spec and the features; store `session_id` and `confirm_time`; set status `running`. It returns this context: run the verifier for the baseline. |
| `... loop-engineer allow <path>` | Adds the path (relative to the worktree, exact match) to `approved_paths`. |
| `... loop-engineer stop` | Sets `stop_requested`. |
| `/safe-lean:loop-approve <slug>` | Finds the loop by slug among the state files whose worktree has the same main checkout as `cwd`, so it works from the worktree and from the main checkout. Requires status `done` or `stopped`, and no branch `feature/loop-<slug>` yet. Creates `feature/loop-<slug>` at the tip of `loop/<slug>`. Copies `LOOP.md` (with the log), `run.json` (with the final token count) and `.loop/bundle.md` to `<main checkout>/.claude/loop-runs/<date>-<slug>/`, and `.loop/lesson.md` to `<main checkout>/.claude/lessons/<date>-loop-<slug>.md`. Moves the state file to `loops/archive/`. It returns the final tokens and a summary: the goal, the scores before and after, the gate verdict with its `secret_scanner`, the reviewer's `Verdict:` line (or "no verdict line") and the bundle path for the open risks. The hook runs outside the sandbox and reads the worktree's `.loop/bundle.md`; a worktree session often cannot read the main checkout, so the copied bundle may be out of the skill's reach. A refusal changes nothing and, with no slug or a wrong one, names the finished loops. |

A confirm in a worktree whose old state has status `done` or `stopped` first moves that state to `loops/archive/`. `repo_setup.py` adds `.claude/loop-runs/` and `.claude/lessons/` to the managed `.gitignore` block, so these copies are never committed.

### §12.2 Record hook (`loop_hook.py record`)

PostToolUse on Bash. It stores the evidence line of an accepted verifier run (§7). If `baseline` is empty, it stores the evidence for the `base` content as `baseline` and sets `best`. A Bash call that exits non-zero fires only PostToolUseFailure, which carries no stdout. So the verifier exits 0 whenever it ran, and the record hook listens to PostToolUse only.

## §13 guard_loop (PreToolUse)

Outside a loop, guard_loop exits early. It walks up from `cwd` to `.git`, computes the key, and checks for the state file. The target is under 50 ms, with a 10 s timeout in hooks.json. It uses `_common.run_guard`, which fails closed. It acts on Read, Edit, Write, MultiEdit, NotebookEdit, Grep, Glob, WebFetch and Bash. On native Windows it returns at once (§1).

The rules are one ordered table, `guard_loop.RULES`: each row has a profile (both or work), a decision, the tools it applies to and a test. The first hit decides, and every deny comes before every ask. A state with no known profile gets the work rules.

### §13.1 Both profiles

| Rule | What guard_loop denies |
|---|---|
| Baseline first | Edit, Write, MultiEdit and NotebookEdit outside `.loop/loop-progress.md` while `baseline` is empty. |
| Outside the worktree | Every file-tool write and Bash redirect outside the worktree: the main checkout, lessons, the state folder, the home folder. The null devices stay allowed. Bash runs in the sandbox, and the sandbox flag is denied, so other Bash writes cannot leave either. |
| Protected paths | File-tool writes to: `tests/**`, `test_*`, `*_test.*`, `*.test.*`, `conftest.py`, `evals/**`, `ruff.toml`, `pyproject.toml`, `setup.cfg`, `mypy.ini`, `pyrightconfig.json`, `tsconfig*.json`, `.eslintrc*`, `eslint.config.*`, `.shellcheckrc`, `.pre-commit-config.yaml`, `.gitleaks.toml`, `.gitleaksignore`, `.github/workflows/**`, `.loop/LOOP.md`, `.loop/loop-features.json`, `.loop/bin/**`, the state folder, the LOOP.md "must not change" list and the §7 self-protection paths, minus `approved_paths`. |
| Bash git writes | Found with `guard_main_branch.git_writes`, given the loop verb set `guard_loop.LOOP_GIT_VERBS`: `WRITES`, `guard_main_branch.TREE_WRITES` and update-ref. A command that `guard_main_branch.READ_ONLY` matches as a whole (for example `git stash list`) is no write. `git push` is in this set, also as `cd x && git push` and `git -C x push`. Every agent git write is denied. |
| Bash writes to protected paths | Found with `guard_secrets.written` and `path_starts`. These checks only warn early; Stop row 7 and `loop_gate` enforce (R10). |
| Deletes outside the worktree | `rm`, `rmdir`, `mv`, `git clean` and `find -delete` (through `guard_compound.inner_commands`) when the path resolves outside the worktree. A `$` variable in the path counts as outside. |
| Sandbox flag | `dangerouslyDisableSandbox: true`, except the §7 exception. |
| PR and repo creation | `forge.sh pr-create` and `forge.sh repo-create`, also the trusted `forge.sh`. |
| `excludedCommands` | Every Bash part that matches a `sandbox.excludedCommands` pattern (`gh`, `glab`, `forge.sh`), as text or normalized, wherever it stands in the command. The patterns come from the same settings files that `guard_compound.load_rules` reads (`settings_files`). The trusted `forge.sh` passes, so its read-only subcommands (`whoami`, `kind`) still work. |
| Key files | Read, Grep, Glob, Edit, Write, MultiEdit, NotebookEdit and Bash words that name a key file: `*.pem`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `id_rsa*`, `id_ed25519*`, `id_ecdsa*`, `credentials*.json`, `*service-account*.json`, `.npmrc`, `.pypirc`, `.netrc`, `kubeconfig`. The lower-case file name is matched with plain `fnmatch`, so `*.pem` also matches `.deploy.pem`. Bash words and Glob patterns are expanded with `guard_secrets.alternatives` first. A Glob pattern or Grep glob counts by its last part as text: `**/*.pem` hits, `**/*` and a Grep with no glob do not. `*.key` is left out, because Keynote files also use it. |

### §13.2 Work profile (R18)

| Rule | Decision |
|---|---|
| Permission mode | Deny every call that guard_loop sees while `permission_mode` is `auto`, `bypassPermissions`, `dontAsk` or missing. The message is "switch to manual or acceptEdits mode". |
| Machine changes | Deny `claude mcp add`, also after `cd x &&`. |
| Network and installs | Ask before WebFetch, `curl`, `wget`, `git clone`, `uv add`, `npm install`, `npm i` and `brew install`. |

The other outward actions are rules of both profiles: `git push` is a git write, `gh` and `glab` are `excludedCommands`, and PR or repo creation is its own rule. Writes to the main checkout are writes outside the worktree.

### §13.3 guard_private_terms

While a loop runs, `guard_private_terms` also counts the files in the worktree's `.loop/` folder as a personal place, so a term from your private-terms list is blocked there like in a lesson. This covers file-tool writes and Bash redirects. The text of these files travels: `Cause:` lines become commit messages, and approve copies the bundle and the lesson to the main checkout. The target code itself is not a personal place. As for guard_loop, only a state file with an active status turns the rule on.

## §14 hooks.json entries and the opt-out

### §14.1 Entries

Every entry starts through the launcher: `bash "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" <script> [argument]`.

| Event | Matcher | Script | Timeout |
|---|---|---|---|
| PreToolUse | `Read\|Edit\|Write\|MultiEdit\|NotebookEdit\|Grep\|Glob\|WebFetch` | `guard_loop.py` | 10 s |
| PreToolUse | `Bash\|PowerShell` (existing) | `guard_bash.py`, with `guard_loop.check` as the last check | existing |
| PostToolUse | `Bash` | `loop_hook.py record` | 10 s |
| Stop | none | `loop_hook.py stop` | 60 s |
| UserPromptSubmit | none | `loop_hook.py prompt` | 30 s |

### §14.2 Opt-out for other Stop hooks

A Stop hook of your own that runs tests or checks for a lesson can step aside while a loop runs: call `python3 -B <hooks>/_loop.py running "$cwd" "$session_id"`. Exit 0 means a loop of that session runs, so the hook should exit 0. Any other code, a crash included, means the hook runs as before.

## §15 loop_gate.py (diff gate)

`base` is the setup commit #0. The gate reads the whole loop branch: the added lines of `git diff base^..HEAD -- . ':(exclude).loop'`, where `base^` is the fork point. So the setup files and their secrets are judged like the iterations. Two rules read only `base..HEAD`, the iterations: `protected` and `skill-growth`, because the setup adds checks and the skill's `## Verification` text by design. The report `files` lists the whole branch. It prints JSON and a table. Exit codes: 0 pass, 1 reject, 2 bad input.

The Stop hook runs it when the loop enters bundling and stores the report in `.loop/run.json`. It also runs alone: `python3 claude/loop_gate.py --base <sha> --target <path>`.

| Rule | Detects | Verdict |
|---|---|---|
| swallow | Python only: bare `except`, `except Exception`, `except ...: pass`, or a return of a default value. Also `ruff check --select BLE,S110` on the changed files. | reject |
| special-case | A new literal in a comparison, when the same literal is in the repo's test files: a string of 3 or more characters that is not an option (`--dry-run` is the interface the tests call), or a number of 3 or more digits (an ID or a code; small numbers are limits). | reject |
| retry | A new `sleep`, `retry`, or a larger `timeout=` value. | reject |
| marker | `TODO`, `HACK`, `FIXME`, `temporary`, `workaround` in code comments. A comment starts a line or follows a space, so a URL is not one. `*.md` files are exempt. | reject |
| operator | A new `__eq__`, `__ne__`, `__lt__`, `__hash__` or `__bool__`. | reject |
| monkeypatch | A new assignment to `time.`, `random.`, `datetime.`, `os.environ[`, `sys.std*` or `builtins.` in non-test code. | reject |
| duplicate | 6 or more normalized lines that equal a block in another file. | reject |
| protected | An iteration (`base..HEAD`) changed a protected path that is not approved. | reject |
| setup-file | A file in the setup commit that is neither protected (a check) nor the LOOP.md `target`. Example: a shell temp file that `git add -A` staged. Paths come from `git diff --name-only`, so an empty file counts. | reject |
| skill-growth | An iteration made a SKILL.md gain net lines, and no check for that skill failed at the baseline. | reject |
| hard-coded | A new literal path, host or ID in code. | warn; the reviewer decides |
| design | More than 3 changed code files (not counting `*.md` other than SKILL.md, and `docs/**`), or a changed public `def` or CLI flag. | warn; the bundle design note is required |
| secret | `gitleaks git --no-banner --redact --config claude/gitleaks-gate.toml --gitleaks-ignore-path /dev/null --ignore-gitleaks-allow --log-opts base^..<head sha> <git common dir>`. The agent writes the worktree, so the gate trusts none of its gitleaks controls: its own config (the default rules) in place of a repo `.gitleaks.toml`, no `gitleaks:allow` comments, and the git common dir as the scan source, because gitleaks reads `<source>/.gitleaksignore` whatever `-i` says. The range names the head commit, since `HEAD` in the common dir is the main checkout's. A built-in regex set runs on every scan, also when gitleaks is not on `PATH` or exits with a code other than 0 or 1. The report field `secret_scanner` (`gitleaks` or `regex`) says which one ran, so a regex pass does not read as a gitleaks pass. | reject |

Judgment rules go to the reviewer: a rule added for one example, and rules that contradict each other.

## §16 Profiles (R17)

The profile decides how strict a loop is. The personal profile may run a skill target (its eval runs outside the sandbox) and may run in auto mode. The work profile may not. A repo that no rule maps to personal gets the work profile.

- **Tracked file:** `claude/loop-profiles.json` ships empty (`[]`): no repo maps to personal, so every repo starts as work. The plugin updates replace this file, so put your own rules in the local file.
- **Local file:** `~/.config/claude/loop-profiles.local.json` (on WSL2, inside the Linux home folder) holds your rules. It is not tracked. Local rules come first, and the first match wins.
- **Rule shapes:**
  - `{"path": "~/git/my-notes", "profile": "personal"}`: a glob on the repo's real path (the main checkout, not a worktree).
  - `{"remote": "github.com/my-login", "profile": "personal"}`: a remote `host` or `host/owner`.
  - `{"owner": "self", "profile": "personal"}`: every repo that only you can use: no origin, or an origin under your own login (`repo_setup.team_owner`, which asks `forge.sh whoami`). An unknown login counts as a team repo.

Example for a person who wants all of their own repos to be personal:

```json
[{"owner": "self", "profile": "personal"}]
```

Map only repos where you accept the personal rules. A repo under collaboration should stay work.

## §17 Skills and agents

### §17.1 The skill

`claude/skills/loop-engineer/SKILL.md`, under 200 lines. Frontmatter: `disable-model-invocation: true`, `model: sonnet`, `effort: medium`, `argument-hint`. Templates: `claude/templates/loop/` holds `LOOP.md`, `loop-features.json` and `loop-progress.md`. `loopctl bundle` writes the bundle from `_loop.BUNDLE_SECTIONS`, so the bundle has no template. Steps: target type, profile, EnterWorktree, `discover`, the `.loop/` files and setup tests, the request to type `confirm`, the iteration routine, diagnosis, the bundle (with the reviewer), the lesson, and the learning routing. It points to step-back, staff-engineer, a test-first workflow and the evals. It does not copy them.

### §17.2 Agents and the other skills

The 3 agents are in `claude/agents/`; the `loop-engineer` skill starts them as `safe-lean:<name>`. `tests/test_loop_agents.py` checks each agent file against its row: the model alias, the tools and the preloaded skills.

| Item | Model | Tools | Job |
|---|---|---|---|
| `loop-audit` skill | none set | read-only | Runs `loopctl audit`, ranks by risk, writes `.claude/audits/YYYY-MM-DD-loop.md`, links the latest slop audit. |
| `loop-approve` skill | none set | none | Shows the bundle. The typed command is the approval. |
| `loop-reviewer` agent | Opus | Read, Grep, Glob | Preloads `safe-lean:step-back`. Answers the 3 R12 questions once for each bundle. |
| `loop-diagnoser` agent | Opus | Read, Grep, Glob | Runs at the start, and after an iteration with no gain. |
| `loop-log-reader` agent | Haiku | Bash, Read, Grep | Runs a verbose command and returns only the failures. |

- **Inputs:** each agent gets only what its row needs, in the prompt. The reviewer gets the goal, the causes, the diff and the worktree path, not the session. The diagnoser also gets the failed checks and their verify output.
- **Guards:** a plugin agent ignores the `hooks`, `mcpServers` and `permissionMode` frontmatter fields. Its Bash runs in the sandbox. PreToolUse and PostToolUse fire for a subagent's tool calls, and PreToolUse carries the parent's `permission_mode`. So in a work loop in acceptEdits mode, guard_loop sees the mode for each agent call and does not deny it for a missing mode (§13.2). The log reader never runs the verifier: the main agent runs it, so that the record hook stores the evidence.
- **Not verified:** that `skills: [safe-lean:step-back]` preloads the skill under its plugin name. Before the first work loop, start the reviewer once and ask it to quote the first step-back rule from its context without Read.

The `loop-engineer` skill has 5 reference files in its `references/` folder, one for each target type and bundle step: `retrofit-skill.md`, `retrofit-script.md`, `repo-task.md`, `review-brief.md`, `learning.md`.

## §18 Behaviors of Claude Code that the design relies on

These were checked by probes. Re-check one when a Claude Code release changes hooks.

| Behavior | Effect on the design |
|---|---|
| UserPromptSubmit gets the raw slash text for a `disable-model-invocation` skill. | The confirm, allow and stop commands work as typed text (§12.1). |
| On exit 0 PostToolUse fires and holds stdout. On exit 1 only PostToolUseFailure fires, with no stdout. | `verify` exits 0 whenever it ran (§10, §12.2). |
| The status line input has `rate_limits`; hook inputs do not. | The usage stop reads a snapshot file (§11.4). |
| Subagent transcripts are in `<transcript without .jsonl>/subagents/agent-<id>.jsonl`, with the same usage fields. | The token count (§11.4). |
| EnterWorktree creates the branch `worktree-<name>`. | The confirm hook switches to `loop/<slug>`. |
| PreToolUse fires for a subagent's tool calls and carries the parent's `permission_mode`. | Work-loop rules work for agents (§17.2). |
| A background subagent makes Stop fire with that task in `background_tasks`. | Stop row 0a. |
| A subagent report comes back as a UserPromptSubmit whose prompt starts with `<agent-message`. | The prompt hook ignores it: it matches only the operator commands. |

## §19 Risks

| # | Risk | Effect | Mitigation |
|---|---|---|---|
| 1 | Code under test fakes an exit code | A false pass | Stop row 7, `loop_gate` and the reviewer |
| 2 | The skill verifier runs outside the sandbox with `--trust-plugin` | Plugin code runs unsandboxed | The protected-path check runs first; personal profile only |
| 3 | Hook commits on `loop/<slug>` are not signed | Unsigned commits on the loop branch | The operator's merge or squash commit is signed |
| 4 | A work loop needs manual or acceptEdits mode | Many permission prompts | acceptEdits allows edits in the worktree without a prompt |
| 5 | An import error in guard_loop | Bash is blocked in every session (guard_bash fails closed) | An import test and a byte-compile test |
| 6 | A guard that times out does not block | A loop rule is skipped | Early exit under 50 ms; 10 s timeout |
| 7 | Two `safe-lean` copies during a pilot | Hooks run twice | Disable the installed copy; check `/hooks` |
| 8 | Eval usage | A skill eval costs model calls: about $3 for each verify run | A 3-iteration cap; ask before the eval runs |
| 9 | The file tools can write `.git/hooks` and maybe `.git/config` (for example `core.fsmonitor`) | Unsandboxed git runs code the agent chose | `settings.base.json` denies both below `~/git`; `repo_setup.py protect` writes the same rules for a repo elsewhere (the `setup-repo` skill runs it). Open: a repo elsewhere until `setup-repo` ran there, the hooks of submodules (`.git/modules/`), and bare repos |
| 10 | A skill eval grades the harness instead of the skill | A check that no skill text can pass, or an unstable one | Read the judge's evidence at the baseline. Fix the harness in a separate change |
| 11 | `sandbox.excludedCommands` (`gh`, `glab`, `forge.sh`) run outside the sandbox | The sandbox does not bind them. guard_loop denies them during a loop, but a hard link or a git call inside a script can still pass | Review before each merge |
| 12 | Code in a worktree runs outside the sandbox when the operator approves a commit, a push (pre-push CI) or a skill verify | Unsandboxed code | The operator reads the diff before the approval |
| 13 | The shared `.git` stays writable (all but `config` and `hooks/`), because worktrees need it | A change there passes no PR review | Review before each merge and pull |
