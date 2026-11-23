"""_loop.py: names, the state file, the content hash, the path matcher, profiles and `running`."""

import json
import py_compile
import subprocess

import _loop
import pytest
from loop_fixtures import (
    CLAUDE,
    HOOKS,
    LOOP_MARKS,
    git,
    own_repos_are_personal,
    personal,
    python,
)

pytestmark = LOOP_MARKS

NEW_CODE = [
    HOOKS / "_loop.py",
    HOOKS / "loop_hook.py",
    HOOKS / "guard_loop.py",
    CLAUDE / "loopctl.py",
    CLAUDE / "loop_gate.py",
]


@pytest.mark.parametrize("path", NEW_CODE, ids=lambda p: p.name)
def test_new_hook_code_compiles_on_the_system_python(path, tmp_path):
    # The hooks run on /usr/bin/python3 (3.9): newer syntax must fail here, not in a session
    out = subprocess.run(
        [python(), "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPYCACHEPREFIX": str(tmp_path)},
    )
    assert out.returncode == 0, out.stderr
    py_compile.compile(str(path), cfile=str(tmp_path / "x.pyc"), doraise=True)


@pytest.mark.parametrize(
    "kind, target, want",
    [
        ("skill", "step-back", "step-back"),
        ("script", "scripts/install-jena.sh", "install-jena"),
        ("task", "Add a dry run flag to the backup script", "add-a-dry-run"),
        ("task", "Fix: the  CSV parser!", "fix-the-csv-parser"),
        ("script", "x" * 40 + ".py", "x" * 30),
    ],
)
def test_slug(kind, target, want):
    assert _loop.slug(kind, target) == want


@pytest.mark.parametrize(
    "rel, hit",
    [
        ("claude/tests/test_x.py", True),
        ("claude/evals/x/graders/a.md", True),
        ("claude/plugins/writing-skills/evals/x/graders/a.md", True),
        ("sub/conftest.py", True),
        ("src/contest.py", False),
        ("pkg/tool_test.go", True),
        ("web/app.test.ts", True),
        ("ruff.toml", True),
        ("sub/pyproject.toml", True),
        (".github/workflows/ci.yml", True),
        (".loop/LOOP.md", True),
        (".loop/run.json", True),
        (".loop/bin/loopctl.py", True),
        (".loop/loop-progress.md", False),
        (".loop/bundle.md", False),
        ("tool.sh", False),
        ("docs/testing.md", False),
    ],
)
def test_protected_paths(rel, hit):
    assert _loop.is_protected(rel) is hit


def test_scope_lists_and_approvals():
    assert _loop.is_protected("keep.txt", extra=["keep.txt"])
    assert not _loop.is_protected("tests/a.py", approved=["tests/a.py"])


@pytest.mark.parametrize(
    "pattern, rel, hit",
    [
        # Gitignore: a trailing / is the folder and everything in it (pilot scope lines)
        ("tests/", "tests/test_cli.py", True),
        ("claude/skills/", "claude/skills/rdf-check/SKILL.md", True),
        (".github/", ".github/workflows/test.yml", True),
        ("evals/", "evals/case/prompt.md", True),
        ("tests/", "src/tests.py", False),
        ("Brewfile*", "Brewfile.personal", True),
        ("docs/decisions.md", "docs/decisions.md", True),
    ],
)
def test_scope_patterns_follow_gitignore(pattern, rel, hit):
    assert _loop.matches(pattern, rel) is hit


SPEC = "---\nslug: a\ntarget_type: script\n---\n## Scope\nmay change: a.sh; must not change: {}\n"
CHECKS = [{"id": "x", "verify": "true"}]


@pytest.mark.parametrize(
    "scope, named",
    [
        # The 3 pilots wrote these; each note made the entry match no file
        (
            "claude/tests/, claude/skills/, Brewfile*, install.sh, every other file",
            ["every other file"],
        ),
        (
            "other skills, claude/evals/, claude/.claude-plugin/plugin.json (bump the plugin version)",
            ["other skills", "plugin.json (bump"],
        ),
        (
            "tests/, src/profile_review.py (prompt and schema; a change needs the evals), uv.lock",
            ["src/profile_review.py (prompt"],
        ),
    ],
)
def test_spec_refuses_a_scope_entry_that_is_not_a_path(scope, named, tmp_path):
    problem = _loop.spec_problem(SPEC.format(scope), CHECKS, tmp_path)
    assert problem and "not enforced" in problem
    assert all(n in problem for n in named)


