"""This repo is public: no file may name its owner, hold an email address or a home path,
or use a term from the owner's private list. The values to look for come from the machine
at test time, so the repo itself never holds them."""

import os
import re
import subprocess
from pathlib import Path

import pytest
from hookrun import ROOT

EMAIL = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}\b"
)  # a domain ends in letters: not ruff@0.17.2
HOME_PATH = re.compile(r"(?:/Users|/home|[A-Za-z]:\\Users)[/\\](\w{2,})", re.IGNORECASE)
PLACEHOLDER_USERS = {"x", "runner", "runneradmin", "me", "you", "user", "name"}


def repo_files():
    out = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [ROOT / f for f in out if (ROOT / f).is_file()]


def texts():
    for path in repo_files():
        try:
            yield path, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def git_value(key):
    p = subprocess.run(
        ["git", "config", "--get", key], capture_output=True, text=True, check=False
    )
    return p.stdout.strip()


def private_terms():
    path = os.environ.get(
        "PRIVATE_TERMS_FILE",
        os.path.join(os.path.expanduser("~"), ".config", "claude", "private-terms.txt"),
    )
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    terms = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line.split("=>")[0].strip())
    return terms


def found(term, text):
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)


def test_no_email_address():
    hits = [
        (p.name, m)
        for p, t in texts()
        for m in EMAIL.findall(t)
        if not m.endswith(("@t", "@y", "@example.com"))
    ]
    assert not hits


def test_no_real_home_path():
    hits = [
        (p.name, m.group(0))
        for p, t in texts()
        for m in HOME_PATH.finditer(t)
        if m.group(1).lower() not in PLACEHOLDER_USERS
    ]
    assert not hits


@pytest.mark.parametrize("key", ["user.name", "user.email"])
def test_no_git_identity_of_this_machine(key):
    value = git_value(key)
    if not value:
        pytest.skip(f"no git {key} here")
    words = [value] + [w for w in value.split() if len(w) > 3]
    hits = [(p.name, w) for p, t in texts() for w in words if found(w, t)]
    assert not hits


def test_no_private_term():
    terms = private_terms()
    if not terms:
        pytest.skip("no private terms file, or the sandbox cannot read it")
    hits = [(p.name, term) for p, t in texts() for term in terms if found(term, t)]
    assert not hits


def test_every_skill_names_itself():
    skills = sorted((ROOT / "claude" / "skills").glob("*/SKILL.md"))
    assert skills
    for skill in skills:
        head = skill.read_text(encoding="utf-8").split("---")[1]
        name = re.search(r"^name:\s*\"?([\w-]+)", head, re.MULTILINE)
        assert name and name.group(1) == skill.parent.name
        assert re.search(r"^description:\s*\S", head, re.MULTILINE)
