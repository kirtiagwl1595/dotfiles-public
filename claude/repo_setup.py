"""Bring a repo (or each repo under a folder) up to the Claude-forward setup. The setup-repo
skill runs it.

Per repo: a managed .gitignore block, .claude/settings.json (merged, never replaced), the
quiet-pytest block for uv projects, then one commit on branch chore/claude-forward. The setup is
judged and built from the default branch, whatever is checked out, and the checkout is never
switched. Dirty repos are skipped; nothing is pushed. Standard library only, Python 3.9+. On
Windows (no sandbox) the project settings get no Bash allow rules: every command there keeps its
approval prompt.

  repo_setup.py plan  [ROOT]     report only, changes nothing (ROOT: a repo or a folder of repos; default: here)
  repo_setup.py apply [ROOT]     make the changes
  repo_setup.py apply [ROOT] --untrack   also git rm --cached tracked personal/secret files (opt-in)
  repo_setup.py team  [REPO]     print the team owner (exit 0), or nothing for your own repo (exit 1)
  repo_setup.py protect [REPO]   lock .git hooks and config in local settings, outside ~/git; no commit

Start it through the plugin's Python launcher (Windows: `python3` can be the Store stub):
  bash "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" ../repo_setup.py plan "$PWD"
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from merge_settings import merge

HERE = (
    Path(__file__).resolve().parent
)  # claude/ in the repo, the version folder in the plugin cache
# Appended, not first: a module in hooks/ must never shadow the stdlib or merge_settings
sys.path.append(str(HERE / "hooks"))
from _private_names import ENV_IGNORE, env_name

BRANCH = "chore/claude-forward"
SUBJECT = "Claude-forward setup: gitignore, project settings"
START, END = (
    "# >>> claude-forward (dotfiles) >>>",
    "# <<< claude-forward (dotfiles) <<<",
)  # the same markers as the dotfiles setup, so a repo never gets two blocks

# Personal per-repo folders: lessons and slop-audit reports quote code and are never committed
# Lessons, audit reports and the loop runs that /loop-approve copies: personal, never committed
PERSONAL_DIRS = [".claude/lessons/", ".claude/audits/", ".claude/loop-runs/"]

IGNORE = {
    "common": [
        ".DS_Store",
        "~$*",
        *ENV_IGNORE,
        "CLAUDE.local.md",
        ".claude/settings.local.json",
        *PERSONAL_DIRS,
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


def git_out(repo, *args):
    """Output as it is. An error raises: an empty answer would read as "nothing to do"."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def file_names(repo, *args):
    """NUL-separated names. A name that is not UTF-8 gets escapes, not a crash."""
    listed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True
    ).stdout.decode(errors="backslashreplace")
    return [name for name in listed.split("\0") if name]


def ok(repo, *args):
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, check=False
        ).returncode
        == 0
    )


class Tip:
    """The committed files at one ref. The setup is judged on these, not on the checkout."""

    def __init__(self, repo, ref):
        self.repo, self.ref = repo, ref
        self.name = ref.split("/", 2)[-1]  # refs/remotes/origin/main -> origin/main
        self.files = file_names(
            repo, "ls-tree", "-r", "-z", "--full-tree", "--name-only", ref
        )

    def read(self, path):
        if path not in self.files:
            return None
        return git_out(self.repo, "show", f"{self.ref}:{path}")

    def ignores(self, path):
        """check-ignore reads only a work tree, so give it one with this ref's ignore files."""
        if path in self.files:
            return False
        common = git_out(self.repo, "rev-parse", "--git-common-dir").strip()
        with tempfile.TemporaryDirectory(prefix="claude-forward-") as tmp:
            for rel in (".gitignore", str(Path(path).parent / ".gitignore")):
                text = self.read(rel)
                if text is not None:
                    (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp) / rel).write_bytes(text.encode("utf-8"))
            return ok(
                tmp,
                f"--git-dir={(self.repo / common).resolve()}",
                f"--work-tree={tmp}",
                *("check-ignore", "-q", "--no-index", path),
            )


