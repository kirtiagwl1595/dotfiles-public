"""loop_hook.py: the typed commands (prompt), the evidence record, and each Stop row (§11, §12)."""

import json
import shutil
import time
from datetime import datetime, timedelta, timezone

import _loop
import pytest
from loop_fixtures import (
    FEATURES,
    LOOP_MARKS,
    LOOP_MD,
    PROGRESS,
    VERIFY,
    confirm,
    git,
    personal,
    prompt,
    record,
    stop,
    team_origin,
    write_loop_files,
)
from loop_fixtures import LOOP_CMD as CMD

pytestmark = LOOP_MARKS


def context(out):
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


def state(env):
    return _loop.load_state(env.wt)


def evidence(env, exits):
    wt = env.wt
    spec = _loop.split_spec((wt / ".loop/LOOP.md").read_text(encoding="utf-8"))[0]
    feats = json.loads((wt / ".loop/loop-features.json").read_text(encoding="utf-8"))
    ev = {
        "content": _loop.content_hash(wt),
        "spec_sha": _loop.sha(spec),
        "features_sha": _loop.features_sha(feats),
        "checks": [{"id": f["id"], "exit": e} for f, e in zip(feats, exits)],
        "score": sum(e == 0 for e in exits),
        "total": len(exits),
        "truncated": False,
    }
    return "some output\n" + _loop.EVIDENCE_TAG + json.dumps(ev) + "\n"


def blocked(out):
    return out.get("decision") == "block"


def baseline(env, exits=(1, 0)):
    confirm(env)
    record(env, evidence(env, exits))
    assert state(env)["baseline"], "baseline not recorded"


def iterate(env, n, exits, text="echo ok\n"):
    """One agent turn: cause and decision, an edit, a verify run."""
    progress = env.wt / ".loop/loop-progress.md"
    old = progress.read_text(encoding="utf-8") if progress.exists() else ""
    progress.write_text(old + PROGRESS.format(n=n), encoding="utf-8")
    (env.wt / "tool.sh").write_text(text, encoding="utf-8")
    record(env, evidence(env, exits))


def edit_state(env, **fields):
    s = state(env)
    s.update(fields)
    _loop.save_state(s)


# ── prompt: confirm ─────────────────────────────────────────────────────────
def test_confirm_creates_the_loop(loop_env):
    out = confirm(loop_env)
    s = state(loop_env)
    wt = loop_env.wt
    assert s["status"] == "running" and s["slug"] == "demo"
    assert s["profile"] == "personal" and s["session_id"] == "s1"
    assert git(wt, "symbolic-ref", "--short", "HEAD") == "loop/demo"
    assert git(wt, "log", "-1", "--format=%s") == "loop(demo) #0: setup"
    assert s["base"] == git(wt, "rev-parse", "HEAD")
    assert (wt / ".loop/bin/loopctl.py").exists() and (
        wt / ".loop/bin/_loop.py"
    ).exists()
    assert s["bin_sha"] == _loop.bin_sha(wt)
    assert s["base_content"] == _loop.content_hash(wt)
    assert "keep.txt" in s["scope_protected"]
    assert (
        json.loads((wt / ".loop/run.json").read_text(encoding="utf-8"))["base"]
        == s["base"]
    )
    assert VERIFY in context(out)
    # .loop/ is never committed
    assert ".loop" not in git(wt, "show", "--name-only", "--format=", "HEAD")


def test_confirm_needs_a_linked_worktree(loop_env):
    personal(loop_env.home, loop_env.main)
    write_loop_files(loop_env.main)
    payload_env = type(loop_env)(**{**vars(loop_env), "wt": loop_env.main})
    _, out, _ = prompt(payload_env, f"{CMD} confirm")
    assert blocked(out) and "worktree" in out["reason"]
    assert _loop.load_state(loop_env.main) is None


def test_confirm_needs_the_loop_files(loop_env):
    personal(loop_env.home, loop_env.main)
    _, out, _ = prompt(loop_env, f"{CMD} confirm")
    assert blocked(out) and "LOOP.md" in out["reason"]


def test_confirm_refuses_a_note_in_the_scope(loop_env):
    personal(loop_env.home, loop_env.main)
    md = LOOP_MD.replace("keep.txt", "keep.txt (the owner's notes)")
    write_loop_files(loop_env.wt, md)
    _, out, _ = prompt(loop_env, f"{CMD} confirm")
    assert blocked(out) and "keep.txt (the owner's notes)" in out["reason"]
    assert state(loop_env) is None


