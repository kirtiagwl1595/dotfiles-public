"""This repo is public: no file may name the owner's private plugins.

The names are built from parts, so that this file does not match its own check.
"""

import subprocess

from hookrun import ROOT

OWNER = "ki" + "rti"  # split: the owner's name must not appear in a tracked file
FORBIDDEN = (OWNER + "-setup", OWNER + "-skills")


def repo_files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    return [ROOT / f for f in out if f and (ROOT / f).is_file()]


def test_no_private_plugin_names():
    found = []
    for path in repo_files():
        text = path.read_bytes().decode("utf-8", errors="ignore").lower()
        found += [
            f"{path.relative_to(ROOT)}: {name}" for name in FORBIDDEN if name in text
        ]
    assert not found, found
