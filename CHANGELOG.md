# Changelog

What changed in each version of this repo and of the `safe-lean` plugin. Newest first. The plugin version is in `claude/.claude-plugin/plugin.json`.

To update: `git pull`, then `./install.sh` (Windows: `.\install.cmd`), then restart Claude Code.

## [0.3.0] - 2026-11-23

### Added
- Loop engineering: `/safe-lean:loop-engineer`, `loop-audit` and `loop-approve`, the agents `loop-diagnoser`, `loop-log-reader` and `loop-reviewer`, and `loopctl.py`, `loop_gate.py`, `loop_hook.py`, `guard_loop.py`. macOS, Linux and WSL2; on native Windows the loop hooks do nothing.
- Skills: `staff-engineer`, `step-back`, `slop-audit`, `new-project`, `rdf-check`.
- Optional plugins: `writing-skills` (`ste-visual-first` moves here, plus `technical-doc-standards`, `winston-presentations`, `fable-agent-patterns`), `anthropic-skills` (Anthropic's `docx`, `pdf`, `pptx`, `xlsx`, `skill-creator`, Apache 2.0, unmodified), `addy-picks`, `ecc-picks`, `hf-picks`.
- Hooks that only advise: `coach_prompt`, `churn_watch`, `after_python_edit`, `graphify_hint`, `notify`. Opt-in: `test_gate`, `lesson_gate`, `guard_live_checkout`. `guard_egm` acts only when an EGM plugin is installed.
- `py.sh --advisory`: with no Python, an advisory hook exits 0; a guard still blocks.
- Packages: `packages/packages.json` with `brew`, `apt` and `winget` names; profiles `minimal`, `developer`, `full`, `work`. `install.py` asks for a profile and each group on every OS. `install.py pkg add|keep|list|brewfile|names`.
- `install.py --only STEP`, `--profile`, `--manager`, `--yes-packages`. New steps: `delta`, `shell`, `statusline`, `templates`, `macos`, `packages`.
- Shell config: zsh (a managed block in `~/.zshrc` and `~/.zprofile`), vim, starship, editorconfig, and a PowerShell profile for Windows. `git/config.delta`.
- Scripts: `backup-home.sh`, `macos-defaults.sh`, `make-bundle.sh`, `import-bundle.sh`, `skill-zip`, `install-jena` (`.sh` and `.ps1`), `bench-shell.sh`, `check-package-names.sh`, `ci-local.sh`.
- `claude/statusline.sh`, `claude/LESSON-STYLE.md`, and templates `CLAUDE.about-me.example.md`, `CLAUDE.profile.example.md`, `BENCHMARK-RECORD.md`.
- The project template gets `.claude/`, `.github/`, a pre-commit config, `src/`, `data/`, `notebooks/` and a smoke test.
- Deny rules: Claude's file tools do not edit `.git/config` or `.git/hooks/` (in the current project and below `~/git`). Ask rules: `gh pr checkout`, `gh repo sync`, `glab mr checkout`.
- A test fails on any private plugin name in the repo.
- `GUIDE.md` (with `docs/guide.html`, built by `docs/build.sh` with pandoc), `docs/SETUP.md`, `docs/decisions.md` (D1 to D24). `tests/test_docs.py` checks that each option, step, path, skill and link named in the docs exists.

### Changed
- `guard_secrets` uses one table of protected roots for file tools, shell words and globs. PowerShell writers (`Set-Content`, `Out-File`, `Add-Content`) count as writes.
- `guard_compound` uses one lexer and a table of checks, and reads `settings.sandbox.json` for excluded commands.
- `guard_main_branch` closes more push and history-write bypasses.
- `setup-repo` and `repo_setup.py` lock `.git` hooks and config of each repo (the `protect` step) and judge the default branch.

### Fixed
- `install.py --check` in a sandbox stopped with a traceback when it could not read a file. It now prints one line and exits 2. A tool folder it cannot read counts as "not found".

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
