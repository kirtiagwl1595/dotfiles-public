#!/usr/bin/env python3
"""loop_gate: the diff gate for a loop branch (docs/loop-engineering.md §15).

`base` is the setup commit (#0). The gate reads the whole loop branch, from the fork
point (`base^`) to HEAD, without .loop/, so the setup files and the setup's secrets are
judged too. The setup may add checks and change the target; a protected path or a growing
SKILL.md counts only when a loop iteration changed it. Judgment calls (a rule for one
example, rules that contradict each other) go to the reviewer, not here.

  loop_gate.py --base <sha> [--root DIR] [--target PATH] [--approved PATH ...] [--baseline-failed]

Prints one JSON line, then a table. Exit 0 pass, 1 reject, 2 bad input.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))
import _loop

TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".html",
    ".css",
    ".csv",
    ".lock",
    ".cfg",
    ".ini",
}
TEST_FILES = ("tests/**", "test_*", "*_test.*", "*.test.*", "conftest.py")
LITERAL = re.compile(
    r"""(?:==|!=|\bin\b|\bis\b)\s*(['"])([^'"]{3,})\1|(['"])([^'"]{3,})\3\s*(?:==|!=)"""
)
# 3 or more digits: an ID or a code (404, 1234). Small numbers are limits, not test data.
NUMBER = re.compile(r"(?:==|!=|<=|>=|<|>)\s*(-?\d{3,}(?:\.\d+)?)\b")
EXCEPT = re.compile(r"^\s*except\s*(:|\(?\s*(Base)?Exception\b)")
EXCEPT_ANY = re.compile(r"^\s*except\b.*:\s*(pass)?\s*$")
DEFAULT_RETURN = re.compile(
    r"^\s*(pass|return(\s+(None|\[\]|\{\}|''|\"\"|0|False))?)\s*$"
)
TIMEOUT = re.compile(r"\btimeout\s*=\s*(\d+)")
RETRY = re.compile(r"\bsleep\b|\bretr(y|ies|ying)\b", re.IGNORECASE)
MARKER = re.compile(
    # A comment starts a line or follows a space: `https://x/temporary` is not one
    r"(?:^|\s)(#|//).*(\b(TODO|HACK|FIXME)\b|\b(temporary|workaround)\b)",
    re.IGNORECASE,
)
OPERATOR = re.compile(r"\bdef\s+__(eq|ne|lt|hash|bool)__\s*\(")
MONKEYPATCH = re.compile(
    r"^\s*((time|random|datetime)\.[\w.]+|os\.environ\[[^\]]+\]|sys\.std(in|out|err)|builtins\.\w+)\s*=(?!=)"
)
HARD_CODED = re.compile(
    r"/Users/\w|/home/\w|https?://|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-|\b[0-9a-f]{24,}\b"
)
PUBLIC_DEF = re.compile(r"^\s*def\s+[A-Za-z]\w*\s*\(")
CLI_FLAG = re.compile(r"""add_argument\(\s*['"]--""")
SECRETS = re.compile(
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{36}|sk-ant-[A-Za-z0-9_-]{20,}|xox[bpas]-[A-Za-z0-9-]{10,}"
)
WINDOW = 6
# Outside the worktree, in the running plugin: the agent cannot change it
GITLEAKS_CONFIG = Path(__file__).resolve().parent / "gitleaks-gate.toml"


class Usage(Exception):
    pass


class Diff:
    """Added lines (line number, text) and removed lines for each changed file."""

    def __init__(
        self,
        root,
        base,
        approved=(),
        baseline_failed=False,
        extra=(),
        self_protect=False,
        target="",
    ):
        self.root = Path(root)
        self.base = base
        self.target = target
        self.approved = set(approved)
        self.baseline_failed = baseline_failed
        self.extra = tuple(extra)  # the LOOP.md "must not change" list
        self.self_protect = self_protect
        # The secret rule sets it: a regex pass must not read as a gitleaks pass
        self.secret_scanner = "regex"
        self.fork = self._git("rev-parse", f"{base}^").strip()
        self.head = self._git("rev-parse", "HEAD").strip()
        self.git_dir = self._git(
            "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).strip()
        # The whole branch for the content rules; the iterations alone for the rest
        self.added, self.removed = self._parse(self._diff(self.fork, "HEAD"))
        self.loop_added, self.loop_removed = self._parse(self._diff(base, "HEAD"))
        # Name lists, not the parsed diff: an empty new file has no +++ line
        self.paths = self._names(self.fork, "HEAD")
        self.loop_paths = self._names(base, "HEAD")
        self.setup = self._names(self.fork, base)

    def _diff(self, a, b, *opts):
        return self._git(
            "diff",
            *(opts or ("--unified=0",)),
            "--no-renames",
            f"{a}..{b}",
            "--",
            ".",
            ":(exclude).loop",
        )

    def _names(self, a, b):
        return sorted(p for p in self._diff(a, b, "--name-only", "-z").split("\0") if p)

    def _git(self, *args):
        p = _loop.git(self.root, *args)
        if p.returncode != 0:
            raise Usage(f"git {args[0]} failed: {p.stderr.strip()}")
        return p.stdout

    @staticmethod
    def _parse(text):
        """({path: [(line, text)]} added, {path: [text]} removed) of a unified diff."""
        added, removed = {}, {}
        path, line = None, 0
        for raw in text.splitlines():
            if raw.startswith("+++ "):
                path = raw[6:] if raw.startswith("+++ b/") else None
                if path:
                    added.setdefault(path, [])
                    removed.setdefault(path, [])
            elif raw.startswith("--- a/"):
                removed.setdefault(raw[6:], [])
            elif raw.startswith("@@"):
                line = int(re.search(r"\+(\d+)", raw).group(1))
            elif path and raw.startswith("+"):
                added[path].append((line, raw[1:]))
                line += 1
            elif path and raw.startswith("-"):
                removed[path].append(raw[1:])
        return added, removed

    def changed(self):
        return self.paths

    def code_lines(self, tests=False):
        """Added lines of code files; test files only when asked."""
        for path, lines in self.added.items():
            if is_code(path) and (tests or not _loop.matches_any(TEST_FILES, path)):
                for n, text in lines:
                    yield path, n, text

    def head_files(self):
        return [
            p for p in self._git("ls-files", "-z").split("\0") if p and _loop.counted(p)
        ]

    def read(self, rel):
        try:
            return (self.root / rel).read_text(errors="ignore", encoding="utf-8")
        except OSError:
            return ""


def is_code(path):
    return Path(path).suffix.lower() not in TEXT_SUFFIXES and not path.startswith(
        "docs/"
    )


def finding(rule, path, line, text):
    return {"rule": rule, "file": path, "line": line, "text": text.strip()[:120]}


# ── reject rules ────────────────────────────────────────────────────────────
def swallow(d):
    out = []
    for path, lines in d.added.items():
        if not path.endswith(".py"):
            continue
        for i, (n, text) in enumerate(lines):
            nxt = lines[i + 1][1] if i + 1 < len(lines) else ""
            broad = EXCEPT.match(text)
            silent = EXCEPT_ANY.match(text) and (
                text.rstrip().endswith("pass") or DEFAULT_RETURN.match(nxt)
            )
            if broad or silent:
                out.append(finding("swallow", path, n, text))
    return out + ruff_swallow(d)


def ruff_swallow(d):
    ruff = shutil.which("ruff")
    files = [p for p in d.added if p.endswith(".py") and (d.root / p).is_file()]
    if not ruff or not files:
        return []
    p = subprocess.run(
        [
            ruff,
            "check",
            "--isolated",
            "--no-cache",
            "--select",
            "BLE,S110",
            "--output-format",
            "json",
            *files,
        ],
        cwd=d.root,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        hits = json.loads(p.stdout or "[]")
    except ValueError:
        return []
    added = {(path, n) for path, lines in d.added.items() for n, _ in lines}
    out = []
    for h in hits:
        rel = str(Path(h["filename"]).resolve().relative_to(d.root.resolve()))
        n = h["location"]["row"]
        if (rel, n) in added:
            out.append(finding("swallow", rel, n, f"{h['code']} {h['message']}"))
    return out


def tests_text(d):
    return "\n".join(
        d.read(p) for p in d.head_files() if _loop.matches_any(TEST_FILES, p)
    )


def special_case(d):
    tests, out = tests_text(d), []
    for path, n, text in d.code_lines():
        # An option such as `--dry-run` is the interface the tests call, not test data
        literals = [m.group(2) or m.group(4) for m in LITERAL.finditer(text)]
        literals = [lit for lit in literals if not lit.startswith("-")]
        literals += [m.group(1) for m in NUMBER.finditer(text)]
        if any(lit in tests for lit in literals):
            out.append(finding("special-case", path, n, text))
    return out


def retry(d):
    out = []
    for path, n, text in d.code_lines(tests=True):
        larger = False
        m = TIMEOUT.search(text)
        if m:
            old = [int(x) for r in d.removed.get(path, []) for x in TIMEOUT.findall(r)]
            larger = bool(old) and int(m.group(1)) > max(old)
        if RETRY.search(text) or larger:
            out.append(finding("retry", path, n, text))
    return out


def by_pattern(rule, pattern, tests=True):
    def check(d):
        return [
            finding(rule, p, n, t)
            for p, n, t in d.code_lines(tests)
            if pattern.search(t)
        ]

    return check


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


def windows(lines):
    kept = [norm(t) for t in lines if norm(t)]
    return {tuple(kept[i : i + WINDOW]) for i in range(len(kept) - WINDOW + 1)}


def duplicate(d):
    out = []
    for path, lines in d.added.items():
        mine = windows([t for _, t in lines])
        if not mine or not is_code(path):
            continue
        suffix = Path(path).suffix
        for other in d.head_files():
            if (
                other != path
                and Path(other).suffix == suffix
                and mine & windows(d.read(other).splitlines())
            ):
                out.append(
                    finding(
                        "duplicate",
                        path,
                        lines[0][0],
                        f"6 or more lines equal to a block in {other}",
                    )
                )
                break
    return out


def protected(d):
    return [
        finding("protected", p, 0, "protected path changed")
        for p in d.loop_paths
        if _loop.is_protected(p, d.extra, d.approved, d.self_protect)
    ]


def setup_file(d):
    """The setup may add checks (protected paths) and change the target, nothing else."""
    return [
        finding("setup-file", p, 0, "the setup commit added a file that is not a check")
        for p in d.setup
        if p != d.target and not _loop.is_protected(p, d.extra, (), d.self_protect)
    ]


def skill_growth(d):
    if d.baseline_failed:
        return []
    plus = {p: len(lines) for p, lines in d.loop_added.items()}
    minus = {p: len(lines) for p, lines in d.loop_removed.items()}
    return [
        finding("skill-growth", p, 0, f"+{plus.get(p, 0)} -{minus.get(p, 0)} lines")
        for p in sorted(plus)
        if Path(p).name == "SKILL.md" and plus[p] > minus.get(p, 0)
    ]


def secret(d):
    """gitleaks with the gate's own config, and the regex set on every run. The agent
    writes the worktree, so its .gitleaks.toml, .gitleaksignore and gitleaks:allow
    comments are not trusted: --config, --ignore-gitleaks-allow, and the scan source is
    the git common dir, because gitleaks reads <source>/.gitleaksignore whatever -i says.
    The range names the HEAD commit: HEAD in the common dir is the main checkout's."""
    out = [
        finding("secret", p, n, "a secret pattern")
        for p, lines in d.added.items()
        for n, t in lines
        if SECRETS.search(t)
    ]
    gitleaks = shutil.which("gitleaks")
    if not gitleaks:
        return out
    p = subprocess.run(
        [
            gitleaks,
            "git",
            "--no-banner",
            "--redact",
            "--config",
            str(GITLEAKS_CONFIG),
            "--gitleaks-ignore-path",
            os.devnull,
            "--ignore-gitleaks-allow",
            "--log-opts",
            f"{d.fork}..{d.head}",
            d.git_dir,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode in (0, 1):  # another code: gitleaks failed; the regex set still ran
        d.secret_scanner = "gitleaks"
    if p.returncode == 1:
        out.append(
            finding("secret", "", 0, "gitleaks found a secret in the loop branch")
        )
    return out


# ── warn rules ──────────────────────────────────────────────────────────────
def design(d):
    code = [
        p
        for p in d.changed()
        if (is_code(p) or Path(p).name == "SKILL.md") and not p.startswith("docs/")
    ]
    out = []
    if len(code) > 3:
        out.append(finding("design", "", 0, f"{len(code)} code files changed"))
    for path, lines in d.removed.items():
        for text in lines:
            if PUBLIC_DEF.match(text) or CLI_FLAG.search(text):
                out.append(
                    finding("design", path, 0, f"public interface changed: {text}")
                )
    return out


REJECTS = (
    swallow,
    special_case,
    retry,
    by_pattern("marker", MARKER),
    by_pattern("operator", OPERATOR),
    by_pattern("monkeypatch", MONKEYPATCH, tests=False),
    duplicate,
    protected,
    setup_file,
    skill_growth,
    secret,
)
WARNINGS = (by_pattern("hard-coded", HARD_CODED, tests=False), design)


def gate(
    root,
    base,
    approved=(),
    baseline_failed=False,
    extra=(),
    self_protect=False,
    target="",
):
    d = Diff(root, base, approved, baseline_failed, extra, self_protect, target)
    rejects = [f for rule in REJECTS for f in rule(d)]
    warnings = [f for rule in WARNINGS for f in rule(d)]
    return {
        "verdict": "reject" if rejects else "pass",
        "base": base,
        "files": d.changed(),
        "rejects": rejects,
        "warnings": warnings,
        "secret_scanner": d.secret_scanner,
    }


def table(report):
    rows = [("reject", f) for f in report["rejects"]] + [
        ("warn", f) for f in report["warnings"]
    ]
    lines = [
        f"verdict: {report['verdict']} (secret scanner: {report['secret_scanner']})",
        "| Verdict | Rule | File:line | Text |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {v} | {f['rule']} | {f['file']}:{f['line']} | {f['text']} |"
        for v, f in rows
    ]
    return "\n".join(lines)


def main(argv):
    p = argparse.ArgumentParser(prog="loop_gate", description=__doc__.split("\n")[0])
    p.add_argument("--base", required=True)
    p.add_argument("--root", default=".")
    p.add_argument("--target", default="")
    p.add_argument("--approved", action="append", default=[])
    p.add_argument("--baseline-failed", action="store_true")
    args = p.parse_args(argv)
    try:
        report = gate(
            args.root,
            args.base,
            args.approved,
            args.baseline_failed,
            target=args.target,
        )
    except Usage as e:
        print(f"loop_gate: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report))
    print(table(report))
    return 1 if report["rejects"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