def test_confirm_refuses_a_symlinked_loop_folder(loop_env):
    personal(loop_env.home, loop_env.main)
    outside, staging = loop_env.tmp / "outside", loop_env.tmp / "staging"
    staging.mkdir()
    write_loop_files(staging)
    (staging / ".loop").rename(outside)
    (outside / "bin").mkdir()
    (outside / "bin/keep.txt").write_text("user file\n", encoding="utf-8")
    (loop_env.wt / ".loop").symlink_to(outside)
    _, out, _ = prompt(loop_env, f"{CMD} confirm")
    assert blocked(out) and "symlink" in out["reason"], out
    assert (outside / "bin/keep.txt").read_text(encoding="utf-8") == "user file\n"
    assert git(loop_env.wt, "symbolic-ref", "--short", "HEAD") == "worktree-demo"


def test_stop_never_writes_through_a_planted_symlink(loop_env):
    # The sandboxed agent runs `ln -s ~/.zshrc .loop/LOOP.md.tmp`; Stop rewrites the mirrors
    baseline(loop_env)
    outside = loop_env.tmp / "zshrc"
    outside.write_text("user file\n", encoding="utf-8")
    for name in ("LOOP.md.tmp", "loop-features.json.tmp", "run.json.tmp"):
        (loop_env.wt / ".loop" / name).symlink_to(outside)
    (loop_env.wt / ".loop/LOOP.md").write_text(
        "tampered\n", encoding="utf-8"
    )  # Stop row 5 restores it
    stop(loop_env)
    assert outside.read_text(encoding="utf-8") == "user file\n"
    assert "tampered" not in (loop_env.wt / ".loop/LOOP.md").read_text(encoding="utf-8")


def test_stop_refuses_a_loop_folder_swapped_for_a_symlink(loop_env):
    baseline(loop_env)
    outside = loop_env.tmp / "outside"
    (loop_env.wt / ".loop").rename(outside)
    (loop_env.wt / ".loop").symlink_to(outside)
    (outside / "LOOP.md").write_text("tampered\n", encoding="utf-8")
    out = stop(loop_env)
    assert (outside / "LOOP.md").read_text(encoding="utf-8") == "tampered\n"
    assert "symlink" in out.get("systemMessage", ""), out


def test_confirm_refuses_a_second_running_loop(loop_env):
    confirm(loop_env)
    _, out, _ = prompt(loop_env, f"{CMD} confirm")
    assert blocked(out) and "already" in out["reason"]


def test_rerun_after_done_archives_the_old_state(loop_env):
    confirm(loop_env)
    edit_state(loop_env, status="done")
    git(loop_env.wt, "switch", "-q", "-c", "next")
    git(loop_env.wt, "branch", "-q", "-D", "loop/demo")
    confirm(loop_env)
    assert state(loop_env)["status"] == "running"
    assert list((_loop.state_dir() / "archive").glob("*.json"))


@pytest.mark.parametrize("mode", ["auto", "bypassPermissions", "dontAsk"])
def test_work_profile_refuses_auto_modes(loop_env, mode):
    team_origin(loop_env)
    write_loop_files(loop_env.wt)
    _, out, _ = prompt(loop_env, f"{CMD} confirm", mode)
    assert blocked(out) and "manual or acceptEdits" in out["reason"]
    assert state(loop_env) is None


def test_work_profile_refuses_a_skill_target(loop_env):
    team_origin(loop_env)
    write_loop_files(
        loop_env.wt, LOOP_MD.replace("target_type: script", "target_type: skill")
    )
    _, out, _ = prompt(loop_env, f"{CMD} confirm", "acceptEdits")
    assert blocked(out) and "skill" in out["reason"]


def test_work_profile_confirms_in_accept_edits(loop_env):
    team_origin(loop_env)
    write_loop_files(loop_env.wt)
    _, out, _ = prompt(loop_env, f"{CMD} confirm", "acceptEdits")
    assert not blocked(out)
    assert state(loop_env)["profile"] == "work"


