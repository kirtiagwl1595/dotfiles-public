"""Shared test setup."""

import os
import re
import subprocess

import pytest

# Fixtures for the loop tests; importing the module also puts claude/ and claude/hooks on sys.path
from loop_fixtures import loop_env, machine_free_git  # noqa: F401


def _forget_the_callers_repo():
    """A git hook (pre-push) exports GIT_DIR, GIT_INDEX_FILE and more.

    Inherited, they point every `git -C <tmp>` in the tests at the real repo.
    Git names its repo-local variables itself.
    """
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    names = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],
        env=clean,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for name in list(os.environ):
        if name in names or re.fullmatch(r"GIT_CONFIG_(KEY|VALUE)_\d+", name):
            del os.environ[name]


_forget_the_callers_repo()


@pytest.fixture(autouse=True)
def unsigned_commits(monkeypatch):
    # Throwaway test repos must not need the user's signing key (the sandbox hides ~/.ssh)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
