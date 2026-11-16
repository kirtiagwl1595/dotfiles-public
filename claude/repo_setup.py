"""Bring a repo (or each repo under a folder) up to the Claude-forward setup. The setup-repo
skill runs it.

Per repo: a managed .gitignore block, .claude/settings.json (merged, never replaced), the
quiet-pytest block for uv projects, then one commit on branch chore/claude-forward. Dirty repos
are skipped; nothing is pushed. Standard library only, Python 3.9+. On Windows (no sandbox) the
project settings get no Bash allow rules: every command there keeps its approval prompt.

  repo_setup.py plan  [ROOT]     report only, changes nothing (ROOT: a repo or a folder of repos; default: here)
  repo_setup.py apply [ROOT]     make the changes
  repo_setup.py apply [ROOT] --untrack   also git rm --cached tracked personal/secret files (opt-in)
  repo_setup.py team  [REPO]     print the team owner (exit 0), or nothing for your own repo (exit 1)

Start it through the plugin's Python launcher (Windows: `python3` can be the Store stub):
  bash "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" ../repo_setup.py plan "$PWD"
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from merge_settings import merge

HERE = (
    Path(__file__).resolve().parent
)  # claude/ in the repo, the version folder in the plugin cache
BRANCH = "chore/claude-forward"
ENV_TEMPLATES = (
    ".env.example",
    ".env.sample",
    ".env.template",
)  # same list as hooks/guard_secrets.py
START, END = (
    "# >>> claude-forward (dotfiles) >>>",
    "# <<< claude-forward (dotfiles) <<<",
)  # the same markers as the dotfiles setup, so a repo never gets two blocks

IGNORE = {
    "common": [
        ".DS_Store",
        "~$*",
        ".env",
        ".env.*",
        "!.env.example",
        "!.env.sample",
        "!.env.template",
        "CLAUDE.local.md",
        ".claude/settings.local.json",
        ".claude/lessons/",
        ".claude/worktrees/",
        "graphify-out/cache/",
    ],
    "python": [
        ".venv/",
        "__pycache__/",
        ".ipynb_checkpoints/",
        ".pytest_cache/",
        ".ruff_cache/",
        "data/raw/",
    ],
    "r": [".Rhistory", ".RData", ".Rproj.user/", "*_cache/", "*.knit.md"],
    "node": ["node_modules/", ".next/", "dist/"],
}
# Native Windows has no sandbox: an allow rule there runs the command with no question
ALLOW = (
    {}
    if os.name == "nt"
    else {
        "python": ["Bash(uv run pytest:*)", "Bash(uv run ruff:*)", "Bash(uv add:*)"],
        "r": ["Bash(Rscript:*)"],
        "node": ["Bash(npm test:*)", "Bash(npm run lint:*)"],
    }
)


def git(repo, *args, check=False):
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )
    return p.stdout.strip() if p.returncode == 0 else ""


def ok(repo, *args):
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, check=False
        ).returncode
        == 0
    )


_users = {}


def team_owner(repo):
    """The owner of a team repo (origin not under your own username), else None.

    No origin → yours. Unknown login → treated as a team repo, so it is never touched by mistake.
    SAFE_LEAN_REPOS_ALL=1 includes team repos.
    """
    url = git(repo, "remote", "get-url", "origin")
    if not url or os.environ.get("SAFE_LEAN_REPOS_ALL") == "1":
        return None
    rest = url.split("://", 1)[-1].split("@", 1)[-1]
    host, _, path = (
        rest.replace(":", "/", 1).partition("/")
        if "://" not in url
        else rest.partition("/")
    )
    host = host.split(":")[0]
    owner = path.split("/")[0]
    if host not in _users and os.environ.get("FORGE_GIT_USER"):
        _users[host] = os.environ[
            "FORGE_GIT_USER"
        ].lower()  # what forge.sh whoami would say
    if host not in _users:
        p = subprocess.run(
            ["bash", str(HERE / "forge.sh"), "whoami", host],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        _users[host] = p.stdout.strip().lower()
    return None if owner.lower() == _users[host] else owner or "?"


def find_repos(root):
    if (root / ".git").exists():  # ROOT is one repo (the setup-repo skill)
        return [root]
    return [
        p.parent for p in sorted(root.glob("*/.git")) + sorted(root.glob("*/*/.git"))
    ]


def languages(repo):
    files = git(repo, "ls-files").splitlines()
    langs = []
    if (repo / "pyproject.toml").exists() or any(
        f.endswith((".py", ".ipynb")) for f in files
    ):
        langs.append("python")
    if any(f.endswith((".R", ".r", ".Rmd", ".Rproj")) for f in files):
        langs.append("r")
    if (repo / "package.json").exists():
        langs.append("node")
    return langs


def gitignore_text(repo, langs):
    """The repo's .gitignore with our block added or replaced (the rest is kept as is)."""
    path = repo / ".gitignore"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = old.splitlines()
    if START in lines and END in lines:
        lines = lines[: lines.index(START)] + lines[lines.index(END) + 1 :]
    while lines and not lines[-1].strip():
        lines.pop()
    block = [START, "# Managed by the setup-repo skill; edit outside this block."]
    for key in ["common", *langs]:
        block += IGNORE[key]
    return "\n".join([*lines, *([""] if lines else []), *block, END]) + "\n"


