# Changelog

What changed in each version of this repo and of the `safe-lean` plugin. Newest first. The plugin version is in `claude/.claude-plugin/plugin.json`.

To update: `git pull`, then `./install.sh` (Windows: `.\install.cmd`), then restart Claude Code.

## [0.2.0] - 2026-11-16

### Added
- `install.sh` (macOS, Linux, Git Bash), `install.cmd` and `install.ps1` (Windows). They find a Python 3.9+, skip the Microsoft Store stub, and start `install.py`. With no Python, they ask, then install one with `winget`, `brew` or `apt-get`.
- `install.py` finds a tool that is installed but not on PATH (for example `~/.local/bin/claude`). On a yes, it adds the folder to PATH: a managed block in your shell file, or the Windows user PATH.
- `install.py` offers to install a missing tool (`git`, `claude`, Git Bash, `bubblewrap`, `socat`) with `winget`, `brew`, `apt-get` or the Claude Code installer. It asks first; `--check` only shows the command.
- `install.py --skip-tools`: only report the tools.
- `install.py` finds an old cached copy of the plugin (Claude Code keeps one per version) and, on a yes, runs `claude plugin update safe-lean@dotfiles-public`. Without it, a `git pull` alone keeps the old skills.
- The `setup-repo` skill, with `claude/repo_setup.py`, `claude/forge.sh` and `claude/templates/`. It makes a repo Claude-forward on branch `chore/claude-forward` and asks before push and PR. On Windows it writes no Bash allow rules.
- Ask rules: `claude plugin update`, GitLab writes (`glab mr create`, `glab api -X ...` and more), Hugging Face writes (`hf upload` and more), `forge.sh pr-create`, publishing an artifact, and the Gmail, Google Drive and Google Calendar connectors.
- Deny rules: `hf auth login` and the Hugging Face CLI install script.
- Sandbox: `glab` and the plugin's own `forge.sh` run outside it (they need the keychain), so they ask. A `forge.sh` from anywhere else stays in the sandbox. Hugging Face token files and `HUGGING_FACE_HUB_TOKEN` are hidden from sandboxed commands.

### Changed
- Auto mode is allowed: it is in the shift+tab cycle. Each session still starts in default mode, and bypass mode stays off.
- An older install left `permissions.disableAutoMode: "disable"`. `install.py` asks before it removes it.

### Fixed
- `claude/hooks/py.sh` passes the arguments after the script name. Before, a skill script got none.
- `install.sh` takes a `y` that ends in `\r` (Git Bash on Windows) as a yes.

## [0.1.0] - 2026-11-16

### Added
- The `safe-lean` plugin: guards for secrets, private terms, `pip install`, commits on `main` and compound commands, for the Bash and PowerShell tools and the file tools, on macOS, Linux and Windows.
- Safe settings (`settings.base.json`, `settings.sandbox.json`), shared rules (`claude/CLAUDE.md`), the writing style, git defaults, and `install.py`.
- Skills: `token-report` and `ste-visual-first`.
