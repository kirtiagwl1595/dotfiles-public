#!/usr/bin/env python3
"""The loop's hooks (docs/loop-engineering.md §11, §12).

  loop_hook.py prompt   UserPromptSubmit: the typed commands confirm, allow, stop
  loop_hook.py record   PostToolUse on Bash: store the verifier's evidence line
  loop_hook.py stop     Stop: guards, then judge (commit or revert), then decide

Only these hooks write the state file, the .loop/ mirrors and the loop branch. The Stop
hook fails open: a crash must not trap the session in a loop.
"""

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import _loop

HERE = Path(__file__).resolve().parent
BIN_SOURCES = (HERE.parent / "loopctl.py", HERE / "_loop.py")
CMD = "/safe-lean:loop-engineer"
APPROVE = "/safe-lean:loop-approve"
FINISHED = ("done", "stopped")
SAFE_GIT = ("-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false")
TARGET_TYPES = ("skill", "script", "task")
USAGE_LIMIT = 90
MAX_STUCK = 5
MAX_BUNDLE_BLOCKS = 3


class Refused(Exception):
    """A typed command that cannot run; the reason goes back to the operator."""


# ── output ──────────────────────────────────────────────────────────────────
def emit(obj):
    if obj:
        print(json.dumps(obj))


def block(reason):
    return {"decision": "block", "reason": reason}


