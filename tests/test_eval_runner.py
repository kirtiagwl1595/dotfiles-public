"""claude/evals/run.sh: which plugin `claude plugin eval` runs against."""

import subprocess

import pytest
from loop_fixtures import (
    CLAUDE,
    LOOP_MARKS,
    machine_free_git,  # noqa: F401 - an autouse fixture
)

pytestmark = LOOP_MARKS

RUNNER = CLAUDE / "evals/run.sh"


def runner(tmp_path, *args):
    """run.sh with a `claude` stub that prints its arguments, so no eval runs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "claude"
    stub.write_text('#!/bin/sh\necho "$@"\n', encoding="utf-8")
    stub.chmod(0o755)
    return subprocess.run(
        ["bash", str(RUNNER), *args],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)},
    )


def test_the_default_plugin_is_safe_lean(tmp_path):
    p = runner(tmp_path)
    assert p.returncode == 0, p.stderr
    assert p.stdout.split()[:3] == ["plugin", "eval", str(CLAUDE)]


def test_plugin_picks_the_plugin_and_is_not_passed_on(tmp_path):
    # `claude plugin eval` reads one plugin's own evals/: a writing-skills case needs writing-skills
    plugin = tmp_path / "other"
    plugin.mkdir()
    p = runner(tmp_path, "--case", "x", "--plugin", str(plugin), "--runs", "3")
    assert p.returncode == 0, p.stderr
    words = p.stdout.split()
    assert words[2] == str(plugin.resolve()) and "--plugin" not in words
    assert words[-4:] == ["--case", "x", "--runs", "3"]


@pytest.mark.parametrize("args", [["--plugin", "/no/such/plugin"], ["--plugin"]])
def test_a_bad_plugin_gets_a_message_and_exit_2(tmp_path, args):
    p = runner(tmp_path, *args)
    assert (p.returncode, p.stdout) == (2, ""), p.stdout
    assert p.stderr.startswith("run.sh: ")
