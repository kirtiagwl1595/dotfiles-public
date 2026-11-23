---
title: "Claude Code setup: user guide"
---

How to work with this setup after the install: where files go, how Claude Code finds its rules, what the guards block, which skills you have, and which habits save tokens.
For the install steps and the failure table, read the [README](README.md). For the design reasons, read [docs/decisions.md](docs/decisions.md). For setup notes and sandbox gotchas, read [docs/SETUP.md](docs/SETUP.md). For the loop engine, read [docs/loop-engineering.md](docs/loop-engineering.md).

This guide has a web version, `docs/guide.html`. Rebuild it with `docs/build.sh` (needs `pandoc`; on Windows, run it in Git Bash).

Which OS: every command below works on macOS, Linux and Windows, unless a line says otherwise. Three things are not for native Windows: zsh (use the PowerShell profile there), the sandbox, and the loop engine. WSL2 has all three: install Claude Code inside WSL2 to use them. On Windows, use PowerShell or Git Bash for the terminal commands.

# 1. Your folders

```
~ (home)             Windows: %USERPROFILE%
├── git/                       all your code (a suggestion, not a rule)
│   ├── dotfiles-public/       this repo (your clone)
│   ├── <project>/             one repo = one project = one .venv
│   └── _external/             other people's repos, read only
├── .claude/                   Claude Code, user level
│   ├── CLAUDE.md              your rules, plus the import lines from this repo
│   ├── settings.json          your settings, plus the safe values from this repo
│   └── plugins/               the safe-lean plugin and any optional plugin
└── .config/claude/            small switch files for opt-in hooks, your private-terms list, loop profiles
```

| Rule | Why |
|---|---|
| Keep code in one folder, for example `~/git/<project>` | One place to search and back up |
| One project = one git repo = one `.venv` | No clash between package versions |
| Keep your clone of this repo in place | `~/.claude/CLAUDE.md` imports files from it by path. If you move it, run the install again. |
| Never commit `.env` files, keys or raw data | `git/gitignore_global` blocks `.env`, `.venv/`, `CLAUDE.local.md` and `.claude/lessons/` in every repo |
| Notebooks explore, `src/` keeps | When notebook code works, move it to `src/` with a test |

# 2. Install, update, undo

| Task | macOS, Linux, Git Bash | Windows PowerShell or Command Prompt |
|---|---|---|
| See what would change | `./install.sh --check` | `.\install.cmd --check` |
| Install | `./install.sh` | `.\install.cmd` |
| Update after a `git pull` | `./install.sh`, then restart Claude Code | `.\install.cmd`, then restart Claude Code |
| Run one step | `./install.sh --only <step>` | `.\install.cmd --only <step>` |
| Run `install.py` yourself | `python3 install.py --check` | `py install.py --check` |

`install.py` asks before each change, saves a `<file>.bak` copy first, and never removes your own values. Running it again changes nothing that is done. The options:

| Option | Does |
|---|---|
| `--check` | Shows what would change. Changes nothing. |
| `--only STEP` | Runs one step. You can repeat it. |
| `--skip-plugin` | Does not run `claude plugin ...` |
| `--skip-tools` | Only reports the tools. Does not install them or change PATH. |
| `--profile NAME` | Package profile. Skips the menu. |
| `--manager brew\|apt\|winget` | Picks the package manager |
| `--yes-packages` | Answers yes to each package group |

The steps:

| Step | What it does | OS |
|---|---|---|
| `tools` | Checks `git`, `claude`, Git Bash and the sandbox tools; offers to install one | all |
| `rules` | Adds the import lines to `~/.claude/CLAUDE.md` | all |
| `settings` | Merges the safe settings into `~/.claude/settings.json` | all (the sandbox file: macOS and Linux) |
| `git` | Includes `git/config.shared` in `~/.gitconfig` | all |
| `plugin` | Installs or updates the `safe-lean` plugin | all |
| `delta` | Offers `git/config.delta` (the `delta` git pager) | all |
| `shell` | A zsh block in `~/.zshrc` and `~/.zprofile`; vim, starship and editorconfig; on Windows, the PowerShell profile | zsh: macOS, Linux; profile: Windows |
| `statusline` | Offers `claude/statusline.sh` as your status line | all (needs `jq`) |
| `templates` | Offers the `CLAUDE.about-me.example.md` and `CLAUDE.profile.example.md` copies in `~/.claude` | all |
| `macos` | Runs `scripts/macos-defaults.sh` after a question | macOS only |
| `packages` | The package menu (section 4) | all |

