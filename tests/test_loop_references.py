"""The loop-engineer reference files: the skill names each one, and the design doc lists them."""

import re

from loop_fixtures import (
    CLAUDE,
    LOOP_MARKS,
    machine_free_git,  # noqa: F401 - an autouse fixture
)

pytestmark = LOOP_MARKS

SKILL_DIR = CLAUDE / "skills/loop-engineer"
DOC = CLAUDE.parent / "docs/loop-engineering.md"


def files():
    return {p.name for p in (SKILL_DIR / "references").glob("*.md")}


def test_the_skill_names_every_reference_file_and_no_other():
    named = re.findall(
        r"references/([a-z-]+\.md)", (SKILL_DIR / "SKILL.md").read_text()
    )
    assert files() and set(named) == files()


def test_the_design_doc_lists_the_reference_files():
    line = next(
        x
        for x in DOC.read_text().splitlines()
        if "reference files in its `references/`" in x
    )
    assert files() and set(re.findall(r"`([a-z-]+\.md)`", line)) == files()


def test_every_reference_file_names_only_files_that_exist():
    """A path in a reference must not go stale: each repo path it names exists."""
    for name in files():
        text = (SKILL_DIR / "references" / name).read_text()
        for rel in re.findall(r"`((?:claude|docs|scripts)/[\w./-]+)`", text):
            assert (CLAUDE.parent / rel).exists(), f"{name}: {rel}"
