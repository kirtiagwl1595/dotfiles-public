# dotfiles-public

A Claude Code and git starter setup for macOS, Linux and Windows. Reader: one person who sets it up on their own computer.

## The problem

Claude Code can read any file your user account can read, and run any command you approve. Without guards, one wrong approval can show Claude an SSH key, a cloud token or a `.env` file. On native Windows there is no sandbox, so the guards and the approval prompts are the only protection. In auto mode on Windows, only the guards and the auto mode classifier remain.

This repo adds:

- **Guards** (a Claude Code plugin, `safe-lean`): hooks that block secret reads, `pip install`, commits on `main` and risky command chains, for the Bash and PowerShell tools and the file tools.
- **Safe settings**: in default mode, Claude asks before every command outside the sandbox. Bypass mode is off. Auto mode is available with shift+tab; each session starts in default mode.
- **Token rules**: short answers in a plain writing style (ASD-STE100), and rules that cut token use.
- **Git defaults**: `main` as the first branch, rebase on pull, prune on fetch, a global ignore file for secrets.
- **Skills** in the same plugin: `setup-repo`, `token-report` and `ste-visual-first`. See "Skills".

What changed in each version: [CHANGELOG.md](CHANGELOG.md).

The install adds to your setup. It never removes your own values. It asks before it replaces a weaker safety value, before it changes PATH, and before it installs a tool.

## Summary

1. Install the prerequisites.
2. `cd ~`, then `git clone https://github.com/kirtiagwl1595/dotfiles-public.git git/dotfiles-public`
3. `cd git/dotfiles-public`, then `./install.sh --check` (Windows: `.\install.cmd --check`). Read the report.
4. `./install.sh` (Windows: `.\install.cmd`). Answer each question.
5. Restart Claude Code. Do the checks in "Verify".

## Prerequisites

