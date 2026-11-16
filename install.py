#!/usr/bin/env python3
"""Set up the Claude Code guards, the token rules and the git defaults from this clone.

  macOS, Linux:  python3 install.py --check     shows what would change; changes nothing
                 python3 install.py             makes the changes
  Windows:       py install.py --check
                 py install.py

  --skip-plugin  do not run `claude plugin ...` (for tests, or before Claude Code is installed)
  --skip-tools   only report the tools; do not install them or change PATH

It adds and never removes your own values. Before it replaces a value that is weaker than the
safe one (for example bypass mode, or auto mode as the start mode), it asks you. A tool that is
installed but not on PATH: it asks, then adds the folder to PATH. A tool that is missing: it
asks, then installs it (winget, brew, apt-get, or the Claude Code installer). It never sets
your git name, email, signing key or credential helper. Before it changes a file, it saves a
copy as <file>.bak. To undo, put the .bak files back.
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


def tool_dirs(name):
    """Folders where an installer puts this tool, also when the folder is not on PATH."""
    home = Path.home()
    dirs = {"claude": [home / ".local" / "bin", home / ".claude" / "local"]}
    if WINDOWS:
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files")]
        roots.append(str(Path(os.environ.get("LOCALAPPDATA", ""), "Programs")))
        dirs["git"] = [Path(root, "Git", "cmd") for root in roots if root]
    else:
        dirs["git"] = [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    return dirs.get(name, [])


def off_path(name):
    """The folder that holds this tool when PATH does not reach it, else None."""
    exe = name + (".exe" if WINDOWS else "")
    for folder in tool_dirs(name):
        if (folder / exe).is_file() and os.access(folder / exe, os.X_OK):
            return folder
    return None


def installer(name):
    """The command that installs this tool here, or None. The first package manager wins."""
    on = shutil.which
    if name in ("git", "bash"):  # Git for Windows brings Git Bash
        if on("winget"):
            return ["winget", "install", "--id", "Git.Git", "-e"]
        if on("brew"):
            return ["brew", "install", "git"]
        if on("apt-get"):
            return ["sudo", "apt-get", "install", "-y", "git"]
        if SYSTEM == "Darwin":
            return ["xcode-select", "--install"]
    if name in ("bwrap", "socat") and on("apt-get"):
        return ["sudo", "apt-get", "install", "-y", "bubblewrap", "socat"]
    if name == "claude":
        # From the Claude Code setup page; brew and winget first: no download piped into a shell
        if on("winget"):
            return ["winget", "install", "Anthropic.ClaudeCode"]
        if on("brew"):
            return ["brew", "install", "--cask", "claude-code"]
        if WINDOWS:
            return [
                "powershell",
                "-NoProfile",
                "-Command",
                "irm https://claude.ai/install.ps1 | iex",
            ]
        return ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]
    return None


# ── PATH ────────────────────────────────────────────────────────────────────
PATH_START, PATH_END = (
    "# >>> dotfiles-public PATH >>>",
    "# <<< dotfiles-public PATH <<<",
)


def shell_file():
    """The file the user's terminal reads at start."""
    shell = os.path.basename(os.environ.get("SHELL", ""))
    home = Path.home()
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "bash":
        # macOS Terminal starts bash as a login shell, which reads ~/.bash_profile only
        return home / (".bash_profile" if SYSTEM == "Darwin" else ".bashrc")
    return home / ".profile"


def path_line(folder):
    try:
        shown = "$HOME/" + folder.relative_to(Path.home()).as_posix()
    except ValueError:
        shown = folder.as_posix()
    return f'export PATH="{shown}:$PATH"'


def shell_file_has(folder):
    target = shell_file()
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    return path_line(folder) in text


def add_to_shell_file(report, folder):
    target = shell_file()
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    lines = text.splitlines()
    if PATH_START in lines and PATH_END in lines:
        i, j = lines.index(PATH_START), lines.index(PATH_END)
        block = [*lines[i + 1 : j], path_line(folder)]
        lines[i : j + 1] = [PATH_START, *block, PATH_END]
        new = "\n".join(lines) + "\n"
    else:
        sep = "" if not text or text.endswith("\n") else "\n"
        new = f"{text}{sep}{PATH_START}\n{path_line(folder)}\n{PATH_END}\n"
    save(report, target, new, f"adds {home_form(folder)} to PATH")


def broadcast_environment_change():
    """Tell Windows that the user environment changed, so new terminals read the new PATH."""
    import ctypes

    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(
        0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result)
    )  # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG, 5 s


def add_to_windows_path(folder, reg=None, broadcast=broadcast_environment_change):
    """Add folder to the user PATH in the registry. Not setx: it cuts PATH at 1024 characters."""
    if reg is None:
        import winreg as reg
    folder = str(folder)
    key = reg.OpenKey(
        reg.HKEY_CURRENT_USER, "Environment", 0, reg.KEY_READ | reg.KEY_WRITE
    )
    try:
        try:
            value, kind = reg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", reg.REG_EXPAND_SZ
        parts = [part for part in value.split(";") if part]
        known = {part.rstrip("\\/").lower() for part in parts}
        if folder.rstrip("\\/").lower() in known:
            return False
        # %USERPROFILE% in other entries works only in an expandable value
        kind = reg.REG_EXPAND_SZ if kind in (reg.REG_SZ, reg.REG_EXPAND_SZ) else kind
        reg.SetValueEx(key, "Path", 0, kind, ";".join([*parts, folder]))
    finally:
        reg.CloseKey(key)
    broadcast()
    return True


