# writing-skills

Four writing skills in one plugin. Reader: a person who wants plain-language rules and doc or deck standards in Claude Code.

| Skill | Use |
|---|---|
| `ste-visual-first` | A visual instead of long text, plus plain-language (ASD-STE100) rewrite examples |
| `technical-doc-standards` | Runbooks, guides, SOPs and troubleshooting pages for teammates |
| `winston-presentations` | Deck and talk structure (Patrick Winston, "How to Speak") |
| `fable-agent-patterns` | A Claude-style agent loop, for an agent that you build on another model or host |

The skill format is the same on claude.ai: zip a skill folder and upload it under Settings, Capabilities, Skills.

## Install

```
claude plugin install writing-skills@dotfiles-public
```

The plugin is optional. It has no hooks and it does not change a setting.

## Change a skill

1. Edit the skill in this folder.
2. Bump `version` in `.claude-plugin/plugin.json`. Claude Code copies a plugin once for each version, so without the bump `claude plugin update` keeps the old copy.
3. Run `uv run --no-project --with pytest pytest -q tests` from the repo root. The tests check the frontmatter, the references and the privacy rules.
