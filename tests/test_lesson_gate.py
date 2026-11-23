"""lesson_gate asks once for a lesson after real work; it is off until the user opts in.

The user opts in with ~/.config/claude/lesson-gate (an empty file). Hook wiring is in test_launcher.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from hookrun import HOOKS, env_for

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH, reason="no bash")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    # The gate is off until the user opts in with this file
    (tmp_path / ".config" / "claude").mkdir(parents=True)
    (tmp_path / ".config" / "claude" / "lesson-gate").write_text("", encoding="utf-8")
    env = {
        **env_for(tmp_path),
        "TMPDIR": str(tmp_path),
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    git = [
        "git",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(["git", "init", "-q", str(r)], check=True, env=env)
    (r / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run([*git, "-C", str(r), "add", "."], check=True, env=env)
    subprocess.run([*git, "-C", str(r), "commit", "-qm", "init"], check=True, env=env)
    return r, env


def gate(mode, repo, env, active=False, session="s1", source=None):
    payload = {"session_id": session, "cwd": str(repo), "stop_hook_active": active}
    if source:
        payload["source"] = source
    p = subprocess.run(
        [BASH, str(HOOKS / "lesson_gate.sh"), mode],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return p.returncode, p.stderr


def test_lesson_quiet_without_change(repo):
    r, env = repo
    assert gate("snapshot", r, env)[0] == 0
    assert gate("check", r, env) == (0, "")


@pytest.mark.parametrize("change", ["new_file", "edit_tracked", "edit_dirty"])
def test_lesson_asked_after_change(repo, change):
    r, env = repo
    if change == "edit_dirty":  # already dirty at start: a further edit still counts
        (r / "a.txt").write_text("two\n", encoding="utf-8")
    gate("snapshot", r, env)
    if change == "new_file":
        (r / "b.txt").write_text("new\n", encoding="utf-8")
    else:
        (r / "a.txt").write_text("three\n", encoding="utf-8")
    code, err = gate("check", r, env)
    assert code == 2 and "lesson" in err


def test_lesson_quiet_when_dirty_tree_unchanged(repo):
    r, env = repo
    (r / "a.txt").write_text("two\n", encoding="utf-8")
    gate("snapshot", r, env)
    assert gate("check", r, env)[0] == 0


def test_lesson_quiet_when_todays_lesson_exists(repo):
    r, env = repo
    gate("snapshot", r, env)
    (r / "b.txt").write_text("new\n", encoding="utf-8")
    lessons = r / ".claude" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / f"{date.today():%Y-%m-%d}-topic.md").write_text(
        "# lesson\n", encoding="utf-8"
    )
    assert gate("check", r, env)[0] == 0


def test_lesson_asked_only_once_per_session(repo):
    r, env = repo
    gate("snapshot", r, env)
    (r / "b.txt").write_text("new\n", encoding="utf-8")
    assert gate("check", r, env)[0] == 2
    assert gate("check", r, env)[0] == 0


def test_lesson_quiet_when_stop_hook_active(repo):
    r, env = repo
    gate("snapshot", r, env)
    (r / "b.txt").write_text("new\n", encoding="utf-8")
    assert gate("check", r, env, active=True)[0] == 0


def test_lesson_quiet_without_snapshot(repo):
    r, env = repo
    (r / "b.txt").write_text("new\n", encoding="utf-8")
    assert gate("check", r, env, session="never-started")[0] == 0


def test_lesson_quiet_outside_a_repo(tmp_path):
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "TMPDIR": str(tmp_path)}
    assert gate("snapshot", tmp_path, env)[0] == 0
    assert gate("check", tmp_path, env)[0] == 0


def test_lesson_quiet_when_home_is_the_repo(tmp_path):
    # A git-tracked home (eval sandbox, bare-dotfiles setups): Claude's own writes under ~ are not real work.
    # The gate is off until the user opts in with this file
    (tmp_path / ".config" / "claude").mkdir(parents=True)
    (tmp_path / ".config" / "claude" / "lesson-gate").write_text("", encoding="utf-8")
    env = {
        **env_for(tmp_path),
        "TMPDIR": str(tmp_path),
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    gate("snapshot", cwd, env)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    assert gate("check", cwd, env)[0] == 0


def worktree(repo, env):
    # Same layout as Claude Code agent worktrees: inside the main checkout
    wt = repo / ".claude" / "worktrees" / "wt"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", str(wt)], check=True, env=env
    )
    return wt


def test_lesson_in_main_checkout_counts_from_a_worktree(repo):
    r, env = repo
    wt = worktree(r, env)
    gate("snapshot", wt, env)
    (wt / "b.txt").write_text("new\n", encoding="utf-8")
    lessons = r / ".claude" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / f"{date.today():%Y-%m-%d}-topic.md").write_text(
        "# lesson\n", encoding="utf-8"
    )
    assert gate("check", wt, env) == (0, "")


def test_lesson_request_from_a_worktree_names_the_main_checkout(repo):
    r, env = repo
    wt = worktree(r, env)
    gate("snapshot", wt, env)
    (wt / "b.txt").write_text("new\n", encoding="utf-8")
    code, err = gate("check", wt, env)
    assert code == 2
    # The hook prints the path as git does (C:/x on Windows): compare the folders, not the text
    named = re.search(r"write the lesson to (.+?)/\.claude/lessons/", err).group(1)
    assert os.path.samefile(named, r)
    assert not os.path.samefile(named, wt)


def commit(path, env, name="b.txt", committer=None, author=None):
    (path / name).write_text("new\n", encoding="utf-8")
    extra = {"GIT_COMMITTER_EMAIL": committer} if committer else {}
    if author:
        extra["GIT_AUTHOR_EMAIL"] = author
    git = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"]
    git += ["-c", "commit.gpgsign=false"]
    subprocess.run([*git, "add", "."], check=True, env=env)
    subprocess.run([*git, "commit", "-qm", "work"], check=True, env={**env, **extra})


def test_lesson_quiet_when_moving_from_dirty_root_to_clean_worktree(repo):
    r, env = repo
    (r / "a.txt").write_text("dirty at start\n", encoding="utf-8")
    gate("snapshot", r, env)
    wt = worktree(r, env)
    assert gate("check", wt, env) == (0, "")


def test_lesson_asked_for_work_committed_in_a_worktree(repo):
    r, env = repo
    gate("snapshot", r, env)
    wt = worktree(r, env)
    commit(wt, env)
    code, err = gate("check", wt, env)
    assert code == 2 and "lesson" in err


def test_lesson_asked_after_a_commit_in_the_start_root(repo):
    r, env = repo
    gate("snapshot", r, env)
    commit(r, env)
    assert gate("check", r, env)[0] == 2


def set_email(r, env):
    subprocess.run(
        ["git", "-C", str(r), "config", "user.email", "t@t"], check=True, env=env
    )


def test_lesson_asked_for_own_pr_squash_merged_by_github(repo):
    # GitHub squash merge pulled in: you are the author, a GitHub no-reply address the committer
    r, env = repo
    set_email(r, env)
    gate("snapshot", r, env)
    commit(r, env, committer="web@gh")
    assert gate("check", r, env)[0] == 2


def test_lesson_quiet_for_commits_by_someone_else(repo):
    # A git pull brings in other people's work (or Dependabot's): not your work
    r, env = repo
    set_email(r, env)
    gate("snapshot", r, env)
    commit(r, env, committer="web@gh", author="other@gh")
    assert gate("check", r, env) == (0, "")


def test_lesson_baseline_survives_compact(repo):
    r, env = repo
    gate("snapshot", r, env, source="startup")
    commit(r, env)
    gate("snapshot", r, env, source="compact")
    assert gate("check", r, env)[0] == 2


def test_lesson_quiet_with_untracked_worktree_folder(repo):
    # The fixture does not ignore .claude/worktrees, as in a repo with no such gitignore line
    r, env = repo
    gate("snapshot", r, env)
    worktree(r, env)
    assert gate("check", r, env) == (0, "")


def test_lesson_old_state_file_still_works(repo):
    # A session started under an older hook has only the fingerprint line
    r, env = repo
    gate("snapshot", r, env)
    state = r.parent / "claude-lesson-s1"
    state.write_text(
        state.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8"
    )
    (r / "b.txt").write_text("new\n", encoding="utf-8")
    assert gate("check", r, env)[0] == 2


def test_lesson_gate_is_off_without_the_opt_in_file(repo):
    r, env = repo
    (Path(env["HOME"]) / ".config" / "claude" / "lesson-gate").unlink()
    gate("snapshot", r, env)
    (r / "b.txt").write_text("new\n", encoding="utf-8")
    assert gate("check", r, env) == (0, "")


@pytest.mark.skip(reason="needs loop engine (agent B)")
def test_lesson_quiet_while_a_loop_of_this_session_runs(repo):
    """Ported with the loop engine: the gate steps aside for a running loop of the session."""


@pytest.mark.skip(reason="needs loop engine (agent B)")
def test_lesson_asked_when_the_loop_check_crashes(repo, tmp_path):
    """Ported with the loop engine: a crash in the loop check means the gate runs as before."""