def test_other_prompts_pass_untouched(loop_env):
    for text in ["hello", f"please {CMD} confirm", "<agent-message from=x>"]:
        code, out, _ = prompt(loop_env, text)
        assert (code, out) == (0, {})


# ── prompt: allow, stop ─────────────────────────────────────────────────────
def test_allow_and_stop(loop_env):
    confirm(loop_env)
    prompt(loop_env, f"{CMD} allow tests/test_tool.py")
    assert state(loop_env)["approved_paths"] == ["tests/test_tool.py"]
    run = json.loads((loop_env.wt / ".loop/run.json").read_text(encoding="utf-8"))
    assert run["approved_paths"] == ["tests/test_tool.py"]
    prompt(loop_env, f"{CMD} stop")
    assert state(loop_env)["stop_requested"] is True


def test_allow_without_a_loop_says_so(loop_env):
    _, out, _ = prompt(loop_env, f"{CMD} allow x")
    assert blocked(out) and "no loop" in out["reason"]


# ── record ──────────────────────────────────────────────────────────────────
def test_record_stores_the_baseline(loop_env):
    confirm(loop_env)
    _, out, _ = record(loop_env, evidence(loop_env, [1, 0]))
    s = state(loop_env)
    assert s["baseline"] == {"prints-ok": 1, "runs": 0}
    assert s["best"] == 1
    assert "1/2" in context(out)


@pytest.mark.parametrize(
    "change",
    ["other command", "subfolder", "other session", "bin changed", "stale content"],
)
def test_record_ignores_evidence_it_cannot_trust(loop_env, change):
    confirm(loop_env)
    stdout = evidence(loop_env, [0, 0])
    kwargs = {}
    if change == "other command":
        kwargs["cmd"] = VERIFY + " && true"
    elif change == "subfolder":
        kwargs["cwd"] = loop_env.wt / "tests"
    elif change == "other session":
        kwargs["sid"] = "s2"
    elif change == "bin changed":
        (loop_env.wt / ".loop/bin/json.py").write_text("x", encoding="utf-8")
    else:
        (loop_env.wt / "tool.sh").write_text("echo ok\n", encoding="utf-8")
    record(loop_env, stdout, **kwargs)
    assert state(loop_env)["baseline"] == {}


# ── stop: part 1 guards ─────────────────────────────────────────────────────
def test_row0_no_loop_allows(loop_env):
    assert stop(loop_env) == {}


def test_row0_other_session_allows(loop_env):
    confirm(loop_env)
    assert stop(loop_env, sid="s2") == {}


def test_row0a_background_task_allows_without_change(loop_env):
    baseline(loop_env)
    before = state(loop_env)
    out = stop(loop_env, background_tasks=[{"id": "a", "status": "running"}])
    assert not blocked(out)
    assert state(loop_env) == before


def test_row1_off_switch_stops(loop_env, monkeypatch):
    baseline(loop_env)
    monkeypatch.setenv("CLAUDE_LOOP_OFF", "1")
    out = stop(loop_env)
    assert not blocked(out) and "stopped" in out["systemMessage"]
    assert state(loop_env)["status"] == "stopped"


def test_row1_typed_stop(loop_env):
    baseline(loop_env)
    prompt(loop_env, f"{CMD} stop")
    assert not blocked(stop(loop_env))
    assert state(loop_env)["status"] == "stopped"


def test_row2_done_allows(loop_env):
    baseline(loop_env)
    edit_state(loop_env, status="done")
    assert not blocked(stop(loop_env))


def test_row3_bundle_incomplete_blocks_then_gives_up(loop_env):
    baseline(loop_env)
    edit_state(loop_env, status="bundling")
    (loop_env.wt / ".loop/bundle.md").write_text(
        "## Goal and cause\nx\n", encoding="utf-8"
    )
    for _ in range(2):
        out = stop(loop_env)
        assert blocked(out) and "Debrief" in out["reason"]
    assert not blocked(stop(loop_env))
    assert state(loop_env)["status"] == "stopped"


def test_row3_complete_bundle_is_done(loop_env):
    baseline(loop_env)
    edit_state(loop_env, status="bundling")
    text = "".join(f"## {s}\nx\n" for s in _loop.BUNDLE_SECTIONS)
    (loop_env.wt / ".loop/bundle.md").write_text(text, encoding="utf-8")
    assert not blocked(stop(loop_env))
    assert state(loop_env)["status"] == "done"


