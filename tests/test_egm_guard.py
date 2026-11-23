"""guard_egm asks before EGM starts; reviewer agents run without a prompt once an EGM skill ran."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CLAUDE = Path(__file__).resolve().parents[1] / "claude"
HOOKS = CLAUDE / "hooks"


def guard(tool, tool_input, transcript=None):
    payload = {"tool_name": tool, "tool_input": tool_input}
    if transcript is not None:
        payload["transcript_path"] = str(transcript)
    p = subprocess.run(
        [sys.executable, "-B", str(HOOKS / "guard_egm.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"] if p.stdout else None


def transcript(tmp_path, *entries):
    t = tmp_path / "session.jsonl"
    t.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return t


def skill_call(skill, uid="t1"):
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": uid,
                    "name": "Skill",
                    "input": {"skill": skill},
                }
            ]
        },
    }


def tool_result(uid="t1", error=False):
    return {
        "type": "user",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": uid, "is_error": error}]
        },
    }


TYPED = {
    "type": "user",
    "message": {"content": "<command-name>/egm:egm_review</command-name>"},
}
REVIEWER = {"subagent_type": "egm:egm-structural", "prompt": "review"}


def test_egm_skill_asks():
    out = guard("Skill", {"skill": "egm:egm_review"})
    assert (
        out["permissionDecision"] == "ask"
        and "design work" in out["permissionDecisionReason"]
    )


@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("Skill", {"skill": "mattpocock-skills:tdd"}),
        ("Agent", {"subagent_type": "general-purpose", "prompt": "x"}),
        ("Agent", {"subagent_type": "Explore", "prompt": "x"}),
        ("Bash", {"command": "ls"}),
    ],
)
def test_other_tools_pass(tool, tool_input):
    assert guard(tool, tool_input) is None


def test_reviewer_runs_after_approved_skill(tmp_path):
    t = transcript(tmp_path, skill_call("egm:egm_review"), tool_result())
    assert guard("Agent", REVIEWER, t) is None


def test_reviewer_runs_after_user_typed_command(tmp_path):
    assert guard("Agent", REVIEWER, transcript(tmp_path, TYPED)) is None


@pytest.mark.parametrize(
    "entries",
    [
        [],  # no EGM in this session
        [skill_call("egm:egm_review"), tool_result(error=True)],  # user said no
        [skill_call("egm:egm_review")],  # asked, no answer yet
        [skill_call("mattpocock-skills:tdd"), tool_result()],  # another skill
    ],
    ids=["empty", "denied", "pending", "other-skill"],
)
def test_reviewer_asks_without_an_egm_start(tmp_path, entries):
    out = guard("Agent", REVIEWER, transcript(tmp_path, *entries))
    assert out["permissionDecision"] == "ask"


def test_reviewer_asks_without_a_transcript(tmp_path):
    assert guard("Agent", REVIEWER)["permissionDecision"] == "ask"
    assert (
        guard("Agent", REVIEWER, tmp_path / "missing.jsonl")["permissionDecision"]
        == "ask"
    )


def test_hook_runs_on_skill_and_agent():
    pre = json.loads((HOOKS / "hooks.json").read_text())["hooks"]["PreToolUse"]
    entry = next(e for e in pre if "guard_egm.py" in e["hooks"][0]["command"])
    assert entry["matcher"] == "Skill|Agent"


def test_silent_without_an_egm_plugin(tmp_path):
    # No EGM plugin: no `egm:` skill or agent exists, so no call matches and nothing is asked
    for tool, inp in [
        ("Skill", {"skill": "writing-skills:ste-visual-first"}),
        ("Agent", {"subagent_type": "general-purpose"}),
        ("Bash", {"command": "ls"}),
    ]:
        assert guard(tool, inp) is None
