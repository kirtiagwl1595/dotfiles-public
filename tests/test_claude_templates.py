"""The personal-file templates and the shared reference files in claude/."""

import re

import pytest
from hookrun import ROOT

CLAUDE = ROOT / "claude"
TEMPLATES = ["CLAUDE.about-me.example.md", "CLAUDE.profile.example.md"]


def read(name):
    return (CLAUDE / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", TEMPLATES)
def test_a_template_has_placeholders_and_the_two_line_note(name):
    text = read(name)
    assert re.search(r"<[a-z][a-z -]+>", text), "no <placeholder>"
    head = text.splitlines()[:6]
    note = " ".join(head)
    assert "~/.claude/" in note and "@import" in note
    assert "fill in" in note.lower()


@pytest.mark.parametrize("name", TEMPLATES)
def test_every_fact_line_of_a_template_is_a_placeholder(name):
    # Term-hunting is the job of test_public_content.py; here the shape must hold
    facts = [x for x in read(name).splitlines() if x.startswith("- ")]
    assert facts
    assert all(re.search(r"<[^>]+>", x) for x in facts), facts


def test_the_templates_are_not_imported_by_the_shared_rules():
    # A file that holds placeholders must never load by itself
    for name in ("CLAUDE.md", "CLAUDE.style.md"):
        assert "example.md" not in read(name)


def test_lesson_style_is_generic():
    text = read("LESSON-STYLE.md")
    assert "Netflix" in text and ".claude/lessons/" in text


def test_benchmark_record_is_an_empty_template():
    text = read("BENCHMARK-RECORD.md")
    for item in ("Model", "Data", "Quality", "Speed", "Cost", "Repeat"):
        assert f"**{item}**" in text or f"- {item}:" in text
    assert not re.search(r"\d+(\.\d+)?\s*%|\bp95\s*=", text), "holds a result"
    assert "<" in text