def test_row4_stuck_goes_to_bundling(loop_env):
    baseline(loop_env)
    edit_state(loop_env, stuck=5)
    out = stop(loop_env)
    assert blocked(out) and "bundle" in out["reason"]
    assert state(loop_env)["status"] == "bundling"


def test_row5_mirror_is_restored(loop_env):
    baseline(loop_env)
    feats = loop_env.wt / ".loop/loop-features.json"
    feats.write_text(json.dumps([{**FEATURES[0], "passes": True}]), encoding="utf-8")
    out = stop(loop_env)
    assert blocked(out) and "belong to the hook" in out["reason"]
    assert json.loads(feats.read_text(encoding="utf-8")) == FEATURES
    assert state(loop_env)["stuck"] == 1


def test_row6_bin_is_restored(loop_env):
    baseline(loop_env)
    (loop_env.wt / ".loop/bin/json.py").write_text("x", encoding="utf-8")
    out = stop(loop_env)
    assert blocked(out)
    assert not (loop_env.wt / ".loop/bin/json.py").exists()
    assert _loop.bin_sha(loop_env.wt) == state(loop_env)["bin_sha"]


def test_row7_protected_change_blocks(loop_env):
    baseline(loop_env)
    (loop_env.wt / "tests/test_tool.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    out = stop(loop_env)
    assert blocked(out) and "tests/test_tool.py" in out["reason"]


def test_row7_approved_path_passes(loop_env):
    baseline(loop_env)
    prompt(loop_env, f"{CMD} allow tests/test_tool.py")
    (loop_env.wt / "tests/test_tool.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    assert "tests/test_tool.py" not in stop(loop_env).get("reason", "")


def test_row7_ignores_verify_output_files(loop_env):
    baseline(loop_env)
    stop(loop_env)  # the baseline turn
    (loop_env.wt / "tests/__pycache__").mkdir()
    (loop_env.wt / "tests/__pycache__/x.pyc").write_bytes(b"x")
    (loop_env.wt / ".pytest_cache").mkdir()
    iterate(loop_env, 1, [0, 0])
    out = stop(loop_env)
    assert state(loop_env)["iteration"] == 1
    assert "undo" not in out.get("reason", "")


def test_row8_no_baseline_blocks(loop_env):
    confirm(loop_env)
    out = stop(loop_env)
    assert blocked(out) and VERIFY in out["reason"]
    assert state(loop_env)["stuck"] == 1


def test_row8a_baseline_turn_blocks_once_without_counting(loop_env):
    baseline(loop_env)
    out = stop(loop_env)
    assert blocked(out) and "Iteration 1" in out["reason"]
    s = state(loop_env)
    assert (s["iteration"], s["no_improve"], s["stuck"]) == (0, 0, 0)
    # A second stop with no change is a judged iteration with no gain, not 8a again
    stop(loop_env)
    s = state(loop_env)
    assert (s["iteration"], s["no_improve"]) == (1, 1)


def test_row10_needs_cause_and_decision(loop_env):
    baseline(loop_env)
    stop(loop_env)
    (loop_env.wt / "tool.sh").write_text("echo ok\n", encoding="utf-8")
    record(loop_env, evidence(loop_env, [0, 0]))
    out = stop(loop_env)
    assert blocked(out) and "Cause:" in out["reason"]


def test_row11_needs_evidence_for_this_content(loop_env):
    baseline(loop_env)
    stop(loop_env)
    iterate(loop_env, 1, [0, 0])
    (loop_env.wt / "tool.sh").write_text("echo ok again\n", encoding="utf-8")
    out = stop(loop_env)
    assert blocked(out) and "verify" in out["reason"]


# ── stop: part 2 judge, part 3 decide ───────────────────────────────────────
def test_gain_is_kept_and_reaching_the_threshold_bundles(loop_env):
    baseline(loop_env)
    stop(loop_env)
    iterate(loop_env, 1, [0, 0])
    out = stop(loop_env)
    s = state(loop_env)
    wt = loop_env.wt
    assert git(wt, "log", "-1", "--format=%s").startswith(
        "loop(demo) #1: tool.sh prints"
    )
    assert (wt / "tool.sh").read_text(encoding="utf-8") == "echo ok\n"
    assert s["best"] == 2 and s["iteration"] == 1 and s["status"] == "bundling"
    assert all(
        f["passes"]
        for f in json.loads(
            (wt / ".loop/loop-features.json").read_text(encoding="utf-8")
        )
    )
    assert blocked(out) and "bundle" in out["reason"]
    assert (
        "#1"
        in (wt / ".loop/LOOP.md")
        .read_text(encoding="utf-8")
        .split(_loop.LOG_HEADING)[1]
    )
    # The hook ran the diff gate; loopctl bundle reads it from run.json
    gate = json.loads((wt / ".loop/run.json").read_text(encoding="utf-8"))["gate"]
    assert gate["verdict"] == "pass" and gate["files"] == ["tool.sh"]


@pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks is not installed")
def test_gitleaks_scans_a_linked_worktree(loop_env):
    # The gate scans the git common dir (the main checkout's .git) with the head commit
    wt = loop_env.wt
    baseline(loop_env)
    stop(loop_env)
    iterate(loop_env, 1, [0, 0], text="echo ok  # " + "AKIA" + "QYLPMTMXQ7ABCDEF\n")
    stop(loop_env)
    gate = json.loads((wt / ".loop/run.json").read_text(encoding="utf-8"))["gate"]
    assert gate["secret_scanner"] == "gitleaks", gate
    assert any("gitleaks" in f["text"] for f in gate["rejects"]), gate


def test_the_gate_judges_the_setup_commit(loop_env):
    # The setup may change the target (tool.sh) and add tests; a stray file is rejected
    wt = loop_env.wt
    (wt / "tool.sh").write_text("echo no  # setup\n", encoding="utf-8")
    (wt / "tests/test_more.py").write_text(
        "def test_more():\n    assert True\n", encoding="utf-8"
    )
    (wt / "sh-thd-1").write_text("", encoding="utf-8")
    baseline(loop_env)
    stop(loop_env)
    iterate(loop_env, 1, [0, 0])
    stop(loop_env)
    gate = json.loads((wt / ".loop/run.json").read_text(encoding="utf-8"))["gate"]
    assert [f["file"] for f in gate["rejects"]] == ["sh-thd-1"], gate


def test_no_gain_is_reverted(loop_env):
    baseline(loop_env)
    stop(loop_env)
    iterate(loop_env, 1, [1, 0], text="echo nope\n")
    out = stop(loop_env)
    s = state(loop_env)
    wt = loop_env.wt
    assert (wt / "tool.sh").read_text(encoding="utf-8") == "echo no\n"
    assert git(wt, "log", "-1", "--format=%s").startswith("Revert")
    assert (s["no_improve"], s["best"], s["status"]) == (1, 1, "running")
    assert (
        blocked(out) and "Iteration 2" in out["reason"] and "prints-ok" in out["reason"]
    )


def test_regression_is_reverted(loop_env):
    baseline(loop_env)
    stop(loop_env)
    iterate(loop_env, 1, [0, 1])
    stop(loop_env)
    assert (loop_env.wt / "tool.sh").read_text(encoding="utf-8") == "echo no\n"


def test_failed_commit_changes_no_score_and_reverts_nothing(loop_env):
    baseline(loop_env)
    stop(loop_env)
    head = git(loop_env.wt, "rev-parse", "HEAD")
    iterate(loop_env, 1, [1, 0], text="echo nope\n")
    lock = loop_env.wt / git(loop_env.wt, "rev-parse", "--git-path", "index.lock")
    lock.write_text("", encoding="utf-8")
    out = stop(loop_env)
    s = state(loop_env)
    assert blocked(out) and "commit" in out["reason"]
    assert (s["stuck"], s["best"], s["iteration"], s["no_improve"]) == (1, 1, 0, 0)
    assert git(loop_env.wt, "rev-parse", "HEAD") == head  # the setup commit stays


def test_off_the_loop_branch_counts_as_stuck(loop_env):
    baseline(loop_env)
    stop(loop_env)
    git(loop_env.wt, "switch", "-q", "-c", "elsewhere")
    iterate(loop_env, 1, [0, 0])
    out = stop(loop_env)
    assert blocked(out) and "loop/demo" in out["reason"]
    assert state(loop_env)["stuck"] == 1


def test_revert_then_unchanged_counts_as_no_gain(loop_env):
    baseline(loop_env)
    stop(loop_env)
    iterate(loop_env, 1, [1, 0], text="echo nope\n")
    stop(loop_env)
    out = stop(loop_env)  # the agent stops again without an edit
    s = state(loop_env)
    assert (s["iteration"], s["no_improve"], s["status"]) == (2, 2, "bundling")
    assert blocked(out) and "no gain" in out["reason"]


def test_iteration_cap_bundles(loop_env):
    baseline(loop_env)
    stop(loop_env)
    edit_state(loop_env, iteration=2)
    iterate(loop_env, 3, [1, 0], text="echo maybe\n")
    out = stop(loop_env)
    assert state(loop_env)["status"] == "bundling"
    assert "cap" in out["reason"]


def test_usage_limit_bundles(loop_env):
    baseline(loop_env)
    stop(loop_env)
    limits = {
        "five_hour": {"used_percentage": 93},
        "seven_day": {"used_percentage": 10},
    }
    _loop.atomic_write(_loop.state_dir() / "rate_limits.json", json.dumps(limits))
    stop(loop_env)
    assert state(loop_env)["status"] == "bundling"
    assert state(loop_env)["usage_stop"] is True


# ── tokens (§11.4) ──────────────────────────────────────────────────────────
def stamp(offset):
    """A transcript timestamp as Claude Code writes it: UTC, milliseconds, a trailing Z."""
    t = datetime.now(timezone.utc) + timedelta(seconds=offset)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def turn(msg_id, offset, output, cache_read=0):
    usage = {
        "input_tokens": 3,
        "output_tokens": output,
        "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": cache_read,
    }
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": stamp(offset),
            "message": {"id": msg_id, "role": "assistant", "usage": usage},
        }
    )


