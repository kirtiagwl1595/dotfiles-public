"""Evals: score this project's output on golden examples in cases.jsonl.

Run:  uv run pytest -m eval        (plain `pytest` skips these, so the test gate never spends tokens)
Each line of cases.jsonl: {"input": ..., "expected": ...}
  "match": "exact" (default) or "contains"
  "criteria": "PASS if ..." -> an LLM judge grades instead (needs `uv add --dev anthropic` and
              ANTHROPIC_API_KEY, e.g. ANTHROPIC_API_KEY=$(secret get ANTHROPIC_API_KEY) uv run pytest -m eval)
"""

import functools
import json
import os
from pathlib import Path

import pytest

CASES = [
    json.loads(line)
    for line in (Path(__file__).parent / "cases.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip()
]
THRESHOLD = 0.8  # share of cases that must pass


def predict(text: str) -> str:
    """Replace with this project's entry point, e.g. `from src.app import answer; return answer(text)`."""
    return text.strip().upper()  # placeholder so the sample cases pass


@functools.cache
def judge_model() -> str:
    """EVAL_JUDGE_MODEL if set, else the newest Opus from the Models API (no model id is hard-coded)."""
    if os.environ.get("EVAL_JUDGE_MODEL"):
        return os.environ["EVAL_JUDGE_MODEL"]
    import anthropic

    return next(
        m.id
        for m in anthropic.Anthropic().models.list()
        if m.id.startswith("claude-opus")
    )


def llm_judge(output: str, criteria: str) -> bool:
    import anthropic

    response = anthropic.Anthropic().beta.messages.create(
        model=judge_model(),
        max_tokens=2048,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": f"Grade this output.\n\n<criteria>\n{criteria}\n</criteria>\n\n"
                f"<output>\n{output}\n</output>\n\nAnswer with one word on the last line: PASS or FAIL.",
            }
        ],
    )
    if response.stop_reason == "refusal":
        return False
    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip().splitlines()[-1].strip().upper() == "PASS"


def passes(case: dict, output: str) -> bool:
    if "criteria" in case:
        return llm_judge(output, case["criteria"])
    if case.get("match") == "contains":
        return case["expected"].lower() in output.lower()
    return output.strip() == case["expected"].strip()


@pytest.mark.eval
def test_pass_rate():
    if any("criteria" in c for c in CASES) and not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("LLM-judged cases need ANTHROPIC_API_KEY (see the docstring)")
    if any("criteria" in c for c in CASES):
        try:
            judge_model()
        except (ImportError, StopIteration):  # SDK not added, or no Opus model listed
            pytest.skip(
                "cannot pick a judge model: `uv add --dev anthropic` or set EVAL_JUDGE_MODEL"
            )
    failed = []
    for case in CASES:
        output = predict(case["input"])
        if not passes(case, output):
            failed.append({"input": case["input"], "got": output})
    rate = 1 - len(failed) / len(CASES)
    print(f"\neval pass rate: {rate:.0%} ({len(CASES) - len(failed)}/{len(CASES)})")
    assert rate >= THRESHOLD, (
        f"pass rate {rate:.0%} is below {THRESHOLD:.0%}; failed: {failed[:5]}"
    )
