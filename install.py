#!/usr/bin/env python3
"""Set up the Claude Code guards, the token rules and the git defaults from this clone.

  macOS, Linux:  python3 install.py --check     shows what would change; changes nothing
                 python3 install.py             makes the changes
  Windows:       py install.py --check
                 py install.py

  --skip-plugin  do not run `claude plugin ...` (for tests, or before Claude Code is installed)

It adds and never removes your own values. Before it replaces a value that is weaker than the
safe one (for example an auto approval mode), it asks you. It never installs a tool, and it
never sets your git name, email, signing key or credential helper. Before it changes a file,
it saves a copy as <file>.bak. To undo, put the .bak files back.
"""

import argparse
import fnmatch
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 9):  # noqa: UP036 - an old python3 must get a message, not a SyntaxError later
    sys.exit("install.py needs Python 3.9 or later.")

ROOT = Path(__file__).resolve().parent
CLAUDE_SRC = ROOT / "claude"
sys.path.insert(0, str(CLAUDE_SRC))
import merge_settings

SYSTEM = platform.system()  # Darwin, Linux or Windows
WINDOWS = SYSTEM == "Windows"
MARKETPLACE, PLUGIN = "dotfiles-public", "safe-lean"
SAFE_MODES = {"default", "plan"}
CLAUDE_SETUP = "https://docs.claude.com/en/docs/claude-code/setup"

FIXES = {
    "git": {
        "Darwin": "xcode-select --install   (or: brew install git)",
        "Linux": "sudo apt install git",
        "Windows": "winget install --id Git.Git -e",
    },
    "bash": {
        "Darwin": "bash comes with macOS",
        "Linux": "sudo apt install bash",
        "Windows": "winget install --id Git.Git -e   (Git for Windows brings Git Bash)",
    },
    "claude": {name: f"see {CLAUDE_SETUP}" for name in ("Darwin", "Linux", "Windows")},
    "bwrap": {"Linux": "sudo apt install bubblewrap socat"},
    "socat": {"Linux": "sudo apt install bubblewrap socat"},
}


class Report:
    def __init__(self, check):
        self.check = check
        self.failed = False

    def line(self, status, text):
        print(f"  {status:<8} {text}")

    def fail(self, text):
        self.failed = True
        self.line("FAILED", text)


# ── tools ───────────────────────────────────────────────────────────────────
def git_bash():
    """Git Bash on Windows. Claude Code runs hooks in it; without it the guards fail open."""
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in filter(None, roots):
        for sub in (("Git", "bin", "bash.exe"), ("Programs", "Git", "bin", "bash.exe")):
            path = Path(root, *sub)
            if path.is_file():
                return str(path)
    found = shutil.which("bash")
    # C:\Windows\System32\bash.exe is WSL, not Git Bash
    return found if found and "system32" not in found.lower() else None


def check_tools(report):
    print("Tools")
    py = ".".join(map(str, sys.version_info[:3]))
    report.line("ok", f"python {py}")
    tools = {"git": shutil.which("git"), "claude": shutil.which("claude")}
    tools["bash"] = git_bash() if WINDOWS else shutil.which("bash")
    if SYSTEM == "Linux":
        tools["bwrap"] = shutil.which("bwrap")
        tools["socat"] = shutil.which("socat")
    for name, path in tools.items():
        if path:
            report.line("ok", f"{name}: {path}")
        else:
            report.line("missing", f"{name}. Fix: {FIXES[name].get(SYSTEM, '')}")
    if SYSTEM == "Linux" and not (tools["bwrap"] and tools["socat"]):
        report.line(
            "note",
            "Without bubblewrap and socat, Claude Code stops (sandbox.failIfUnavailable).",
        )
    if not tools["git"]:
        report.fail("git is needed. Install it, then run install.py again.")
    if WINDOWS and not tools["bash"]:
        report.fail(
            "Git Bash is needed: Claude Code runs the guards in it. Without it, no guard runs."
        )


# ── files ───────────────────────────────────────────────────────────────────
def home_form(path):
    """`~/x` for a path in the home folder, else the full path, always with `/`."""
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return path.as_posix()