def transcript(env):
    """A main transcript and one subagent transcript, as Claude Code lays them out."""
    main = env.tmp / "session.jsonl"
    lines = [
        turn("before", -3600, 999),  # before confirm: not this loop
        turn("m1", 60, 10, cache_read=5000),
        turn("m1", 61, 10, cache_read=5000),  # one message, two content blocks
        json.dumps({"type": "user", "timestamp": stamp(62), "message": {}}),
        "not json",
        turn("m2", 63, 20),
    ]
    main.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sub = env.tmp / "session/subagents/agent-a1.jsonl"
    sub.parent.mkdir(parents=True)
    sub.write_text(turn("s1", 64, 40) + "\n", encoding="utf-8")
    return str(main)


SUMS = {
    "input_tokens": 9,
    "output_tokens": 70,
    "cache_creation_input_tokens": 300,
    "cache_read_input_tokens": 5000,
    "messages": 3,
}


def test_stop_sums_the_tokens_of_this_loop(loop_env):
    baseline(loop_env)
    stop(loop_env, transcript_path=transcript(loop_env))
    assert state(loop_env)["usage"] == SUMS
    run = json.loads((loop_env.wt / ".loop/run.json").read_text(encoding="utf-8"))
    assert run["usage"] == SUMS and run["usage_stop"] is False