def test_spec_takes_path_patterns(tmp_path):
    text = SPEC.format("tests/, evals/, src/profile_review.py, *.lock, .github/")
    assert _loop.spec_problem(text, CHECKS, tmp_path) is None
    assert _loop.must_not_change(text) == [
        "tests/",
        "evals/",
        "src/profile_review.py",
        "*.lock",
        ".github/",
    ]


def test_a_repo_with_the_engine_protects_its_loop_code():
    rels = ["claude/hooks/x.py", "claude/loopctl.py", "claude/agents/a.md"]
    assert all(_loop.is_protected(r, self_protect=True) for r in rels)
    assert not _loop.is_protected("claude/hooks/x.py")


def test_state_path_is_fixed_and_keyed_by_real_path(loop_env):
    p = _loop.state_path(loop_env.wt)
    assert p.parent == loop_env.home / ".local/state/claude-safe-lean/loops"
    assert len(p.stem) == 16
    link = loop_env.tmp / "link"
    link.symlink_to(loop_env.wt)
    assert _loop.state_path(link) == p


def test_state_round_trip_is_atomic(loop_env):
    assert _loop.load_state(loop_env.wt) is None
    _loop.save_state({"worktree": str(loop_env.wt), "status": "running"})
    assert _loop.load_state(loop_env.wt)["status"] == "running"
    assert not list(_loop.state_path(loop_env.wt).parent.glob("*.tmp"))


def test_atomic_write_never_writes_through_a_symlink(loop_env):
    # The agent can plant links in .loop/; the hook that writes there runs unsandboxed
    outside = loop_env.tmp / "outside.txt"
    outside.write_text("user file\n")
    loop = loop_env.wt / ".loop"
    loop.mkdir()
    (loop / "LOOP.md.tmp").symlink_to(outside)
    (loop / "run.json").symlink_to(outside)
    for name in ("LOOP.md", "run.json"):
        _loop.atomic_write(loop / name, "hook text\n", root=loop_env.wt)
        assert not (loop / name).is_symlink()
        assert (loop / name).read_text() == "hook text\n"
    assert outside.read_text() == "user file\n"


def test_atomic_write_refuses_a_symlinked_folder_below_the_root(loop_env):
    outside = loop_env.tmp / "outside"
    outside.mkdir()
    (loop_env.wt / ".loop").symlink_to(outside)
    with pytest.raises(_loop.Unsafe, match="symlink"):
        _loop.atomic_write(loop_env.wt / ".loop/LOOP.md", "x", root=loop_env.wt)
    assert list(outside.iterdir()) == []


def test_worktree_root_walks_up(loop_env):
    sub = loop_env.wt / "tests"
    assert _loop.worktree_root(sub) == loop_env.wt.resolve()
    assert _loop.worktree_root(loop_env.tmp) is None
    assert _loop.worktree_root(loop_env.tmp / "missing") is None


def test_content_hash_skips_loop_folder_and_tool_output(loop_env):
    wt = loop_env.wt
    before = _loop.content_hash(wt)
    (wt / ".loop").mkdir()
    (wt / ".loop/loop-progress.md").write_text("x")
    (wt / "tests/__pycache__").mkdir()
    (wt / "tests/__pycache__/x.pyc").write_bytes(b"x")
    (wt / ".pytest_cache").mkdir()
    (wt / ".pytest_cache/v").write_text("x")
    assert _loop.content_hash(wt) == before
    (wt / "new.py").write_text("x = 1\n")
    assert _loop.content_hash(wt) != before


def test_changed_paths_against_base(loop_env):
    wt = loop_env.wt
    base = git(wt, "rev-parse", "HEAD")
    (wt / "tool.sh").write_text("echo ok\n")
    (wt / "tests/test_new.py").write_text("x")
    (wt / "keep.txt").unlink()
    (wt / ".loop").mkdir()
    (wt / ".loop/x").write_text("x")
    assert _loop.changed_paths(wt, base) == {
        "tool.sh",
        "tests/test_new.py",
        "keep.txt",
    }