def save(report, path, new_text, what):
    """Write new_text to path, after a .bak copy of the old file. Nothing in --check mode."""
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == new_text:
        report.line("ok", f"{path} {what}")
        return
    if report.check:
        report.line("would", f"change {path}: {what}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if old is not None:
        shutil.copyfile(path, path.with_name(path.name + ".bak"))
    path.write_text(new_text, encoding="utf-8")
    report.line("changed", f"{path}: {what}")


def setup_rules(report):
    print("Rules (~/.claude/CLAUDE.md)")
    target = Path.home() / ".claude" / "CLAUDE.md"
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    imports = [
        f"@{home_form(CLAUDE_SRC / name)}" for name in ("CLAUDE.md", "CLAUDE.style.md")
    ]
    missing = [line for line in imports if line not in text.splitlines()]
    new = "\n".join(missing) + "\n" + ("\n" + text if text else "") if missing else text
    save(report, target, new, "imports the shared rules and the writing style")


# ── settings ────────────────────────────────────────────────────────────────
def load_json(path):
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError) as err:
        raise SystemExit(
            f"{path} is not valid JSON ({err}). Fix or move the file, then run again."
        ) from None
    if not isinstance(data, dict):
        raise SystemExit(
            f"{path} must hold a JSON object. Fix or move the file, then run again."
        )
    return data


def ours():
    base = load_json(CLAUDE_SRC / "settings.base.json")
    if WINDOWS:
        return base  # native Windows has no sandbox
    return merge_settings.merge(base, load_json(CLAUDE_SRC / "settings.sandbox.json"))


def allows_without_question(rule, excluded):
    """True for an allow rule that lets a command run outside the sandbox unasked."""
    if not rule.startswith(("Bash(", "PowerShell(")):
        return False
    if WINDOWS:
        return True  # no sandbox: every allowed command runs unasked
    text = rule[rule.index("(") + 1 : -1].removesuffix(":*").rstrip("*").strip()
    return any(
        fnmatch.fnmatchcase(text + " x", p) or fnmatch.fnmatchcase(text, p)
        for p in excluded
    )


def weaker_values(live, safe):
    """(label, fix) for each value in live that is weaker than ours. fix(live) repairs it."""
    found = []
    perms, safe_perms = live.setdefault("permissions", {}), safe["permissions"]

    def replace(section, key, value):
        return lambda s: s.setdefault(section, {}).__setitem__(key, value)

    if perms.get("defaultMode") not in SAFE_MODES:
        found.append(
            (
                f"permissions.defaultMode is {perms.get('defaultMode')!r}, safe: 'default'",
                replace("permissions", "defaultMode", safe_perms["defaultMode"]),
            )
        )
    for key in ("disableBypassPermissionsMode", "disableAutoMode"):
        if perms.get(key) != "disable":
            found.append(
                (
                    f"permissions.{key} is {perms.get(key)!r}, safe: 'disable'",
                    replace("permissions", key, "disable"),
                )
            )
    box = live.get("sandbox", {})
    if "sandbox" in safe:
        for key, value in (
            ("enabled", True),
            ("failIfUnavailable", True),
            ("enableWeakerNestedSandbox", False),
            ("enableWeakerNetworkIsolation", False),
        ):
            if box.get(key) != value:
                found.append(
                    (
                        f"sandbox.{key} is {box.get(key)!r}, safe: {value!r}",
                        replace("sandbox", key, value),
                    )
                )
    excluded = box.get("excludedCommands", [])
    for rule in perms.get("allow", []):
        if allows_without_question(rule, excluded):
            why = "no sandbox on Windows" if WINDOWS else "it runs outside the sandbox"
            found.append(
                (
                    f"permissions.allow has {rule}: it runs with no question ({why})",
                    lambda s, r=rule: s["permissions"]["allow"].remove(r),
                )
            )
    return found


def ask(question):
    print(f"  {question} Replace it? [y/N] ", end="", flush=True)
    answer = sys.stdin.readline()
    print()
    return answer.strip().lower() in ("y", "yes")