Details and the undo steps: [README](README.md).

# 3. Where Claude Code reads its instructions

Claude Code reads all these files and joins them. They add up; they do not replace each other.

```
 Managed policy (IT, if any)   cannot be overridden
        │
 You, every project            ~/.claude/CLAUDE.md
        │                        ├── @<clone>/claude/CLAUDE.md        shared rules (from this repo)
        │                        ├── @<clone>/claude/CLAUDE.style.md  writing style (from this repo)
        │                        ├── @~/.claude/CLAUDE.about-me.md    optional: about you
        │                        └── @~/.claude/CLAUDE.profile.md     optional: about this computer
        │                        your own text goes below these lines
 This project, the team        <project>/CLAUDE.md      in git
        │
 This project, only you        <project>/CLAUDE.local.md   not in git
        │
 A sub-folder                  <project>/src/api/CLAUDE.md   loads when Claude works there
```

The two optional files come from the templates `claude/CLAUDE.about-me.example.md` and `claude/CLAUDE.profile.example.md`. The `templates` step copies each one to `~/.claude`. Fill in the `<placeholder>` values, then add the `@` import line to `~/.claude/CLAUDE.md`. The step never replaces a file you have.

| You want Claude to know | Put it in |
|---|---|
| A rule for every project on your machine | Your own text in `~/.claude/CLAUDE.md`, below the import lines |
| Something about you | `~/.claude/CLAUDE.about-me.md` |
| Something about this computer (OS, shell, package manager) | `~/.claude/CLAUDE.profile.md` |
| How to run, test and lint one project | That project's `CLAUDE.md` |
| A private note for one project, or your rules for a team repo | That project's `CLAUDE.local.md` (the global gitignore keeps it out of git) |
| A rule for one folder | `src/api/CLAUDE.md`, or `.claude/rules/api.md` with a `paths:` line |
| Lessons that Claude writes for you | `.claude/lessons/` in the repo (never in git) |

Commands and tips:

- `/init` writes a first `CLAUDE.md` for a project by reading the code. Edit it after.
- `/memory` shows which files are loaded and opens them. It also turns auto memory on or off.
- A line `@path/to/file` inside a CLAUDE.md imports that file.
- Keep each CLAUDE.md under about 200 lines. Short and specific rules work best.
- Settings stack the same way: `~/.claude/settings.json` (you), `.claude/settings.json` (project, in git), `.claude/settings.local.json` (project, only you).
- Instructions are advice. A guard (section 6) blocks what must never happen.

# 4. Packages and shell

## Packages

`packages/packages.json` is one list of tools. Each package has a `brew`, an `apt` and a `winget` name, or a note when an OS has none.

| Profile | Groups | brew | apt | winget |
|---|---|---|---|---|
| `minimal` | essentials | 5 | 3 | 5 |
| `developer` | + core-cli, shell, dev-checks, data-utils, fonts | 30 | 19 | 25 |
| `full` | + utilities, apps | 44 | 25 | 34 |
| `work` | `developer` + work-extras | 31 | 19 | 26 |

1. Run `./install.sh --only packages` (Windows: `.\install.cmd --only packages`).
2. Pick a profile by number. `0` skips.
3. Answer `y` or `N` for each group. Nothing installs before your `y`.

Run `python3 install.py --only packages --check` (Windows: `py install.py --only packages --check`) to see the plan only.

| Command | Does |
|---|---|
| `python3 install.py pkg add <name>` | Installs one package and records it as a trial |
| `python3 install.py pkg keep <name>` | Moves a trial into your own list |
| `python3 install.py pkg list` | Shows trials and kept packages |
| `python3 install.py pkg brewfile <profile>` | Prints a Brewfile for `brew bundle` |
| `python3 install.py pkg names` | Prints the names of one manager, for scripts |

Your trial list and your own list (`packages/trials.json`, `packages/local.json`) stay out of git. On Windows, use `py install.py pkg ...`. Some `apt` and `winget` names are not checked on a real machine: `scripts/check-package-names.sh brew|apt|winget` reports a name that the manager does not know (macOS, Linux, Git Bash).

## Shell: macOS and Linux (zsh)