def settings_text(repo, langs):
    path = repo / ".claude" / "settings.json"
    if ok(repo, "check-ignore", "-q", ".claude/settings.json"):
        return None  # the team ignores .claude/ on purpose: leave it alone
    try:
        user = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        sys.exit(f"{path}: not valid JSON")
    allow = [a for lang in langs for a in ALLOW.get(lang, [])]
    if not allow:
        return None  # nothing to add (always so on Windows): no empty settings file
    base = {"permissions": {"allow": allow}}
    merged = merge(user, base)
    return (
        None
        if merged == user and path.exists()
        else json.dumps(merged, indent=2) + "\n"
    )


def pytest_block(repo, langs):
    py = repo / "pyproject.toml"
    if (
        "python" not in langs
        or not py.exists()
        or "[tool.pytest.ini_options]" in py.read_text(encoding="utf-8")
    ):
        return None
    return (
        py.read_text(encoding="utf-8").rstrip("\n")
        + "\n"
        + (HERE / "templates/pyproject-pytest.toml").read_text(encoding="utf-8")
    )


def changes(repo):
    """{relative path: new text} for every file that needs to change."""
    langs = languages(repo)
    out = {}
    if gitignore_text(repo, langs) != (
        (repo / ".gitignore").read_text(encoding="utf-8")
        if (repo / ".gitignore").exists()
        else ""
    ):
        out[".gitignore"] = gitignore_text(repo, langs)
    if (s := settings_text(repo, langs)) is not None:
        out[".claude/settings.json"] = s
    if (p := pytest_block(repo, langs)) is not None:
        out["pyproject.toml"] = p
    return out


def tracked_personal(repo):
    files = git(repo, "ls-files").splitlines()
    return [
        f
        for f in files
        if Path(f).name in (".env", "CLAUDE.local.md")
        or f.endswith(".claude/settings.local.json")
        or "/.claude/lessons/" in f"/{f}"
        or (Path(f).name.startswith(".env.") and Path(f).name not in ENV_TEMPLATES)
    ]


