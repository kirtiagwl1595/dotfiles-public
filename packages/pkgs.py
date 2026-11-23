"""Read packages.json and plan what to install with brew, apt-get or winget.

install.py imports this file for its "packages" step. It also has a small command line:

  python3 install.py pkg add [--manager M] [--cask] <name>   install one package, record a trial
  python3 install.py pkg keep <name>                          move a trial into your local list
  python3 install.py pkg list                                 trials and kept packages
  python3 install.py pkg brewfile [profile]                   print a Brewfile for `brew bundle`
  python3 packages/pkgs.py names <manager> [manifest.json]    names for scripts/check-package-names.sh

Your own lists are two untracked files, trials.json and local.json, in this folder
(or in $DOTFILES_PACKAGES_DIR). local.json is a group called "local" in every profile.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANAGERS = ("brew", "apt", "winget")
PROGRAM = {"brew": "brew", "apt": "apt-get", "winget": "winget"}
# winget exit codes for "already installed" and "no newer version" (0x8A15002B, 0x8A150061)
WINGET_FINE = {0, 0x8A15002B, 0x8A150061, -1978335189, -1978335135}
WINGET_FLAGS = ["--exact", "--accept-package-agreements", "--accept-source-agreements"]
PLAIN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+-]*$")
FIX = {
    "brew": "see https://brew.sh",
    "apt": "apt-get comes with Debian and Ubuntu; on other systems use brew",
    "winget": "winget comes with Windows 11 (App Installer in the Microsoft Store)",
}


def data_dir():
    return Path(os.environ.get("DOTFILES_PACKAGES_DIR") or HERE)


def load(path=None):
    return json.loads(Path(path or HERE / "packages.json").read_text(encoding="utf-8"))


def read_list(name):
    path = data_dir() / name
    if not path.is_file():
        return {"packages": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_list(name, data):
    path = data_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def default_manager(system, which=shutil.which):
    if system == "Windows":
        return "winget"
    if system == "Linux" and (which("apt-get") or not which("brew")):
        return "apt"
    return "brew"


def profile_groups(manifest, profile):
    """Group names of a profile, those of the profile it extends first."""
    spec = manifest["profiles"][profile]
    base = profile_groups(manifest, spec["extends"]) if "extends" in spec else []
    return base + [g for g in spec["groups"] if g not in base]


def groups_for(manifest, profile):
    """[(name, group)] of a profile, plus your own "local" group when you have one."""
    found = [(g, manifest["groups"][g]) for g in profile_groups(manifest, profile)]
    local = read_list("local.json")["packages"]
    if local:
        found.append(("local", {"title": "Packages you kept", "packages": local}))
    return found


def package_name(pkg, manager):
    """The name the manager knows, without the cask: prefix; None when it has none."""
    value = pkg.get(manager)
    return value.removeprefix("cask:") if value else None


def split(group, manager):
    """(packages this manager can install, packages it has no name for)."""
    have = [p for p in group["packages"] if p.get(manager)]
    return have, [p for p in group["packages"] if not p.get(manager)]


def count(manifest, profile, manager):
    return sum(len(split(g, manager)[0]) for _, g in groups_for(manifest, profile))


def find_manager(manager):
    """Full path of the manager program (Windows cannot start brew.cmd by name), else None."""
    return shutil.which(PROGRAM[manager])


def sudo_prefix():
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    return [shutil.which("sudo") or "sudo"]


def apt_update_command():
    return [*sudo_prefix(), "apt-get", "update"]


def batch_commands(manager, exe, packages):
    """The commands that install all packages at once. winget takes one id per call."""
    if manager == "winget":
        return single_commands(manager, exe, packages)
    names = [package_name(p, manager) for p in packages]
    if manager == "apt":
        return [[*sudo_prefix(), "apt-get", "install", "-y", *names]]
    formulas = [package_name(p, "brew") for p in packages if not is_cask(p)]
    casks = [package_name(p, "brew") for p in packages if is_cask(p)]
    cmds = []
    if formulas:
        cmds.append([exe, "install", *formulas])
    if casks:
        cmds.append([exe, "install", "--cask", *casks])
    return cmds


def single_commands(manager, exe, packages):
    cmds = []
    for p in packages:
        name = package_name(p, manager)
        if manager == "winget":
            cmds.append([exe, "install", "--id", name, *WINGET_FLAGS])
        elif manager == "apt":
            cmds.append([*sudo_prefix(), "apt-get", "install", "-y", name])
        else:
            cask = ["--cask"] if is_cask(p) else []
            cmds.append([exe, "install", *cask, name])
    return cmds


def is_cask(pkg):
    return (pkg.get("brew") or "").startswith("cask:")


def run(cmd, manager):
    """True when the command worked (for winget, also when the package was there already)."""
    try:
        code = subprocess.run(cmd, check=False, timeout=3600).returncode
    except (OSError, subprocess.TimeoutExpired) as err:
        print(f"  {err}")
        return False
    return code == 0 or (manager == "winget" and code in WINGET_FINE)


def install_group(manager, exe, packages):
    """Install a group. Returns the names that failed. A failed batch is retried one by one."""
    if manager != "winget":
        results = [run(c, manager) for c in batch_commands(manager, exe, packages)]
        if all(results):  # every command ran: a cask is tried after the formulas
            return []
        if len(packages) == 1:
            return [package_name(packages[0], manager)]
    singles = single_commands(manager, exe, packages)
    return [
        package_name(p, manager)
        for p, cmd in zip(packages, singles)
        if not run(cmd, manager)
    ]


def brewfile(manifest, profile):
    lines = [f"# Brewfile for the {profile} profile, made from packages/packages.json"]
    for group, spec in groups_for(manifest, profile):
        lines.append(f"\n# {group}")
        for p in spec["packages"]:
            if p.get("brew"):
                kind = "cask" if is_cask(p) else "brew"
                lines.append(f'{kind} "{package_name(p, "brew")}"')
    return "\n".join(lines) + "\n"


# ── command line: install.py pkg ... ────────────────────────────────────────
def say(text):
    print(text)


def known_names(manifest):
    names = set()
    for spec in manifest["groups"].values():
        for p in spec["packages"]:
            names.add(p["name"])
            names.update(package_name(p, m) for m in MANAGERS if p.get(m))
    return names


def cmd_add(args, system):
    name = args.name
    if not PLAIN_NAME.match(name):
        say(f"pkg: '{name}' is not a plain package name (no URL, no tap, no spaces).")
        return 2
    manager = args.manager or default_manager(system)
    trials = read_list("trials.json")
    if name in {t["name"] for t in trials["packages"]} | known_names(load()):
        say(f"pkg: {name} is already a trial or in the manifest.")
        return 1
    exe = find_manager(manager)
    if not exe:
        say(f"pkg: {PROGRAM[manager]} not found. Fix: {FIX[manager]}")
        return 1
    pkg = {"name": name, manager: ("cask:" if args.cask else "") + name}
    if not all(run(c, manager) for c in single_commands(manager, exe, [pkg])):
        say(f"pkg: install of {name} failed; nothing recorded.")
        return 1
    trials["packages"].append({"name": name, "manager": manager, "cask": args.cask})
    write_list("trials.json", trials)
    say(
        f"added {name} as a trial on this computer. Keep it: install.py pkg keep {name}"
    )
    return 0


def cmd_keep(args):
    trials = read_list("trials.json")
    trial = next((t for t in trials["packages"] if t["name"] == args.name), None)
    if trial is None:
        say(f"pkg: {args.name} is not a trial (install.py pkg list shows them).")
        return 1
    pkg = {m: None for m in MANAGERS}
    pkg[trial["manager"]] = ("cask:" if trial.get("cask") else "") + args.name
    pkg.update(
        name=args.name,
        desc="a package you kept",
        note=f"kept from a trial with {trial['manager']}; no name known for the other managers",
    )
    local = read_list("local.json")
    local["packages"].append(pkg)
    write_list("local.json", local)
    trials["packages"] = [t for t in trials["packages"] if t is not trial]
    write_list("trials.json", trials)
    say(f"kept {args.name} in {data_dir() / 'local.json'} (not tracked by git).")
    return 0


def cmd_list():
    for title, name in (("trials", "trials.json"), ("kept", "local.json")):
        items = read_list(name)["packages"]
        say(f"{title}: " + (", ".join(p["name"] for p in items) or "none"))
    return 0


def cmd_names(manager, manifest_path):
    for spec in load(manifest_path)["groups"].values():
        for p in spec["packages"]:
            if p.get(manager):
                kind = "cask" if is_cask(p) else manager
                say(f"{kind} {package_name(p, manager)}")
    return 0


def cli(argv, system):
    parser = argparse.ArgumentParser(prog="install.py pkg")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="install one package and record it as a trial")
    add.add_argument("name")
    add.add_argument("--manager", choices=MANAGERS)
    add.add_argument("--cask", action="store_true", help="a Homebrew cask")
    keep = sub.add_parser("keep", help="move a trial into your local list")
    keep.add_argument("name")
    sub.add_parser("list", help="show trials and kept packages")
    bf = sub.add_parser("brewfile", help="print a Brewfile for brew bundle")
    bf.add_argument("profile", nargs="?", default="developer")
    names = sub.add_parser("names", help="names of one manager, for scripts")
    names.add_argument("manager", choices=MANAGERS)
    names.add_argument("manifest", nargs="?")
    args = parser.parse_args(argv)
    if args.cmd == "add":
        return cmd_add(args, system)
    if args.cmd == "keep":
        return cmd_keep(args)
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "names":
        return cmd_names(args.manager, args.manifest)
    manifest = load()
    if args.profile not in manifest["profiles"]:
        say(
            f"pkg: no profile {args.profile}. Profiles: {', '.join(manifest['profiles'])}"
        )
        return 2
    sys.stdout.write(brewfile(manifest, args.profile))
    return 0


if __name__ == "__main__":
    import platform

    sys.exit(cli(sys.argv[1:], platform.system()))
