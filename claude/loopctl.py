#!/usr/bin/env python3
"""loopctl: the loop's command line (docs/loop-engineering.md §10).

Confirm copies this file and _loop.py into `.loop/bin/`; run it from the worktree root:
  python3 -B .loop/bin/loopctl.py discover|verify|status|bundle
and `audit` from any repo root (read-only; it needs no loop).

It reads .loop/ only: the sandbox cannot read the state file, so the hooks mirror what
loopctl needs into .loop/run.json. Bad input gets a message and exit 2, not a traceback.
"""

import argparse
import collections
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# In the repo, _loop.py is in hooks/; in .loop/bin it sits next to this file
sys.path[:0] = [str(HERE), str(HERE / "hooks")]
import _loop

CHECK_TIMEOUT = 300
LINES_PER_CHECK = 40
MAX_LINES = 400  # Bash output that Claude Code cuts would lose the evidence line
LABELS = ("test", "lint", "format", "type")
LABELLED = re.compile(r"\s*([^:]+?):\s*`([^`]+)`")
PYPROJECT = {
    "tool.pytest": "uv run pytest -q",
    "tool.ruff": "uv run ruff check .",
    "tool.mypy": "uv run mypy .",
}
PACKAGE_SCRIPTS = ("test", "lint", "typecheck")
MAKE_TARGETS = ("test", "lint")
EVAL_RUNS = 3
EVAL_PASSES = 2  # one run is noisy, so a grader passes in 2 of 3 runs (§8.4)
EVAL_TIMEOUT = 540  # under the 600 s Bash cap, so the evidence line still prints
EVAL_OUT = ".loop/eval"
# run.sh caps each eval at EVAL_MAX_USD (default $10); a stuck loop verifies up to 5 times
EVAL_MAX_USD = "3"


class Usage(Exception):
    """Bad input: print the message, exit 2."""


def check_env():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.setdefault("EVAL_MAX_USD", EVAL_MAX_USD)
    env["PYTEST_ADDOPTS"] = (
        env.get("PYTEST_ADDOPTS", "") + " -p no:cacheprovider"
    ).strip()
    return env


