# Setup notes: how it works and what to know

Start with the [README](../README.md) for what this repo does and how to install it. The [user guide](../GUIDE.md) covers daily work. This file explains each piece, and lists the sandbox and settings facts that can surprise you.

## 1. What is in the repo

```
 install.sh / install.cmd / install.ps1   find a Python 3.9+, start install.py
 install.py                               the installer (--check first, --only STEP, pkg ...)
 packages/                                packages.json (one list for brew, apt, winget), pkgs.py
 shell/                                   zsh block, PowerShell profile, vim, starship, editorconfig
 git/                                     config.shared, config.delta, gitignore_global
 scripts/                                 bundle, backup, macOS defaults, Jena, skill zip, checks
 docs/                                    this file, decisions.md, loop-engineering.md, the guide page
 claude/                                  Claude Code
 ├── CLAUDE.md, CLAUDE.style.md           shared rules and writing style, imported by ~/.claude/CLAUDE.md
 ├── CLAUDE.*.example.md                  templates for your own about-me and computer files
 ├── settings.base.json                   merged into ~/.claude/settings.json (all OS)
 ├── settings.sandbox.json                merged too, on macOS and Linux only
 ├── merge_settings.py                    the merge: your values stay
 ├── repo_setup.py, forge.sh              helpers of the setup-repo skill
 ├── loopctl.py, loop_gate.py             the loop engine: checks and diff gate
 ├── loop-profiles.json                   which repos get the personal loop profile (ships empty)
 ├── statusline.sh                        the status line
 ├── .claude-plugin/                      makes this folder a plugin (safe-lean) and a marketplace
 ├── hooks/                               guards and advisory hooks, started by py.sh
 ├── skills/, agents/                     the safe-lean skills and the loop agents
 ├── plugins/                             optional plugins (section 6)
 ├── evals/                               skill trigger evals (run.sh)
 └── templates/                           project and loop files that skills copy
 tests/                                   pytest for the installer, the hooks, the helpers and these docs
```

## 2. The building blocks

| Concept | What it is | Where here |
|---|---|---|
| CLAUDE.md | Instructions that Claude reads at the start of each session | `claude/CLAUDE.md`, `claude/templates/project/CLAUDE.md` |
| settings.json | Permissions (allow, ask, deny), environment variables, sandbox | `claude/settings.base.json`, `claude/settings.sandbox.json` |
| Permission mode | How much Claude asks before it acts. Switch with Shift+Tab. | Default mode at start; bypass mode off |
| Hooks | Commands that Claude Code runs at fixed events. Exit code 2 blocks the call and sends the message to Claude. | `claude/hooks/hooks.json` |
| Skills | A folder with `SKILL.md`. Claude loads it when the task matches, or you type `/<name>`. | `claude/skills/` |
| Plugin | A bundle of hooks, skills and agents, installed from a marketplace | `claude/.claude-plugin/` |

## 3. The hooks

Guards block. They fail closed: input a guard cannot parse is blocked (exit 2), and an error inside a check gives a deny. They start through `claude/hooks/py.sh`, which exits 2 when it finds no Python 3.9 or later.

| Guard | Event | What it does |
|---|---|---|
| `guard_secrets.py` | PreToolUse, file tools and Bash | Blocks private folders and files (SSH, cloud and git credentials, keychains, `.env` files, `~/Documents`) from one table of roots, for file tools, shell words and globs. A PowerShell write (`Set-Content`, `Out-File`, `Add-Content`) counts as a write. |
| `guard_bash.py` | PreToolUse, Bash and PowerShell | Runs the Bash guards below, and the Bash form of `guard_private_terms` and `guard_loop`, in one Python process. The strongest result wins: block, deny, ask. |
| `guard_pip.py` | through `guard_bash` | Blocks `pip install`, also `python -m pip` and `py -m pip` |
| `guard_main_branch.py` | through `guard_bash` | Blocks history writes on `main` or `master`. Opt out per repo: `git config claude.allowMain true`. |
| `guard_compound.py` | through `guard_bash` | One lexer and a table of checks. Splits a compound command and checks each part against the ask and deny rules. Denies a download piped into a shell. |
| `guard_private_terms.py` | PreToolUse, file tools | Blocks a term from your own list when written into lessons, Claude memory or a `dotfiles` repo |
| `guard_loop.py` | PreToolUse, file tools and Bash | Acts only while a loop runs in the worktree. See [loop-engineering.md](loop-engineering.md) section 13. |
| `guard_live_checkout.py` | through `guard_bash` | Off until you list a clone in `~/.config/claude/live-checkout.txt` |
| `guard_egm.py` | PreToolUse, Skill and Agent | Acts only when an EGM plugin is installed |

