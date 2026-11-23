"""claude/repo_setup.py: every end state of a repo, in the one line that it prints. The setup is
judged on the default branch, never on the checkout; a branch that is not today's setup is never
rewritten; a tracked personal file is never hidden."""

import subprocess
import sys

import pytest
from hookrun import ROOT, env_for

sys.path.insert(0, str(ROOT / "claude"))
import repo_setup

SCRIPT = ROOT / "claude" / "repo_setup.py"
SYMLINKS = pytest.mark.skipif(
    sys.platform == "win32", reason="a symlink needs a privilege on Windows"
)


def make_repo(path, files):
    path.mkdir(parents=True)
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text, encoding="utf-8")
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-q", "-m", "init"],
    ):
        subprocess.run(["git", "-C", str(path), *cmd], check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """Repos below ~/git of a throwaway home: the folder where settings.base.json locks .git."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("FORGE_GIT_USER", "me")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "t")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@t")
    root = home / "git"
    make_repo(
        root / "py-proj",
        {"pyproject.toml": '[project]\nname = "p"\n', "src/app.py": "x = 1\n"},
    )
    make_repo(root / "r-proj", {"analysis.Rmd": "# hi\n", ".gitignore": ".Rhistory\n"})
    make_repo(root / "group/web", {"package.json": "{}\n", "CLAUDE.md": "# web\n"})
    make_repo(root / "dirty", {"a.py": "x = 1\n"})
    (root / "dirty/a.py").write_text("x = 2\n", encoding="utf-8")
    return root


def committed(repo, path):
    p = subprocess.run(
        ["git", "-C", str(repo), "show", f"chore/claude-forward:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return p.stdout if p.returncode == 0 else None


def repo_setup_lines(repos, *args):
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=env_for(PYTHONUTF8="1"),
    )
    # The script prints paths with forward slashes on every OS
    return p.stdout.replace(repos.as_posix(), "ROOT").splitlines()


NOTE = "  (no CLAUDE.md: run `claude` there, then /setup-repo)"
SCAN = "  ✓ scanning ~/git"
DIRTY = "  ! dirty: has uncommitted changes, skipped (commit or stash, then run again)"
TEAM = "  ✓ team: team repo, skipped (only your own repos are changed; SAFE_LEAN_REPOS_ALL=1 for all)"
SECRET = "  ! {}: personal/secret files are tracked: {}. They stay in git history: rotate any key in them."
HINT = "      To untrack (copy the files first: merging that commit deletes them from disk): repo_setup.py apply ROOT --untrack"
DETACHED = "  ! loose: detached HEAD, skipped (switch to a branch, then run again)"
READY = "  ✓ {}: ready on chore/claude-forward, waiting for you to merge it into main (no remote)"
READY_TO_PUSH = (
    "  ✓ {}: ready on chore/claude-forward, waiting for you to push + merge it (PR/MR)"
)
NO_BASE = "  ! {}: no default branch with files (origin/HEAD, main or master), skipped until work is merged there"
TODO = "  → {} [{}]: {} on branch chore/claude-forward"
DONE = "  → {}: committed on chore/claude-forward ({}); not pushed"
FILES = ".gitignore, .claude/settings.json"


def test_repo_setup_prints_one_line_per_repo_state(repos, monkeypatch):
    """Every output line of plan and apply, one repo for each state."""
    monkeypatch.setenv("FORGE_GIT_USER", "me")

    def git(name, *args):
        subprocess.run(["git", "-C", str(repos / name), *args], check=True)

    def merged_setup(name):
        repo_setup_lines(repos, "apply", str(repos / name))
        git(name, "merge", "-q", "--ff-only", "chore/claude-forward")

    make_repo(repos / "leaky", {"app.py": "x = 1\n", ".env": "K=1\n"})
    make_repo(repos / "team", {"app.py": "x = 1\n"})
    git("team", "remote", "add", "origin", "git@github.com:acme/t.git")
    make_repo(repos / "loose", {"app.py": "x = 1\n"})
    git("loose", "switch", "-q", "--detach")
    make_repo(repos / "done", {"app.py": "x = 1\n", "CLAUDE.md": "# d\n"})
    merged_setup("done")
    make_repo(
        repos / "warned",
        {"app.py": "x = 1\n", "CLAUDE.md": "# w\n", "CLAUDE.local.md": "# me\n"},
    )
    merged_setup("warned")
    py_files = f"{FILES}, pyproject.toml"
    assert repo_setup_lines(repos, "plan", str(repos)) == [
        SCAN,
        DIRTY,
        "  ✓ done is Claude-forward",
        SECRET.format("leaky", ".env"),
        HINT,
        TODO.format("leaky", "python", FILES) + NOTE,
        TODO.format("loose", "python", FILES) + NOTE,
        TODO.format("py-proj", "python", py_files) + NOTE,
        TODO.format("r-proj", "r", FILES) + NOTE,
        TEAM,
        SECRET.format("warned", "CLAUDE.local.md"),
        HINT,
        TODO.format("group/web", "node", FILES),
    ]
    assert repo_setup_lines(repos, "apply", str(repos)) == [
        SCAN,
        DIRTY,
        "  ✓ done is Claude-forward",
        SECRET.format("leaky", ".env"),
        HINT,
        DONE.format("leaky", FILES) + NOTE,
        DETACHED,
        DONE.format("py-proj", py_files) + NOTE,
        DONE.format("r-proj", FILES) + NOTE,
        TEAM,
        SECRET.format("warned", "CLAUDE.local.md"),
        HINT,
        DONE.format("group/web", FILES),
    ]
    ready = [READY.format(n) + NOTE for n in ("py-proj", "r-proj")]
    assert repo_setup_lines(repos, "plan", str(repos)) == [
        SCAN,
        DIRTY,
        "  ✓ done is Claude-forward",
        SECRET.format("leaky", ".env"),
        HINT,
        READY.format("leaky") + NOTE,
        TODO.format("loose", "python", FILES) + NOTE,
        *ready,
        TEAM,
        SECRET.format("warned", "CLAUDE.local.md"),
        HINT,
        READY.format("group/web"),
    ]
    assert repo_setup_lines(repos, "apply", str(repos), "--untrack") == [
        SCAN,
        DIRTY,
        "  ✓ done is Claude-forward",
        SECRET.format("leaky", ".env"),
        DONE.format("leaky", "untrack .env") + NOTE,  # the files are on the branch
        DETACHED,
        *ready,
        TEAM,
        SECRET.format("warned", "CLAUDE.local.md"),
        DONE.format("warned", "untrack CLAUDE.local.md"),
        READY.format("group/web"),
    ]


def run_git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit_file(repo, name, text):
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")
    run_git(repo, "add", "--", name)
    run_git(repo, "commit", "-qm", f"change {name}")


def test_setup_is_built_from_the_default_branch(repos):
    """A checkout on a feature branch adds nothing to the setup branch, and is not touched."""
    repo = repos / "pilot"
    make_repo(repo, {"app.py": "x = 1\n"})
    run_git(repo, "switch", "-qc", "feature/pilot")
    commit_file(repo, "pilot.py", "y = 1\n")
    tip = run_git(repo, "rev-parse", "HEAD")
    repo_setup_lines(repos, "apply", str(repo))
    assert run_git(repo, "rev-parse", "chore/claude-forward^") == run_git(
        repo, "rev-parse", "main"
    )
    assert run_git(repo, "branch", "--show-current") == "feature/pilot"
    assert run_git(repo, "rev-parse", "HEAD") == tip


STALE = "  ! case: chore/claude-forward is stale ({}), do not merge it as setup. {}"
RENAME = (
    "Rename it, then run again:"
    " git -C ROOT/case branch -m chore/claude-forward chore/claude-forward-old"
)
KEEP = (
    "Keep it: other work or an open PR/MR can depend on it. Review it first:"
    " git -C ROOT/case log --oneline main..{}"
)
OLD_SETUP = STALE.format("older setup", RENAME)
OLD_SETUP_KEEP = STALE.format("older setup", KEEP.format("chore/claude-forward"))
OTHER_WORK = "built on work that is not on main"
WRONG_BASE = STALE.format(OTHER_WORK, KEEP.format("chore/claude-forward"))


def ready_branch(repos, repo):
    repo_setup_lines(repos, "apply", str(repo))


def old_block(repos, repo):
    ready_branch(repos, repo)
    run_git(repo, "switch", "-q", "chore/claude-forward")
    lines = (
        (repo / ".gitignore")
        .read_text(encoding="utf-8")
        .replace(".claude/audits/\n", "")
    )
    (repo / ".gitignore").write_text(lines, encoding="utf-8")
    run_git(repo, "commit", "-qa", "--amend", "--no-edit")
    run_git(repo, "switch", "-q", "main")


def old_block_squash_merged(repos, repo):
    old_block(repos, repo)
    run_git(repo, "merge", "-q", "--squash", "chore/claude-forward")
    run_git(repo, "commit", "-qm", "squash")


def old_block_pushed(repos, repo):
    """A PR can be open on it, and another PR can use it as its base."""
    old_block(repos, repo)
    run_git(
        repo,
        "update-ref",
        "refs/remotes/origin/chore/claude-forward",
        "chore/claude-forward",
    )


def old_block_with_more_work(repos, repo):
    old_block(repos, repo)
    run_git(repo, "switch", "-q", "chore/claude-forward")
    commit_file(repo, "feature.py", "y = 1\n")
    run_git(repo, "switch", "-q", "main")


def squash_merged(repos, repo):
    ready_branch(repos, repo)
    run_git(repo, "merge", "-q", "--squash", "chore/claude-forward")
    run_git(repo, "commit", "-qm", "squash")


def wrong_base(repos, repo):
    """The shape that the checked-out-branch bug left: the setup on top of feature work."""
    ready_branch(repos, repo)
    setup = run_git(repo, "rev-parse", "chore/claude-forward")
    run_git(repo, "switch", "-qc", "feature/pilot")
    commit_file(repo, "pilot.py", "y = 1\n")
    run_git(repo, "switch", "-qC", "chore/claude-forward")
    run_git(repo, "cherry-pick", setup)
    run_git(repo, "switch", "-q", "feature/pilot")


def wrong_base_only_on_origin(repos, repo):
    wrong_base(repos, repo)
    tip = run_git(repo, "rev-parse", "chore/claude-forward")
    run_git(repo, "update-ref", "refs/remotes/origin/chore/claude-forward", tip)
    run_git(repo, "branch", "-qD", "chore/claude-forward")


def main_moved_on(repos, repo):
    ready_branch(repos, repo)
    commit_file(repo, "more.py", "z = 1\n")


def more_work_on_the_branch(repos, repo):
    ready_branch(repos, repo)
    run_git(repo, "switch", "-q", "chore/claude-forward")
    commit_file(repo, "CLAUDE.md", "# case\n")  # what /setup-repo adds
    run_git(repo, "switch", "-q", "main")


def line_after_the_block(repos, repo):
    ready_branch(repos, repo)
    run_git(repo, "switch", "-q", "chore/claude-forward")
    with (repo / ".gitignore").open("a", encoding="utf-8") as f:
        f.write("graphify-out/\n")  # as SETUP.md says: echo ... >> .gitignore
    run_git(repo, "commit", "-qam", "ignore the graph")
    run_git(repo, "switch", "-q", "main")


def done_on_main_seen_from_a_feature_branch(repos, repo):
    run_git(repo, "branch", "feature/old")  # forked before the setup was merged
    squash_merged(repos, repo)
    run_git(repo, "switch", "-q", "feature/old")


@pytest.mark.parametrize(
    "build, want",
    [
        (ready_branch, [READY.format("case") + NOTE]),
        (main_moved_on, [READY.format("case") + NOTE]),
        (more_work_on_the_branch, [READY.format("case")]),  # CLAUDE.md waits there
        (line_after_the_block, [READY.format("case") + NOTE]),
        (squash_merged, ["  ✓ case is Claude-forward" + NOTE]),
        (
            done_on_main_seen_from_a_feature_branch,
            ["  ✓ case is Claude-forward" + NOTE],
        ),
        (old_block, [OLD_SETUP]),
        (old_block_squash_merged, [OLD_SETUP]),
        (wrong_base, [WRONG_BASE]),
        (
            wrong_base_only_on_origin,
            [STALE.format(OTHER_WORK, KEEP.format("origin/chore/claude-forward"))],
        ),
        (old_block_pushed, [OLD_SETUP_KEEP]),
        (old_block_with_more_work, [OLD_SETUP_KEEP]),
    ],
)
def test_setup_branch_is_ready_only_from_main_with_todays_setup(repos, build, want):
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n"})
    build(repos, repo)
    refs = run_git(repo, "for-each-ref")
    for mode in ("plan", "apply"):  # apply never rewrites a branch that has commits
        lines = repo_setup_lines(repos, mode, str(repos))
        assert [line for line in lines if " case" in line] == want
    assert run_git(repo, "for-each-ref") == refs


def with_origin(repos, repo):
    run_git(repo, "remote", "add", "origin", "https://github.com/me/case.git")
    ready_branch(repos, repo)


def empty_main(repos, repo):
    """main is one empty commit and all work is on a feature branch."""
    run_git(repo, "switch", "-q", "-c", "feature/pilot")
    empty = run_git(repo, "commit-tree", "-m", "empty", run_git(repo, "mktree"))
    run_git(repo, "branch", "-qf", "main", empty)


def empty_main_with_setup_on_the_feature(repos, repo):
    empty_main(repos, repo)
    run_git(repo, "switch", "-qc", "chore/claude-forward")
    commit_file(repo, ".gitignore", "old\n")
    run_git(repo, "switch", "-q", "feature/pilot")


def no_main_or_master(repos, repo):
    run_git(repo, "branch", "-qm", "main", "develop")


def master_only(repos, repo):
    run_git(repo, "branch", "-qm", "main", "master")


def default_on_origin(repos, repo):
    run_git(repo, "remote", "add", "origin", "https://github.com/me/case.git")
    run_git(repo, "update-ref", "refs/remotes/origin/develop", "main")
    run_git(
        repo,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        "refs/remotes/origin/develop",
    )
    run_git(repo, "branch", "-qm", "main", "topic")


@pytest.mark.parametrize(
    "build, want",
    [
        (ready_branch, [READY.format("case") + NOTE]),
        (with_origin, [READY_TO_PUSH.format("case") + NOTE]),
        (empty_main, [NO_BASE.format("case")]),
        (empty_main_with_setup_on_the_feature, [WRONG_BASE]),
        (no_main_or_master, [NO_BASE.format("case")]),
        (master_only, [TODO.format("case", "python", FILES) + NOTE]),
        (default_on_origin, [TODO.format("case", "python", FILES) + NOTE]),
    ],
)
def test_each_repo_gets_a_next_step_that_it_can_do(repos, monkeypatch, build, want):
    monkeypatch.setenv("FORGE_GIT_USER", "me")
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n"})
    build(repos, repo)
    lines = repo_setup_lines(repos, "plan", str(repos))
    assert [line for line in lines if " case" in line] == want


def dirty(repos, repo):
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")


def team_repo(repos, repo):
    run_git(repo, "remote", "add", "origin", "https://github.com/acme/case.git")


def personal_only_on_main(repos, repo):
    run_git(repo, "switch", "-qc", "feature/clean")
    run_git(repo, "rm", "-q", "CLAUDE.local.md")
    run_git(repo, "commit", "-qm", "untrack")


def personal_only_on_the_checkout(repos, repo):
    run_git(repo, "switch", "-qc", "feature/notes")
    run_git(repo, "branch", "-qf", "main", "main~1")


@pytest.mark.parametrize(
    "build, can_untrack",
    [
        (ready_branch, True),
        (dirty, True),
        (personal_only_on_main, True),
        (personal_only_on_the_checkout, False),  # the branch from main has no such file
        (old_block, False),
        (no_main_or_master, False),
        (team_repo, False),
    ],
)
def test_no_state_hides_a_tracked_personal_file(repos, monkeypatch, build, can_untrack):
    monkeypatch.setenv("FORGE_GIT_USER", "me")
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n"})
    commit_file(repo, "CLAUDE.local.md", "# me\n")
    build(repos, repo)
    lines = repo_setup_lines(repos, "plan", str(repos))
    at = lines.index(SECRET.format("case", "CLAUDE.local.md"))
    assert (lines[at + 1] == HINT) == can_untrack


def test_apply_keeps_an_ignored_file_that_main_tracks(repos):
    """A switch to main would overwrite it, and the switch back would delete it."""
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n", "data.csv": "main\n"})
    run_git(repo, "switch", "-qc", "feature/data")
    run_git(repo, "rm", "-q", "data.csv")
    commit_file(repo, ".gitignore", "data.csv\n")
    (repo / "data.csv").write_text("mine, not in git\n", encoding="utf-8")
    repo_setup_lines(repos, "apply", str(repo))
    assert (repo / "data.csv").read_text(encoding="utf-8") == "mine, not in git\n"
    assert "data.csv" not in committed(repo, ".gitignore")  # built from main
    assert run_git(repo, "worktree", "list").count("\n") == 0  # none left behind


def test_apply_works_while_main_is_checked_out_in_another_worktree(repos):
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n"})
    run_git(repo, "switch", "-qc", "feature/a")
    run_git(repo, "worktree", "add", "-q", str(repos.parent / "case-main"), "main")
    lines = repo_setup_lines(repos, "apply", str(repo))
    assert DONE.format("case", FILES) + NOTE in lines


@SYMLINKS
def test_apply_never_writes_through_a_committed_symlink(repos):
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n"})
    target = repos.parent / "outside.txt"
    target.write_text("keep\n", encoding="utf-8")
    (repo / ".gitignore").symlink_to(target)
    run_git(repo, "add", ".gitignore")
    run_git(repo, "commit", "-qm", "link")
    lines = repo_setup_lines(repos, "apply", str(repo))
    assert target.read_text(encoding="utf-8") == "keep\n"
    assert any("case: failed, nothing changed" in line for line in lines)


def test_a_file_name_that_is_not_utf8_does_not_stop_the_run(repos):
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n"})
    blob = run_git(repo, "rev-parse", "HEAD:app.py")
    # macOS cannot create this name on disk, but a commit from Linux can hold it
    entry = b"100644 blob " + blob.encode() + b"\tcaf\xe9.txt\n"
    tree = subprocess.run(
        ["git", "-C", str(repo), "mktree"], input=entry, capture_output=True, check=True
    ).stdout.decode()
    new = run_git(repo, "commit-tree", "-m", "latin-1 name", "-p", "main", tree.strip())
    run_git(repo, "switch", "-qc", "feature/a")
    run_git(repo, "branch", "-qf", "main", new)
    assert any(" case" in line for line in repo_setup_lines(repos, "plan", str(repos)))


TODAY = repo_setup.gitignore_text("", [])
OLD = f"{repo_setup.START}\nold-line\n{repo_setup.END}\n"


@pytest.mark.parametrize(
    "old, want",
    [
        ("mine\n", "mine\n\n" + TODAY),  # no block yet: at the end
        ("mine\n\n" + OLD, "mine\n\n" + TODAY),
        (OLD + "after\n", TODAY + "after\n"),
        ("mine\n" + OLD + "\nafter\n", "mine\n" + TODAY + "\nafter\n"),
        (TODAY + "after\n", None),
        (TODAY + "\n", None),
        (TODAY.rstrip("\n"), None),
    ],
)
def test_the_block_is_replaced_where_it_is(old, want):
    assert repo_setup.gitignore_text(old, []) == want


def test_untrack_never_runs_hooks_from_a_branch_that_is_only_on_origin(repos):
    """A fetched branch is not code that you chose to run. Hooks often run a tracked script."""
    repo = repos / "case"
    make_repo(repo, {"app.py": "x = 1\n"})
    commit_file(repo, "CLAUDE.local.md", "# me\n")
    ready_branch(repos, repo)
    run_git(repo, "switch", "-q", "chore/claude-forward")
    marker = repos.parent / "hook-ran"
    commit_file(repo, "check.sh", f"touch '{marker}'\n")
    run_git(repo, "switch", "-q", "main")
    run_git(
        repo,
        "update-ref",
        "refs/remotes/origin/chore/claude-forward",
        "chore/claude-forward",
    )
    run_git(repo, "branch", "-qD", "chore/claude-forward")
    hook = repo / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\n[ ! -f check.sh ] || sh check.sh\n", encoding="utf-8")
    hook.chmod(0o755)
    refs = run_git(repo, "for-each-ref")
    planned = repo_setup_lines(repos, "plan", str(repos))
    repo_setup_lines(repos, "apply", str(repos), "--untrack")
    assert not marker.exists()
    assert run_git(repo, "for-each-ref") == refs
    at = planned.index(SECRET.format("case", "CLAUDE.local.md"))
    assert planned[at + 1] != HINT  # no hint for a run that does nothing


ENV_SAMPLES = [
    *(".env", ".env.local", ".env.local.bak", "prod.env", "dev.env.bak"),
    *(".env.example", ".env.sample", ".env.template", "environment.py", "env.py"),
    *("prod.env.example", "docker.env.sample", "prod.env.PROD"),
]


def test_env_ignore_lines_follow_the_env_name_rule(tmp_path):
    from _private_names import ENV_IGNORE, env_name

    repo = tmp_path / "r"
    repo.mkdir()
    text = repo_setup.gitignore_text("", [])
    # All lines there, in order: git uses the last match, so negations stay last
    assert [line for line in text.splitlines() if line in ENV_IGNORE] == ENV_IGNORE
    (repo / ".gitignore").write_text(text, encoding="utf-8")
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    hits = subprocess.run(
        [*git, "check-ignore", "--no-index", *ENV_SAMPLES],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    assert {n: n in hits for n in ENV_SAMPLES} == {n: env_name(n) for n in ENV_SAMPLES}


@pytest.mark.parametrize("folder", repo_setup.PERSONAL_DIRS)
def test_personal_folders_are_ignored_and_flagged_when_tracked(repos, folder):
    repo = repos / "taught"
    make_repo(repo, {"app.py": "x = 1\n", f"{folder}2026-10-26-x.md": "# x\n"})
    out = "\n".join(repo_setup_lines(repos, "apply", str(repos)))
    assert f"taught: personal/secret files are tracked: {folder}2026-10-26-x.md" in out
    assert folder in committed(repo, ".gitignore")


@pytest.mark.parametrize("name", ["prod.env", "dev.env.bak"])
def test_named_env_files_are_flagged(repos, name):
    make_repo(repos / "named", {"app.py": "x = 1\n", name: "API_KEY=abc\n"})
    out = "\n".join(repo_setup_lines(repos, "plan", str(repos)))
    assert f"named: personal/secret files are tracked: {name}" in out