def run(command, timeout=CHECK_TIMEOUT):
    """(exit code, output lines) of a shell text or an argument list; exit 124 on a
    timeout, as in coreutils. A timeout stops the whole process group: killing only the
    shell would leave `claude` under run.sh running, spending and writing results."""
    p = subprocess.Popen(
        command,
        shell=isinstance(command, str),
        cwd=".",
        env=check_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return 124, [f"timed out after {timeout} s"]
    return p.returncode, out.splitlines()


def root():
    wt = _loop.worktree_root(".")
    if wt is None or wt != Path.cwd().resolve():
        raise Usage("Run loopctl from the worktree root.")
    return wt


# ── discover ────────────────────────────────────────────────────────────────
def from_claude_md(text):
    section = re.split(r"^## Commands\s*$", text, flags=re.MULTILINE)
    if len(section) < 2:
        return []
    body = re.split(r"^## ", section[1], flags=re.MULTILINE)[0]
    found = []
    for line in body.splitlines():
        if not line.startswith("- "):
            continue
        # `·` separates commands; a label starts its part, so `(options: `x`)` is no command
        for part in line[2:].split("·"):
            m = LABELLED.match(part)
            if m:
                label = m.group(1).replace("`", "").strip()
                found.append(
                    {"label": label, "command": m.group(2), "source": "CLAUDE.md"}
                )
    return found


def runnable(command):
    """Discover runs only the Test, Lint, Format and Type commands; the audit lists them."""
    return command["label"].lower().startswith(LABELS)


def from_project_files(wt):
    found = []
    pyproject = wt / "pyproject.toml"
    if pyproject.is_file():
        headers = re.findall(
            r"^\[([^\]]+)\]", pyproject.read_text(), flags=re.MULTILINE
        )
        for prefix, cmd in PYPROJECT.items():
            if any(h == prefix or h.startswith(prefix + ".") for h in headers):
                found.append(
                    {"label": prefix, "command": cmd, "source": "pyproject.toml"}
                )
    package = wt / "package.json"
    if package.is_file():
        scripts = json.loads(package.read_text()).get("scripts", {})
        for name in PACKAGE_SCRIPTS:
            if name in scripts:
                found.append(
                    {
                        "label": name,
                        "command": f"npm run {name}",
                        "source": "package.json",
                    }
                )
    makefile = wt / "Makefile"
    if makefile.is_file():
        targets = re.findall(
            r"^([A-Za-z_-]+):", makefile.read_text(), flags=re.MULTILINE
        )
        for name in MAKE_TARGETS:
            if name in targets:
                found.append(
                    {"label": name, "command": f"make {name}", "source": "Makefile"}
                )
    return found


def repo_commands(wt):
    """The commands that CLAUDE.md and the project files name, each once; none run."""
    claude_md = wt / "CLAUDE.md"
    found = from_claude_md(claude_md.read_text()) if claude_md.is_file() else []
    found += from_project_files(wt)
    seen, out = set(), []
    for c in found:
        if c["command"] not in seen:
            seen.add(c["command"])
            out.append(c)
    return out


def outside_reads(lines, wt):
    """Paths outside the worktree in "Operation not permitted" lines: sandbox denials."""
    inside = os.path.realpath(wt) + os.sep
    found = []
    for line in lines:
        if "Operation not permitted" in line:
            for path in re.findall(r"(/[^\s`'\"():]+)", line):
                if not os.path.realpath(path).startswith(inside) and path not in found:
                    found.append(path)
    return found


def discover(_args):
    wt = root()
    out = repo_commands(wt)
    for c in out:
        if not runnable(c):
            c["skipped"] = "the label is not Test, Lint, Format or Type"
        else:
            start = time.time()
            c["exit"], lines = run(c["command"])
            c["seconds"] = round(time.time() - start, 1)
            c["tail"] = lines[-10:]
            if c["exit"] != 0:
                c["outside_reads"] = outside_reads(lines, wt)
        print(f"{c['label']}: {c['command']} -> {c.get('exit', c.get('skipped'))}")
        for path in c.get("outside_reads", ()):
            print(
                f"  the sandbox denied a read outside the worktree: {path}. A tool that "
                "searches parent folders (uv, git) cannot run here as it is; tell the "
                "operator (references/repo-task.md, 'Reads outside the worktree')."
            )
    _loop.atomic_write(wt / ".loop/discovery.json", json.dumps(out, indent=2) + "\n")
    ran = [c for c in out if "exit" in c]
    print(f"{len(ran)} commands ran; see .loop/discovery.json")
    return 0 if ran else 1


# ── verify ──────────────────────────────────────────────────────────────────
def loop_files(wt):
    try:
        text = (wt / ".loop/LOOP.md").read_text()
        features = json.loads((wt / ".loop/loop-features.json").read_text())
        run_json = json.loads((wt / ".loop/run.json").read_text())
    except (OSError, ValueError) as e:
        raise Usage(
            f"No confirmed loop here ({e}). Type the confirm command first."
        ) from e
    problem = _loop.spec_problem(text, features, wt)
    if problem:
        raise Usage(problem)
    return text, features, run_json


def protected_changes(wt, run_json):
    return sorted(
        rel
        for rel in _loop.changed_paths(wt, run_json["base"])
        if _loop.is_protected(
            rel,
            run_json.get("scope_protected") or (),
            run_json.get("approved_paths") or (),
            run_json.get("self_protect"),
        )
    )


def eval_runs(wt, case):
    """The `with` runs of one new eval of `case`. A result it cannot read is Usage
    (exit 2), never a score: a score of 0 would look real to the Stop hook."""
    # Each eval gets its own new folder and verify reads only that one, so an old result
    # never counts again; the folders stay for the bundle's eval spend
    out = wt / EVAL_OUT / str(time.time_ns())
    out.mkdir(parents=True)
    # The spec check found exactly one folder for the case (_loop.spec_problem)
    plugin = _loop.eval_case_dirs(wt, case)[0].parents[1]
    code, lines = run(
        ["bash", _loop.EVAL_RUNNER, "--case", case, "--ablation", "none"]
        + ["--runs", str(EVAL_RUNS), "--plugin", str(plugin), "--output-dir", str(out)],
        EVAL_TIMEOUT,
    )
    try:
        data = json.loads((out / "aggregate-result.json").read_text())
    except (OSError, ValueError):
        tail = " | ".join(lines[-5:])
        raise Usage(f"The eval wrote no result (run.sh exit {code}): {tail}") from None
    if not isinstance(data, dict) or data.get("partial"):
        raise Usage("The eval result is partial (did the cost cap stop it?).")
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    found = next(
        (c for c in cases if isinstance(c, dict) and c.get("name") == case), None
    )
    if found is None:
        raise Usage(f"The eval result has no case {case}.")
    arms = found.get("arms")
    runs = arms.get("with") if isinstance(arms, dict) else None
    if not isinstance(runs, list) or len(runs) != EVAL_RUNS:
        raise Usage(f"The eval result for {case} must hold {EVAL_RUNS} runs.")
    return runs


def grader_votes(runs, name):
    """Whether grader `name` passed in each run. A run that ended in an error fails."""
    votes = []
    for r in runs:
        if not isinstance(r, dict):
            raise Usage("An eval run in the result is not an object.")
        if r.get("error"):
            votes.append(False)
            continue
        graders = r.get("graders") if isinstance(r.get("graders"), list) else []
        g = next(
            (g for g in graders if isinstance(g, dict) and g.get("name") == name), None
        )
        if g is None:
            raise Usage(f"Grader {name} is missing from an eval run.")
        votes.append(g.get("passed") is True)
    return votes


def verify(_args):
    wt = root()
    text, features, run_json = loop_files(wt)
    changed = protected_changes(wt, run_json)
    if changed:
        raise Usage(
            f"Protected paths changed since the setup commit: {', '.join(changed)}. Undo them."
        )
    case, runs = _loop.frontmatter(text).get("eval_case"), None
    checks, printed, truncated = [], 0, False
    for f in features:
        if f.get("grader"):
            runs = runs or eval_runs(wt, case)  # one eval run serves every grader
            votes = grader_votes(runs, f["grader"])
            code = 0 if sum(votes) >= EVAL_PASSES else 1
            lines = [f"grader {f['grader']}: passed {sum(votes)} of {len(votes)} runs"]
        else:
            code, lines = run(f["verify"])
        checks.append({"id": f["id"], "exit": code})
        if code == 0:
            continue
        shown = [f"FAIL {f['id']} (exit {code})", *lines[-LINES_PER_CHECK:]]
        truncated = truncated or len(lines) > LINES_PER_CHECK
        room = MAX_LINES - printed
        if len(shown) > room:
            shown, truncated = shown[:room], True
        printed += len(shown)
        if shown:
            print("\n".join(shown))
    ev = {
        "content": _loop.content_hash(wt),
        "spec_sha": _loop.sha(_loop.split_spec(text)[0]),
        "features_sha": _loop.features_sha(features),
        "checks": checks,
        "score": sum(c["exit"] == 0 for c in checks),
        "total": len(checks),
        "truncated": truncated,
    }
    print(_loop.EVIDENCE_TAG + json.dumps(ev))
    return 0


# ── status ──────────────────────────────────────────────────────────────────
def status(_args):
    wt = root()
    text, features, run_json = loop_files(wt)
    passing = sum(bool(f.get("passes")) for f in features)
    print(
        f"loop {run_json.get('slug')}: {run_json.get('status')}, iteration "
        f"{run_json.get('iteration')} of {run_json.get('max_iterations')}, "
        f"best score {run_json.get('best')}, {passing}/{len(features)} checks pass"
    )
    print(_loop.split_spec(text)[1] or "(no iterations yet)")
    return 0


# ── bundle ──────────────────────────────────────────────────────────────────
AGENT_SECTIONS = {
    "Reviewer answers": "The loop-reviewer answers: root-cause fix or patch; a cheated check; what breaks next.",
    "Debrief": "Goal, result, causes, changes kept and reverted, rules added, open risks.",
    "Lesson": "The lesson in .loop/lesson.md (approve copies it to .claude/lessons/), and where each finding was routed.",
}


def git_out(wt, *args):
    return _loop.git(wt, *args).stdout.strip() or "(none)"


def eval_spend(wt):
    """(usd, runs) over every eval of this loop, from the eval's own `costUsd`."""
    total, runs = 0.0, 0
    for path in sorted((wt / EVAL_OUT).glob("*/aggregate-result.json")):
        try:
            cost = json.loads(path.read_text()).get("costUsd")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(cost, (int, float)):
            total, runs = total + cost, runs + 1
    return total, runs


def iterations_and_tokens(wt, run_json):
    """R23. The Stop hook counts the tokens (loopctl cannot read the transcripts), so the
    count ends at the last Stop before this bundle; approve shows the final count."""
    tokens = _loop.token_text(run_json.get("usage"))
    stop = (
        "Usage stop: on (the statusline writes rate_limits.json)."
        if run_json.get("usage_stop")
        else "Usage stop: off (no rate_limits.json from the statusline): only a typed stop or a cap ended the loop early."
    )
    return "\n".join(
        [
            f"Iterations: {run_json.get('iteration')} of {run_json.get('max_iterations')}.",
            f"Tokens from confirm to the last Stop, main and subagent transcripts: {tokens}."
            if tokens
            else "Tokens: not counted (the Stop hook found no transcript).",
            stop,
            *eval_line(wt),
        ]
    )


def eval_line(wt):
    usd, runs = eval_spend(wt)
    if not runs:
        return []
    note = (
        "the eval's own costUsd; its transcripts are not in the token count, "
        "and an eval that wrote no result is not counted"
    )
    return [f"Eval spend: ${usd:.2f} in {runs} eval runs ({note})."]


def design_note(gate, kept):
    warned = any(r.get("rule") == "design" for r in (gate or {}).get("warnings", []))
    if warned:
        return (
            kept
            if kept and _loop.FILL not in kept
            else f"{_loop.FILL}\nThe design rule warned: explain the design.\n"
        )
    return "Not required: the design rule did not warn.\n"


def bundle_sections(wt, text, features, run_json, old):
    base = run_json["base"]
    spec = _loop.split_spec(text)[0]
    goal = _loop.sections(spec).get("Goal", "").strip()
    causes = re.findall(r"^Cause:.*$", _loop.progress_text(wt), flags=re.MULTILINE)
    gate = run_json.get("gate")
    out = {
        "Goal and cause": f"{goal}\n\n" + "\n".join(causes or ["(no cause recorded)"]),
        "Diff stat": "```text\n"
        + git_out(wt, "diff", "--stat", f"{base}..HEAD", "--", ".", ":(exclude).loop")
        + "\n```",
        "Commits": "```text\n"
        + git_out(wt, "log", "--format=%h %s", f"{base}..HEAD")
        + "\n```\n\n"
        + "\n".join(run_json.get("log") or []),
        "Gate result": "```json\n" + json.dumps(gate, indent=2) + "\n```"
        if gate
        else "The gate did not run.",
        "Scores": "Checks that pass: "
        + _loop.score_text(
            run_json.get("baseline"), run_json.get("best"), len(features)
        )
        + ".",
        "Iterations and tokens": iterations_and_tokens(wt, run_json),
        "Design note": design_note(gate, old.get("Design note")),
    }
    for name, hint in AGENT_SECTIONS.items():
        kept = old.get(name, "")
        out[name] = (
            kept
            if kept.strip() and _loop.FILL not in kept
            else f"{_loop.FILL}\n{hint}\n"
        )
    return out


def bundle(_args):
    wt = root()
    text, features, run_json = loop_files(wt)
    path = wt / ".loop/bundle.md"
    old = _loop.sections(path.read_text()) if path.is_file() else {}
    sections = bundle_sections(wt, text, features, run_json, old)
    body = "".join(
        f"## {name}\n{sections[name].rstrip()}\n\n" for name in _loop.BUNDLE_SECTIONS
    )
    _loop.atomic_write(path, f"# Loop bundle: {run_json.get('slug')}\n\n{body}")
    missing = _loop.missing_sections(path.read_text())
    if missing:
        print(f"Wrote .loop/bundle.md. Fill these sections: {', '.join(missing)}.")
        return 1
    print("Wrote .loop/bundle.md. Every section is complete.")
    return 0


# ── audit ───────────────────────────────────────────────────────────────────
TEST_FILES = ("tests/**", "test_*", "*_test.*", "*.test.*")
FIXTURES = (*TEST_FILES, "evals/**")  # eval scaffolds and test helpers are not scripts
CHURN_DAYS = 90


def path_to(name):
    """A test that runs a script builds the path to the file (`ROOT / "scripts/x.sh"`);
    a test that only lists the name (`["scripts/x.sh"]`) runs nothing."""
    return re.compile(rf"/\s*[\"'][^\"'\n]*(?<![\w-]){re.escape(name)}[\"']")


SIDE_EFFECTS = (
    ("deletes", r"\brm\s+-[A-Za-z]*[rf]"),
    ("downloads", r"\b(curl|wget)\b"),
    ("installs", r"\b(brew|npm|pip3?|uv tool)\s+install\b"),
    ("pushes", r"\bgit\s+push\b"),
    ("writes home", r"(>|\b(cp|mv|ln|mkdir|tee)\b)[^\n;|&]*(~/|\$HOME|\$\{HOME\})"),
)


def tracked(wt):
    return git_out(wt, "ls-files").splitlines()


def read(wt, rel):
    try:
        return (wt / rel).read_text(errors="replace")
    except OSError:
        return ""


def names(word, text):
    return re.search(rf"(?<![\w-]){re.escape(word)}(?!\w)", text) is not None


def churn(wt):
    """Commits in the last CHURN_DAYS days, by path."""
    log = git_out(wt, "log", f"--since={CHURN_DAYS}.days", "--name-only", "--format=")
    return collections.Counter(line for line in log.splitlines() if line)


def is_script(wt, rel):
    if _loop.matches_any(FIXTURES, rel):
        return False
    in_scripts = "scripts" in Path(rel).parts[:-1]
    return rel.endswith(".sh") or (in_scripts and read(wt, rel).startswith("#!"))


def eval_cases(wt, files):
    """{case name: the text of its files}, for each folder just below an evals/ folder."""
    cases = collections.defaultdict(str)
    for rel in files:
        parts = Path(rel).parts
        if "evals" in parts[:-2]:
            i = parts.index("evals")
            cases[parts[i + 1]] += read(wt, rel)
    return cases


def audit_skills(wt, files, tests, cases, commits):
    out = []
    for rel in files:
        parts = Path(rel).parts
        if len(parts) < 3 or parts[-3] != "skills" or parts[-1] != "SKILL.md":
            continue
        name = parts[-2]
        evals = sorted(
            c
            for c, text in cases.items()
            if c == name or c.startswith(name + "-") or names(name, text)
        )
        named = sorted(t for t, text in tests.items() if names(name, text))
        out.append(
            {
                "name": name,
                "path": rel,
                "eval": evals,
                "tests": named,
                # A test that names a skill checks its text; only an eval checks what it does
                "verifier": "eval" if evals else None,
                "churn": sum(
                    n
                    for p, n in commits.items()
                    if p.startswith(str(Path(rel).parent) + "/")
                ),
            }
        )
    return out


def audit_scripts(wt, files, tests, commits):
    out = []
    for rel in (f for f in files if is_script(wt, f)):
        text = read(wt, rel)
        name = Path(rel).name
        named = sorted(t for t, body in tests.items() if names(name, body))
        runs = any(path_to(name).search(tests[t]) for t in named)
        dry_run = "--dry-run" in text or "--check" in text
        out.append(
            {
                "path": rel,
                "tests": named,
                "dry_run": dry_run,
                "side_effects": [n for n, pat in SIDE_EFFECTS if re.search(pat, text)],
                "verifier": "test" if runs else "dry-run" if dry_run else None,
                "churn": commits.get(rel, 0),
            }
        )
    return out


def audit_areas(files, tests, commits):
    areas = collections.defaultdict(lambda: {"files": 0, "tests": 0, "churn": 0})
    for rel in files:
        if "/" not in rel:
            continue
        a = areas[rel.split("/", 1)[0]]
        a["files"] += 1
        a["tests"] += rel in tests
        a["churn"] += commits.get(rel, 0)
    return [{"path": p, **a} for p, a in sorted(areas.items())]


def audit(_args):
    """Read-only: no command runs, and nothing is written. The loop-audit skill ranks it."""
    wt = root()
    files = tracked(wt)
    tests = {f: read(wt, f) for f in files if _loop.matches_any(TEST_FILES, f)}
    commits = churn(wt)
    report = {
        "skills": audit_skills(wt, files, tests, eval_cases(wt, files), commits),
        "scripts": audit_scripts(wt, files, tests, commits),
        "areas": audit_areas(files, tests, commits),
        "commands": [c for c in repo_commands(wt) if runnable(c)],
    }
    print(json.dumps(report, indent=2))
    return 0


COMMANDS = {
    "audit": audit,
    "discover": discover,
    "verify": verify,
    "status": status,
    "bundle": bundle,
}


def parser():
    p = argparse.ArgumentParser(prog="loopctl", description=__doc__.split("\n")[0])
    p.add_argument("command", choices=sorted(COMMANDS))
    return p


def main(argv):
    args = parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except Usage as e:
        print(f"loopctl: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
