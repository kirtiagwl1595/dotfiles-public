"""prune_backups.py keeps the newest two copies of each item in an install backup folder."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNS = ["2026-01-01-000001", "2026-01-02-000002", "2026-01-03-000003"]
BACKUP = ".claude-backup"
# A link needs a privilege on Windows
pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the test seeds symbolic links"
)


@pytest.fixture
def home(tmp_path):
    return tmp_path


def snapshot(home):
    return sorted(str(p.relative_to(home)) for p in home.rglob("*"))


def seed_backups(home):
    root = home / BACKUP
    for run in RUNS:
        (root / run).mkdir(parents=True)
        (root / run / ".zshrc").write_text(run, encoding="utf-8")
        (root / run / "tool/sub").mkdir(parents=True)
        (root / run / "tool/sub/file").write_text(run, encoding="utf-8")
        (root / run / "link").symlink_to(home / "target-that-stays")
    (home / "target-that-stays").write_text("keep", encoding="utf-8")
    (root / RUNS[0] / ".gitconfig").write_text("only copy", encoding="utf-8")
    (root / RUNS[0] / "cleanup/.pyenv").mkdir(parents=True)
    (root / RUNS[0] / "cleanup/.pyenv/x").write_text("moved tool", encoding="utf-8")
    (root / "gitconfig-before-pull-rebase").write_text("hand", encoding="utf-8")
    return root


def assert_pruned(home, root):
    assert not (root / RUNS[0] / ".zshrc").exists()
    assert not (root / RUNS[0] / "tool").exists()
    assert not (root / RUNS[0] / "link").is_symlink()
    assert (home / "target-that-stays").read_text(encoding="utf-8") == "keep"
    for run in RUNS[1:]:
        assert (root / run / ".zshrc").read_text(encoding="utf-8") == run
        assert (root / run / "tool/sub/file").exists()
        assert (root / run / "link").is_symlink()
    assert (root / RUNS[0] / ".gitconfig").read_text(encoding="utf-8") == "only copy"
    assert (root / RUNS[0] / "cleanup/.pyenv/x").read_text(
        encoding="utf-8"
    ) == "moved tool"
    assert (root / "gitconfig-before-pull-rebase").read_text(encoding="utf-8") == "hand"


def prune(root, command):
    return subprocess.run(
        [sys.executable, str(ROOT / "claude" / "prune_backups.py"), command, str(root)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_prune_keeps_two_newest_per_item(home):
    root = seed_backups(home)
    before = snapshot(home)
    assert prune(root, "plan").splitlines()[0] == "3"
    assert snapshot(home) == before
    prune(root, "apply")
    assert_pruned(home, root)
    assert prune(root, "plan").splitlines()[0] == "0"


def test_prune_removes_a_run_folder_left_empty(home):
    root = home / BACKUP
    for run in RUNS:
        (root / run).mkdir(parents=True)
        (root / run / ".zshrc").write_text(run, encoding="utf-8")
    prune(root, "apply")
    assert not (root / RUNS[0]).exists()


def test_prune_never_reads_a_bad_argument(tmp_path):
    p = subprocess.run(
        [
            sys.executable,
            str(ROOT / "claude" / "prune_backups.py"),
            "nope",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 2 and "usage" in p.stderr and "Traceback" not in p.stderr
