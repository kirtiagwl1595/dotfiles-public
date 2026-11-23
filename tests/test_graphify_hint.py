"""graphify_hint tells Claude to query the graph first, only in repos that have one."""

import json
import os
import shutil
import subprocess

import pytest
from hookrun import HOOKS

HOOK = HOOKS / "graphify_hint.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH, reason="no bash")


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def hint(cwd):
    p = subprocess.run(
        [BASH, str(HOOK)],
        input=json.dumps({"cwd": str(cwd)}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0
    return p.stdout


def repo_with_commit(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.py").write_text("x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "a")
    return tmp_path


def test_silent_without_a_graph(tmp_path):
    assert hint(repo_with_commit(tmp_path)) == ""


def test_fresh_graph_gives_the_hint(tmp_path):
    repo = repo_with_commit(tmp_path)
    (repo / "graphify-out").mkdir()
    (repo / "graphify-out" / "graph.json").write_text("{}")
    out = hint(repo / "graphify-out")  # a subfolder finds the repo root
    assert "graphify query" in out
    assert "--update" not in out


def test_stale_graph_asks_for_update(tmp_path):
    repo = repo_with_commit(tmp_path)
    (repo / "graphify-out").mkdir()
    graph = repo / "graphify-out" / "graph.json"
    graph.write_text("{}")
    os.utime(graph, (0, 0))  # older than the commit
    assert "graphify . --update" in hint(repo)