The `shell` step adds a block `# >>> dotfiles-public zsh >>>` to `~/.zshrc` and `~/.zprofile`. The block loads `shell/zsh/` from your clone. Your own lines stay. Every tool is optional: a missing tool skips its lines. Put your own extra lines in `~/.zshrc.local`.

| Type | Does |
|---|---|
| `z <part of a folder name>` | Jumps to a folder that you used before (zoxide) |
| Ctrl+R, Ctrl+T | Fuzzy search of your history and of files (fzf) |
| `ll`, `la`, `lt` | Better `ls`: list, with hidden files, as a tree (eza) |
| `cat` | `bat`: colours and line numbers |
| `lg` | `lazygit`, git in a terminal UI |
| `gs` | `git status -sb` |
| `py`, `act`, `venv` | `uv run python`, activate `.venv`, make a `.venv` |
| `newproj <dir>` | A new uv project with a Jupyter kernel |
| `cw <task>` | Claude in its own git worktree and branch (parallel agents) |
| `pkgadd`, `pkgkeep`, `pkgtrials` | Shortcuts for `install.py pkg add`, `keep` and `list` |
| `brewup`, `update_all` | Update Homebrew; update the OS, Homebrew and uv tools |
| `mkcd <folder>`, `extract <file>` | Make a folder and enter it; unpack any archive |

`scripts/bench-shell.sh` times your login shell (`zsh -il -c exit`) and prints the median.

## Shell: Windows (PowerShell)

The `shell` step copies `shell/powershell/Microsoft.PowerShell_profile.ps1` to the path that PowerShell reports in `$PROFILE`. It has the same ideas as the zsh block: `..`, `mkcd`, `gs`, `py`, `act`, `venv`, Up and Down history search, listing aliases, and `z` and the starship prompt when those tools exist. Put your own lines in `$HOME\.profile.local.ps1`.

## Git defaults

`git/config.shared` gives you: first branch `main`, rebase on pull, prune on fetch, a first `git push` that sets the upstream, and the aliases `git st` (short status), `git lg` (graph of the last 20 commits), `git last` (last commit with files) and `git unstage <file>` (undo `git add`). It sets no name, email or signing key. The `delta` step adds `git/config.delta` (colours and line numbers in diffs).

# 5. Start a project

Ask Claude: "start a new project called churn-model" (the `new-project` skill). It makes the folder, the uv project and `.venv`, a Jupyter kernel, the project template, the tests and the first commit. It asks before it creates a private repo on GitHub or GitLab.

By hand, the same on all three OS:

1. `mkdir ~/git/churn-model`, then `cd ~/git/churn-model`, then `git init`. (This works in bash, zsh and PowerShell.)
2. `uv init`, then `uv add pandas`. `uv` makes the `.venv`. In zsh, `newproj ~/git/churn-model` does steps 1 and 2 and adds a Jupyter kernel.
3. `claude`, then type `/setup-repo`.

Install `uv` if you have none: it is in the `essentials` group of the packages for `brew` and `winget` (macOS `brew install uv`, Windows `winget install --id astral-sh.uv -e`). On Linux, use `brew` or the installer on the uv documentation page: `apt` has no `uv`.

The project template (`claude/templates/project/`) gives:

```
<project>/
├── CLAUDE.md                 project rules for Claude
├── .claude/settings.json     project permissions
├── .github/                  pull request template
├── .pre-commit-config.yaml   ruff runs before each commit
├── pyproject.toml, uv.lock   packages (uv add ...)
├── src/                      code that is kept
├── tests/                    pytest, with a smoke test
├── evals/                    golden examples (section 14)
├── notebooks/                Jupyter
├── data/raw/                 input data (never committed)
└── docs/                     doc rules, decisions.md, tests/test_docs.py
```

The daily loop:

```
git switch -c feature/clean-data     1. branch (never work on main)
uv add pandas                        2. packages: uv add, never pip install
uv run pytest -q                     3. test
git commit -am "Clean the data"      4. commit
git push -u origin HEAD              5. push (Claude asks you first)
                                     6. open the PR (GitHub) or MR (GitLab)
```

`gh pr create` opens a PR on GitHub. `glab mr create` opens an MR on GitLab. The `setup-repo` skill uses `claude/forge.sh pr-create`, which picks `gh` or `glab` from the `origin` remote.

# 6. What the guards do for you