def test_a_finished_loop_counts_no_more_tokens(loop_env):
    baseline(loop_env)
    edit_state(loop_env, status="done", usage={"output_tokens": 1})
    stop(loop_env, transcript_path=transcript(loop_env))
    assert state(loop_env)["usage"] == {"output_tokens": 1}


def test_an_unreadable_transcript_keeps_the_last_count(loop_env):
    baseline(loop_env)
    edit_state(loop_env, usage={"output_tokens": 1})
    out = stop(loop_env, transcript_path=str(loop_env.tmp / "gone.jsonl"))
    assert state(loop_env)["usage"] == {"output_tokens": 1}
    assert blocked(out)  # the loop goes on


# ── approve (§12.1) ─────────────────────────────────────────────────────────
APPROVE = "/safe-lean:loop-approve"


def finished(env, **fields):
    """A done loop with a bundle and a lesson."""
    baseline(env)
    edit_state(env, status="done", **fields)
    (env.wt / ".loop/bundle.md").write_text("# Loop bundle: demo\n", encoding="utf-8")
    (env.wt / ".loop/lesson.md").write_text(
        "# What the loop taught\n", encoding="utf-8"
    )


def run_dir(env):
    return env.main / ".claude/loop-runs" / f"{time.strftime('%Y-%m-%d')}-demo"


