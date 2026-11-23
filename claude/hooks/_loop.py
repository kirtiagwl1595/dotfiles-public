#!/usr/bin/env python3
"""Shared parts of the loop hooks and loopctl (docs/loop-engineering.md).

Standard library only, Python 3.9: confirm copies this file into `.loop/bin/` next to
loopctl.py, where no other hook module exists.

CLI: `_loop.py running <cwd> <session_id>` exits 0 while a loop of that session runs
(the test and lesson gates use it to step aside).
"""

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

VERIFY_CMD = "python3 -B .loop/bin/loopctl.py verify"
EVIDENCE_TAG = "LOOP-EVIDENCE v1 "
LOG_HEADING = "## Iteration log"
ACTIVE = ("running", "bundling")
# Modes with no prompt: the work profile refuses them (R18)
AUTO_MODES = ("auto", "bypassPermissions", "dontAsk")
LOOP_DIR = ".loop"
# Skill targets (this repo only): each own plugin keeps its eval cases in <plugin>/evals/.
# `claude plugin eval` runs one plugin, so a case runs against the plugin that holds it.
# Own plugins only: the eval runs the plugin's code outside the sandbox (§7), and the
# third-party picks in claude/plugins/ are not ours to change (§3.3).
EVAL_HOMES = ("claude", "claude/plugins/writing-skills")
EVAL_RUNNER = "claude/evals/run.sh"
# Files only the hooks write: the state file holds the real copies (mirrors, §7)
MIRRORS = (".loop/LOOP.md", ".loop/loop-features.json", ".loop/run.json")