def context(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


# ── git and mirrors ─────────────────────────────────────────────────────────
def safe_git(wt, *args):
    return _loop.git(wt, *SAFE_GIT, *args)


def pathspec():
    out = [".", ":(exclude).loop"]
    return out + [f":(exclude,glob)**/{p}" for p in _loop.TOOL_OUTPUT]


def commit(wt, message, allow_empty=False):
    """Commit every counted change; True when a commit was made."""
    safe_git(wt, "add", "-A", "--", *pathspec())
    extra = ["--allow-empty"] if allow_empty else []
    done = safe_git(wt, "commit", "-q", "--no-verify", *extra, "-m", message)
    return done.returncode == 0


def on_loop_branch(state):
    """Hooks write git only on loop/<slug> in a linked worktree (§7)."""
    wt = state["worktree"]
    branch = _loop.git(wt, "symbolic-ref", "--short", "HEAD").stdout.strip()
    return branch == state["branch"] and linked(wt)


def linked(wt):
    dirs = _loop.git(
        wt,
        "rev-parse",
        "--path-format=absolute",
        "--git-dir",
        "--git-common-dir",
    ).stdout.split()
    return len(dirs) == 2 and dirs[0] != dirs[1]


def run_view(state):
    """.loop/run.json: what loopctl needs and cannot read from the state file (sandbox)."""
    keys = (
        "slug",
        "base",
        "approved_paths",
        "scope_protected",
        "self_protect",
        "baseline",
        "best",
        "iteration",
        "max_iterations",
        "status",
        "log",
        "gate",
        "usage",
        "usage_stop",
    )
    return {k: state.get(k) for k in keys}


def mirror_texts(state):
    log = "".join(f"{line}\n" for line in state["log"])
    return {
        ".loop/LOOP.md": f"{state['spec_text']}{_loop.LOG_HEADING}\n{log}",
        ".loop/loop-features.json": json.dumps(state["features"], indent=2) + "\n",
        ".loop/run.json": json.dumps(run_view(state), indent=2) + "\n",
    }


def write_mirrors(state):
    for rel, text in mirror_texts(state).items():
        _loop.atomic_write(Path(state["worktree"]) / rel, text, root=state["worktree"])


def mirrors_differ(state):
    wt = Path(state["worktree"])
    for rel, text in mirror_texts(state).items():
        try:
            if (wt / rel).read_text(encoding="utf-8") != text:
                return True
        except OSError:
            return True
    return False


def copy_bin(wt):
    folder = Path(wt) / ".loop/bin"
    _loop.real_folder(wt, folder)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for src in BIN_SOURCES:
        shutil.copy(src, folder / src.name)
    return _loop.bin_sha(wt)


def save(state):
    _loop.save_state(state)
    write_mirrors(state)


# ── prompt ──────────────────────────────────────────────────────────────────
def read_spec(wt):
    try:
        # Before any branch or commit: confirm writes .loop/bin and the mirrors
        _loop.real_folder(wt, wt / ".loop/bin")
    except _loop.Unsafe as e:
        raise Refused(str(e)) from e
    try:
        text = (wt / ".loop/LOOP.md").read_text(encoding="utf-8")
        features = json.loads(
            (wt / ".loop/loop-features.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as e:
        raise Refused(
            f"Write .loop/LOOP.md and .loop/loop-features.json first ({e})."
        ) from e
    meta = _loop.frontmatter(text)
    if meta.get("target_type") not in TARGET_TYPES:
        raise Refused(f"LOOP.md target_type must be one of {', '.join(TARGET_TYPES)}.")
    if not meta.get("slug") or meta["slug"] != _loop.slug("skill", meta["slug"]):
        raise Refused("LOOP.md slug must be lower case with hyphens.")
    problem = _loop.spec_problem(text, features, wt)
    if problem:
        raise Refused(problem)
    return text, meta, features


def check_profile(profile, meta, mode):
    if profile != "work":
        return
    if meta["target_type"] == "skill":
        raise Refused(
            "The work profile does not run skill targets (the eval runs unsandboxed)."
        )
    if mode in _loop.AUTO_MODES:
        raise Refused(
            f"Permission mode is {mode}: switch to manual or acceptEdits mode."
        )


def archive_old(wt):
    old = _loop.load_state(wt)
    if old and old.get("status") in _loop.ACTIVE:
        raise Refused(f"A loop already runs here. Type `{CMD} stop` first.")
    if old:
        archive_state(wt)


def archive_state(wt):
    """Move the state file to loops/archive/, so that a new loop can start here."""
    dest = _loop.state_dir() / "archive" / f"{_loop.key(wt)}-{int(time.time())}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(_loop.state_path(wt), dest)


def holds_engine(wt):
    """True in a repo that holds the loop engine itself (this repo, or a fork of it).

    The loop must not change its own hooks, agents and judges there (§7). The check is
    on content, not on a path, so that a clone in any folder counts.
    """
    main = _loop.main_checkout(wt)
    return all(
        (main / rel).is_file() for rel in ("claude/loopctl.py", "claude/hooks/_loop.py")
    )


def new_state(wt, data, text, meta, features, profile):
    spec = _loop.split_spec(text)[0]
    cap = meta.get("max_iterations", "5")
    return {
        "version": 1,
        "slug": meta["slug"],
        "worktree": str(wt),
        "branch": f"loop/{meta['slug']}",
        "session_id": data.get("session_id"),
        "profile": profile,
        "target_type": meta["target_type"],
        "target": meta.get("target", ""),
        "confirm_time": int(time.time()),
        "max_iterations": int(cap) if cap.isdigit() else 5,
        "threshold": meta.get("threshold", "all"),
        "spec_text": spec,
        "spec_sha": _loop.sha(spec),
        "features": features,
        "features_sha": _loop.features_sha(features),
        "scope_protected": _loop.must_not_change(spec),
        "self_protect": holds_engine(wt),
        "baseline": {},
        "status": "running",
        "iteration": 0,
        "best": None,
        "no_improve": 0,
        "stuck": 0,
        "last_judged": None,
        "evidence": None,
        "approved_paths": [],
        "stop_requested": False,
        "bundle_blocks": 0,
        "log": [],
        "gate": None,
        "usage": {},
    }


def confirm(wt, data):
    if not linked(wt):
        raise Refused(
            "Run confirm in a linked git worktree (EnterWorktree loop-<slug>)."
        )
    text, meta, features = read_spec(wt)
    profile = _loop.profile_for(wt)
    check_profile(profile, meta, data.get("permission_mode"))
    archive_old(wt)
    state = new_state(wt, data, text, meta, features, profile)
    switched = safe_git(wt, "switch", "-q", "-c", state["branch"])
    if switched.returncode != 0:
        raise Refused(f"Could not create {state['branch']}: {switched.stderr.strip()}")
    commit(wt, f"loop({state['slug']}) #0: setup", allow_empty=True)
    state["base"] = _loop.git(wt, "rev-parse", "HEAD").stdout.strip()
    state["bin_sha"] = copy_bin(wt)
    state["base_content"] = _loop.content_hash(wt)
    save(state)
    return (
        f"Loop {state['slug']} confirmed ({profile} profile) on {state['branch']}. "
        f"Now run {verify_step(state)}, for the baseline. Do not edit any file before it."
    )


def running_state(wt):
    state = _loop.load_state(wt)
    if not state or state.get("status") not in _loop.ACTIVE:
        raise Refused("There is no loop running in this worktree.")
    return state


def allow(wt, path):
    state = running_state(wt)
    rel = os.path.relpath(os.path.join(str(wt), path), str(wt))
    if rel.startswith(".."):
        raise Refused(f"{path} is outside the worktree.")
    if rel not in state["approved_paths"]:
        state["approved_paths"].append(rel)
    save(state)
    return f"The operator approved changes to {rel} for this loop."


def request_stop(wt):
    state = running_state(wt)
    state["stop_requested"] = True
    save(state)
    return "The operator asked the loop to stop. Finish this step and stop."


def repo_loops(main):
    """The state files of the loops whose worktree belongs to the main checkout `main`."""
    out = []
    for path in sorted(_loop.state_dir().glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # rate_limits.json and broken files are no loops
        wt = state.get("worktree") if isinstance(state, dict) else None
        if (
            isinstance(wt, str)
            and os.path.isdir(wt)
            and same_path(_loop.main_checkout(wt), main)
        ):
            out.append(state)
    return out


def same_path(a, b):
    return os.path.realpath(str(a)) == os.path.realpath(str(b))


def approve(root, slug):
    """§12.1: the typed approval. Nothing is pushed; the operator reviews the branch."""
    main = _loop.main_checkout(root)
    loops = repo_loops(main)
    found = [s for s in loops if s.get("slug") == slug]
    if len(found) != 1:
        names = ", ".join(s["slug"] for s in loops if s.get("status") in FINISHED)
        raise Refused(
            f"No finished loop {slug or '(no slug typed)'} in this repo. "
            f"Finished loops: {names or 'none'}. Type `{APPROVE} <slug>`."
        )
    state = found[0]
    if state["status"] not in FINISHED:
        raise Refused(
            f"Loop {slug} is {state['status']}: approve needs done or stopped."
        )
    wt = Path(state["worktree"])
    branch = f"feature/loop-{slug}"
    made = _loop.git(wt, "branch", branch, state["branch"])
    if made.returncode != 0:
        raise Refused(f"Could not create {branch}: {made.stderr.strip()}")
    day = time.strftime("%Y-%m-%d")
    copied, lesson = copy_run(state, main, day)
    archive_state(wt)
    tokens = _loop.token_text(state.get("usage")) or "not counted"
    return (
        f"Approved loop {slug}: {branch} is at the tip of {state['branch']}. "
        f"Copied {', '.join(copied)} to .claude/loop-runs/{day}-{slug}/ in {main}, "
        f"and {lesson}. Final tokens from confirm: {tokens}. "
        "The loop state is archived. Nothing was pushed.\n"
        + summary(state, f".claude/loop-runs/{day}-{slug}/bundle.md")
    )


def summary(state, bundle_rel):
    """What the operator approved. A worktree session often cannot read the main
    checkout, so the copied bundle may be out of its reach; this message is not."""
    gate = state.get("gate") or {}
    bundle = read_or_none(Path(state["worktree"]) / ".loop/bundle.md") or ""
    verdict = next(
        (x.strip() for x in bundle.splitlines() if x.startswith("Verdict:")),
        "no verdict line",
    )
    goal = _loop.sections(state.get("spec_text", "")).get("Goal", "").strip()
    scanner = gate.get("secret_scanner", "not recorded")
    gate_text = f"{gate.get('verdict', 'not run')} (secret scanner: {scanner})"
    return "\n".join(
        [
            f"Goal: {goal}",
            "Scores: "
            + _loop.score_text(
                state.get("baseline"), state.get("best"), len(state["features"])
            ),
            f"Gate: {gate_text}",
            f"Reviewer: {verdict}",
            f"Open risks: the Debrief in {bundle_rel}",
        ]
    )


def read_or_none(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def copy_run(state, main, day):
    """Copy the run record and the lesson to the main checkout; the names copied."""
    loop = Path(state["worktree"]) / ".loop"
    texts = mirror_texts(state)
    files = {
        "LOOP.md": texts[".loop/LOOP.md"],
        "run.json": texts[".loop/run.json"],  # the final token count
        "bundle.md": read_or_none(loop / "bundle.md"),
    }
    copied = [name for name, text in files.items() if text is not None]
    for name in copied:
        _loop.atomic_write(
            main / ".claude/loop-runs" / f"{day}-{state['slug']}" / name, files[name]
        )
    lesson = read_or_none(loop / "lesson.md")
    if lesson is None:
        return copied, "no lesson (no .loop/lesson.md)"
    rel = f".claude/lessons/{day}-loop-{state['slug']}.md"
    _loop.atomic_write(main / rel, lesson)
    return copied, f"the lesson to {rel}"


def typed_action(text, wt, data):
    """The hook's part of a typed command, or None when the skill handles the text."""
    if text == APPROVE or text.startswith(APPROVE + " "):
        return lambda: approve(wt, text[len(APPROVE) :].strip())
    if not text.startswith(CMD + " "):
        return None
    verb, _, arg = text[len(CMD) + 1 :].strip().partition(" ")
    actions = {
        "confirm": lambda: confirm(wt, data),
        "allow": lambda: allow(wt, arg.strip()),
        "stop": lambda: request_stop(wt),
    }
    if verb not in actions or (verb == "allow") != bool(arg.strip()):
        return None  # the target form: the skill handles it
    return actions[verb]


def prompt(data):
    wt = _loop.worktree_root(data.get("cwd") or ".")
    action = typed_action(str(data.get("prompt", "")).strip(), wt, data)
    if action is None:
        return None
    try:
        if wt is None:
            raise Refused("Not in a git worktree.")
        return context("UserPromptSubmit", action())
    except Refused as e:
        return block(str(e))


# ── record ──────────────────────────────────────────────────────────────────
def evidence_line(stdout):
    for line in reversed(str(stdout or "").splitlines()):
        if line.startswith(_loop.EVIDENCE_TAG):
            try:
                ev = json.loads(line[len(_loop.EVIDENCE_TAG) :])
            except ValueError:
                return None
            return ev if isinstance(ev, dict) else None
    return None


def trusted_state(data):
    """The running state when this call is the exact verifier, run at the worktree root."""
    if data.get("tool_name") != "Bash":
        return None
    if str(data.get("tool_input", {}).get("command", "")).strip() != _loop.VERIFY_CMD:
        return None
    wt = _loop.worktree_root(data.get("cwd") or ".")
    if wt is None or Path(data.get("cwd")).resolve() != wt:
        return None
    state = _loop.load_state(wt)
    ok = (
        state
        and state.get("status") == "running"
        and state.get("session_id") == data.get("session_id")
    )
    return state if ok else None


def record(data):
    state = trusted_state(data)
    if not state:
        return None
    wt = state["worktree"]
    ev = evidence_line(data.get("tool_response", {}).get("stdout"))
    why = None
    if _loop.bin_sha(wt) != state["bin_sha"]:
        why = ".loop/bin changed"
    elif not ev:
        why = "no evidence line"
    elif (ev.get("spec_sha"), ev.get("features_sha")) != (
        state["spec_sha"],
        state["features_sha"],
    ):
        why = "the spec or the checks changed"
    elif ev.get("content") != _loop.content_hash(wt):
        why = "the files changed after the run"
    if why:
        return context("PostToolUse", f"Loop evidence not recorded: {why}.")
    state["evidence"] = ev
    if not state["baseline"] and ev["content"] == state["base_content"]:
        state["baseline"] = {c["id"]: c["exit"] for c in ev["checks"]}
        state["best"] = ev["score"]
    save(state)
    return context(
        "PostToolUse", f"Loop evidence recorded: {ev['score']}/{ev['total']}."
    )


def verify_step(state):
    """The verifier call for the hook messages, which the agent follows. A skill eval needs
    `claude` and the network, and guard_loop lets only this call leave the sandbox (§7)."""
    flag = (
        ", dangerouslyDisableSandbox: true"
        if state.get("target_type") == "skill"
        else ""
    )
    return f"`{_loop.VERIFY_CMD}` from the worktree root (Bash timeout 600000{flag})"


# ── stop ────────────────────────────────────────────────────────────────────
def allow_stop(message=None):
    return {"systemMessage": message} if message else {}


def failed_ids(state):
    ev = state.get("evidence") or {}
    return [c["id"] for c in ev.get("checks", []) if c["exit"] != 0]


def routine(state):
    n = state["iteration"] + 1
    failed = ", ".join(failed_ids(state)) or "none"
    return (
        f"Iteration {n} of {state['max_iterations']}. Failed checks: {failed}.\n"
        "1. Run pwd and `git log --oneline -5`; read .loop/loop-progress.md and "
        f"`{_loop.VERIFY_CMD.replace('verify', 'status')}`.\n"
        "2. Pick one failed check. Run a smoke test of the target.\n"
        f"3. In .loop/loop-progress.md, write `## Iteration {n}` with one-line "
        "`Cause:` (the cause and the design decision that allowed it) and `Decision:`.\n"
        "4. Fix the cause where it starts. Do not edit tests, evals or checks.\n"
        f"5. Run {verify_step(state)}, then stop."
    )


def run_gate(state):
    """The diff gate's report; loopctl bundle shows it from .loop/run.json."""
    sys.path.insert(0, str(HERE.parent))
    import loop_gate

    try:
        return loop_gate.gate(
            state["worktree"],
            state["base"],
            state["approved_paths"],
            any(e != 0 for e in state["baseline"].values()),
            state["scope_protected"],
            state["self_protect"],
            state.get("target", ""),
        )
    except loop_gate.Usage as e:
        return {"verdict": "error", "error": str(e), "rejects": [], "warnings": []}


def enter_bundling(state, reason):
    state["status"] = "bundling"
    state["log"].append(f"- bundling: {reason}")
    state["gate"] = run_gate(state)
    return block(
        f"The loop ends ({reason}). Build the bundle: run "
        f"`{_loop.VERIFY_CMD.replace('verify', 'bundle')}`, then fill each section "
        f"marked {_loop.FILL} (reviewer answers, debrief, lesson), then stop."
    )


def bump_stuck(state, reason):
    state["stuck"] += 1
    return block(reason)


def protected_change(state):
    wt = state["worktree"]
    for rel in sorted(_loop.changed_paths(wt, state["base"])):
        if _loop.is_protected(
            rel,
            state["scope_protected"],
            state["approved_paths"],
            state["self_protect"],
        ):
            return rel
    return None


def cause_entry(state):
    """{"Cause": ..., "Decision": ...} from this iteration's block; a missing line is ""."""
    n = state["iteration"] + 1
    text = _loop.progress_text(state["worktree"])
    _, found, block_text = text.partition(f"## Iteration {n}\n")
    entry = {"Cause": "", "Decision": ""}
    for line in block_text.split("\n## ", 1)[0].splitlines() if found else []:
        tag, sep, value = line.strip().partition(":")
        if sep and tag in entry and not entry[tag]:
            entry[tag] = value.strip()
    return entry


def rate_limits():
    """The statusline's snapshot (§11.4), or None: then no usage stop can fire."""
    try:
        limits = json.loads(
            (_loop.state_dir() / "rate_limits.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    return limits if isinstance(limits, dict) else None


def usage_high():
    limits = rate_limits() or {}
    return any(
        (w or {}).get("used_percentage", 0) >= USAGE_LIMIT
        for w in (limits.get("five_hour"), limits.get("seven_day"))
    )


def epoch(stamp):
    """Seconds for a transcript timestamp; Python 3.9 cannot read the trailing Z."""
    try:
        text = str(stamp).replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def lines_of(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def token_usage(path, since):
    """The token sums of the main and subagent transcripts after `since`, each message
    once (one message has a line for each content block). None: no main transcript."""
    if not path:
        return None
    main = Path(path)
    try:
        lines = [(main, lines_of(main))]
    except OSError:
        return None
    for sub in sorted(main.with_suffix("").glob("subagents/agent-*.jsonl")):
        try:
            lines.append((sub, lines_of(sub)))
        except OSError:
            continue
    last = {}
    for file, text in lines:
        for n, line in enumerate(text):
            try:
                entry = json.loads(line) if '"usage"' in line else None
            except ValueError:
                continue
            msg = entry.get("message") if isinstance(entry, dict) else None
            usage = msg.get("usage") if isinstance(msg, dict) else None
            when = epoch(entry.get("timestamp")) if usage else None
            if isinstance(usage, dict) and when is not None and when >= since:
                last[msg.get("id") or f"{file}:{n}"] = usage
    sums = {
        k: sum(u[k] for u in last.values() if isinstance(u.get(k), int))
        for k, _label in _loop.TOKENS
    }
    return {**sums, "messages": len(last)}


def count_usage(state, data):
    """Tokens and the usage stop. It runs after the guards: row 5 compares the mirrors
    with the state as the last Stop saved it."""
    state["usage_stop"] = rate_limits() is not None
    usage = token_usage(data.get("transcript_path"), state["confirm_time"])
    if usage is not None:
        state["usage"] = usage


def bundle_check(state):
    try:
        text = (Path(state["worktree"]) / ".loop/bundle.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    missing = _loop.missing_sections(text)
    if not missing:
        state["status"] = "done"
        return allow_stop("Loop done: the bundle is ready for review.")
    state["bundle_blocks"] += 1
    if state["bundle_blocks"] >= MAX_BUNDLE_BLOCKS:
        state["status"] = "stopped"
        return allow_stop(
            f"Loop stopped: the bundle still misses {', '.join(missing)}."
        )
    return block(f"Finish .loop/bundle.md. Missing or unfilled: {', '.join(missing)}.")


def stopped(state, _content):
    off = (
        os.environ.get("CLAUDE_LOOP_OFF") == "1" or (_loop.state_dir() / "OFF").exists()
    )
    return off or state["stop_requested"]


def set_stopped(state, _content):
    state["status"] = "stopped"
    return allow_stop("Loop stopped by the operator.")


def restore_mirrors(state, _content):
    write_mirrors(state)
    return bump_stuck(
        state,
        "The .loop/ spec, checks and run files belong to the hook; it restored them.",
    )


def restore_bin(state, _content):
    copy_bin(state["worktree"])
    return bump_stuck(state, ".loop/bin belongs to the hook; it restored it.")


def undo_protected(state, _content):
    rel = protected_change(state)
    return bump_stuck(
        state,
        f"Undo the change to {rel}: it is protected. "
        f"The operator can type `{CMD} allow {rel}`.",
    )


def first_routine(state, content):
    # Row 8a fires once: last_judged is set, so a later stop with no edit is judged (row 9)
    state["last_judged"] = content
    return block(routine(state))


# Part 1 (§11.1): (row, condition, action); the first condition that holds ends the hook
GUARDS = (
    ("1", stopped, set_stopped),
    ("2", lambda s, c: s["status"] in ("done", "stopped"), lambda s, c: allow_stop()),
    ("3", lambda s, c: s["status"] == "bundling", lambda s, c: bundle_check(s)),
    (
        "4",
        lambda s, c: s["stuck"] >= MAX_STUCK,
        lambda s, c: enter_bundling(s, "stuck: the same guard blocked 5 times"),
    ),
    ("5", lambda s, c: mirrors_differ(s), restore_mirrors),
    ("6", lambda s, c: _loop.bin_sha(s["worktree"]) != s["bin_sha"], restore_bin),
    ("7", lambda s, c: protected_change(s) is not None, undo_protected),
    (
        "8",
        lambda s, c: not s["baseline"],
        lambda s, c: bump_stuck(
            s,
            f"Run {verify_step(s)} before any edit, for the baseline.",
        ),
    ),
    (
        "8a",
        lambda s, c: s["last_judged"] is None and c == s["base_content"],
        first_routine,
    ),
)


def guards(state, content):
    for _row, holds, action in GUARDS:
        if holds(state, content):
            return action(state, content)
    return None


def nothing_new(state, content):
    if content == state["last_judged"]:
        return True
    status = _loop.git(state["worktree"], "status", "--porcelain", "--", *pathspec())
    return not status.stdout.strip()


def ready(state, content):
    """Part 1 rows 10 and 11: the turn has a cause and evidence for this content."""
    if not all(cause_entry(state).values()):
        n = state["iteration"] + 1
        return bump_stuck(
            state,
            f"Write `## Iteration {n}` with `Cause:` and `Decision:` in .loop/loop-progress.md.",
        )
    ev = state.get("evidence") or {}
    if ev.get("content") != content:
        return bump_stuck(
            state, f"Run {verify_step(state)} for the current files, then stop."
        )
    return None


def keep(state, n, ev, exits):
    state["best"] = ev["score"]
    for f in state["features"]:
        # A check the agent wrote without `passes` has not passed yet
        f["passes"] = bool(f.get("passes")) or exits.get(f["id"]) == 0
    state["no_improve"] = 0
    state["log"].append(f"- #{n} kept: score {ev['score']}/{ev['total']}")


def judge(state):
    """Part 2 (§11.2): commit, then keep or revert. A failed git step changes no score."""
    wt = state["worktree"]
    n = state["iteration"] + 1
    ev = state["evidence"]
    if not on_loop_branch(state):
        return bump_stuck(
            state,
            f"The worktree must be on {state['branch']}; the hooks commit only there.",
        )
    if not commit(
        wt, f"loop({state['slug']}) #{n}: {cause_entry(state)['Cause'][:72]}"
    ):
        return bump_stuck(
            state,
            "The hook could not commit this iteration; check `git status` and stop again.",
        )
    exits = {c["id"]: c["exit"] for c in ev["checks"]}
    regressed = [
        i for i, e in state["baseline"].items() if e == 0 and exits.get(i) != 0
    ]
    if regressed or ev["score"] <= state["best"]:
        why = f"regressed {', '.join(regressed)}" if regressed else "no gain"
        if safe_git(wt, "revert", "--no-edit", "HEAD").returncode != 0:
            # The bad commit stays on the branch: only the operator should decide what to do
            return enter_bundling(state, f"the revert of #{n} failed ({why})")
        state["no_improve"] += 1
        state["log"].append(
            f"- #{n} reverted ({why}): score {ev['score']}/{ev['total']}"
        )
    else:
        keep(state, n, ev, exits)
    state["last_judged"] = _loop.content_hash(wt)
    state["iteration"] = n
    state["stuck"] = 0
    return None


def threshold(state):
    t = str(state["threshold"])
    return len(state["features"]) if t == "all" or not t.isdigit() else int(t)


def decide(state):
    """Part 3 (§11.3)."""
    if (state["best"] or 0) >= threshold(state):
        return enter_bundling(state, "the checks reached the threshold")
    if state["iteration"] >= state["max_iterations"]:
        return enter_bundling(state, "the iteration cap")
    if state["no_improve"] >= 2:
        return enter_bundling(state, "2 iterations with no gain")
    if usage_high():
        return enter_bundling(state, f"usage at {USAGE_LIMIT}% of a limit")
    return block(routine(state))


def stop(data):
    wt = _loop.worktree_root(data.get("cwd") or ".")
    state = _loop.load_state(wt) if wt else None
    if not state or state.get("session_id") != data.get("session_id"):
        return None
    if any(t.get("status") == "running" for t in data.get("background_tasks") or []):
        return None  # the task's hand-back starts the next turn
    counting = state["status"] in _loop.ACTIVE  # a finished loop counts no more
    content = _loop.content_hash(state["worktree"])
    out = guards(state, content)
    if out is None:
        if nothing_new(state, content):
            state["iteration"] += 1
            state["no_improve"] += 1
            state["log"].append(f"- #{state['iteration']} no change")
        else:
            out = ready(state, content) or judge(state)
        out = out or decide(state)
    if counting:
        count_usage(state, data)
    save(state)
    return out


MODES = {"prompt": prompt, "record": record, "stop": stop}


def main(argv):
    if sys.platform == "win32":
        return 0  # the loop needs the OS sandbox: no loop on native Windows, normal work goes on
    mode = argv[0] if argv else ""
    if mode not in MODES:
        print("usage: loop_hook.py prompt|record|stop", file=sys.stderr)
        return 0
    try:
        emit(MODES[mode](json.load(sys.stdin)))
    except Exception as e:  # noqa: BLE001 - fail open: a crash must not trap the session
        emit(
            {"systemMessage": f"loop hook failed, loop paused: {type(e).__name__}: {e}"}
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