def setup_settings(report):
    print("Settings (~/.claude/settings.json)")
    target = Path.home() / ".claude" / "settings.json"
    live = load_json(target)
    safe = ours()
    for line in merge_settings.added(live, safe):
        report.line("add", line)
    merged = merge_settings.merge(live, safe)
    for label, fix in weaker_values(merged, safe):
        if report.check:
            report.line("weaker", label)
        elif ask(label):
            fix(merged)
        else:
            report.line("kept", label)
    save(report, target, json.dumps(merged, indent=2) + "\n", "holds the safe baseline")


# ── git ─────────────────────────────────────────────────────────────────────
def git_config(*args):
    p = subprocess.run(
        ["git", "config", "--global", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    return p.returncode, p.stdout.strip()


def setup_git(report):
    print("Git (~/.gitconfig)")
    if not shutil.which("git"):
        report.line("skipped", "no git")
        return
    target = Path.home() / ".gitconfig"
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    shared = home_form(ROOT / "git" / "config.shared")
    # On top: a value later in ~/.gitconfig wins, so the user's own choices stay
    new = (
        text
        if shared in text
        else f"[include]\n\tpath = {shared}\n" + ("\n" + text if text else "")
    )
    save(report, target, new, "includes git/config.shared at the top")
    ignore = home_form(ROOT / "git" / "gitignore_global")
    _, current = git_config("--get", "core.excludesFile")
    if current == ignore:
        report.line("ok", f"core.excludesFile = {ignore}")
    elif current:
        report.line(
            "kept",
            f"your core.excludesFile = {current}. Copy the lines you want from {ignore}.",
        )
    elif report.check:
        report.line("would", f"set core.excludesFile = {ignore}")
    else:
        code, _ = git_config("core.excludesFile", ignore)
        if code:
            report.fail("could not set core.excludesFile")
        else:
            report.line("changed", f"core.excludesFile = {ignore}")


# ── plugin ──────────────────────────────────────────────────────────────────
def claude_cli(exe, *args):
    try:
        p = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return 1, str(err)
    return p.returncode, p.stdout + p.stderr


def setup_plugin(report):
    print("Plugin (guards and skills)")
    commands = [
        ("plugin", "marketplace", "add", CLAUDE_SRC.as_posix()),
        ("plugin", "install", f"{PLUGIN}@{MARKETPLACE}"),
    ]
    exe = shutil.which("claude")
    if not exe:
        report.line("missing", "claude. After you install Claude Code, run:")
        for cmd in commands:
            report.line("", "claude " + " ".join(cmd))
        return
    checks = [("plugin", "marketplace", "list"), ("plugin", "list")]
    names = [MARKETPLACE, f"{PLUGIN}@{MARKETPLACE}"]
    for cmd, check, name in zip(commands, checks, names):
        code, out = claude_cli(exe, *check)
        if code == 0 and name in out:
            report.line("ok", name)
        elif report.check:
            report.line("would", "run: claude " + " ".join(cmd))
        else:
            code, out = claude_cli(exe, *cmd)
            if code:
                report.fail(f"claude {' '.join(cmd)}: {out.strip()[:300]}")
            else:
                report.line("changed", "claude " + " ".join(cmd))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--check", action="store_true", help="show what would change; change nothing"
    )
    parser.add_argument(
        "--skip-plugin", action="store_true", help="do not run `claude plugin ...`"
    )
    args = parser.parse_args()
    report = Report(args.check)
    print(f"dotfiles-public install{' --check' if args.check else ''} on {SYSTEM}\n")
    check_tools(report)
    if report.failed and not args.check:
        return 1
    setup_rules(report)
    setup_settings(report)
    setup_git(report)
    if not args.skip_plugin:
        setup_plugin(report)
    if report.failed:
        print("\nSome steps failed. Read the FAILED lines above.")
        return 1
    if not args.check:
        print(
            "\nDone. Restart Claude Code. To undo a change, put the <file>.bak copy back."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
