# anthropic-skills

Five skills by Anthropic, PBC, copied without changes. License: Apache 2.0 (`LICENSE.txt` here and in each skill folder).

| Skill | What it does |
|---|---|
| `docx` | Create, read and edit Word documents |
| `pdf` | Read, merge, split, fill and create PDF files |
| `pptx` | Create, read and edit PowerPoint decks |
| `xlsx` | Create, read and edit spreadsheets |
| `skill-creator` | Create and test new skills |

Why a copy: claude.ai gives these skills to its users. A Claude Code user without claude.ai skill sync does not have them. This plugin gives them the same set.

Source: [anthropics/skills](https://github.com/anthropics/skills), the `document-skills` and `example-skills` plugins. The files are a copy of the claude.ai synced version of 2026-11-23.

## Use the upstream instead

To get Anthropic's updates directly, do not enable this plugin. Run in Claude Code:

```
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
/plugin install example-skills@anthropic-agent-skills
```

## Update on purpose

1. Copy the 5 skill folders again from the upstream repo or from your synced claude.ai copy.
2. Keep each `LICENSE.txt`. Change nothing else in the skill folders.
3. Bump `version` in `.claude-plugin/plugin.json` and add a line to `CHANGELOG.md`.

The repo's lint and privacy checks skip `skills/` here: the files stay as Anthropic wrote them.

Some scripts need extra tools (LibreOffice, Poppler, Python packages). Each `SKILL.md` names them.