The advisory hooks (`coach_prompt`, `churn_watch`, `after_python_edit`, `graphify_hint`, `notify`) and the opt-in Stop hooks (`test_gate`, `lesson_gate`) start with `py.sh --advisory`, or exit at once without their switch file. They never block your prompts. Each Stop hook steps aside while a loop of the session runs.

The `guard_compound` check is not a security boundary. The sandbox and the network allowlist are the real control. A form is covered only if a test in `tests/test_guard_compound.py` covers it.

Change a hook: write the test first, run `uv run --no-project --with pytest pytest -q tests`, raise `version` in `claude/.claude-plugin/plugin.json`, add a section to `CHANGELOG.md`, then run `claude plugin update safe-lean@dotfiles-public`. Claude Code copies a plugin once for each version. New hook entries load in the next session. Where `claude plugin list` shows that the plugin is read from your clone, the working tree runs, and a changed hook script runs at the next call.

## 4. Permissions (`settings.base.json`)

The full lists are in `claude/settings.base.json`. This is the shape of each one.

- **allow**: nothing in the base file. The sandbox file adds read-only git commands, `ls`, `uv run pytest` and `ruff check` (macOS and Linux only).
- **ask**: pushes, PR and MR creation, deletes (`rm`, `Remove-Item`, `git branch -d`, `git clean`, `git reset --hard`), writes through `gh` and `glab`, `gh pr checkout`, `gh repo sync` and `glab mr checkout` (they rewrite a checkout), installs (`brew`, `apt`, `winget`, `choco`, `scoop`, `uv tool install`, `npx`), plugin changes (`claude plugin enable|disable|install|uninstall|update`), the Hugging Face commands that publish or cost money, publishing an artifact, and the Gmail, Drive and Calendar connectors.
- **deny**: reading and editing credentials (`~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.azure`, `~/.kube`, git credentials, `.netrc`, `.npmrc`, Claude's own credentials, the Windows credential folders, `.env` in any folder), editing `.git/config` and `.git/hooks/` (in the current project and below `~/git`), `sudo`, `rm -rf /` and `rm -rf ~`, printing a `gh` or `glab` token, `npm` with `-g`, `npx --yes`, and the Hugging Face login and install script. `disableBypassPermissionsMode` turns off `--dangerously-skip-permissions`.
- **env**: `PYTHONUTF8=1`, `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, `DISABLE_ERROR_REPORTING=1`.
- `enableAllProjectMcpServers` is `false`, so a cloned repo cannot approve its own `.mcp.json` servers. `cleanupPeriodDays` is 90, so `/token-report` sees more than the default period.
- `blockReadsOutsideWorkingDirectories` is `true`. Use `/add-dir <folder>` to add a folder for one session.

Avoid broad allow rules such as `Bash(bash *)` or `Bash(cd *)` in your own settings: they bypass the prompts.

## 5. The sandbox (macOS, Linux and WSL2)

Native Windows has no sandbox. There, every command asks in default mode, and the guards are the main protection. WSL2 has the sandbox: install Claude Code inside WSL2 to use it. The loop engine needs it.

`claude/settings.sandbox.json` turns the sandbox on with `failIfUnavailable`, so on Linux you need `bubblewrap` and `socat` (`sudo apt install bubblewrap socat`). Network: `allowedDomains` lists GitHub, GitLab, PyPI and `ghcr.io`. In auto mode, the classifier can still approve another host. `/sandbox` shows the live state.

Sandbox gotchas:

| Symptom | Cause | What to do |
|---|---|---|
| `gh` or `glab` fails with `x509`, `certificate signed by unknown authority`, or "token missing from the operating system keyring" (macOS) | The command ran inside the sandbox. The Go CLIs fail the macOS TLS check and cannot read the keychain there. `excludedCommands` matches only the start of the command. | Run `gh ...` or `glab ...` alone, not after `cd x &&` or `VAR=1`. Never run `gh auth login` for this. |
| A self-hosted GitLab fails to connect | Its host is not in `allowedDomains` | Add the host to `sandbox.network.allowedDomains` in your own `~/.claude/settings.json` |
| "Operation not permitted" on `.git/config` or `.git/hooks/`, for example `git init`, `git push -u`, or deleting a branch that has an upstream | The sandbox makes both read-only. The rest of `.git/` is writable, so `git add` and `git switch -c` work. | Run that one command outside the sandbox. Claude retries it, and you approve. |
| A signed `git commit` fails | Signing needs `~/.ssh`, which the sandbox hides | Same: Claude runs the commit outside the sandbox, and it asks you |
| A shell command cannot write `~/.zshrc`, `~/.bashrc` or another shell startup file | The sandbox always blocks them | Use the Edit tool, or edit the file yourself |
| `mktemp` with no template writes to `/var/folders` and fails (macOS) | `mktemp` ignores `TMPDIR` without a template | Give a template: `mktemp "$TMPDIR/x.XXXXXX"` |
| An empty root commit fails | `git switch --orphan` writes state that the sandbox denies | Use `git mktree </dev/null`, `git commit-tree` and `git branch` |
| The first `pre-commit run` in a repo fails with a proxy or TLS error | `pre-commit` drops the proxy login that git needs | Run `pre-commit run --all-files` once in a normal terminal. Then the cache is full and the sandbox works. |
| `hf` fails with `OSStatus -26276` (macOS) | Python TLS and the Rust Xet client both fail the macOS check in the sandbox | Run it as `SSL_CERT_FILE=/etc/ssl/cert.pem HF_HUB_DISABLE_XET=1 hf ...`, for that command only |
| `ccusage` shows no use inside the sandbox | The sandbox hides `~/.claude/projects` | The `token-report` skill runs it outside the sandbox, and it asks you |
| `defaults write` fails, `scripts/macos-defaults.sh` stops (macOS) | `defaults` writes `~/Library/Preferences`, which the sandbox denies | Run `./install.sh --only macos` outside the sandbox, in your own terminal |
| `soffice` hangs (LibreOffice) | It needs a private profile folder | Run it with `--headless` and `-env:UserInstallation=file://<dir>` |
| Claude Code stops: the sandbox is not available (Linux) | `bubblewrap` or `socat` is missing | Install both |

Never fix a TLS error with a CA variable in `env`, `--trusted-host` or an `excludedCommands` entry. Each one applies to every command.

## 6. Plugins

The marketplace `dotfiles-public` (the folder `claude/`) lists six plugins. `install.py` installs only `safe-lean`. The others are optional: install one with `claude plugin install <name>@dotfiles-public`.

| Plugin | Where | Source and license |
|---|---|---|
| `safe-lean` | `claude/` | This repo |
| `writing-skills` | `claude/plugins/writing-skills/` | This repo |
| `anthropic-skills` | `claude/plugins/anthropic-skills/` | Anthropic, Apache 2.0, unmodified |
| `addy-picks` | `claude/plugins/addy-picks/` | One skill from a third-party repo, MIT, edited |
| `ecc-picks` | `claude/plugins/ecc-picks/` | One skill from a third-party repo, MIT |
| `hf-picks` | `claude/plugins/hf-picks/` | One skill from Hugging Face, Apache 2.0 |

Before you install a third-party plugin, read its `hooks/` and scripts. `claude/plugin-hooks.lock` holds a sha256 of the hook and MCP config of each third-party plugin that you reviewed, and `claude/plugin_lock.py` checks it. Each plugin folder has a README with the pinned version and the update steps.

Each installed plugin adds its skill descriptions to every session. Leave a plugin that you do not use uninstalled or disabled; `coach_prompt` hints when a disabled plugin fits your prompt. Enable one for one repo: `claude plugin enable <name>@dotfiles-public --scope local`.

## 7. Manual steps (once per machine)

1. **Git identity.** The install never sets it. Run `git config --global user.name "<your name>"` and `git config --global user.email "<your email>"`. Use your noreply address on a public host.
2. **Signed commits (optional).** Make a key (`ssh-keygen -t ed25519`), add it to your host as a signing key, then run `git config --global gpg.format ssh`, `git config --global user.signingkey <path to the .pub file>` and `git config --global commit.gpgsign true`.
3. **Private terms (optional).** Write one term per line in `~/.config/claude/private-terms.txt` (Windows: `%USERPROFILE%\.config\claude\private-terms.txt`). Keep this file out of every repo.
4. **Opt-in hooks (optional).** Create `~/.config/claude/test-gate` or `~/.config/claude/lesson-gate` (an empty file) to turn on `test_gate` or `lesson_gate`.
5. **Loop profiles (optional).** Write rules in `~/.config/claude/loop-profiles.local.json` for the repos that you accept the personal loop rules for.

## 8. Check that it works

```
claude plugin list                                        # safe-lean is enabled
uv run --no-project --with pytest pytest -q tests         # all pass
```

In a new Claude Code session:

- Ask Claude to run `pip install requests`. It is blocked and suggests `uv add`.
- On `main` in a repo, ask for a commit. It is blocked and suggests `git switch -c`.
- Ask Claude to read `~/.ssh/id_rsa`. It is blocked.
- `/hooks` lists the hooks. `/token-report` shows today's tokens.

## 9. Day to day

| I want to | Do this |
|---|---|
| Start a project | `/new-project` in Claude |
| Start a repo for Claude | `/setup-repo` in Claude |
| Add a package to a project | `uv add <name>` (never pip) |
| Add a tool to my machine | `python3 install.py pkg add <name>`, then `pkg keep <name>` to keep it |
| Change a hook or skill | Branch, test, PR. After the merge: `git pull`, run the install again, restart Claude Code. |
| See token use | `/token-report`, `/cost` |
| Undo the install | The "Reverse procedure" section of the [README](../README.md) |
