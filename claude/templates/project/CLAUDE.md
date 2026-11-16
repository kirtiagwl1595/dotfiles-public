# <name>

## Layout
- `src/` code, `tests/` pytest, `evals/` golden examples (`cases.jsonl`), `notebooks/` exploration (kernel: "Python (<name>)"), `data/raw/` input (never committed).

## Commands
- Run: `uv run python main.py`  ·  Test: `uv run pytest`  ·  Evals: `uv run pytest -m eval`  ·  Lint: `uv run ruff check .`
- Add a package: `uv add <pkg>` (dev: `uv add --dev <pkg>`)

## Rules
- When behaviour changes (prompts, models, data logic), run the evals. Add a case to `evals/cases.jsonl` unless that breaks a comparison in progress.
- Docs follow the rules in `docs/README.md`. `tests/test_docs.py` checks them.
- Move logic out of notebooks into `src/` once it works, with a test.
