"""repo_setup.py protect: lock the Git hooks and config of a repo outside ~/git (probes P9, P10).

settings.base.json covers ~/git. Elsewhere the rules need absolute paths, so they go to the main
checkout's .claude/settings.local.json, which a worktree session reads and nobody commits.
"""

import json
import os
import subprocess
import sys

import pytest
from loop_fixtures import (
    CLAUDE,
    git,
)

SCRIPT = CLAUDE / "repo_setup.py"
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the rules hold POSIX absolute paths and the cases use symlinks",
)


@pytest.fixture
def home(tmp_path, monkeypatch, machine_free_git):
    (tmp_path / "ignore").write_text(
        "**/.claude/settings.local.json\n", encoding="utf-8"
    )
    config = f"[user]\n\tname = t\n\temail = t@t\n[core]\n\texcludesFile = {tmp_path / 'ignore'}\n"
    (tmp_path / ".gitconfig").write_text(config, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    # conftest switches the global ignore off; this command depends on it
    monkeypatch.setenv("GIT_CONFIG_VALUE_1", str(tmp_path / "ignore"))
    return tmp_path.resolve()


def make(path):
    path.mkdir(parents=True)
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    git(path, "init", "-q", "-b", "main")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "init")
    return path


def protect(path, mode="protect"):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), mode, str(path)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )


def deny_rules(repo):
    text = (repo / ".claude/settings.local.json").read_text(encoding="utf-8")
    return json.loads(text)["permissions"]["deny"]


def expected(repo):
    return [f"Edit(/{repo}/.git/config)", f"Edit(/{repo}/.git/hooks/**)"]


def test_a_repo_outside_the_code_folder_gets_local_absolute_rules(home):
    repo = make(home / "work/app")
    p = protect(repo)
    assert p.returncode == 0, p.stderr
    assert deny_rules(repo) == expected(repo)
    assert git(repo, "status", "--porcelain") == ""  # never committed, never shown


def test_from_a_worktree_the_rules_go_to_the_main_checkout(home):
    repo = make(home / "work/app")
    wt = repo.parent / "app-wt"
    git(repo, "worktree", "add", "-q", "-b", "wt", str(wt))
    assert protect(wt).returncode == 0
    assert deny_rules(repo) == expected(repo)
    assert not (wt / ".claude/settings.local.json").exists()


def test_own_entries_stay_and_a_second_run_changes_nothing(home):
    repo = make(home / "work/app")
    local = repo / ".claude/settings.local.json"
    local.parent.mkdir()
    mine = {
        "permissions": {"allow": ["Bash(make:*)"], "deny": ["Bash(x:*)"]},
        "model": "x",
    }
    local.write_text(json.dumps(mine), encoding="utf-8")
    assert protect(repo).returncode == 0
    once = local.read_text(encoding="utf-8")
    merged = json.loads(once)
    assert merged["model"] == "x" and merged["permissions"]["allow"] == ["Bash(make:*)"]
    assert deny_rules(repo) == ["Bash(x:*)", *expected(repo)]
    assert protect(repo).returncode == 0
    assert local.read_text(encoding="utf-8") == once


@pytest.mark.parametrize("place", ["git/app", "git/group/app"])
def test_a_repo_that_the_user_settings_cover_gets_no_file(home, place):
    repo = make(home / place)
    p = protect(repo)
    assert p.returncode == 0, p.stderr
    # The message names the condition: this is a path rule, not a check of the loaded settings
    assert "below ~/git" in p.stdout and "deny rules that install.py writes" in p.stdout
    assert not (repo / ".claude").exists()


def link_the_file(home, repo):
    (repo / ".claude").mkdir()
    (home / "victim").write_text("{}", encoding="utf-8")
    (repo / ".claude/settings.local.json").symlink_to(home / "victim")


def link_the_folder(home, repo):
    (home / "victim").mkdir()
    (repo / ".claude").symlink_to(home / "victim")


def bad_json(home, repo):
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.local.json").write_text("{not json", encoding="utf-8")


def not_ignored(home, repo):
    (home / "ignore").write_text("", encoding="utf-8")


def odd_shape(home, repo):
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.local.json").write_text("[]", encoding="utf-8")


@pytest.mark.parametrize(
    "spoil", [link_the_file, link_the_folder, bad_json, not_ignored, odd_shape]
)
def test_it_refuses_with_a_message_and_writes_nothing(home, spoil):
    # setup-repo runs this outside the sandbox: a planted link would choose what it overwrites
    repo = make(home / "work/app")
    spoil(home, repo)

    def files():
        found = (p for p in home.rglob("*") if p.is_file() and ".git" not in p.parts)
        return {p: p.read_bytes() for p in found}

    before = files()
    p = protect(repo)
    assert p.returncode != 0
    assert p.stderr.strip() and "Traceback" not in p.stderr
    assert files() == before


@pytest.mark.parametrize("name", ["app[1]", "app*", "app(old)"])
def test_a_path_that_would_change_the_rule_is_refused(home, name):
    repo = make(home / "work" / name)
    p = protect(repo)
    assert p.returncode != 0 and "Traceback" not in p.stderr and p.stderr.strip()
    assert not (repo / ".claude").exists()


def test_the_bulk_run_protects_team_and_dirty_repos_and_plan_changes_nothing(
    home, monkeypatch
):
    # a bulk run over ~/work: no repo needs the rules added by hand
    monkeypatch.setenv("FORGE_GIT_USER", "me")
    team, dirty, broken = (make(home / "work" / n) for n in ("team", "dirty", "broken"))
    git(team, "remote", "add", "origin", "https://github.com/acme/team.git")
    (dirty / "a.txt").write_text("changed\n", encoding="utf-8")
    bad_json(home, broken)

    plan = protect(home / "work", "plan")
    assert plan.returncode == 0, plan.stderr
    assert "→ team: lock .git hooks and config" in plan.stdout
    assert not (team / ".claude").exists() and not (dirty / ".claude").exists()

    done = protect(home / "work", "apply")
    assert done.returncode == 0, done.stderr
    assert deny_rules(team) == expected(team)
    assert deny_rules(dirty) == expected(dirty)
    assert "! broken: .git hooks and config not locked" in done.stdout
    assert git(team, "status", "--porcelain") == ""
    assert "lock .git" not in protect(home / "work", "plan").stdout


def test_a_folder_that_is_no_repo_is_refused(home):
    (home / "plain").mkdir()
    p = protect(home / "plain")
    assert p.returncode != 0 and "Traceback" not in p.stderr and p.stderr.strip()
