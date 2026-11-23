# ecc-picks

Skills copied from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) (ECC) **v2.2.3**, MIT licence (see `LICENSE`).

| Skill | Why it is here |
|---|---|
| `eval-harness` | Eval-driven development: capability + regression evals, pass@k / pass^k |

Why copy instead of installing ECC (measured 2026-10-25 with a sandbox dry run of `--profile minimal --with capability:machine-learning`):
~23.6k tokens added to every session (165 skill + 68 agent descriptions, 10 always-on rules), 58 agents pinned to Sonnet,
an always-on 80% coverage rule, and overlaps with mattpocock `tdd` / `code-review`.

Update on purpose: dry-run the new ECC version, diff the picked skills, copy, bump `version` in `.claude-plugin/plugin.json`.