These guards run on every OS. They start through `claude/hooks/py.sh`, which finds a working Python 3.9 or later. Without one, a guard blocks the tool call; it never fails open.

| When Claude... | Guard | Result |
|---|---|---|
| runs any Bash or PowerShell command | `guard_bash` | Runs the Bash checks below in one process |
| runs `pip install` | `guard_pip` | Blocked. Says "use `uv add`". |
| commits, pushes or merges on `main` | `guard_main_branch` | Blocked. Says "make a branch". |
| reads or writes SSH keys, cloud or git credentials, keychains, `.env` files or `~/Documents` | `guard_secrets` | Blocked |
| chains commands (`a && b`, `$(...)`, `bash -c`) | `guard_compound` | Checks each part against the ask and deny rules. Outside the sandbox, denies a chain of steps that are not all allowed. |
| writes a term from your own list into lessons, Claude memory or a `dotfiles` repo | `guard_private_terms` | Blocked. The list is `~/.config/claude/private-terms.txt`, one term per line. No file: no effect. |
| runs a loop (section 11) | `guard_loop` | Denies writes outside the loop worktree, edits of tests and checks, agent git writes and PR creation. Acts only while a loop runs. |

Opt out of the main-branch guard for one repo: `git config claude.allowMain true`.

The deny rules also stop Claude's file tools from editing `.git/config` and `.git/hooks/`, in the current project and in every repo below `~/git`. A Git hook runs code on each commit, so this keeps Claude from planting one. `/setup-repo` writes the same rule for a repo in another folder (section 9).

What each guard matches in detail: [README](README.md), section "What each guard blocks".

## Permission modes

| Where the command runs | What happens |
|---|---|
| macOS, Linux: inside the sandbox | Runs with no question |
| macOS, Linux: outside the sandbox | Claude asks you |
| Windows, default mode | Claude asks you for every command (no sandbox) |
| Any OS: a command that matches an ask rule (`git push`, `rm`, `gh pr create`, `winget install`) | Claude asks you |
| Any OS: a command that a guard or a deny rule blocks | Claude cannot run it |

Press Shift+Tab to change the mode: default, accept edits, plan mode and auto mode. Bypass mode is off. Each session starts in default mode.

In auto mode, a classifier decides instead of you. Deny rules and guards still apply. On Windows, nothing else stands between Claude and the shell: use auto mode with care.

# 7. Hooks that advise or that you switch on

The advisory hooks start with `py.sh --advisory`: with no Python they do nothing, so they never block your prompts.

| Hook | What it does | On by default |
|---|---|---|
| `coach_prompt` | A one-line tip when a prompt says "just quickly" or is very long, or when a disabled plugin of this repo fits your prompt | yes |
| `churn_watch` | Says when one file was edited many times in a session (a sign of patch-on-patch code); points to `/step-back` | yes |
| `after_python_edit` | Runs `ruff format` and `ruff check` on an edited `.py` file, when `ruff` is installed | yes |
| `graphify_hint` | Points Claude to `graphify-out/` when a repo has a code graph | yes |
| `notify` | A desktop note when Claude finishes or waits (macOS, Linux `notify-send`, Windows toast) | yes |
| `test_gate` | Runs the repo's tests when Claude says it is done and `.py` files changed. It runs outside the sandbox. | no: create `~/.config/claude/test-gate` |
| `lesson_gate` | Asks once for a lesson file in `.claude/lessons/` after real work | no: create `~/.config/claude/lesson-gate` |
| `guard_live_checkout` | Blocks edits and file-changing git in a clone that you name as "live" | no: list the folder in `~/.config/claude/live-checkout.txt` |
| `guard_egm` | Asks before an EGM reviewer agent starts outside a run that you began. Acts only when an EGM plugin is installed. | yes |

An empty file is enough for `test-gate` and `lesson-gate`. To turn one off, delete the file. Windows: the folder is `%USERPROFILE%\.config\claude`.

`guard_live_checkout` is for a clone that you use as the live copy of your config. Claude then works in a worktree of that clone (`.claude/worktrees/`), and you deploy by merge and pull.

# 8. Skills and plugins

## Skills in `safe-lean`

