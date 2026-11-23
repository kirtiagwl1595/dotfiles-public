# addy-picks

One skill copied from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills), commit `301b02b`, MIT licence (see `LICENSE`). The copy is edited; the changes are listed below.

| Skill | Why it is here |
|---|---|
| `doubt-driven-development` | Fresh-context adversarial review during the work, with a 3-cycle stop. `code-review` runs after the work; `grilling` questions the user, not the artifact (both from the `mattpocock-skills` plugin, if you have it). |

Why copy instead of installing the plugin: the other 24 skills overlap skills and rules that this repo already has.

## Changes from upstream

| Change in `SKILL.md` | Reason |
|---|---|
| Removed the "Cross-model escalation" section (Gemini CLI, Codex CLI, manual external review), with its shell examples. | The upstream skill makes the offer mandatory in each cycle and sends the artifact to outside tools. Rule: your data stays on your machine. |
| Removed the cross-model rows from Common Rationalizations. | Same reason. |
| Removed the external CLI and cross-model items from Red Flags. | Same reason. |
| Removed the three cross-model and external CLI items from Verification. | Same reason. |
| Removed the links to `../../references/orchestration-patterns.md` from Loading Constraints and Interaction with Other Skills. | The file is not copied. |
| Reworded the Loading Constraints item about subagents. | It referred to roles from the upstream `agents/` directory, which is not copied. The rule stays: a subagent cannot spawn another subagent. |
| Replaced the text on role-based reviewers in Step 3 with a generic fresh subagent. | The upstream reviewers are not copied. A generic subagent also has no default response shape to override. |
| Replaced `/review` with `mattpocock-skills:code-review`. | A named code review skill; use your own if you do not have that plugin. |
| Replaced `test-driven-development` with `mattpocock-skills:tdd` and `debugging-and-error-recovery` with `mattpocock-skills:diagnosing-bugs`. | Same reason. |
| Removed the `source-driven-development` sibling. | That skill is not adopted. |

Cost of the removal: the reviewer is the same model family as the author, so it can share blind spots.

Update on purpose: diff the upstream skill against commit `301b02b`, scan it, apply the changes above again, and bump `version` in `.claude-plugin/plugin.json`.
