"""The plugins under claude/plugins: valid skills, listed in the marketplace, third-party notes kept.

Privacy of the content is checked for the whole repo by test_public_content.py."""

import json
import re

import pytest
from hookrun import ROOT

PLUGINS = ROOT / "claude" / "plugins"
# Skip dot folders: the Claude Code sandbox can leave an empty .claude/ here, and it is not a skill.
SKILLS = sorted(
    skill
    for plugin in PLUGINS.iterdir()
    if (plugin / "skills").is_dir()
    for skill in (plugin / "skills").iterdir()
    if not skill.name.startswith(".")
)
THIRD_PARTY = ("addy-picks", "ecc-picks", "hf-picks")


def frontmatter(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, f"{skill.name}: no frontmatter"
    pairs = (line.split(":", 1) for line in m.group(1).splitlines())
    return {k.strip(): v.strip().strip('"') for k, v in pairs}


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_frontmatter(skill):
    meta = frontmatter(skill)
    assert meta["name"] == skill.name
    assert 0 < len(meta["description"]) < 1536


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_referenced_files_exist(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for ref in set(re.findall(r"references/[\w.-]+\.md", text)):
        assert (skill / ref).is_file(), ref


def test_writing_skills_holds_the_four_skills():
    names = {p.name for p in (PLUGINS / "writing-skills/skills").iterdir()}
    assert names == {
        "ste-visual-first",
        "technical-doc-standards",
        "winston-presentations",
        "fable-agent-patterns",
    }
    # one place for each skill: safe-lean does not keep a second copy
    assert not (ROOT / "claude/skills/ste-visual-first").exists()


@pytest.mark.parametrize("plugin", sorted(p.name for p in PLUGINS.iterdir()))
def test_plugin_is_listed_in_the_marketplace_and_named_right(plugin):
    market = json.loads(
        (ROOT / "claude/.claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    sources = {p["name"]: p["source"] for p in market["plugins"]}
    assert sources.get(plugin) == f"./plugins/{plugin}"
    manifest = json.loads(
        (PLUGINS / plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == plugin


@pytest.mark.parametrize("plugin", THIRD_PARTY)
def test_third_party_picks_keep_their_licence_and_source(plugin):
    folder = PLUGINS / plugin
    assert (folder / "LICENSE").read_text(encoding="utf-8").strip()
    manifest = json.loads(
        (folder / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["license"] and manifest["homepage"].startswith(
        "https://github.com/"
    )
