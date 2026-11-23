"""The user docs name only things that exist in the repo.

Each test states a rule for every doc, never one exact sentence: a flag, a script, a skill, a
guard or a link that a doc names must exist. A doc that names a missing command is a defect.
"""

import json
import re
import subprocess
import sys

import pytest
from hookrun import ROOT

DOCS = [
    ROOT / "README.md",
    ROOT / "GUIDE.md",
    ROOT / "docs" / "SETUP.md",
    ROOT / "docs" / "decisions.md",
]
MARKETPLACE = json.loads(
    (ROOT / "claude" / ".claude-plugin" / "marketplace.json").read_text(
        encoding="utf-8"
    )
)
PLUGINS = {p["name"] for p in MARKETPLACE["plugins"]}
# Every skill of every plugin in the marketplace (a plugin skill is at <plugin>/skills/<name>)
SKILLS = {p.parent.name for p in (ROOT / "claude").rglob("skills/*/SKILL.md")}
# Commands that Claude Code itself provides: they are not in this repo
BUILT_IN = {
    "add-dir",
    "clear",
    "compact",
    "context",
    "cost",
    "hooks",
    "init",
    "memory",
    "model",
    "plugin",
    "resume",
    "rewind",
    "sandbox",
    "usage",
}
INSTALLERS = r"(?:install\.py|install\.sh|install\.cmd|install\.ps1)"
FORGE_COMMANDS = {"kind", "pr-create", "whoami", "auth-check"}
REPO_SETUP_COMMANDS = {"plan", "apply", "team", "protect"}


def text(path):
    return path.read_text(encoding="utf-8")


def code_spans(doc):
    """Inline code and fenced blocks, where a doc names commands and paths."""
    body = text(doc)
    return re.findall(r"`([^`\n]+)`", body) + re.findall(
        r"```.*?\n(.*?)```", body, re.DOTALL
    )


def run_help(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "install.py"), *args, "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def is_ignored(path):
    """A file the user makes, for example packages/trials.json, is ignored by git on purpose."""
    return (
        subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=ROOT, check=False
        ).returncode
        == 0
    )


def installer_options():
    return set(re.findall(r"--[a-z-]+", run_help()))


def installer_steps():
    return set(re.search(r"--only \{([\w,]+)\}", run_help()).group(1).split(","))


def pkg_commands():
    return set(re.search(r"\{([\w,]+)\}", run_help("pkg")).group(1).split(","))


def installer_lines(doc):
    for span in code_spans(doc):
        for line in span.splitlines():
            if re.search(INSTALLERS, line):
                yield line


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_installer_option_exists(doc):
    known = installer_options()
    named = set()
    for span in code_spans(doc):
        for line in span.splitlines():
            if re.search(INSTALLERS, line):
                named |= set(re.findall(r"--[a-z-]+", line))
    assert named <= known, (
        f"{doc.name} names options that install.py lacks: {named - known}"
    )


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_script_path_exists(doc):
    for span in code_spans(doc):
        for path in re.findall(
            r"(?<![\w./-])((?:scripts|claude|tests|git|shell|packages|docs)/[\w./-]*\w\.\w+)",
            span,
        ):
            assert (ROOT / path).exists() or is_ignored(path), (
                f"{doc.name} names {path}"
            )


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_slash_command_exists(doc):
    for span in re.findall(r"`(/[\w:-]+)(?: [^`]*)?`", text(doc)):
        name = span[1:]
        if ":" in name:
            plugin, skill = name.split(":", 1)
            assert plugin in PLUGINS, f"{doc.name}: {span} is not a plugin of this repo"
            assert skill in SKILLS, f"{doc.name}: no skill {skill}"
        else:
            assert name in SKILLS | BUILT_IN, f"{doc.name} names {span}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_guard_exists(doc):
    for name in set(re.findall(r"\bguard_[a-z_]+", text(doc))):
        assert (ROOT / "claude" / "hooks" / f"{name}.py").exists(), (
            f"{doc.name} names {name}"
        )


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_helper_command_exists(doc):
    body = text(doc)
    for sub in re.findall(r"forge\.sh (?!--)([a-z-]+)", body):
        assert sub in FORGE_COMMANDS, f"{doc.name}: forge.sh has no command {sub}"
    for sub in re.findall(r"repo_setup\.py (?!--)([a-z]+)", body):
        assert sub in REPO_SETUP_COMMANDS, (
            f"{doc.name}: repo_setup.py has no mode {sub}"
        )


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_relative_link_resolves(doc):
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text(doc)):
        if re.match(r"[a-z]+:", target):
            continue
        assert (doc.parent / target).exists(), f"{doc.name} links to {target}"


def test_forge_commands_match_the_script():
    script = text(ROOT / "claude" / "forge.sh")
    for sub in FORGE_COMMANDS:
        assert re.search(rf"^\s+{re.escape(sub)}\)", script, re.MULTILINE)


def test_the_html_guide_has_every_section_of_the_markdown_guide():
    """docs/build.sh makes the page from GUIDE.md: a stale page misses a heading."""
    html = " ".join(text(ROOT / "docs" / "guide.html").split())  # pandoc wraps lines
    for heading in re.findall(r"^# \d+\. (.+)$", text(ROOT / "GUIDE.md"), re.MULTILINE):
        escaped = heading.replace("&", "&amp;")
        assert escaped in html, (
            f"docs/guide.html is stale: run docs/build.sh ({heading})"
        )


def test_decision_ids_are_unique_and_in_order():
    ids = re.findall(
        r"^\| D(\d+) \|", text(ROOT / "docs" / "decisions.md"), re.MULTILINE
    )
    assert ids == [str(n) for n in range(1, len(ids) + 1)]


def test_superseded_decisions_name_a_real_successor():
    body = text(ROOT / "docs" / "decisions.md")
    known = set(re.findall(r"^\| (D\d+) \|", body, re.MULTILINE))
    for target in re.findall(r"Superseded by (D\d+)", body):
        assert target in known


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_install_step_and_pkg_command_exists(doc):
    steps, subs = installer_steps(), pkg_commands()
    for line in installer_lines(doc):
        for step in re.findall(r"--only ([a-z]+)", line):
            assert step in steps, f"{doc.name} names step {step}"
        for sub in re.findall(r"install\.py pkg ([a-z]+)", line):
            assert sub in subs, f"{doc.name} names pkg {sub}"
