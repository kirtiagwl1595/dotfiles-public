"""The loop agents: each file in claude/agents matches its row in docs/loop-engineering.md §17.2."""

import re

import _loop
import pytest
from loop_fixtures import (
    CLAUDE,
    LOOP_MARKS,
    machine_free_git,  # noqa: F401 - an autouse fixture
)

pytestmark = LOOP_MARKS

DOC = CLAUDE.parent / "docs/loop-engineering.md"
AGENTS = CLAUDE / "agents"
ALIASES = {"opus", "sonnet", "haiku", "fable", "inherit"}
MODEL_ID = re.compile(r"claude-(opus|sonnet|haiku|fable)-\d")


def design_rows():
    """{name: (model, tools, preloads)} for each `<name>` agent row of the §17.2 table."""
    section = DOC.read_text().split("### §17.2", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        m = re.fullmatch(r"`([a-z-]+)` agent", cells[0]) if len(cells) == 4 else None
        if m:
            tools = {t.strip() for t in cells[2].split(",")}
            preloads = re.findall(r"Preloads `([^`]+)`", cells[3])
            rows[m.group(1)] = (cells[1].lower(), tools, preloads)
    return rows


def skills_of(text):
    """The YAML list under `skills:` in the frontmatter."""
    m = re.search(r"^skills:\n((?:[ \t]+- .+\n)+)", text, re.MULTILINE)
    return re.findall(r"- (\S+)", m.group(1)) if m else []


ROWS = design_rows()


def test_the_design_table_names_the_agents():
    assert set(ROWS) == {"loop-reviewer", "loop-diagnoser", "loop-log-reader"}


def test_every_agent_file_has_a_design_row():
    assert {p.stem for p in AGENTS.glob("*.md")} == set(ROWS)


@pytest.mark.parametrize("name", sorted(ROWS))
def test_agent_file_matches_its_design_row(name):
    model, tools, preloads = ROWS[name]
    text = (AGENTS / f"{name}.md").read_text()
    meta = _loop.frontmatter(text)
    assert meta["name"] == name
    assert meta.get("description")
    assert meta["model"] == model and model in ALIASES
    assert {t.strip() for t in meta["tools"].split(",")} == tools
    assert skills_of(text) == preloads
    assert not MODEL_ID.search(text)


@pytest.mark.parametrize("name", sorted(ROWS))
def test_preloaded_skills_exist(name):
    text = (AGENTS / f"{name}.md").read_text()
    for skill in skills_of(text):
        plugin, _, short = skill.partition(":")
        assert (
            plugin == "safe-lean" and (CLAUDE / "skills" / short / "SKILL.md").is_file()
        )
