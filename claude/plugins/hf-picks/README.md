# hf-picks

The `hf-cli` skill copied from [huggingface/skills](https://github.com/huggingface/skills) at commit `25910b3d0ba31a2ba102f901cdc9e008c278a69c` (generated with `huggingface_hub` 2.4.0), Apache 2.0 licence (see `LICENSE`).

| Skill | Why it is here |
|---|---|
| `hf-cli` | The Hugging Face Hub CLI (`hf`): download models and datasets, browse the Hub, manage repos, jobs, Spaces and endpoints |

Why copy instead of adding the marketplace (checked 2026-10-28): the repo has 25 skills, so 25 descriptions in every session.
This one description is about 250 tokens, and the skill body (34 KB, about 8.5k tokens) loads only when a task uses it.
The skill has one file: no scripts, hooks, MCP servers or model pins.

## Off by default

Install the plugin, then leave it disabled until you need it. A disabled plugin costs 0 tokens in sessions that do not use Hugging Face.

```bash
claude plugin enable hf-picks@dotfiles-public --scope local   # this repo only (.claude/settings.local.json)
claude plugin disable hf-picks@dotfiles-public --scope local  # undo
```

For one session only, use `/plugin` and enable it there.

## Safety

- Claude may run read-only commands (`hf download`, `hf models info`, `hf cache list`). Each gets the normal permission prompt. Do not pre-allow commands that publish, delete, cost money or touch login.
- Token: store it in your OS keychain (macOS Keychain, Windows Credential Manager, or `secret-tool` on Linux). Give it to `hf` through an environment variable that you set in your own terminal, not in a Claude Code session. Never run `hf auth login`: it writes the token as plain text. The skill text still shows `hf auth login`; this rule wins.
- The token files in `~/.cache/huggingface` are hidden from Claude by the settings of this repo. Keep `HF_TOKEN` and `HUGGING_FACE_HUB_TOKEN` out of files that Claude can read.
- In the macOS sandbox, you may need `SSL_CERT_FILE=/etc/ssl/cert.pem HF_HUB_DISABLE_XET=1` before `hf` (the TLS check fails under Seatbelt). Hosts: `huggingface.co`, `*.hf.co`.
- The skill says to install with `curl ... | bash`. Do not. Install `hf` with your package manager, for example `uv tool install huggingface_hub`, after you read what it installs.

## Update on purpose

1. Look at the newest commit of `skills/hf-cli/SKILL.md` upstream (or run `hf skills add --force` in a scratch folder).
2. Diff it against `skills/hf-cli/SKILL.md` here and read every changed line.
3. Copy it, set the new commit here and in `.claude-plugin/plugin.json`, and bump `version`.