| Item | macOS | Linux (Ubuntu) | Windows |
|---|---|---|---|
| git | `xcode-select --install` | `sudo apt install git` | `winget install --id Git.Git -e` |
| bash | comes with macOS | comes with Linux | Git Bash, from Git for Windows (same command) |
| Python 3.9 or later | `brew install python` or python.org | `sudo apt install python3` | `winget install --id Python.Python.3.12 -e` |
| Sandbox tools | built in | `sudo apt install bubblewrap socat` | none (no sandbox on native Windows) |
| Claude Code | [setup page](https://docs.claude.com/en/docs/claude-code/setup) | same | same |

> **Windows: Git Bash is required.** Claude Code runs hooks in Git Bash. Without Git Bash it runs them in PowerShell, `bash` is not found, and no guard runs. `install.py` stops when it finds no Git Bash.

## Procedure

1. Clone the repo. These lines work in bash, zsh and PowerShell. (In Windows PowerShell, `git clone ... ~/git/x` makes a folder named `~`, so start with `cd ~`.)

   ```
   cd ~
   git clone https://github.com/kirtiagwl1595/dotfiles-public.git git/dotfiles-public
   cd git/dotfiles-public
   ```

2. Run the dry run. It changes nothing.
   - macOS, Linux, Git Bash: `./install.sh --check`
   - Windows PowerShell or Command Prompt: `.\install.cmd --check`. It starts `install.ps1` even when PowerShell blocks scripts.
   - All three find a Python 3.9+ and start `install.py`. With no Python, they ask, then install one (`winget`, `brew` or `apt-get`). You can also run `python3 install.py --check` (Windows: `py install.py --check`).

   Verify: each tool line shows `ok`. A `missing` line names the command that fixes it. A `weaker` line names a setting of yours that the install will ask about.

3. Run the install. Use the same command without `--check`: `./install.sh` or `.\install.cmd`.
   - For each `weaker` value, the install asks `Replace it? [y/N]`. Type `y` to take the safe value. Press Enter to keep yours.
   - Before it changes a file, it saves a copy as `<file>.bak`.

   Verify: the last line is `Done. Restart Claude Code.`

4. Restart Claude Code.

### What the install changes

| File | Change |
|---|---|
| `~/.claude/CLAUDE.md` | Two import lines at the top: `claude/CLAUDE.md` (shared rules) and `claude/CLAUDE.style.md` (writing style). Your own text stays below. |
| `~/.claude/settings.json` | Adds `claude/settings.base.json`; on macOS and Linux also `claude/settings.sandbox.json`. Your values win, except where you answer `y`. Removes `permissions.disableAutoMode` from an older install only when you answer `y`. |
| `~/.gitconfig` | An `[include]` of `git/config.shared` at the top, so your own values win. Sets `core.excludesFile` only when you have none. Never sets your name, email, signing key or credential helper. |
| Claude Code plugins | `claude plugin marketplace add <clone>/claude`, then `claude plugin install safe-lean@dotfiles-public`. When the cached plugin copy is older than `claude/.claude-plugin/plugin.json` (after a `git pull`), it asks, then runs `claude plugin update safe-lean@dotfiles-public`. |
| PATH (only on `y`) | A tool that is installed but not on PATH (for example `~/.local/bin/claude`): macOS and Linux get a `# >>> dotfiles-public PATH >>>` block in `~/.zshrc`, `~/.bash_profile` (bash on macOS), `~/.bashrc` (bash on Linux) or `~/.profile`. Windows gets the folder in the user PATH (registry, not `setx`). |
| Tools (only on `y`) | A missing tool is installed with the first that it finds: `winget`, `brew`, `apt-get` (with `sudo`). Claude Code without `winget` or `brew`: the installer from the Claude Code setup page. git on macOS without `brew`: `xcode-select --install`. `--skip-tools` only reports. |

## How approval works

| Where the command runs | What happens |
|---|---|
| macOS, Linux: inside the sandbox | Runs with no question. The sandbox limits files and network. |
| macOS, Linux: outside the sandbox (Claude retries with `dangerouslyDisableSandbox`, or a `gh` or `glab` command) | Claude asks you. No allow rule skips the question. |
| Windows (no sandbox), default mode | Claude asks you for every command. |
| Any OS: a command that matches an ask rule (`git push`, `glab mr create`, `hf upload`, `rm`, `Remove-Item`, `winget install`, ...), or publishing an artifact or using a Google connector | Claude asks you. |
| Any OS: a command that a guard or a deny rule blocks | Claude cannot run it. |
| Any OS, auto mode (you select it with shift+tab) | A classifier approves or blocks each action instead of you. Deny rules and guards still apply. On Windows, nothing else is between Claude and the shell. |

## What each guard blocks

All guards run on every OS. They match paths in any case, with `\` or `/`, and with `~`, `$HOME`, `%USERPROFILE%`, `$env:USERPROFILE`, `C:\Users\<name>` or `/c/Users/<name>`.

| Guard | Blocks |
|---|---|
| `guard_secrets` | A shell call with no command text. Reads and writes of SSH keys (the guard lets a shell read `.pub`, `known_hosts` and `config`; the Read tool still cannot, because the deny rule `Read(~/.ssh/**)` covers the whole folder), `.aws`, `.azure`, `.kube`, `.gnupg`, `.config/gh`, `.git-credentials`, `.netrc`, `.npmrc`, `.pypirc`, `.docker/config.json`, `.env` files (`.env.example` is fine), `~/Documents`, the macOS Keychain, Linux keyrings, the Windows credential folders (`AppData\...\Microsoft\Credentials`, `Protect`, `Vault`, `GitHub CLI`), and the commands `security find-generic-password -w`, `cmdkey`, `vaultcmd`, `Get-StoredCredential`, `secret-tool lookup`. |
| `guard_compound` | Checks each part of a chain (`a && b`, `$(...)`, `bash -c`, `cmd /c`, `powershell -Command`) against the ask and deny rules. Denies a download piped into a shell (`curl x \| sh`, `irm x \| iex`). Asks for `powershell -EncodedCommand`. Outside the sandbox, denies a chain of steps that are not all allowed. |
| `guard_pip` | `pip install`, `python -m pip install`, `py -m pip install`. Use `uv add`. |
| `guard_main_branch` | `git commit`, `push`, `merge`, `rebase` and other history writes on `main`. Opt out per repo: `git config claude.allowMain true`. |
| `guard_private_terms` | Writing a term from your own list into lessons, Claude memory or a `dotfiles` repo. Your list: `~/.config/claude/private-terms.txt`, one term per line; it never goes in a repo. No file: the guard does nothing. |

Every guard starts through `claude/hooks/py.sh`. When it finds no working Python 3.9+, it blocks the tool call (exit 2). A guard that crashes denies the call.

## Skills

The plugin brings these skills. In Claude Code, type the name with a `/`, or ask for the task in your own words.

| Skill | What it does |
|---|---|
| `/setup-repo` | Makes the current repo Claude-forward: a managed `.gitignore` block, `.claude/settings.json` (no Bash allow rules on Windows), a quiet pytest block, a project `CLAUDE.md`. It commits on `chore/claude-forward` and asks before push and PR. A team repo (its `origin` is not under your user name) gets only local, ignored files. Helpers: `claude/repo_setup.py`, `claude/forge.sh` (picks `gh` or `glab` from `origin`). |
| `/token-report` | Your Claude Code token use and cost. |
| `/ste-visual-first` | Picks a table or a diagram over long text. |

`setup-repo` writes `.git/config` and `.claude/settings.json`, which the sandbox denies. Claude runs those single commands outside the sandbox, and each one asks you.

## Verify

Do these checks in Claude Code after the restart.

| Check | Expected |
|---|---|
| Ask Claude: "Read ~/.ssh/id_rsa" | Blocked or denied: the guard says "touches a private file or secret", or the deny rule gives its own message. |
| Press shift+tab several times | Auto mode is in the cycle. Bypass mode is not. A new session starts in default mode. |
| Windows: ask Claude to list the files here | An approval prompt. |
| macOS, Linux: ask Claude to run `git status` | It runs with no prompt (in the sandbox). |
| macOS, Linux: ask Claude to run `gh auth status` | An approval prompt (`gh` runs outside the sandbox). |
| Type `/setup-repo` | The skill is in the list (`safe-lean:setup-repo`). |

## Failure scenarios

| Symptom | Cause | Resolution |
|---|---|---|
| `Blocked: the Claude Code guards found no working Python 3.9 or later.` | No Python, or only the Microsoft Store stub. | Install Python (see Prerequisites). Restart Claude Code. |
| `$'\r': command not found` in a hook error | `py.sh` was checked out with CRLF line ends. | `git config core.autocrlf false`, then `git checkout -- claude/hooks/py.sh`. `.gitattributes` keeps it LF on a fresh clone. |
| `install.sh needs Python 3.9 or later, and found none.` (or `install.ps1 ...`) | No Python 3.9+, or only the Microsoft Store stub. | Answer `y` to install one, or install Python yourself (see Prerequisites). Then open a new terminal and run the script again. |
| `claude: command not found` after the install added it to PATH | The open terminal read PATH before the change. | Open a new terminal. |
| `install.py` says `FAILED Git Bash is needed` | Windows without Git for Windows. | `winget install --id Git.Git -e`, then run the install again. |
| Claude Code stops: the sandbox is not available (Linux) | `bubblewrap` or `socat` is missing; `sandbox.failIfUnavailable` is on. | `sudo apt install bubblewrap socat`. |
| `<path> is not valid JSON` from `install.py` | Your `~/.claude/settings.json` has a syntax error. | Fix the file or move it away, then run the install again. |
| `Blocked: git commit on 'main'` | The main-branch guard. | `git switch -c feature/<name>`, or opt out for this repo: `git config claude.allowMain true`. |
| `... is outside <folder>; the permissions.blockReadsOutsideWorkingDirectories setting blocks reads outside the working directories` | Claude reads only the folder it started in, and folders you add. | In Claude Code, type `/add-dir <folder>` for this session. |

## Reverse procedure

1. `claude plugin uninstall safe-lean@dotfiles-public`
2. Put each `.bak` copy back: `~/.claude/CLAUDE.md.bak`, `~/.claude/settings.json.bak`, `~/.gitconfig.bak`. Without a `.bak` copy, the file did not exist before: delete it.
3. If the install set it: `git config --global --unset core.excludesFile`.
4. PATH: delete the `dotfiles-public PATH` block from your shell file (the `.bak` copy has the old file). Windows: Settings > System > About > Advanced system settings > Environment Variables, then remove the folder from the user `Path`.
5. A tool that the install installed: remove it with the same package manager (`brew uninstall`, `winget uninstall`, `sudo apt-get remove`).
6. Restart Claude Code.

## Development

- Tests: `uv run --no-project --with pytest pytest -q tests`. They use a fake home folder; they never touch your real `~/.claude` or `~/.gitconfig`.
- Lint: `uvx ruff@0.17.2 check . && uvx ruff@0.17.2 format --check .`
- CI runs both, and `install.py --check`, on Windows, Ubuntu and macOS for each push and PR.

## Facts this setup relies on

From the Claude Code docs (checked 2026-11-16):

- Hooks on Windows run in Git Bash; with no Git Bash, in PowerShell. A `PowerShell` tool exists, so the Bash guard also matches `PowerShell`.
- The sandbox runs on macOS, Linux and WSL2, not on native Windows. Without `bubblewrap` and `socat` it runs unsandboxed, unless `sandbox.failIfUnavailable` is on.
- `autoAllowBashIfSandboxed` is off by default. A `dangerouslyDisableSandbox` retry and an excluded command get the normal prompt in default mode, unless an allow rule matches.
- `permissions.disableBypassPermissionsMode: "disable"` turns bypass mode off. Without `permissions.disableAutoMode`, auto mode is in the shift+tab cycle; `defaultMode: "default"` keeps it from being the start mode.
- Install commands for Claude Code (setup page, checked 2026-11-16): `brew install --cask claude-code`, `winget install Anthropic.ClaudeCode`, or the native installer (`https://claude.ai/install.sh`, Windows `https://claude.ai/install.ps1`). The native installer puts `claude` in `~/.local/bin`; if the shell does not find it, that folder is not on PATH.
- Not documented: whether a deny rule like `Read(~/.ssh/**)` matches a Windows path with `\`. The guards cover it either way; the Windows CI job tests the guards.