def default_tip(repo):
    """The branch that a PR targets (as in forge.sh), else the local main or master.

    None when there is no such branch: nothing to judge a setup on.
    """
    head = git(repo, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    names = ("remotes/origin/main", "remotes/origin/master", "heads/main")
    for ref in [head, *(f"refs/{n}" for n in names), "refs/heads/master"]:
        if ref and ok(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}"):
            return Tip(repo, ref)
    return None


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


def languages(files):
    langs = []
    if "pyproject.toml" in files or any(f.endswith((".py", ".ipynb")) for f in files):
        langs.append("python")
    if any(f.endswith((".R", ".r", ".Rmd", ".Rproj")) for f in files):
        langs.append("r")
    if "package.json" in files:
        langs.append("node")
    return langs


def gitignore_text(old, langs):
    """The .gitignore text with our block replaced where it is, else added at the end.

    None if the block is current. The lines around it are the user's: they stay as they are,
    in their order, so a line after the block is neither moved nor a reason to call it old.
    """
    block = [START, "# Managed by the setup-repo skill; edit outside this block."]
    for key in ["common", *langs]:
        block += IGNORE[key]
    block.append(END)
    lines = old.splitlines()
    if START in lines and END in lines[lines.index(START) :]:
        first = lines.index(START)
        after = lines.index(END, first) + 1
        if lines[first:after] == block:
            return None
        lines[first:after] = block
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += [*([""] if lines else []), *block]
    return "\n".join(lines) + "\n"


def settings_text(tip, langs):
    path = ".claude/settings.json"
    if tip.ignores(path):
        return None  # the team ignores .claude/ on purpose: leave it alone
    old = tip.read(path)
    try:
        user = {} if old is None else json.loads(old)
    except ValueError:
        sys.exit(f"{tip.repo / path} on {tip.name}: not valid JSON")
    base = {
        "permissions": {"allow": [a for lang in langs for a in ALLOW.get(lang, [])]}
    }
    merged = merge(user, base)
    if old is not None and merged == user:
        return None
    return json.dumps(merged, indent=2) + "\n"


def pytest_block(old, langs):
    if "python" not in langs or old is None or "[tool.pytest.ini_options]" in old:
        return None
    block = (HERE / "templates/pyproject-pytest.toml").read_text(encoding="utf-8")
    return old.rstrip("\n") + "\n" + block


def changes(tip, langs):
    """{relative path: new text} for every file that needs to change at this tip."""
    texts = {
        ".gitignore": gitignore_text(tip.read(".gitignore") or "", langs),
        ".claude/settings.json": settings_text(tip, langs),
        "pyproject.toml": pytest_block(tip.read("pyproject.toml"), langs),
    }
    return {rel: text for rel, text in texts.items() if text is not None}


class Refused(Exception):
    """A file that is not written; the message says why."""


LOCAL = ".claude/settings.local.json"


def main_checkout(repo):
    """The main checkout of `repo`: worktrees share its .git and read its local settings."""
    common = git(repo, "rev-parse", "--git-common-dir")
    if not common:
        raise Refused(f"{shown(repo)}: not a git repo")
    folder = (repo / common).resolve()
    if folder.name != ".git":
        raise Refused(f"{shown(repo)}: no plain checkout (bare repo or submodule)")
    return folder.parent


def covered(main):
    """True where settings.base.json already locks .git: below ~/git."""
    return (Path.home() / "git").resolve() in main.parents


def protection(repo):
    """(file, new text) that locks the repo's .git hooks and config, or None if nothing to write.

    Not in changes(): those are committed, and team or dirty repos skip them. These rules hold
    absolute paths, so they go to the ignored local settings of the main checkout (probe P10).
    """
    main = main_checkout(repo)
    if covered(main):
        return None
    if set("*?[]{}()!\\") & set(str(main)):
        raise Refused(
            f"{shown(main)}: this path cannot be written as a permission rule"
        )
    path = main / LOCAL
    # This runs outside the sandbox: a planted link would choose what it overwrites
    if path.is_symlink() or path.parent.is_symlink():
        raise Refused(f"{shown(path)}: is or is below a symlink, not written")
    if not ok(main, "check-ignore", "-q", LOCAL):
        raise Refused(
            f"{shown(path)}: git does not ignore it, not written (install.sh --only git links the global ignore)"
        )
    try:
        user = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        raise Refused(f"{shown(path)}: not valid JSON") from None
    wanted = [f"Edit(/{main}/.git/{name})" for name in ("config", "hooks/**")]
    merged = merge(user, {"permissions": {"deny": wanted}})
    try:
        locked = set(wanted) <= set(merged["permissions"]["deny"])
    except (TypeError, KeyError):
        locked = False
    if not locked:  # merge lets the user's value win, so another shape stays as it is
        raise Refused(f"{shown(path)}: permissions.deny is not a list")
    return None if merged == user else (path, json.dumps(merged, indent=2) + "\n")


def write_protection(todo):
    path, text = todo
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def protect(repo):
    """The `protect` command. Returns the exit code."""
    try:
        main, todo = main_checkout(repo), protection(repo)
        if todo:
            write_protection(todo)
    except (Refused, OSError) as e:
        print(f"repo_setup.py protect: {e}", file=sys.stderr)
        return 2
    if covered(main):
        print(
            f"  ✓ {main.name}: below ~/git, so its .git hooks and config are covered"
            " by the deny rules that install.py writes to the user settings"
        )
    else:
        print(
            f"  ✓ {main.name}: .git hooks and config locked in {LOCAL} (not committed)"
        )
    return 0


def tracked_personal(files):
    return [
        f
        for f in files
        if env_name(Path(f).name)
        or Path(f).name == "CLAUDE.local.md"
        or f.endswith(".claude/settings.local.json")
        or any(f"/{d}" in f"/{f}" for d in PERSONAL_DIRS)
    ]


# One line for each end state of a repo; "nothing" prints only its warnings
MESSAGES = {
    "team": "  ✓ {name}: team repo, skipped (only your own repos are changed; SAFE_LEAN_REPOS_ALL=1 for all)",
    "done": "  ✓ {name} is Claude-forward{note}",
    "pending": "  ✓ {name}: ready on {branch}, waiting for you to {next}{note}",
    "stale": "  ! {name}: {branch} is stale ({why}), do not merge it as setup. {remedy}",
    "dirty": "  ! {name}: has uncommitted changes, skipped (commit or stash, then run again)",
    "no_base": "  ! {name}: no default branch with files (origin/HEAD, main or master), skipped until work is merged there",
    "nothing": "",
    "todo": "  → {name} [{langs}]: {what} on branch {branch}{note}",
    "detached": "  ! {name}: detached HEAD, skipped (switch to a branch, then run again)",
    "failed": "  ! {name}: failed, nothing changed ({err})",
    "committed": "  → {name}: committed on {branch} ({what}); not pushed{note}",
}


def setup_branch(repo, base):
    """Our branch, local or else on origin, when it has commits that the default branch lacks."""
    for ref in (f"refs/heads/{BRANCH}", f"refs/remotes/origin/{BRANCH}"):
        if ok(repo, "rev-parse", "-q", "--verify", ref) and (
            not base or git_out(repo, "rev-list", "-n1", f"{base.ref}..{ref}")
        ):
            return Tip(repo, ref)
    return None


def staleness(base, branch, langs):
    """Why a merge of our branch would not bring today's setup alone, or ''.

    Our setup commit is the first one that the branch adds. Commits after it are fine:
    /setup-repo puts CLAUDE.md and docs there.
    """
    span = f"{base.ref}..{branch.ref}"
    added = git_out(
        base.repo, "log", "--reverse", "--first-parent", "--format=%s", span
    )
    if added.splitlines()[:1] != [SUBJECT]:
        return f"built on work that is not on {base.name}"
    return "older setup" if changes(branch, langs) else ""


def shown(path):
    """A path as the user sees it: forward slashes on every OS. git and both Windows shells
    take them, so one printed hint works everywhere."""
    return path.as_posix() if hasattr(path, "as_posix") else str(path)


def secret_warnings(name, personal, root, can_untrack):
    """The lines that name tracked personal files, and how to untrack them."""
    if not personal:
        return []
    tracked = (
        f"  ! {name}: personal/secret files are tracked: {', '.join(personal)}."
        " They stay in git history: rotate any key in them."
    )
    if not can_untrack:
        return [tracked]
    hint = (
        "      To untrack (copy the files first: merging that commit deletes them from disk):"
        f" repo_setup.py apply {shown(root)} --untrack"
    )
    return [tracked, hint]


def next_step(repo, base):
    """What you can do with a ready branch."""
    if ok(repo, "remote", "get-url", "origin"):
        return "push + merge it (PR/MR)"
    return f"merge it into {base.name} (no remote)" if base else ""


def stale_remedy(repo, base, branch):
    """The safe next step for a stale branch. It never says to delete or close anything.

    A rename is safe only for a local branch that holds setup commits and nothing else:
    other work can live only there, and a pushed branch can have a PR, or be the base of one.
    """
    at = f"git -C {shlex.quote(shown(repo))}"
    span = f"{base.ref}..{branch.ref}"
    setup_only = set(git_out(repo, "log", "--format=%s", span).splitlines()) == {
        SUBJECT
    }
    pushed = ok(repo, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{BRANCH}")
    if setup_only and not pushed:
        return f"Rename it, then run again: {at} branch -m {BRANCH} {BRANCH}-old"
    return (
        "Keep it: other work or an open PR/MR can depend on it. Review it first:"
        f" {at} log --oneline {base.name}..{branch.name}"
    )


def repo_name(repo, root):
    return shown(repo.relative_to(root)) if repo != root else repo.name


def status(repo, root, untrack):
    """(end state, warnings, facts) for one repo. It changes nothing.

    The setup is judged on the default branch and on our branch, never on what is checked out.
    The warnings cover all three and come first, so that no end state can hide them.
    """
    name = repo_name(repo, root)
    team = repo != root and team_owner(repo)
    base = default_tip(repo)
    branch = setup_branch(repo, base)
    seen = set(file_names(repo, "ls-files", "-z"))
    for tip in filter(None, (base, branch)):
        seen.update(tip.files)
    langs, todo, why, untrackable, done = [], {}, "", [], False
    if base and not team:
        langs = languages(base.files)
        todo = changes(base, langs)
        done = not todo and not tracked_personal(base.files)
        if not done:
            why = staleness(base, branch, langs) if branch else ""
            # Only where an --untrack run would commit, so that the hint is never a dead end.
            # Not on a branch that is only fetched: the commit hooks would run its scripts.
            fetched_only = branch and not branch.ref.startswith("refs/heads/")
            if not why and not fetched_only:
                untrackable = tracked_personal((branch or base).files)
    warnings = secret_warnings(
        name, tracked_personal(sorted(seen)), root, untrackable and not untrack
    )
    shown = base if done else branch or base  # a CLAUDE.md can wait on our branch
    facts = {
        "name": name,
        "branch": BRANCH,
        "note": ""
        if shown and "CLAUDE.md" in shown.files
        else "  (no CLAUDE.md: run `claude` there, then /setup-repo)",
        # Every key that a MESSAGES line can name, so a new placeholder cannot raise KeyError
        "langs": "",
        "what": "",
        "err": "",
        "why": why,
        "next": next_step(repo, base),
        "remedy": stale_remedy(repo, base, branch) if base and branch and why else "",
        "start": "",
        "todo": {},
        "personal": [],
    }
    if team:
        return "team", warnings, facts
    if done:
        return "done", warnings, facts
    if why:
        return "stale", warnings, facts
    if not base or not base.files:
        return "no_base", warnings, facts
    personal = untrackable if untrack else []
    if branch:
        if not personal:
            return "pending", warnings, facts
        todo = {}  # the branch has the files: only the untrack is one more commit
    if git(repo, "status", "--porcelain"):
        return "dirty", warnings, facts
    facts |= {
        "langs": ", ".join(langs) or "no code",
        "start": (branch or base).ref,
        "todo": todo,
        "personal": personal,
        "what": ", ".join(
            [*todo, *(["untrack " + ", ".join(personal)] if personal else [])]
        ),
    }
    return ("todo" if todo or personal else "nothing"), warnings, facts


def error_line(e):
    """The last line that git printed, else the error itself."""
    lines = (getattr(e, "stderr", "") or "").strip().splitlines()
    return lines[-1] if lines else str(e)


def apply_repo(repo, facts):
    """Commit the changes on our branch. Returns the end state."""
    if not git(repo, "symbolic-ref", "--short", "HEAD"):
        return "detached"
    try:
        apply_one(repo, facts["start"], facts["todo"], facts["personal"])
    except (subprocess.CalledProcessError, Refused, OSError) as e:
        facts["err"] = error_line(e)
        return "failed"
    return "committed"


def apply_one(repo, start, todo, personal):
    """One commit on top of `start`, made in a throwaway worktree; our branch moves only then.

    A switch in the user's checkout would overwrite ignored files. commit-tree would need no
    worktree, but it skips the repo's commit hooks and signing.
    """
    with tempfile.TemporaryDirectory(prefix="claude-forward-") as tmp:
        tree = Path(tmp).resolve() / "tree"
        git(repo, "worktree", "add", "-q", "--detach", str(tree), start, check=True)
        try:
            for rel, text in todo.items():
                path = tree / rel
                # This runs outside the sandbox: a committed link would choose what it overwrites
                if path.resolve() != path:
                    raise Refused(f"{rel} is or is below a symlink, not written")
                path.parent.mkdir(parents=True, exist_ok=True)
                # open(), not write_text(newline=): that needs Python 3.10
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            if personal:
                git(tree, "rm", "-q", "--cached", "--", *personal, check=True)
            if todo:
                git(tree, "add", "--", *todo, check=True)
            git(tree, "commit", "-q", "-m", SUBJECT, check=True)
            new = git(tree, "rev-parse", "HEAD", check=True)
            git(repo, "branch", "-q", "-f", BRANCH, new, check=True)
        finally:
            git(repo, "worktree", "remove", "--force", str(tree))


def protection_line(repo, name, apply):
    """The bulk run's line for protection(), also for a team or dirty repo; '' if nothing to do."""
    try:
        todo = protection(repo)
        if todo and apply:
            write_protection(todo)
    except (Refused, OSError) as e:
        return f"  ! {name}: .git hooks and config not locked ({e})"
    if not todo:
        return ""
    if apply:
        return f"  → {name}: locked .git hooks and config in {LOCAL} (not committed)"
    return f"  → {name}: lock .git hooks and config in {LOCAL} (not committed)"


def report(root, apply=False, untrack=False):
    repos = find_repos(root)
    print(f"  ✓ scanning {shown(root).replace(shown(Path.home()), '~', 1)}")
    if not repos:
        print(f"  ✓ no repos under {shown(root)}")
    for repo in repos:
        name = repo_name(repo, root)
        try:
            state, warnings, facts = status(repo, root, untrack)
        except subprocess.CalledProcessError as e:  # one broken repo, not the whole run
            state, warnings = "failed", []
            facts = {"name": name, "err": error_line(e)}
        if line := protection_line(repo, name, apply):
            print(line)
        if state == "todo" and apply:
            state = apply_repo(repo, facts)
        for line in [*warnings, MESSAGES[state].format(**facts)]:
            if line:
                print(line)


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
    if mode == "protect":  # the setup-repo skill, for every repo, team repos too
        sys.exit(protect(Path(args[1] if len(args) > 1 else ".").resolve()))
    root = Path(args[1]).expanduser().resolve() if len(args) > 1 else Path.cwd()
    report(root, apply=mode == "apply", untrack=untrack)
