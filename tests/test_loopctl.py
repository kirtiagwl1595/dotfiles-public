"""loopctl: discover, verify (script and task mode), status and bundle (§10)."""

import json
import subprocess
import time
from pathlib import Path

import _loop
import pytest
from loop_fixtures import (
    CLAUDE,
    FEATURES,
    HOOKS,
    LOOP_CMD,
    LOOP_MARKS,
    LOOP_MD,
    PROGRESS,
    confirm,
    copy_bin,
    git,
    loopctl,
    personal,
    prompt,
    python,
    record,
    stop,
    write_loop_files,
)

pytestmark = LOOP_MARKS

COMMANDS = """# demo

## Commands
- Test: `sh -c 'exit 0'`
- Lint: `true` · Format check: `false`
- Deploy: `echo deploy`
"""


def loopctl_source():
    return HOOKS.parent / "loopctl.py"


def evidence(out):
    last = out.strip().splitlines()[-1]
    assert last.startswith(_loop.EVIDENCE_TAG), out
    return json.loads(last[len(_loop.EVIDENCE_TAG) :])


def test_copied_bin_runs_alone(loop_env):
    # .loop/bin holds only loopctl.py and _loop.py: neither may import another hook module
    b = loop_env.tmp / "bin"
    copy_bin(b)
    p = subprocess.run(
        [python(), "-B", str(b / "loopctl.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stderr


# ── discover ────────────────────────────────────────────────────────────────
def test_discover_runs_the_allowed_commands(loop_env):
    (loop_env.wt / "CLAUDE.md").write_text(COMMANDS)
    copy_bin(loop_env.wt / ".loop/bin")
    p = loopctl(loop_env, "discover")
    assert p.returncode == 0, p.stderr
    found = json.loads((loop_env.wt / ".loop/discovery.json").read_text())
    by_label = {c["label"]: c for c in found}
    assert by_label["Test"]["exit"] == 0
    assert by_label["Lint"]["exit"] == 0
    assert by_label["Format check"]["exit"] == 1
    assert "skipped" in by_label["Deploy"] and "exit" not in by_label["Deploy"]


# The shapes of 3 real CLAUDE.md lines (pilot 3 and the dotfiles audit), with safe commands
REAL_LINES = """## Commands
- Review: `echo review` (options: `--goal "..."`, `--out <folder>`)
- Dry run of the setup: `echo check` (one part: `echo check-one`)
- Rebuild the guide after a `GUIDE.md` change: `echo build`
- Test: `true`  ·  Evals: `echo evals`  ·  Lint: `echo lint`
"""


def test_discover_takes_the_label_at_the_start_of_each_part(loop_env):
    (loop_env.wt / "CLAUDE.md").write_text(REAL_LINES)
    copy_bin(loop_env.wt / ".loop/bin")
    assert loopctl(loop_env, "discover").returncode == 0
    found = json.loads((loop_env.wt / ".loop/discovery.json").read_text())
    assert [(c["label"], c["command"]) for c in found] == [
        ("Review", "echo review"),
        ("Dry run of the setup", "echo check"),
        ("Rebuild the guide after a GUIDE.md change", "echo build"),
        ("Test", "true"),
        ("Evals", "echo evals"),
        ("Lint", "echo lint"),
    ]


def test_discover_reads_project_files(loop_env):
    wt = loop_env.wt
    (wt / "package.json").write_text(
        json.dumps({"scripts": {"test": "x", "build": "y"}})
    )
    (wt / "Makefile").write_text("lint:\n\ttrue\nbuild:\n\ttrue\n")
    (wt / "pyproject.toml").write_text("[project]\nname='x'\n[tool.ruff]\n")
    copy_bin(wt / ".loop/bin")
    loopctl(loop_env, "discover")
    found = json.loads((wt / ".loop/discovery.json").read_text())
    commands = {c["command"] for c in found}
    assert {"npm run test", "make lint", "uv run ruff check ."} <= commands
    assert not {"npm run build", "make build"} & commands


def test_discover_names_a_denied_read_outside_the_worktree(loop_env):
    # Pilot 3: uv walked up from the nested worktree to the main checkout's pyproject.toml
    wt, outside = loop_env.wt, loop_env.main / "pyproject.toml"
    (wt / "fail.sh").write_text(
        f"echo 'error: failed to open file `{outside}`: Operation not permitted (os error 1)'\n"
        f"echo 'warning: `{wt}/x`: Operation not permitted'\n"
        "exit 2\n"
    )
    (wt / "CLAUDE.md").write_text("## Commands\n- Test: `sh fail.sh`\n")
    copy_bin(wt / ".loop/bin")
    p = loopctl(loop_env, "discover")
    found = json.loads((wt / ".loop/discovery.json").read_text())
    assert found[0]["exit"] == 2 and found[0]["outside_reads"] == [str(outside)]
    assert str(outside) in p.stdout and "repo-task.md" in p.stdout


def test_discover_finds_nothing(loop_env):
    copy_bin(loop_env.wt / ".loop/bin")
    assert loopctl(loop_env, "discover").returncode == 1


def test_bad_input_is_a_message_not_a_traceback(loop_env):
    copy_bin(loop_env.wt / ".loop/bin")
    p = loopctl(loop_env, "verify")
    assert p.returncode == 2
    assert "Traceback" not in p.stderr and "confirm" in p.stderr


# ── verify ──────────────────────────────────────────────────────────────────
def test_verify_prints_evidence_last_and_exits_0_when_it_ran(loop_env):
    confirm(loop_env)
    p = loopctl(loop_env, "verify")
    assert p.returncode == 0, p.stderr
    ev = evidence(p.stdout)
    assert ev["checks"] == [{"id": "prints-ok", "exit": 1}, {"id": "runs", "exit": 0}]
    assert (ev["score"], ev["total"]) == (1, 2)
    assert ev["content"] == _loop.content_hash(loop_env.wt)
    assert "FAIL prints-ok" in p.stdout


def test_verify_output_does_not_change_the_content(loop_env):
    feats = [
        {
            **FEATURES[1],
            "verify": "mkdir -p tests/__pycache__ && touch tests/__pycache__/a.pyc",
        }
    ]
    confirm(loop_env, features=feats)
    before = _loop.content_hash(loop_env.wt)
    ev = evidence(loopctl(loop_env, "verify").stdout)
    assert ev["content"] == before


def test_verify_caps_output_and_keeps_the_evidence_line(loop_env):
    noisy = "i=0; while [ $i -lt 100 ]; do echo line$i; i=$((i+1)); done; exit 1"
    feats = [{**FEATURES[1], "id": f"c{i}", "verify": noisy} for i in range(30)]
    confirm(loop_env, features=feats)
    p = loopctl(loop_env, "verify")
    ev = evidence(p.stdout)
    assert ev["truncated"] is True and ev["score"] == 0
    assert len(p.stdout.splitlines()) <= 402


def test_verify_stops_on_a_protected_change(loop_env):
    confirm(loop_env)
    (loop_env.wt / "tests/test_tool.py").write_text("x = 1\n")
    p = loopctl(loop_env, "verify")
    assert p.returncode == 2
    assert "tests/test_tool.py" in p.stderr and _loop.EVIDENCE_TAG not in p.stdout


def test_verify_task_mode(loop_env):
    confirm(
        loop_env, loop_md=LOOP_MD.replace("target_type: script", "target_type: task")
    )
    assert loopctl(loop_env, "verify").returncode == 0


# ── verify, skill mode: grader checks from one eval run ────────────────────
SKILL_MD = LOOP_MD.replace("target_type: script", "target_type: skill").replace(
    "threshold: all", "threshold: all\neval_case: demo-case"
)
GRADERS = [
    {"id": "one-rule", "category": "behavior", "grader": "one-rule"},
    {"id": "fires", "category": "trigger", "grader": "skill-fired"},
]
# Copies $STUB_RESULT to --output-dir, as `claude plugin eval` writes its result there
STUB = """#!/bin/sh
echo "$@" >> "$STUB_CALLS"
echo "$EVAL_MAX_USD" >> "$STUB_CALLS.usd"
out=""
while [ $# -gt 0 ]; do [ "$1" = --output-dir ] && out=$2; shift; done
[ -n "$STUB_RESULT" ] || exit 1
cp "$STUB_RESULT" "$out/aggregate-result.json"
"""


def aggregate(votes, case="demo-case", partial=False, errors=()):
    """An aggregate-result.json in the shape of `claude plugin eval` (2026-11-17)."""
    runs = len(next(iter(votes.values())))
    arm = [
        {
            "passed": True,
            "error": "timeout" if i in errors else None,
            "graders": []
            if i in errors
            else [{"name": n, "passed": v[i]} for n, v in votes.items()],
        }
        for i in range(runs)
    ]
    return {"partial": partial, "cases": [{"name": case, "arms": {"with": arm}}]}


@pytest.fixture
def skill(loop_env, monkeypatch):
    """A skill loop on a stub run.sh; set(result) chooses what the next eval writes."""
    evals = loop_env.wt / "claude/evals"
    (evals / "demo-case/graders").mkdir(parents=True)
    for g in ("one-rule", "skill-fired"):
        (evals / f"demo-case/graders/{g}.md").write_text("---\ntype: llm\n---\n")
    (evals / "run.sh").write_text(STUB)
    calls = loop_env.tmp / "calls.txt"
    monkeypatch.setenv("STUB_CALLS", str(calls))

    def set_result(result):
        if result is None:
            monkeypatch.delenv("STUB_RESULT", raising=False)
            return
        path = loop_env.tmp / "result.json"
        path.write_text(json.dumps(result))
        monkeypatch.setenv("STUB_RESULT", str(path))

    loop_env.set_result = set_result
    loop_env.calls = calls
    return loop_env


def test_a_grader_passes_in_2_of_3_runs(skill):
    confirm(skill, loop_md=SKILL_MD, features=GRADERS)
    skill.set_result(
        aggregate(
            {"one-rule": [True, False, True], "skill-fired": [False, False, True]}
        )
    )
    p = loopctl(skill, "verify")
    assert p.returncode == 0, p.stderr
    ev = evidence(p.stdout)
    assert ev["checks"] == [{"id": "one-rule", "exit": 0}, {"id": "fires", "exit": 1}]
    assert "FAIL fires" in p.stdout and "1 of 3" in p.stdout
    args = skill.calls.read_text().split()
    assert args[:6] == ["--case", "demo-case", "--ablation", "none", "--runs", "3"]
    # A stuck loop verifies up to 5 times: each eval gets a small cost cap (G5)
    assert (skill.tmp / "calls.txt.usd").read_text().split() == ["3"]


@pytest.mark.parametrize("plugin", ["claude", "claude/plugins/writing-skills"])
def test_the_eval_runs_against_the_plugin_that_holds_the_case(skill, plugin):
    # `claude plugin eval` reads one plugin's own evals/: a writing-skills case needs writing-skills
    case = skill.wt / plugin / "evals/demo-case"
    if not case.exists():
        case.parent.mkdir(parents=True)
        (skill.wt / "claude/evals/demo-case").rename(case)
    confirm(skill, loop_md=SKILL_MD, features=GRADERS)
    skill.set_result(aggregate({"one-rule": [True] * 3, "skill-fired": [True] * 3}))
    p = loopctl(skill, "verify")
    assert p.returncode == 0, p.stderr
    args = skill.calls.read_text().split()
    assert Path(args[args.index("--plugin") + 1]) == (skill.wt / plugin).resolve()


def test_confirm_refuses_a_case_of_a_third_party_pick(skill):
    # The eval runs the plugin's code outside the sandbox: only own plugins count (§7, §3.3)
    pick = skill.wt / "claude/plugins/ecc-picks/evals/demo-case"
    pick.parent.mkdir(parents=True)
    (skill.wt / "claude/evals/demo-case").rename(pick)
    personal(skill.home, skill.main)
    write_loop_files(skill.wt, SKILL_MD, GRADERS)
    _, out, _ = prompt(skill, f"{LOOP_CMD} confirm")
    assert out.get("decision") == "block" and "eval_case" in out["reason"], out


def test_confirm_refuses_a_case_name_that_two_plugins_hold(skill):
    (skill.wt / "claude/plugins/writing-skills/evals/demo-case/graders").mkdir(
        parents=True
    )
    personal(skill.home, skill.main)
    write_loop_files(skill.wt, SKILL_MD, GRADERS)
    _, out, _ = prompt(skill, f"{LOOP_CMD} confirm")
    assert out.get("decision") == "block" and "2 plugins" in out["reason"], out


def test_one_eval_run_serves_every_grader_and_shell_checks_still_run(skill):
    confirm(skill, loop_md=SKILL_MD, features=[*GRADERS, FEATURES[1]])
    skill.set_result(
        aggregate({"one-rule": [True] * 3, "skill-fired": [True, True, False]})
    )
    ev = evidence(loopctl(skill, "verify").stdout)
    assert [c["exit"] for c in ev["checks"]] == [0, 0, 0]
    assert len(skill.calls.read_text().splitlines()) == 1


def test_a_run_with_an_error_counts_as_a_fail(skill):
    confirm(skill, loop_md=SKILL_MD, features=GRADERS[:1])
    skill.set_result(aggregate({"one-rule": [True, True, True]}, errors=(0, 1)))
    assert evidence(loopctl(skill, "verify").stdout)["checks"][0]["exit"] == 1


def test_an_old_result_never_counts_again(skill):
    # run.sh fails before it writes: the last run's pass must not be read as new evidence
    confirm(skill, loop_md=SKILL_MD, features=GRADERS[:1])
    skill.set_result(aggregate({"one-rule": [True] * 3}))
    assert loopctl(skill, "verify").returncode == 0
    skill.set_result(None)
    p = loopctl(skill, "verify")
    assert p.returncode == 2 and "no result" in p.stderr
    assert _loop.EVIDENCE_TAG not in p.stdout
    # Each eval writes to its own new folder: a late writer cannot fill the next one
    first, second = (line.split()[-1] for line in skill.calls.read_text().splitlines())
    assert first != second and ".loop/eval/" in second


def test_the_bundle_adds_up_the_eval_spend(skill):
    """The eval's `claude` runs write their own transcripts, so the token count misses them."""
    confirm(skill, loop_md=SKILL_MD, features=GRADERS[:1])
    passed = aggregate({"one-rule": [True] * 3})
    # A run that the cost cap stopped still spent
    capped = aggregate({"one-rule": [True] * 3}, partial=True)
    for result, cost in ((passed, 0.5), (passed, 0.25), (capped, 0.25)):
        skill.set_result({**result, "costUsd": cost})
        loopctl(skill, "verify")
    loopctl(skill, "bundle")
    text = (skill.wt / ".loop/bundle.md").read_text()
    assert "Eval spend: $1.00 in 3 eval runs" in text, text


@pytest.mark.parametrize(
    "result, why",
    [
        (aggregate({"one-rule": [True] * 3}, partial=True), "partial"),
        (aggregate({"one-rule": [True] * 3}, case="other"), "demo-case"),
        (aggregate({"one-rule": [True, True]}), "3 runs"),
        (aggregate({"another": [True] * 3}), "one-rule"),
        ({"cases": "x"}, "demo-case"),
    ],
)
def test_a_result_it_cannot_read_is_exit_2_not_a_score(skill, result, why):
    confirm(skill, loop_md=SKILL_MD, features=GRADERS[:1])
    skill.set_result(result)
    p = loopctl(skill, "verify")
    assert p.returncode == 2 and why in p.stderr, p.stderr
    assert _loop.EVIDENCE_TAG not in p.stdout


def test_eval_output_is_no_change_and_nothing_to_commit(skill):
    confirm(skill, loop_md=SKILL_MD, features=GRADERS[:1])
    skill.set_result(aggregate({"one-rule": [True] * 3}))
    content = _loop.content_hash(skill.wt)
    for _ in range(2):  # a second verify must not see a protected change
        p = loopctl(skill, "verify")
        assert p.returncode == 0, p.stderr
    assert evidence(p.stdout)["content"] == content
    assert git(skill.wt, "status", "--porcelain", "--", ".", ":(exclude).loop") == ""


@pytest.mark.parametrize(
    "loop_md, features, why",
    [
        (SKILL_MD.replace("eval_case: demo-case", ""), GRADERS, "eval_case"),
        (SKILL_MD.replace("demo-case", "no-such-case"), GRADERS, "eval_case"),
        (SKILL_MD.replace("demo-case", "../evals"), GRADERS, "eval_case"),
        (SKILL_MD, [{**GRADERS[0], "grader": "typo"}], "typo"),
        (SKILL_MD, [{**GRADERS[0], "verify": "true"}], "exactly one"),
        (SKILL_MD, [{"id": "x"}], "exactly one"),
        # Only a skill loop may run the eval outside the sandbox (§7)
        (
            SKILL_MD.replace("target_type: skill", "target_type: script"),
            GRADERS,
            "skill",
        ),
    ],
)
def test_confirm_refuses_a_grader_spec_it_cannot_run(skill, loop_md, features, why):
    personal(skill.home, skill.main)
    write_loop_files(skill.wt, loop_md, features)
    _, out, _ = prompt(skill, f"{LOOP_CMD} confirm")
    assert out.get("decision") == "block" and why in out["reason"], out
    assert _loop.load_state(skill.wt) is None


# ── status, bundle ──────────────────────────────────────────────────────────
def test_status(loop_env):
    confirm(loop_env)
    p = loopctl(loop_env, "status")
    assert p.returncode == 0
    assert "demo" in p.stdout and "0/2 checks pass" in p.stdout


def test_bundle_writes_every_section_and_names_the_ones_to_fill(loop_env):
    confirm(loop_env)
    (loop_env.wt / "tool.sh").write_text("echo ok\n")
    git(loop_env.wt, "commit", "-qam", "loop(demo) #1: fix")
    p = loopctl(loop_env, "bundle")
    text = (loop_env.wt / ".loop/bundle.md").read_text()
    assert p.returncode == 1
    assert all(f"## {s}" in text for s in _loop.BUNDLE_SECTIONS)
    assert "tool.sh" in text and "loop(demo) #1: fix" in text
    assert set(_loop.missing_sections(text)) == {
        "Reviewer answers",
        "Debrief",
        "Lesson",
    }
    assert "Debrief" in p.stdout


def test_bundle_shows_the_causes_and_not_the_template_hint(loop_env):
    # Pilots 1 and 2: the hint inside the template's HTML comment reached the bundle
    confirm(loop_env)
    template = (CLAUDE / "templates/loop/loop-progress.md").read_text()
    (loop_env.wt / ".loop/loop-progress.md").write_text(
        template + "\n" + PROGRESS.format(n=1)
    )
    loopctl(loop_env, "bundle")
    text = (loop_env.wt / ".loop/bundle.md").read_text()
    causes = [x for x in text.splitlines() if x.startswith("Cause:")]
    assert causes == ["Cause: tool.sh prints the wrong word."], causes


def test_bundle_keeps_what_the_agent_filled(loop_env):
    confirm(loop_env)
    loopctl(loop_env, "bundle")
    path = loop_env.wt / ".loop/bundle.md"
    path.write_text(path.read_text().replace(_loop.FILL, "written"))
    p = loopctl(loop_env, "bundle")
    assert p.returncode == 0, p.stdout
    assert _loop.missing_sections(path.read_text()) == []


@pytest.mark.parametrize(
    ("usage", "usage_stop", "shown"),
    [
        (
            {"input_tokens": 9, "output_tokens": 26500, "messages": 3},
            True,
            ["output 26,500", "input 9", "3 messages", "Usage stop: on"],
        ),
        ({}, False, ["Tokens: not counted", "Usage stop: off"]),
    ],
)
def test_bundle_shows_the_tokens_and_the_usage_stop(loop_env, usage, usage_stop, shown):
    confirm(loop_env)
    path = loop_env.wt / ".loop/run.json"
    run = json.loads(path.read_text())
    path.write_text(json.dumps({**run, "usage": usage, "usage_stop": usage_stop}))
    loopctl(loop_env, "bundle")
    text = (loop_env.wt / ".loop/bundle.md").read_text()
    section = text.split("## Iterations and tokens\n", 1)[1].split("\n## ", 1)[0]
    assert all(s in section for s in shown), section
    assert "Eval spend" not in section  # a script loop runs no eval


@pytest.mark.parametrize("command", ["status", "bundle"])
def test_commands_need_a_confirmed_loop(loop_env, command):
    copy_bin(loop_env.wt / ".loop/bin")
    assert loopctl(loop_env, command).returncode == 2


# ── audit: read-only; what has no verifier (R16) ───────────────────────────
AUDIT_FILES = {
    "CLAUDE.md": COMMANDS,
    "claude/skills/alpha/SKILL.md": "---\nname: alpha\n---\n",
    "claude/skills/beta/SKILL.md": "---\nname: beta\n---\n",
    "claude/skills/gamma/SKILL.md": "---\nname: gamma\n---\n",
    "claude/evals/alpha-trigger/case.yaml": "name: alpha-trigger\n",
    "claude/evals/fires/graders/fired.md": "input_match: '(?:x:)?gamma'\n",
    "claude/evals/fires/scaffold.sh": "#!/bin/sh\nrm -rf /tmp/x\n",
    "claude/tests/test_beta.py": "def test_beta():\n    assert 'beta'\n",
    "claude/tests/test_safe.py": "SAFE = ROOT / 'scripts/safe.sh'\nrun(['bash', SAFE])\n",
    "claude/tests/test_list.py": "SCRIPTS = ['scripts/install.sh', 'scripts/tool']\n",
    "scripts/install.sh": '#!/bin/sh\ncurl -o x https://example.com\nrm -rf "$HOME/x"\n'
    "brew install jq\ngit push\nln -s x ~/y\n",
    "scripts/safe.sh": '#!/bin/sh\n[ "$1" = --dry-run ] && exit 0\n',
    "scripts/tool": "#!/usr/bin/env python3\nprint(1)\n",
    "scripts/notes.txt": "not a script\n",
}


def test_audit_lists_what_has_a_verifier_and_changes_nothing(loop_env):
    repo = loop_env.main
    for rel, text in AUDIT_FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "add")
    (repo / "scripts/install.sh").write_text(AUDIT_FILES["scripts/install.sh"] + "#\n")
    git(repo, "commit", "-qam", "again")
    before = sorted(str(p) for p in repo.rglob("*") if ".git" not in p.parts)

    p = subprocess.run(
        [python(), "-B", str(loopctl_source()), "audit"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)

    skills = {s["name"]: s for s in out["skills"]}
    assert skills["alpha"]["eval"] == ["alpha-trigger"]
    assert skills["alpha"]["verifier"] == "eval"
    assert skills["gamma"]["eval"] == ["fires"]  # a grader names it
    assert skills["beta"]["tests"] == ["claude/tests/test_beta.py"]
    assert skills["beta"]["verifier"] is None  # a test that names a skill checks text
    scripts = {s["path"]: s for s in out["scripts"]}
    # eval scaffolds and test files are fixtures, not scripts; a text file is not a script
    assert set(scripts) == {
        "tool.sh",  # from the loop_env repo
        "scripts/install.sh",
        "scripts/safe.sh",
        "scripts/tool",
    }
    install = scripts["scripts/install.sh"]
    # a test that only lists the file name runs nothing
    assert install["tests"] == ["claude/tests/test_list.py"]
    assert install["verifier"] is None and install["dry_run"] is False
    assert install["side_effects"] == [
        "deletes",
        "downloads",
        "installs",
        "pushes",
        "writes home",
    ]
    assert install["churn"] == 2
    assert scripts["scripts/safe.sh"]["verifier"] == "test"
    assert scripts["scripts/safe.sh"]["dry_run"] is True
    areas = {a["path"]: a for a in out["areas"]}
    assert areas["claude"]["tests"] == 3 and areas["scripts"]["files"] == 4
    # The commands that discover would run, as loop-audit/SKILL.md says: not Deploy
    assert [c["label"] for c in out["commands"]] == ["Test", "Lint", "Format check"]
    assert all("exit" not in c for c in out["commands"])  # audit never runs them

    assert git(repo, "status", "--porcelain") == ""
    assert sorted(str(p) for p in repo.rglob("*") if ".git" not in p.parts) == before


def test_audit_outside_a_repo_root_is_a_message(loop_env):
    p = subprocess.run(
        [python(), "-B", str(loopctl_source()), "audit"],
        cwd=loop_env.main / "tests",
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 2 and "root" in p.stderr and "Traceback" not in p.stderr


def test_the_stop_hook_judges_a_grader_spec(skill):
    # The whole turn on a skill spec: baseline, edit, verify, record, Stop
    confirm(skill, loop_md=SKILL_MD, features=GRADERS[:1])
    skill.set_result(aggregate({"one-rule": [False] * 3}))
    record(skill, loopctl(skill, "verify").stdout)
    assert blocked_by(stop(skill))  # row 8a: the routine for iteration 1
    (skill.wt / ".loop/loop-progress.md").write_text(PROGRESS.format(n=1))
    (skill.wt / "tool.sh").write_text("echo ok\n")
    skill.set_result(aggregate({"one-rule": [True] * 3}))
    record(skill, loopctl(skill, "verify").stdout)
    out = stop(skill)
    assert "failed" not in out.get("systemMessage", ""), out
    s = _loop.load_state(skill.wt)
    assert (s["iteration"], s["best"]) == (1, 1), s
    assert s["features"][0]["passes"] is True
    assert "claude/evals" not in git(skill.wt, "show", "--stat", "HEAD")


def blocked_by(out):
    return out.get("decision") == "block"


FLAG = "dangerouslyDisableSandbox: true"


def test_every_verify_step_of_a_skill_loop_leaves_the_sandbox(skill):
    """The agent follows the hook messages; in the sandbox the eval cannot reach the API."""
    out = confirm(skill, loop_md=SKILL_MD, features=GRADERS[:1])
    assert FLAG in out["hookSpecificOutput"]["additionalContext"]
    assert FLAG in stop(skill)["reason"]  # row 8: no baseline yet
    skill.set_result(aggregate({"one-rule": [False] * 3}))
    record(skill, loopctl(skill, "verify").stdout)
    assert FLAG in stop(skill)["reason"]  # row 8a: the routine for iteration 1


def test_a_script_loop_keeps_the_verifier_in_the_sandbox(loop_env):
    out = confirm(loop_env)
    assert FLAG not in out["hookSpecificOutput"]["additionalContext"]
    assert FLAG not in stop(loop_env)["reason"]


def test_a_timeout_stops_every_process_it_started(tmp_path, monkeypatch):
    # The eval runs `claude` under bash: killing bash alone leaves it running and spending
    import loopctl as ctl

    monkeypatch.chdir(tmp_path)
    code, _ = ctl.run("(sleep 2; touch late) & wait", timeout=1)
    assert code == 124
    time.sleep(2.5)
    assert not (tmp_path / "late").exists()