def test_features_sha_ignores_passes():
    a = [{"id": "x", "verify": "true", "passes": False}]
    b = [{"id": "x", "verify": "true", "passes": True}]
    c = [{"id": "x", "verify": "false", "passes": False}]
    assert _loop.features_sha(a) == _loop.features_sha(b) != _loop.features_sha(c)


def test_spec_split_and_frontmatter():
    text = "---\nslug: a\nmax_iterations: 3   # cap\n---\n## Goal\ng\n## Iteration log\n- #1 kept\n"
    spec, log = _loop.split_spec(text)
    assert spec.endswith("g\n") and log == "- #1 kept\n"
    assert _loop.frontmatter(text) == {"slug": "a", "max_iterations": "3"}


def test_bin_sha_covers_every_file(loop_env):
    b = loop_env.wt / ".loop/bin"
    b.mkdir(parents=True)
    (b / "_loop.py").write_text("x = 1\n")
    first = _loop.bin_sha(loop_env.wt)
    (b / "json.py").write_text("x")
    assert _loop.bin_sha(loop_env.wt) != first


@pytest.mark.parametrize(
    "origin, want",
    [
        (None, "personal"),  # nobody else has access
        ("git@github.com:me/r.git", "personal"),
        ("https://github.com/me/r.git", "personal"),
        ("git@github.com:team/r.git", "work"),  # under collaboration
    ],
)
def test_profile_follows_collaboration(loop_env, origin, want):
    own_repos_are_personal(
        loop_env.home
    )  # the generic rule that docs/loop-engineering.md §16 documents
    if origin:
        git(loop_env.main, "remote", "add", "origin", origin)
    assert _loop.profile_for(loop_env.wt) == want


def test_unknown_login_is_work(loop_env, monkeypatch):
    # forge.sh whoami could not answer: the repo is treated as a team repo
    import repo_setup

    monkeypatch.setattr(repo_setup, "_users", {})  # the login cache of earlier tests
    monkeypatch.setenv("FORGE_GIT_USER", "")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # no gh or glab
    own_repos_are_personal(loop_env.home)
    git(loop_env.main, "remote", "add", "origin", "git@github.com:me/r.git")
    assert _loop.profile_for(loop_env.wt) == "work"


def test_profile_path_rule_uses_the_main_checkout(loop_env):
    personal(loop_env.home, loop_env.main)
    assert _loop.profile_for(loop_env.wt) == "personal"


@pytest.mark.parametrize(
    "remote, rule, want",
    [
        ("https://github.com/me/r.git", "github.com/me", "personal"),
        ("git@github.com:me/r.git", "github.com", "personal"),
        ("git@github.com:other/r.git", "github.com/me", "work"),
    ],
)
def test_profile_remote_rule(loop_env, remote, rule, want):
    git(loop_env.main, "remote", "add", "origin", remote)
    cfg = loop_env.home / ".config/claude"
    cfg.mkdir(parents=True)
    rules = [{"remote": rule, "profile": "personal"}]
    (cfg / "loop-profiles.local.json").write_text(json.dumps(rules))
    assert _loop.profile_for(loop_env.wt) == want


def test_the_shipped_rules_map_no_repo_to_personal(loop_env):
    """A repo that no rule maps is work: the strict default. The user maps their own repos."""
    shipped = json.loads((CLAUDE / "loop-profiles.json").read_text(encoding="utf-8"))
    assert [r for r in shipped if r.get("profile") == "personal"] == []
    assert not any("path" in r for r in shipped)
    assert _loop.profile_for(loop_env.wt) == "work"  # no origin, no rule


@pytest.mark.parametrize(
    "status, sid, code",
    [
        ("running", "s1", 0),
        ("bundling", "s1", 0),
        ("done", "s1", 1),
        ("running", "s2", 1),
    ],
)
def test_running_cli(loop_env, status, sid, code):
    _loop.save_state(
        {"worktree": str(loop_env.wt.resolve()), "status": status, "session_id": "s1"}
    )
    p = subprocess.run(
        [python(), "-B", str(HOOKS / "_loop.py"), "running", str(loop_env.wt), sid],
        check=False,
    )
    assert p.returncode == code
