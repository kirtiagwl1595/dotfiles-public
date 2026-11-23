#!/usr/bin/env python3
"""Set up the Claude Code guards, the token rules and the git defaults from this clone.

  macOS, Linux:  python3 install.py --check     shows what would change; changes nothing
                 python3 install.py             makes the changes
  Windows:       py install.py --check
                 py install.py

  --skip-plugin  do not run `claude plugin ...` (for tests, or before Claude Code is installed)
  --skip-tools   only report the tools; do not install them or change PATH
  --only STEP    run only the named steps: tools, rules, settings, git, plugin, delta, shell,
                 statusline, templates, macos, packages (repeat the option for more)
  --profile P    the package profile (minimal, developer, full, work): skips the menu
  --manager M    brew, apt or winget: the default fits your system
  --yes-packages answer yes to each package group (the profile is still your choice)
  pkg add|keep|list|brewfile   your own packages; see packages/pkgs.py

It adds and never removes your own values. Before it replaces a value that is weaker than the
safe one (for example bypass mode, or auto mode as the start mode), it asks you. A tool that is
installed but not on PATH: it asks, then adds the folder to PATH. A tool that is missing: it
asks, then installs it (winget, brew, apt-get, or the Claude Code installer). It never sets
your git name, email, signing key or credential helper. Before it changes a file, it saves a
copy as <file>.bak. To undo, put the .bak files back.

Packages: it asks for a profile (a numbered menu; the default is to skip), then asks for each
group of packages. brew, apt-get and winget only run after your yes. With no terminal (stdin
closed), every question gets its default, No. --check lists the plan and installs nothing.
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
sys.path.insert(0, str(ROOT / "packages"))
import merge_settings
import pkgs

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
def is_file(path):
    """Path.is_file(), but a path we may not read (a sandbox, another user's folder) is no file.

    Path.is_file() hides only "not found" errors; a PermissionError would stop --check."""
    try:
        return path.is_file()
    except OSError:
        return False


def git_bash():
    """Git Bash on Windows. Claude Code runs hooks in it; without it the guards fail open."""
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in filter(None, roots):
        for sub in (("Git", "bin", "bash.exe"), ("Programs", "Git", "bin", "bash.exe")):
            path = Path(root, *sub)
            if is_file(path):
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
        if is_file(folder / exe) and os.access(folder / exe, os.X_OK):
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
        target = home / ".zshrc"
    elif shell == "bash":
        # macOS Terminal starts bash as a login shell, which reads ~/.bash_profile only
        target = home / (".bash_profile" if SYSTEM == "Darwin" else ".bashrc")
    else:
        target = home / ".profile"
    return target


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
    print(f"  {' '.join(filter(None, [question, prompt]))} [y/N] ", end="", flush=True)
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
    update_plugin(report, exe)


def plugin_version():
    path = CLAUDE_SRC / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))["version"]


def update_plugin(report, exe):
    """Claude Code runs a cached copy per version: after a git pull, the old copy stays."""
    cache = Path.home() / ".claude" / "plugins" / "cache" / MARKETPLACE / PLUGIN
    version = plugin_version()
    if not cache.is_dir() or (cache / version).is_dir():
        return
    cmd = ("plugin", "update", f"{PLUGIN}@{MARKETPLACE}")
    text = "claude " + " ".join(cmd)
    if report.check:
        report.line("would", f"run: {text} (the plugin copy is older than {version})")
    elif ask(f"The {PLUGIN} plugin copy is older than {version}.", f"Run {text} ?"):
        code, out = claude_cli(exe, *cmd)
        if code:
            report.fail(f"{text}: {out.strip()[:300]}")
        else:
            report.line("changed", f"{text}. Restart Claude Code.")
    else:
        report.line("kept", f"old {PLUGIN} copy. Later: {text}")


def setup_delta(report):
    print("Git pager (delta)")
    if not shutil.which("delta"):
        report.line("skipped", "delta is not installed (package git-delta)")
        return
    target = Path.home() / ".gitconfig"
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    shared = home_form(ROOT / "git" / "config.shared")
    delta = home_form(ROOT / "git" / "config.delta")
    if delta in text:
        report.line("ok", f"{target} includes git/config.delta")
    elif report.check:
        report.line("would", "ask to use delta as the git pager (git/config.delta)")
    elif ask(
        "delta is installed.", "Use it as the git pager (includes git/config.delta)?"
    ):
        line = f"\tpath = {shared}\n"
        new = text.replace(line, f"{line}\tpath = {delta}\n", 1)
        if new == text:  # no shared include to sit under: add a block at the end
            new = f"{text.rstrip()}\n[include]\n\tpath = {delta}\n".lstrip()
        save(report, target, new, "includes git/config.delta")
    else:
        report.line("kept", "git pager")


# ── shell config ────────────────────────────────────────────────────────────
def documents_folder():
    """Where Documents is: the registry value follows a OneDrive move; else ~/Documents."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "Personal")
        finally:
            winreg.CloseKey(key)
        return Path(os.path.expandvars(value))
    except (ImportError, OSError):
        return Path.home() / "Documents"


def powershell_profiles():
    """[(path, policy)] for each PowerShell here: the file it reads at start, its execution policy.

    PowerShell 7 (pwsh) and Windows PowerShell 5.1 (powershell) are asked, because OneDrive
    can move Documents. If the question fails, the usual folder is the guess (policy None).
    A computer with neither program gets no entry: no shell would read the file.
    """
    query = "$PROFILE.CurrentUserCurrentHost; Get-ExecutionPolicy"
    found = []
    for exe, folder in (("pwsh", "PowerShell"), ("powershell", "WindowsPowerShell")):
        path = shutil.which(exe)
        if not path:
            continue
        guess = documents_folder() / folder / "Microsoft.PowerShell_profile.ps1"
        try:
            p = subprocess.run(
                [path, "-NoProfile", "-Command", query],
                capture_output=True,
                stdin=subprocess.DEVNULL,  # it must not read the answers meant for ask()
                text=True,
                encoding="utf-8",
                check=False,
                timeout=60,
            )
            lines = p.stdout.split("\n") if p.returncode == 0 else []
            lines = [x.strip() for x in lines if x.strip()]
        except (OSError, subprocess.TimeoutExpired):
            lines = []
        entry = (
            (Path(lines[0]), lines[1] if len(lines) > 1 else None)
            if lines
            else (guess, None)
        )
        if entry[0] not in [f[0] for f in found]:
            found.append(entry)
    return found


def config_files():
    """[(source in this clone, target in the home folder)] to link or copy."""
    home = Path.home()
    files = [
        (ROOT / "shell" / "vim" / ".vimrc", home / ".vimrc"),
        (ROOT / "shell" / "starship.toml", home / ".config" / "starship.toml"),
        (ROOT / "shell" / "editorconfig", home / ".editorconfig"),
    ]
    if WINDOWS:
        profile = ROOT / "shell" / "powershell" / "Microsoft.PowerShell_profile.ps1"
        files += [(profile, path) for path, _ in powershell_profiles()]
    return files


def zsh_blocks():
    """[(file in this clone, your file)]: your file gets a block that sources the clone file."""
    zsh, home = ROOT / "shell" / "zsh", Path.home()
    return [(zsh / ".zshrc", home / ".zshrc"), (zsh / ".zprofile", home / ".zprofile")]


def block_markers(name):
    return f"# >>> dotfiles-public {name} >>>", f"# <<< dotfiles-public {name} <<<"


def set_block(text, name, body):
    """text with the block `name` set to body: replaced if it is there, else added at the end."""
    start, end = block_markers(name)
    lines = text.splitlines()
    if start in lines and end in lines:
        i, j = lines.index(start), lines.index(end)
        lines[i : j + 1] = [start, *body, end]
        return "\n".join(lines) + "\n"
    sep = "" if not text or text.endswith("\n") else "\n"
    return f"{text}{sep}{start}\n" + "\n".join(body) + f"\n{end}\n"


def place_block(report, src, dst):
    """Add a block to your own file that sources src. The rest of your file stays as it is."""
    shown = home_form(dst)
    text = dst.read_text(encoding="utf-8") if dst.exists() else ""
    try:
        where = '"$HOME/' + src.relative_to(Path.home()).as_posix() + '"'
    except ValueError:
        where = f'"{src.as_posix()}"'
    new = set_block(text, "zsh", [f"[[ -f {where} ]] && source {where}"])
    if new == text:
        report.line("ok", f"{shown} sources {src.relative_to(ROOT).as_posix()}")
    elif report.check:
        report.line("would", f"ask to add a block to {shown} that sources {src.name}")
    elif ask(
        f"{shown} {'exists' if dst.exists() else 'is missing'}.",
        f"Add a block that sources {src.name}? Your own lines stay; the old file is saved as {shown}.bak.",
    ):
        save(report, dst, new, f"sources {src.relative_to(ROOT).as_posix()}")
    else:
        report.line("kept", shown)


def same_as(src, dst):
    if WINDOWS:  # Windows copies: a symlink there needs special rights
        return dst.is_file() and dst.read_bytes() == src.read_bytes()
    return dst.is_symlink() and dst.resolve() == src.resolve()


def place(report, src, dst):
    shown, what = home_form(dst), "copy" if WINDOWS else "link"
    if same_as(src, dst):
        report.line("ok", f"{shown} is a {what} of {src.relative_to(ROOT).as_posix()}")
        return
    exists = dst.exists() or dst.is_symlink()
    if report.check:
        report.line("would", f"ask to put a {what} of {src.name} at {shown}")
        return
    state = f"{shown} exists." if exists else f"{shown} is missing."
    saved = f" The old file is saved as {shown}.bak." if exists else ""
    if not ask(state, f"Put a {what} of {src.name} there?{saved}"):
        report.line("kept", shown)
        return
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if exists:
            os.replace(dst, dst.with_name(dst.name + ".bak"))
        if WINDOWS:
            shutil.copyfile(src, dst)
        else:
            os.symlink(src, dst)
    except OSError as err:
        report.fail(f"{shown}: {err}")
        return
    report.line("changed", f"{shown} is a {what} of {src.name}")


def setup_shell(report):
    print("Shell config (zsh or PowerShell, vim, starship, editorconfig)")
    if not WINDOWS:
        for src, dst in zsh_blocks():
            place_block(report, src, dst)
    else:
        profiles = powershell_profiles()
        if not profiles:
            report.line(
                "skipped", "no PowerShell found (pwsh or powershell): no profile to set"
            )
        if any(policy == "Restricted" for _, policy in profiles):
            report.line(
                "note",
                "The execution policy is Restricted: PowerShell will not load a profile. "
                "To allow it, run yourself: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned",
            )
    for src, dst in config_files():
        place(report, src, dst)


# ── Claude Code status line, templates, macOS defaults ──────────────────────
def setup_statusline(report):
    print("Status line (Claude Code)")
    command = f'bash "{(CLAUDE_SRC / "statusline.sh").as_posix()}"'
    target = Path.home() / ".claude" / "settings.json"
    live = load_json(target)
    current = live.get("statusLine")
    if isinstance(current, dict) and current.get("command") == command:
        report.line("ok", "status line is claude/statusline.sh")
        return
    if report.check:
        report.line("would", "ask to use claude/statusline.sh as the status line")
        return
    state = "You have a status line already." if current else "No status line is set."
    if not ask(state, "Use claude/statusline.sh (model, context, git branch, cost)?"):
        report.line("kept", "status line")
        return
    live["statusLine"] = {"type": "command", "command": command}
    save(report, target, json.dumps(live, indent=2) + "\n", "uses claude/statusline.sh")


TEMPLATES = ("CLAUDE.about-me", "CLAUDE.profile")


def setup_templates(report):
    print("Personal templates (~/.claude)")
    for name in TEMPLATES:
        src = CLAUDE_SRC / f"{name}.example.md"
        dst = Path.home() / ".claude" / f"{name}.md"
        shown = home_form(dst)
        if dst.exists():
            report.line("ok", f"{shown} exists; never replaced")
        elif report.check:
            report.line("would", f"ask to copy {src.name} to {shown}")
        elif ask(f"{shown} is missing.", f"Copy the template {src.name} there?"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            report.line(
                "changed",
                f"{shown}. Fill it in, then add this line to ~/.claude/CLAUDE.md:",
            )
            report.line("", f"@{shown}")
        else:
            report.line("kept", f"no {shown}")


def real_home():
    """The home folder of this user account, whatever $HOME says."""
    import pwd

    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def setup_macos(report):
    print("macOS defaults (Finder, Dock, keyboard)")
    if SYSTEM != "Darwin":
        report.line("skipped", "macOS only")
        return
    if real_home() != Path.home():
        # `defaults` writes the real preferences, not the folder in $HOME
        report.line("skipped", f"$HOME is not your real home folder ({real_home()})")
        return
    script = ROOT / "scripts" / "macos-defaults.sh"
    if report.check:
        report.line("would", f"ask to run scripts/{script.name}")
    elif ask(
        "Finder, Dock and keyboard settings.",
        f"Run scripts/{script.name}? It saves your values first.",
    ):
        env = {**os.environ, "DOTFILES_MACOS_OK": "1"}
        code = subprocess.run(["bash", str(script)], env=env, check=False).returncode
        if code:
            report.fail(f"scripts/{script.name} exit code {code}")
        else:
            report.line("changed", f"ran scripts/{script.name}")
    else:
        report.line("kept", "macOS settings")


# ── packages ────────────────────────────────────────────────────────────────
def plural(n):
    return f"{n} package{'s' if n != 1 else ''}"


def choose_profile(manifest, manager):
    """A numbered menu. Only a number or an exact name picks a profile; all else skips."""
    names = list(manifest["profiles"])
    print("  Package profile:")
    for i, name in enumerate(names, 1):
        n = pkgs.count(manifest, name, manager)
        text = manifest["profiles"][name]["description"]
        print(f"    {i}. {name:<10} {text} ({plural(n)} for {manager})")
    print("    0. skip (default)")
    print(f"  Profile [0-{len(names)}]: ", end="", flush=True)
    answer = sys.stdin.readline().strip().lower()
    print()
    if answer.isdigit() and 1 <= int(answer) <= len(names):
        return names[int(answer) - 1]
    return answer if answer in names else None


def setup_packages(report, args):
    print("Packages")
    manifest = pkgs.load()
    profiles = list(manifest["profiles"])
    if args.profile and args.profile not in profiles:
        print(f"  No profile {args.profile}. Profiles: {', '.join(profiles)}")
        report.failed = True
        return
    manager = args.manager or pkgs.default_manager(SYSTEM)
    exe = pkgs.find_manager(manager)
    if not exe:
        text = f"{pkgs.PROGRAM[manager]} not found. Fix: {pkgs.FIX[manager]}"
        if args.profile and not report.check:
            report.fail(text)  # you named a profile: it cannot be installed
            return
        report.line("missing", text)
        if not report.check:
            return
    profile = args.profile
    if not profile and report.check:
        for name in profiles:
            n = pkgs.count(manifest, name, manager)
            report.line(
                "plan",
                f"{name}: {plural(n)} for {manager}. Add --profile {name} to see the groups.",
            )
        return
    if not profile:
        profile = choose_profile(manifest, manager)
    if not profile:
        report.line("skipped", "no package profile chosen")
        return
    failed, updated = [], False
    for group, spec in pkgs.groups_for(manifest, profile):
        have, missing = pkgs.split(spec, manager)
        for p in missing:
            report.line(
                "skipped",
                f"{p['name']}: no {manager} package. {p.get('note', '')}".rstrip(),
            )
        if not have:
            continue
        names = ", ".join(p["name"] for p in have)
        if report.check:
            report.line("would", f"install {group} ({plural(len(have))}): {names}")
            continue
        report.line("group", f"{group}: {names}")
        for cmd in pkgs.batch_commands(manager, exe, have):
            report.line("run", " ".join(cmd))
        if args.yes_packages:
            print(f"  Install {group} ({plural(len(have))})? [y/N] y")
        elif not ask(f"Install {group} ({plural(len(have))})?", ""):
            report.line("kept", f"{group} not installed")
            continue
        if manager == "apt" and not updated:
            updated = True  # once per run, after the first yes
            if not pkgs.run(pkgs.apt_update_command(), manager):
                report.line(
                    "note", "apt-get update failed; the install may use an old index"
                )
        failed += pkgs.install_group(manager, exe, have)
    for name in failed:
        report.fail(f"{manager} could not install {name}")
    if not report.check and not failed:
        report.line("done", f"profile {profile}")


STEPS = (
    "tools",
    "rules",
    "settings",
    "git",
    "plugin",
    "delta",
    "shell",
    "statusline",
    "templates",
    "macos",
    "packages",
)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "pkg":
        return pkgs.cli(sys.argv[2:], SYSTEM)
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
    parser.add_argument(
        "--only", action="append", choices=STEPS, help="run only this step (repeatable)"
    )
    parser.add_argument("--profile", help="package profile: skips the menu")
    parser.add_argument("--manager", choices=pkgs.MANAGERS, help="brew, apt or winget")
    parser.add_argument(
        "--yes-packages", action="store_true", help="answer yes to each package group"
    )
    args = parser.parse_args()
    report = Report(args.check)
    print(f"dotfiles-public install{' --check' if args.check else ''} on {SYSTEM}\n")

    def wanted(step):
        return not args.only or step in args.only

    # One rule: with --only, exactly the named steps run; without it, all of them run
    if wanted("tools"):
        check_tools(report, fix=not args.skip_tools)
        if report.failed and not args.check:
            return 1
    if wanted("rules"):
        setup_rules(report)
    if wanted("settings"):
        setup_settings(report)
    if wanted("git"):
        setup_git(report)
    if wanted("plugin") and not args.skip_plugin:
        setup_plugin(report)
    # New steps come last: a question in an earlier step keeps its place in the answers
    for step, run in (
        ("delta", setup_delta),
        ("shell", setup_shell),
        ("statusline", setup_statusline),
        ("templates", setup_templates),
        ("macos", setup_macos),
    ):
        if wanted(step):
            run(report)
    if wanted("packages"):
        setup_packages(report, args)
    if report.failed:
        print("\nSome steps failed. Read the FAILED lines above.")
        return 1
    if not args.check:
        print(
            "\nDone. Restart Claude Code. To undo a change, put the <file>.bak copy back."
        )
    return 0


def run():
    """main(), with a file we may not read reported as one line: a sandbox can hide ~/.claude."""
    try:
        return main()
    except PermissionError as e:
        print(
            f"install.py: cannot read {e.filename}: {e.strerror}. "
            "Run it in a normal terminal, outside a sandbox.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(run())