def archived(env):
    return list((_loop.state_dir() / "archive").glob("*.json"))


@pytest.mark.parametrize("where", ["wt", "main"])
def test_approve_branches_copies_and_archives(loop_env, where):
    usage = {"input_tokens": 9, "output_tokens": 26500, "messages": 3}
    finished(loop_env, usage=usage)
    _, out, _ = prompt(loop_env, f"{APPROVE} demo", cwd=getattr(loop_env, where))
    text = context(out)
    assert "feature/loop-demo" in text and "output 26,500" in text, out
    tip = git(loop_env.wt, "rev-parse", "loop/demo")
    assert git(loop_env.wt, "rev-parse", "feature/loop-demo") == tip
    assert (run_dir(loop_env) / "bundle.md").read_text(
        encoding="utf-8"
    ) == "# Loop bundle: demo\n"
    assert "## Goal" in (run_dir(loop_env) / "LOOP.md").read_text(encoding="utf-8")
    run = json.loads((run_dir(loop_env) / "run.json").read_text(encoding="utf-8"))
    assert run["usage"] == usage
    lesson = (
        loop_env.main
        / ".claude/lessons"
        / f"{run_dir(loop_env).name[:10]}-loop-demo.md"
    )
    assert lesson.read_text(encoding="utf-8") == "# What the loop taught\n"
    assert state(loop_env) is None and len(archived(loop_env)) == 1


def test_approve_message_carries_the_summary(loop_env):
    # A worktree session cannot read the copied bundle in the main checkout: the hook,
    # which runs outside the sandbox, puts what the operator approves in its message
    gate = {
        "verdict": "pass",
        "rejects": [],
        "warnings": [],
        "secret_scanner": "gitleaks",
    }
    finished(loop_env, best=2, gate=gate)
    (loop_env.wt / ".loop/bundle.md").write_text(
        "## Reviewer answers\n1. Root cause.\n\nVerdict: accept with risks\n",
        encoding="utf-8",
    )
    _, out, _ = prompt(loop_env, f"{APPROVE} demo")
    text = context(out)
    for part in (
        "Goal: Make tool.sh print ok.",
        "Scores: before 1/2, after 2/2",
        "Gate: pass (secret scanner: gitleaks)",
        "Reviewer: Verdict: accept with risks",
        f"{run_dir(loop_env).name}/bundle.md",
    ):
        assert part in text, (part, text)


def test_approve_reads_a_0_6_0_state(loop_env):
    """Pilot 1 ran on 0.6.0: no usage_stop, no token count, a gate without secret_scanner."""
    finished(
        loop_env, usage={}, gate={"verdict": "pass", "rejects": [], "warnings": []}
    )
    s = state(loop_env)
    s.pop("usage_stop", None)
    _loop.save_state(s)
    (loop_env.wt / ".loop/lesson.md").unlink()
    _, out, _ = prompt(loop_env, f"{APPROVE} demo")
    assert "feature/loop-demo" in context(out), out
    assert "no lesson" in context(out) and "not counted" in context(out)
    assert "secret scanner: not recorded" in context(out)
    assert "Reviewer: no verdict line" in context(out)


@pytest.mark.parametrize(
    ("setup", "typed", "why"),
    [
        (lambda env: baseline(env), "demo", "running"),
        (lambda env: finished(env), "other", "No finished loop other"),
        (lambda env: finished(env), "", "demo"),  # no slug: name the finished loops
        (
            lambda env: (finished(env), git(env.wt, "branch", "feature/loop-demo")),
            "demo",
            "feature/loop-demo",
        ),
    ],
)
def test_approve_refuses_and_changes_nothing(loop_env, setup, typed, why):
    setup(loop_env)
    before = state(loop_env)
    _, out, _ = prompt(loop_env, f"{APPROVE} {typed}".strip())
    assert blocked(out) and why in out["reason"], out
    assert state(loop_env) == before and not run_dir(loop_env).exists()


def test_hook_failure_fails_open(loop_env):
    baseline(loop_env)
    _loop.state_path(loop_env.wt).write_text(
        '{"worktree": 1, "status": "running", "session_id": "s1"}', encoding="utf-8"
    )
    out = stop(loop_env)
    assert not blocked(out) and "loop hook failed" in out["systemMessage"]
