"""churn_watch (PostToolUse Edit|Write|MultiEdit|Skill): nudge a step back when one file keeps changing, and log it."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "claude" / "hooks" / "churn_watch.py"


@pytest.fixture
def env(tmp_path):
    return {**os.environ, "TMPDIR": str(tmp_path), "XDG_STATE_HOME": str(tmp_path)}


def log_lines(env):
    log = Path(env["XDG_STATE_HOME"]) / "safe-lean" / "churn.jsonl"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def edit(env):
    def run(file_path="/repo/a.py", session="s1", tool="Edit", tool_input=None):
        payload = {
            "session_id": session,
            "cwd": "/repo",
            "tool_name": tool,
            "tool_input": tool_input or {"file_path": file_path},
        }
        p = subprocess.run(
            [sys.executable, "-B", str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        return p.returncode, p.stdout

    return run


def nudge(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else None


def test_fourth_edit_of_one_file_nudges(edit):
    outs = [edit()[1] for _ in range(4)]
    assert outs[:3] == ["", "", ""]
    assert "step-back" in (nudge(outs[3]) or "")
    assert json.loads(outs[3])["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_nudges_only_at_the_fourth_and_eighth_edit(edit):
    nudged = [n for n in range(1, 11) if edit(tool="MultiEdit")[1]]
    assert nudged == [4, 8]


def test_files_outside_the_repo_never_nudge(edit):
    # plans, memory and scratch notes change often by design
    assert [edit(file_path="/home/.claude/plans/p.md")[1] for _ in range(8)] == [""] * 8


@pytest.mark.parametrize(
    "other",
    [{"file_path": "/repo/b.py"}, {"session": "s2"}],
    ids=["other-file", "other-session"],
)
def test_counts_each_file_and_session_apart(edit, other):
    for _ in range(3):
        edit()
    assert edit(**other)[1] == ""


@pytest.mark.parametrize("raw", ["not json", "[]", '{"session_id": "s1"}'])
def test_bad_input_is_quiet_and_exits_0(tmp_path, raw):
    p = subprocess.run(
        [sys.executable, "-B", str(HOOK)],
        input=raw,
        capture_output=True,
        text=True,
        env={**os.environ, "TMPDIR": str(tmp_path)},
        check=False,
    )
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")


def test_each_nudge_is_logged(edit, env):
    for _ in range(8):
        edit()
    got = [
        (e["event"], e["session"], e["repo"], e["file"], e["edits"])
        for e in log_lines(env)
    ]
    assert got == [
        ("nudge", "s1", "/repo", "/repo/a.py", 4),
        ("nudge", "s1", "/repo", "/repo/a.py", 8),
    ]


@pytest.mark.parametrize(
    "skill,logged",
    [
        ("safe-lean:step-back", True),
        ("step-back", True),
        ("safe-lean:token-report", False),
    ],
)
def test_only_step_back_skill_calls_are_logged(edit, env, skill, logged):
    code, out = edit(tool="Skill", tool_input={"skill": skill})
    assert (code, out) == (0, "")
    events = log_lines(env) if logged else []
    assert [e["event"] for e in events] == (["step-back"] if logged else [])


def report(env):
    p = subprocess.run(
        [sys.executable, "-B", str(HOOK), "report"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return p.returncode, p.stdout


def test_report_counts_step_back_after_a_nudge(edit, env):
    # s1: nudge, then step-back; s2: nudge only; s3: step-back with no nudge (the rule fired)
    for _ in range(4):
        edit(session="s1")
    edit(session="s1", tool="Skill", tool_input={"skill": "safe-lean:step-back"})
    for _ in range(4):
        edit(session="s2", file_path="/repo/b.py")
    edit(session="s3", tool="Skill", tool_input={"skill": "step-back"})
    code, out = report(env)
    assert code == 0
    assert "nudges: 2 in 2 sessions" in out
    assert "step-back after a nudge: 1 of 2 sessions" in out
    assert "step-back without a nudge: 1 session" in out


def test_report_without_a_log_says_so(env):
    assert report(env) == (0, "No churn_watch events logged yet.\n")