| Skill | What it does |
|---|---|
| `/setup-repo` | Makes the current repo Claude-forward on branch `chore/claude-forward`. Asks before push and PR. A team repo gets only local, ignored files. |
| `/new-project` | A new Python project (section 5) |
| `/token-report` | Your Claude Code token use and cost: today, the last 7 days, and each session |
| `/staff-engineer` | For a feature or a multi-file change: read first, two options, the tests, the failure modes, then code |
| `/step-back` | Stops patch-on-patch code: writes one general rule, rewrites to it, deletes the patches, folds the tests into one table |
| `/slop-audit` | Audits an existing repo for patch-on-patch code and slop; ranks the hot spots; fixes only the findings you pick |
| `/rdf-check` | Validates RDF files and runs SPARQL with Apache Jena. Install Jena: `scripts/install-jena.sh` (Windows: `scripts/install-jena.ps1`). |
| `/loop-engineer`, `/loop-audit`, `/loop-approve` | The loop engine (section 11). You type these; Claude does not start them. |

The full names have the plugin first: `/safe-lean:setup-repo`, `/safe-lean:loop-engineer` and so on. Type `/` to see all skills. Say the task in your own words, and Claude loads the matching skill.

## Optional plugins

Each plugin adds its skill descriptions to every session, so install only what you use. Install one with `claude plugin install <name>@dotfiles-public`.

| Plugin | Skills | Notes |
|---|---|---|
| `writing-skills` | `ste-visual-first`, `technical-doc-standards`, `winston-presentations`, `fable-agent-patterns` | This repo's own writing skills |
| `anthropic-skills` | `docx`, `pdf`, `pptx`, `xlsx`, `skill-creator` | By Anthropic, unmodified, Apache 2.0. For Claude Code users who do not get these skills from claude.ai. |
| `addy-picks` | `doubt-driven-development` | A fresh-context adversarial review of code and decisions during work. MIT. |
| `ecc-picks` | `eval-harness` | Helps design bigger eval suites. MIT. |
| `hf-picks` | `hf-cli` | The Hugging Face `hf` command. Leave it disabled until you need it. Apache 2.0. |

For the Hugging Face skill: do not use `hf auth login`, because it saves the token as plain text, and the deny rules block it. Keep the token in your OS keychain or password manager, and run commands that need it yourself, in your own terminal. Commands that publish or cost money ask first.

# 9. Set up one repo or many

`/setup-repo` runs `claude/repo_setup.py`. You can run it yourself through the same launcher the guards use. The launcher finds a working Python on every OS. Run these from the root of your clone:

| Command | Does |
|---|---|
| `bash claude/hooks/py.sh ../repo_setup.py plan <repo-or-folder>` | Report only. Changes nothing. |
| `bash claude/hooks/py.sh ../repo_setup.py apply <repo-or-folder>` | Makes the changes and commits them on `chore/claude-forward`. Never pushes. |
| `bash claude/hooks/py.sh ../repo_setup.py apply <repo-or-folder> --untrack` | Also runs `git rm --cached` on tracked personal or secret files. The files stay on disk. |
| `bash claude/hooks/py.sh ../repo_setup.py team <repo>` | Prints the team owner (exit 0) for a team repo, nothing (exit 1) for your own repo |
| `bash claude/hooks/py.sh ../repo_setup.py protect <repo>` | Locks `.git/hooks` and `.git/config` for Claude in a repo outside `~/git`, in the ignored `.claude/settings.local.json` of the main checkout. No commit. |

On Windows, run these in Git Bash. A folder of repos works too: it sets up each repo under it.

- The setup is judged and built from the default branch (`origin/HEAD`, else `main` or `master`), whatever is checked out. Your checkout is never switched.
- A repo with uncommitted work is skipped.
- A setup branch with an older setup, or built on other work, shows as stale. Do not merge a stale branch as setup. The tool never deletes or rewrites it.
- It never pushes.

`forge.sh` is one helper for GitHub and GitLab: `bash claude/forge.sh kind`, `auth-check`, `whoami` and `pr-create`. It reads the host from the `origin` URL, never targets `upstream`, and needs no Python. Add `--dry-run` as the first argument to print the command instead of running it.

# 10. Stop band-aid code

A band-aid is a special case that makes one reported input work: a third `if`, a third test, all green. It passes its own test, so a failing test never stops it. These layers watch for signals that a band-aid cannot hide:

```
 write time   CLAUDE.md rule: before a 2nd special case on one idea ─┐
 edit time    churn_watch hook: many edits of one file              ─┼─► /step-back
 you          "band-aid", "hack", "step back"                       ─┘     1. write the one rule for all cases
                                                                           2. two designs, pick one
 after        /slop-audit ──► report ──► fix one finding per branch        3. rewrite, delete the patches
                                                                           4. fold tests into one table, keep every row
```

Clean an existing repo:

1. Open Claude in the repo and type `/slop-audit`. It runs only read commands and writes a report in `.claude/audits/` (never committed).
2. Pick 1 to 3 findings from the report. Start with a file that is changed often and is complex.
3. Claude fixes each finding on its own branch. Tests that pin today's behavior come first, then the `/step-back` steps.

`churn_watch` sees only Edit, Write and MultiEdit calls. A file changed through Bash does not count.

# 11. Verified improvement loops

A loop improves one target (a script, a skill or a repo task) in its own git worktree. Claude does the work. Hooks run the checks after each try, keep a gain, revert a loss, and stop at success, at the cap, when nothing improves, or at 90 percent of your usage limit. You approve the result.

```
 you: /safe-lean:loop-audit                          ──► ranked list of what has no verifier
 you: /safe-lean:loop-engineer script scripts/bench-shell.sh   ──► worktree, checks, .loop/LOOP.md
 you: /safe-lean:loop-engineer confirm               ──► branch loop/<slug>, setup commit
      each turn: cause ──► edit ──► verify ──► Stop hook: keep (commit) or revert
      ends: checks pass, the cap, 2 turns with no gain, or the usage limit ──► bundle
 you: read .loop/bundle.md and decide (the loop never pushes)
 you: /safe-lean:loop-approve <slug>                 ──► branch feature/loop-<slug>, bundle and lesson copied
```

| Fact | Detail |
|---|---|
| Platforms | macOS, Linux and WSL2. On native Windows the loop hooks do nothing and normal work is never blocked. |
| Targets | `script <path>`, `task "<goal>"` or `skill <name>` |
| Stop | `/safe-lean:loop-engineer stop` |
| Allow one more file | `/safe-lean:loop-engineer allow <path>` |
| Locked during a loop | Tests, checks, lint config and the loop spec (`guard_loop`) |
| Output | `.loop/bundle.md` in the loop worktree. Never create `.loop/` by hand. |
| Profiles | A repo gets the work profile unless a rule maps it to personal. Put your rules in `~/.config/claude/loop-profiles.local.json`. |
| Agents | `loop-diagnoser` (finds causes), `loop-log-reader` (returns only the failures of a long command), `loop-reviewer` (answers three review questions once for each bundle) |
| Usage stop | Needs a status line script that writes `rate_limits.json` to the loop state folder. This repo's `claude/statusline.sh` does not write it, so the usage stop is off and the bundle says so. |

Run a loop in the work profile in manual or accept-edits mode, not auto mode. Design, rules and file formats: [docs/loop-engineering.md](docs/loop-engineering.md).

# 12. The status line

The `statusline` step offers `claude/statusline.sh` as your status line. It shows `model · ctx 34% · branch ✘2 · $0.42 · cache 91%`: the model, the context used, the branch and the count of uncommitted files, the session cost and the prompt-cache hits. It needs `jq`; without it, it prints only `Claude`. It works in Git Bash on Windows.

# 13. Save tokens

Quality first: pick a strong model for hard work. Cut only waste.

| Habit | Why |
|---|---|
| `/clear` between unrelated tasks | Old context goes with every message |
| `/compact focus on X` when the context is large | Keeps what matters, drops the rest |
| `/context`, `/usage`, `/cost` | See where tokens go |
| Specific prompts ("add a test for `load_sales` in `src/io.py`") | A vague prompt makes Claude read many files |
| Plan mode for big work; Esc early and `/rewind` when it goes wrong | No expensive wrong turns |
| `graphify query "..."` before broad reading, in a repo that has `graphify-out/` | The graph answers without opening files |
| Quiet pytest (`-q --tb=short`, which `/setup-repo` sets for uv projects) | Test logs are big |
| `/token-report` each week | Today, the week, each session |

`graphify` is an optional third-party tool. This repo does not install it. The setup sets the subagent model to `sonnet` (`CLAUDE_CODE_SUBAGENT_MODEL` in `claude/settings.base.json`); your own `~/.claude/settings.json` wins if you set another.

