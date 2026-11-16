"""CHANGELOG.md has a dated section for the plugin version, so each release has its notes."""

import json
import re

from hookrun import ROOT

CHANGELOG = ROOT / "CHANGELOG.md"
PLUGIN = ROOT / "claude" / ".claude-plugin" / "plugin.json"
SECTION = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$", re.MULTILINE)


def sections():
    return SECTION.findall(CHANGELOG.read_text(encoding="utf-8"))


def test_the_plugin_version_has_a_dated_section():
    version = json.loads(PLUGIN.read_text(encoding="utf-8"))["version"]
    assert version in [v for v, _ in sections()]


def test_newest_section_comes_first():
    versions = [tuple(map(int, v.split("."))) for v, _ in sections()]
    assert versions == sorted(versions, reverse=True)


def test_each_section_has_entries():
    text = CHANGELOG.read_text(encoding="utf-8")
    parts = SECTION.split(text)[1:]
    for version, _, body in zip(parts[::3], parts[1::3], parts[2::3]):
        assert re.search(r"^- ", body, re.MULTILINE), version