def offer_path(report, name, folder):
    """Ask, then put folder on PATH: for new terminals and for the rest of this run."""
    shown = home_form(folder)
    if not WINDOWS and shell_file_has(folder):
        report.line(
            "ok", f"{name}: {shell_file().name} adds {shown}; open a new terminal"
        )
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
        return True
    where = "your user PATH" if WINDOWS else home_form(shell_file())
    if report.check:
        report.line("not on PATH", f"{name}: {shown}. Would add it to PATH in {where}.")
        return False
    if not ask(f"{name} is in {shown}, which is not on PATH.", f"Add it to {where}?"):
        report.line("kept", f"{name} not on PATH ({shown})")
        return False
    if WINDOWS:
        try:
            add_to_windows_path(folder)
        except OSError as err:
            report.line("failed", f"could not change the user PATH: {err}")
            return False
        report.line("changed", f"user PATH += {folder}")
    else:
        add_to_shell_file(report, folder)
    os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
    report.line("note", "Open a new terminal, so that it reads the new PATH.")
    return True


def offer_install(report, name, offered):
    """Ask, then run the install command. True when the tool can be found after it."""
    cmd = installer(name)
    if not cmd:
        report.line("missing", f"{name}. Fix: {FIXES[name].get(SYSTEM, '')}")
        return False
    text = " ".join(cmd)
    if text in offered:  # bwrap and socat come from one command: ask once
        report.line("missing", f"{name}. Same install command as above: {text}")
        return not report.check  # after a run, the caller looks for the tool again
    offered.add(text)
    if report.check:
        report.line("would", f"install {name}: {text}")
        return False
    if not ask(f"{name} is not installed.", f"Install it now with: {text} ?"):
        report.line("missing", f"{name}. Fix: {text}")
        return False
    try:
        code = subprocess.run(cmd, check=False, timeout=1800).returncode
    except (OSError, subprocess.TimeoutExpired) as err:
        report.line("failed", f"{text}: {err}")
        return False
    if code:
        report.line("failed", f"{text}: exit code {code}")
        return False
    if cmd[0] == "xcode-select":  # opens a dialog and returns at once
        report.line("note", "Finish the install dialog, then run ./install.sh again.")
        return False
    report.line("changed", f"installed {name}")
    return True


def check_tools(report, fix=True):
    """Report each tool. With fix, offer to put an installed tool on PATH, or to install it."""
    print("Tools")
    py = ".".join(map(str, sys.version_info[:3]))
    report.line("ok", f"python {py}")
    names = ["git", "claude", "bash"]
    if SYSTEM == "Linux":
        names += ["bwrap", "socat"]
    offered = set()

    def find(name):
        return git_bash() if WINDOWS and name == "bash" else shutil.which(name)

    found = {}
    for name in names:
        path = find(name)
        if not path and fix:
            folder = off_path(name)
            if not folder and offer_install(report, name, offered):
                path = find(name)
                folder = None if path else off_path(name)
            if folder and offer_path(report, name, folder):
                path = find(name)
        elif not path:
            report.line("missing", f"{name}. Fix: {FIXES[name].get(SYSTEM, '')}")
        if path:
            report.line("ok", f"{name}: {path}")
        found[name] = path
    if SYSTEM == "Linux" and not (found["bwrap"] and found["socat"]):
        report.line(
            "note",
            "Without bubblewrap and socat, Claude Code stops (sandbox.failIfUnavailable).",
        )
    if not found["git"]:
        report.fail("git is needed. Install it, then run install.py again.")
    if WINDOWS and not found["bash"]:
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
    if perms.get("disableBypassPermissionsMode") != "disable":
        found.append(
            (
                (
                    f"permissions.disableBypassPermissionsMode is "
                    f"{perms.get('disableBypassPermissionsMode')!r}, safe: 'disable'"
                ),
                replace("permissions", "disableBypassPermissionsMode", "disable"),
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


# Values that an older version of this setup wrote and no longer wants: (path, value, question)
RETIRED = [
    (
        ("permissions", "disableAutoMode"),
        "disable",
        (
            "permissions.disableAutoMode is 'disable' (from an older install): auto mode is "
            "off. This setup now allows it with shift+tab; sessions still start in default mode."
        ),
        "Allow auto mode again?",
    ),
]


def retired_values(live):
    """(label, prompt, fix) for each value an older install wrote. fix(live) removes it."""
    found = []
    for (section, key), value, label, prompt in RETIRED:
        if live.get(section, {}).get(key) == value:
            found.append((label, prompt, lambda s, a=section, k=key: s[a].pop(k)))
    return found


def ask(question, prompt="Replace it?"):
    print(f"  {question} {prompt} [y/N] ", end="", flush=True)
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
    for label, prompt, fix in retired_values(merged):
        if report.check:
            report.line("retired", label)
        elif ask(label, prompt):
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
    parser.add_argument(
        "--skip-tools",
        action="store_true",
        help="only report the tools; do not install them or change PATH",
    )
    args = parser.parse_args()
    report = Report(args.check)
    print(f"dotfiles-public install{' --check' if args.check else ''} on {SYSTEM}\n")
    check_tools(report, fix=not args.skip_tools)
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