# 14. Secrets and evals

## Secrets

Keep keys out of `.env` files in git and out of chat. The guards block Claude from the places where an OS keeps secrets:

| OS | Where keys can live | Claude cannot run |
|---|---|---|
| macOS | Keychain | `security find-generic-password -w` |
| Linux | A keyring | `secret-tool lookup` |
| Windows | Credential Manager | `cmdkey`, `vaultcmd`, `Get-StoredCredential` |

1. Store a key with your OS tool or a password manager, in your own terminal.
2. Export the key in your own terminal, for example `export ANTHROPIC_API_KEY=...` (PowerShell: `$env:ANTHROPIC_API_KEY = "..."`). Then run the command that needs it.
3. If Claude needs to know which variables exist, give it only the names.

In the sandbox (macOS, Linux), the variables `GH_TOKEN`, `GITHUB_TOKEN`, `GITLAB_TOKEN`, `ANTHROPIC_API_KEY`, the AWS keys and `HF_TOKEN` are hidden from every command.

## Evals: advice, enforce, measure

```
 CLAUDE.md and skills  = advice    (Claude should ...)
 guards and deny rules = enforce   (Claude cannot ...)
 evals                 = measure   (does it work, and does the plugin help?)
```

| Evals for | Where | Run |
|---|---|---|
| This plugin (does a skill fire on normal words? no skill for a plain question? tests before a commit? team repos stay local?) | `claude/evals/` | `claude/evals/run.sh` (macOS, Linux, WSL2). It costs model calls on your plan; try `claude/evals/run.sh --case no-skill-for-questions --runs 1 --ablation none` first. |
| Your projects (is the output still right?) | `evals/cases.jsonl` in each new project | `uv run pytest -m eval` |

Plain `pytest` skips project evals, so they never spend tokens by accident. Each line of `cases.jsonl` holds `input` and `expected`, or a `criteria` line for an LLM judge (needs `uv add --dev anthropic` and `ANTHROPIC_API_KEY` in your environment).

# 15. Scripts

All scripts are in `scripts/`. Run them from the root of your clone.

| Script | Does | OS |
|---|---|---|
| `scripts/make-bundle.sh` | Packs the repo into one file to carry to another computer | macOS, Linux, Git Bash |
| `scripts/import-bundle.sh` | Applies such a bundle (fast-forward `main`). It asks first and never merges or resets. | macOS, Linux, Git Bash |
| `scripts/backup-home.sh <folder>` | An encrypted archive of your home folder, with `age`, before big changes | macOS, Linux |
| `scripts/macos-defaults.sh` | User-level macOS settings. It saves the old values first. `install.py --only macos` runs it. | macOS only |
| `scripts/install-jena.sh`, `scripts/install-jena.ps1` | Apache Jena for `/rdf-check` | macOS, Linux; Windows |
| `scripts/skill-zip.sh <skill>` | Packs one skill into a zip to upload to claude.ai | all (Python) |
| `scripts/check-package-names.sh <manager>` | Reports package names that a manager does not know | macOS, Linux, Git Bash |
| `scripts/bench-shell.sh` | Times your login zsh | macOS, Linux |
| `scripts/ci-local.sh` | Runs the checks of the CI workflow on your computer, before you push | macOS, Linux, Git Bash |

# 16. Run the tests of this repo

| Task | Command |
|---|---|
| Tests | `uv run --no-project --with pytest pytest -q tests` |
| Lint and format check | `uvx ruff@0.17.2 check .` and `uvx ruff@0.17.2 format --check .` |
| Both, as CI does | `scripts/ci-local.sh` |

Change a guard: write a test first, run the tests, raise `version` in `claude/.claude-plugin/plugin.json`, add a dated section to `CHANGELOG.md`, commit, then run `claude plugin update safe-lean@dotfiles-public`. Claude Code copies a plugin once for each version: without a version change, the old guards keep running.

# 17. More

- Install steps, failure table and undo: [README](README.md)
- Setup notes and sandbox gotchas: [docs/SETUP.md](docs/SETUP.md)
- Design decisions: [docs/decisions.md](docs/decisions.md)
- The loop engine: [docs/loop-engineering.md](docs/loop-engineering.md)
- What changed in each version: [CHANGELOG.md](CHANGELOG.md)
- Claude Code docs: <https://code.claude.com/docs>