def report(root, apply=False, untrack=False):
    repos = find_repos(root)
    print(f"  ✓ scanning {str(root).replace(str(Path.home()), '~', 1)}")
    if not repos:
        print(f"  ✓ no repos under {root}")
    for repo in repos:
        name = str(repo.relative_to(root)) if repo != root else repo.name
        if repo != root and team_owner(repo):
            print(
                f"  ✓ {name}: team repo, skipped (only your own repos are changed; SAFE_LEAN_REPOS_ALL=1 for all)"
            )
            continue
        todo, personal = changes(repo), tracked_personal(repo)
        note = (
            ""
            if (repo / "CLAUDE.md").exists()
            else "  (no CLAUDE.md: run `claude` there, then /setup-repo)"
        )
        if not todo and not personal:
            print(f"  ✓ {name} is Claude-forward{note}")
            continue
        on_branch = git(repo, "ls-tree", "-r", "--name-only", BRANCH).splitlines()
        pending = any(  # local branch, or only on the remote (an open PR/MR)
            git(repo, "rev-list", "--count", f"HEAD..{ref}") not in ("", "0")
            for ref in (BRANCH, f"origin/{BRANCH}")
        )
        if pending and not (
            untrack and set(personal) & set(on_branch)
        ):  # merged branches don't count
            print(
                f"  ✓ {name}: ready on {BRANCH}, waiting for you to push + merge it (PR/MR){note}"
            )
            continue
        if git(repo, "status", "--porcelain"):
            print(
                f"  ! {name}: has uncommitted changes, skipped (commit or stash, then run again)"
            )
            continue
        if personal:
            print(
                f"  ! {name}: personal/secret files are tracked: {', '.join(personal)}."
                " They stay in git history: rotate any key in them."
                + (
                    ""
                    if untrack
                    else f"\n      To untrack (files stay on disk): repo_setup.py apply {root} --untrack"
                )
            )
        personal = personal if untrack else []
        if not todo and not personal:
            continue
        what = ", ".join(todo) + (
            ", untrack " + ", ".join(personal) if personal else ""
        )
        if not apply:
            print(
                f"  → {name} [{', '.join(languages(repo)) or 'no code'}]: {what} on branch {BRANCH}{note}"
            )
            continue
        start = git(repo, "symbolic-ref", "--short", "HEAD")
        if not start:
            print(
                f"  ! {name}: detached HEAD, skipped (switch to a branch, then run again)"
            )
            continue
        try:
            apply_one(repo, todo, personal, fresh=not pending)
            git(repo, "switch", "-q", start, check=True)
        except subprocess.CalledProcessError as e:
            rollback(repo, start)
            err = (e.stderr or "").strip().splitlines()[-1:] or [str(e)]
            print(f"  ! {name}: failed, nothing changed ({err[0]})")
            continue
        print(f"  → {name}: committed on {BRANCH} ({what}); not pushed{note}")


def apply_one(repo, todo, personal, fresh=True):
    # fresh: the branch has no unmerged commits, so start it again from HEAD (an old,
    # merged branch would get files made from today's HEAD on top of old content)
    if fresh:
        git(repo, "switch", "-q", "-C", BRANCH, check=True)
    elif not ok(repo, "switch", "-q", BRANCH):
        git(repo, "switch", "-q", "-c", BRANCH, check=True)
    for rel, text in todo.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        # open(), not write_text(newline=): that needs Python 3.10
        with open(repo / rel, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    if personal:
        git(repo, "rm", "-q", "--cached", "--", *personal, check=True)
    if todo:
        git(repo, "add", "--", *todo, check=True)
    git(
        repo,
        "commit",
        "-q",
        "-m",
        "Claude-forward setup: gitignore, project settings",
        check=True,
    )


def rollback(repo, start):
    """Undo a half-done apply: drop our edits, go back, delete the branch if it has no commits of its own."""
    git(
        repo, "reset", "-q", "--hard"
    )  # the repo was clean before (dirty repos are skipped)
    git(repo, "clean", "-q", "-fd", "--", ".claude")  # only files we may have created
    git(repo, "switch", "-q", start)
    if git(repo, "rev-list", "--count", f"{start}..{BRANCH}") in ("", "0"):
        git(repo, "branch", "-q", "-D", BRANCH)


if __name__ == "__main__":
    untrack = "--untrack" in sys.argv
    # flags may come anywhere
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = args[0] if args else "plan"
    if mode == "team":  # the setup-repo skill: team repos get only local, ignored files
        owner = team_owner(Path(args[1] if len(args) > 1 else ".").resolve())
        if owner:
            print(owner)
        sys.exit(0 if owner else 1)
    root = Path(args[1]).expanduser().resolve() if len(args) > 1 else Path.cwd()
    report(root, apply=mode == "apply", untrack=untrack)