# A verifier run writes these; they never count as a change (§8.4)
TOOL_OUTPUT = (
    "__pycache__/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    ".mypy_cache/**",
    "node_modules/**",
    "claude/evals/results/**",
)
PROTECTED = (
    "tests/**",
    "test_*",
    "*_test.*",
    "*.test.*",
    "conftest.py",
    "evals/**",
    "ruff.toml",
    "pyproject.toml",
    "setup.cfg",
    "mypy.ini",
    "pyrightconfig.json",
    "tsconfig*.json",
    ".eslintrc*",
    "eslint.config.*",
    ".shellcheckrc",
    ".pre-commit-config.yaml",
    ".gitleaks.toml",
    ".gitleaksignore",
    ".github/workflows/**",
    ".loop/bin/**",
    *MIRRORS,
)
# In a repo that holds the loop engine the loop must not change its own judges (§7)
SELF_PROTECTED = (
    "claude/hooks/**",
    "claude/loopctl.py",
    "claude/loop_gate.py",
    "claude/gitleaks-gate.toml",
    "claude/loop-profiles.json",
    "claude/.claude-plugin/plugin.json",
    "claude/agents/**",
)
BUNDLE_SECTIONS = (
    "Goal and cause",
    "Diff stat",
    "Commits",
    "Gate result",
    "Scores",
    "Iterations and tokens",
    "Reviewer answers",
    "Design note",
    "Debrief",
    "Lesson",
)
FILL = "<!-- fill -->"
# message.usage fields and their bundle labels (§11.4)
TOKENS = (
    ("input_tokens", "input"),
    ("output_tokens", "output"),
    ("cache_creation_input_tokens", "cache write"),
    ("cache_read_input_tokens", "cache read"),
)


def token_text(usage):
    """The token sums for a person to read, or None when nothing was counted."""
    if not usage:
        return None
    sums = ", ".join(f"{label} {usage.get(k, 0):,}" for k, label in TOKENS)
    return f"{sums}, in {usage.get('messages', 0)} messages"


def missing_sections(text):
    """Bundle sections that are absent or still hold the fill marker (Stop row 3)."""
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    found = {p.split("\n", 1)[0].strip(): p for p in parts[1:]}
    return [s for s in BUNDLE_SECTIONS if s not in found or FILL in found[s]]


def state_dir():
    # A fixed path, not XDG_STATE_HOME: the deny rules name it
    return Path.home() / ".local/state/claude-safe-lean/loops"


def slug(target_type, target):
    """Lower case with hyphens, at most 30 characters (§6)."""
    if target_type == "script":
        target = Path(target).stem
    elif target_type == "task":
        target = " ".join(re.findall(r"[A-Za-z0-9]+", target)[:4])
    words = re.findall(r"[a-z0-9]+", target.lower())
    return "-".join(words)[:30].strip("-")


def worktree_root(cwd):
    """The folder that holds `.git` (a folder, or a file in a linked worktree), or None."""
    try:
        here = Path(cwd).resolve()
    except (OSError, RuntimeError, TypeError):
        return None
    for folder in (here, *here.parents):
        if (folder / ".git").exists():
            return folder
    return None


def key(worktree):
    real = os.path.realpath(str(worktree))
    return hashlib.sha256(real.encode()).hexdigest()[:16]


def state_path(worktree):
    return state_dir() / f"{key(worktree)}.json"


def load_state(worktree):
    try:
        return json.loads(state_path(worktree).read_text())
    except (OSError, ValueError):
        return None


class Unsafe(Exception):
    """A hook would write through a symlink that the agent may have planted."""


def real_folder(root, folder):
    """Raise Unsafe when `folder`, or a folder between `root` and it, is a symlink. The
    hooks run outside the sandbox: a link in the worktree would aim their writes, or
    copy_bin's rmtree, at any path the user can write."""
    current = Path(root)
    for part in Path(folder).relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise Unsafe(
                f"{current} is a symlink; the loop hook does not write through it"
            )


def atomic_write(path, text, root=None):
    """Write `text` to `path` through a new temp file. mkstemp makes a fresh name with
    O_EXCL, so a planted `<name>.tmp` link is never followed, and os.replace swaps a
    link at `path` itself instead of writing through it. With `root`, the folders below
    it must be real (real_folder)."""
    path = Path(path)
    if root is not None:
        real_folder(root, path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def save_state(state):
    atomic_write(state_path(state["worktree"]), json.dumps(state, indent=2))


def git(repo, *args, check=False):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _same(pats, parts):
    return len(pats) == len(parts) and all(
        fnmatch.fnmatchcase(n, p) for p, n in zip(pats, parts)
    )


def matches(pattern, rel):
    """Gitignore-style match on a path relative to the worktree (§9).

    No `/` in the pattern: the file name at any depth. `dir/**` or `dir/`: that folder
    at any depth. Otherwise the whole path. Case does not count (macOS file names).
    """
    if pattern.endswith("/"):
        pattern += "**"
    pats = pattern.lower().strip("/").split("/")
    parts = rel.lower().strip("/").split("/")
    if len(pats) == 1:
        return fnmatch.fnmatchcase(parts[-1], pats[0])
    if pats[-1] == "**":
        head = pats[:-1]
        return any(
            _same(head, parts[i : i + len(head)]) for i in range(len(parts) - len(head))
        )
    return _same(pats, parts)


def matches_any(patterns, rel):
    return any(matches(p, rel) for p in patterns)


def is_protected(rel, extra=(), approved=(), self_protect=False):
    if rel in approved:
        return False
    pats = (*PROTECTED, *extra, *(SELF_PROTECTED if self_protect else ()))
    return matches_any(pats, rel)


def counted(rel):
    """True for a file the content hash and the commit count: not .loop/ nor tool output."""
    return not (rel == LOOP_DIR or rel.startswith(LOOP_DIR + "/")) and not matches_any(
        TOOL_OUTPUT, rel
    )


def _names(out):
    return {n for n in out.split("\0") if n and counted(n)}


def files(worktree):
    """Tracked and untracked files that git does not ignore."""
    out = git(worktree, "ls-files", "-z", "-c", "-o", "--exclude-standard").stdout
    return sorted(_names(out))


def _file_sha(path):
    if path.is_symlink():
        return hashlib.sha256(os.readlink(str(path)).encode()).hexdigest()
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return "deleted"


def content_hash(worktree):
    """A sha256 over each counted path and its file's sha256. It only reads files."""
    h = hashlib.sha256()
    for rel in files(worktree):
        h.update(f"{rel}\0{_file_sha(Path(worktree) / rel)}\n".encode())
    return h.hexdigest()


def changed_paths(worktree, base):
    """Counted paths that differ from the commit `base`, untracked files included."""
    diff = git(worktree, "diff", "--name-only", "--no-renames", "-z", base, "--")
    new = git(worktree, "ls-files", "-z", "-o", "--exclude-standard")
    return _names(diff.stdout) | _names(new.stdout)


def split_spec(text):
    """(spec, log): the sealed part above `## Iteration log`, and the lines below it."""
    spec, _, log = text.partition(LOG_HEADING)
    return spec, log.lstrip("\n")


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        name, sep, value = line.partition(":")
        if sep:
            out[name.strip()] = value.split("#", 1)[0].strip()
    return out


def sections(text):
    """{heading: body} of the `## ` sections of a Markdown text."""
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    return {
        p.split("\n", 1)[0].strip(): p.split("\n", 1)[1] if "\n" in p else ""
        for p in parts[1:]
    }


def score_text(baseline, best, total):
    """The checks that pass at the baseline (exit 0) and at the best kept iteration."""
    before = sum(v == 0 for v in (baseline or {}).values())
    return f"before {before}/{total}, after {best}/{total}"


def progress_text(worktree):
    """loop-progress.md without HTML comments: the template's hints are not the agent's
    causes. "" when the file is missing."""
    try:
        text = (Path(worktree) / LOOP_DIR / "loop-progress.md").read_text()
    except OSError:
        return ""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def must_not_change(text):
    """The LOOP.md "must not change" entries: the patterns the guard, Stop and the gate protect."""
    for line in text.splitlines():
        _, sep, rest = line.partition("must not change:")
        if sep:
            return [p.strip() for p in rest.split(",") if p.strip()]
    return []


def spec_problem(text, features, worktree):
    """Why this LOOP.md and these checks cannot run, else None. A check has exactly one of
    `verify` (a shell command) or `grader` (a grader of the LOOP.md `eval_case`, run by
    EVAL_RUNNER). A scope entry is a path pattern: a note in it would match no file."""
    meta = frontmatter(text)
    notes = [p for p in must_not_change(text) if re.search(r"[\s()]", p)]
    if notes:
        return (
            "LOOP.md 'must not change' takes path patterns only (gitignore style: "
            f"`tests/`, `*.lock`). Move the note out of: {'; '.join(notes)}. "
            "'may change' is advice and is not enforced."
        )
    if not isinstance(features, list) or not all(
        isinstance(f, dict)
        and f.get("id")
        and bool(f.get("verify")) != bool(f.get("grader"))
        for f in features
    ):
        return "loop-features.json must be a list of checks, each with an id and exactly one of verify or grader."
    graders = [f["grader"] for f in features if f.get("grader")]
    return grader_problem(meta, graders, worktree) if graders else None


def grader_problem(meta, graders, worktree):
    """Why these grader checks cannot run, else None: one case folder must hold each grader."""
    if meta.get("target_type") != "skill":
        # Only a skill loop may run its verifier outside the sandbox, and an eval needs that
        return "A grader check needs target_type: skill."
    case = meta.get("eval_case") or ""
    folders = eval_case_dirs(worktree, case)
    where = [str(f.relative_to(worktree)) for f in folders]
    if not folders:
        return (
            "A grader check needs LOOP.md eval_case: the name of a case folder in "
            + " or ".join(f"{home}/evals/" for home in EVAL_HOMES)
            + "."
        )
    if len(folders) > 1:
        return f"eval_case {case} is in {len(folders)} plugins: {', '.join(where)}. Rename one case."
    missing = [g for g in graders if not (folders[0] / "graders" / f"{g}.md").is_file()]
    if missing:
        return f"No grader file for {', '.join(missing)} in {where[0]}/graders/."
    return None


def eval_case_dirs(worktree, case):
    """Each folder of EVAL_HOMES that holds eval case `case`; its plugin is the grandparent.
    A name that is not a plain folder name matches nothing."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", case or ""):
        return []
    root = Path(worktree)
    return sorted(
        d
        for home in EVAL_HOMES
        for d in root.glob(f"{home}/evals/{case}")
        if d.is_dir()
    )


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def features_sha(features):
    """The check definitions without `passes`: the hook rewrites `passes`, never the checks."""
    plain = [{k: v for k, v in f.items() if k != "passes"} for f in features]
    return sha(json.dumps(plain, sort_keys=True))


def bin_sha(worktree):
    """Every file name and content in .loop/bin: an extra json.py would shadow the stdlib."""
    folder = Path(worktree) / LOOP_DIR / "bin"
    h = hashlib.sha256()
    for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
        if path.is_file():
            h.update(f"{path.relative_to(folder)}\0{_file_sha(path)}\n".encode())
    return h.hexdigest()


def main_checkout(worktree):
    common = git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")
    path = Path(common.stdout.strip())
    return path.parent if path.name == ".git" else Path(worktree)


def _remote(worktree):
    """(host, owner) of origin, for https and scp-style URLs."""
    url = git(worktree, "remote", "get-url", "origin").stdout.strip()
    m = re.match(r"(?:\w+://)?(?:[^@/]+@)?([^/:]+)[:/]([^/]+)/", url)
    return (m.group(1).lower(), m.group(2).lower()) if m else ("", "")


def _rules():
    tracked = Path(__file__).resolve().parent.parent / "loop-profiles.json"
    local = Path.home() / ".config/claude/loop-profiles.local.json"
    rules = []
    for path in (local, tracked):  # local first: the operator's rules win
        try:
            rules += json.loads(path.read_text())
        except (OSError, ValueError):
            continue
    return [r for r in rules if isinstance(r, dict)]


def own_repo(repo):
    """True when only you have access: no origin, or an origin under your own login.

    repo_setup.team_owner is the repo's one definition of a team repo; an unknown login
    counts as a team. It is absent in .loop/bin, where no profile is looked up."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        import repo_setup
    except ImportError:
        return False
    return repo_setup.team_owner(repo) is None


def _rule_hits(rule, repo, remote):
    if rule.get("owner") == "self":
        return own_repo(repo)
    if "path" in rule:
        pattern = os.path.realpath(os.path.expanduser(rule["path"]))
        return fnmatch.fnmatchcase(repo, pattern)
    host, owner = remote
    want = str(rule.get("remote", "")).lower().split("/")
    return bool(host) and want == [host, owner][: len(want)]


def profile_for(worktree):
    """The first rule that matches the repo; a repo no rule matches is `work` (§16)."""
    repo = os.path.realpath(str(main_checkout(worktree)))
    remote = _remote(worktree)
    for rule in _rules():
        if _rule_hits(rule, repo, remote):
            return rule.get("profile", "work")
    return "work"


def running(cwd, session_id):
    root = worktree_root(cwd)
    state = load_state(root) if root else None
    return bool(
        state
        and state.get("status") in ACTIVE
        and state.get("session_id") == session_id
    )


def main(argv):
    if len(argv) == 3 and argv[0] == "running":
        return 0 if running(argv[1], argv[2]) else 1
    print("usage: _loop.py running <cwd> <session_id>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
