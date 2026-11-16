"""The settings files keep the approval rule: inside the sandbox, a command runs as allowed;
outside it (an escape, an excluded command, every command on Windows), Claude asks the user.
Auto mode is allowed but never the default: when the user picks it, a classifier decides
instead of the user, and the deny rules and the guards still apply."""

import fnmatch
import json

import pytest
from hookrun import ROOT

CLAUDE = ROOT / "claude"
BASE = json.loads((CLAUDE / "settings.base.json").read_text(encoding="utf-8"))
SANDBOX = json.loads((CLAUDE / "settings.sandbox.json").read_text(encoding="utf-8"))


def rules(settings, kind):
    return settings.get("permissions", {}).get(kind, [])


def bash_rule(rule):
    """The command text of `Bash(git status:*)` → `git status`, else None."""
    if not (rule.startswith("Bash(") and rule.endswith(")")):
        return None
    return rule[5:-1].removesuffix(":*").rstrip("*").strip()


def test_default_mode_asks_bypass_is_off_and_auto_is_allowed():
    perms = BASE["permissions"]
    assert perms["defaultMode"] == "default"
    assert perms["disableBypassPermissionsMode"] == "disable"
    assert "disableAutoMode" not in perms


def test_base_allows_no_command_so_windows_always_asks():
    # Native Windows has no sandbox: an allowed command there runs with no guard but the hooks
    assert not [
        r for r in rules(BASE, "allow") if r.startswith(("Bash(", "PowerShell("))
    ]


def test_no_allow_entry_skips_the_question_for_an_excluded_command():
    # Excluded commands run outside the sandbox: an allow entry would run them unasked
    excluded = SANDBOX["sandbox"]["excludedCommands"]
    allowed = [bash_rule(r) for r in rules(BASE, "allow") + rules(SANDBOX, "allow")]
    clash = [
        (a, pattern)
        for a in allowed
        if a
        for pattern in excluded
        if fnmatch.fnmatchcase(a + " x", pattern) or fnmatch.fnmatchcase(a, pattern)
    ]
    assert not clash


def test_sandbox_fails_closed_and_escapes_ask():
    box = SANDBOX["sandbox"]
    assert box["enabled"] is True
    assert box["failIfUnavailable"] is True
    assert box["autoAllowBashIfSandboxed"] is True
    assert box["allowUnsandboxedCommands"] is True
    assert box["enableWeakerNestedSandbox"] is False
    assert box["enableWeakerNetworkIsolation"] is False
    assert "gh *" in box["excludedCommands"]


def test_sandbox_allow_entries_are_read_only():
    allowed = [bash_rule(r) for r in rules(SANDBOX, "allow")]
    assert allowed and all(allowed)
    writes = ("push", "commit", "rm", "install", "reset", "clean", "-d", "-D")
    assert not [a for a in allowed if any(w in a.split() for w in writes)]


@pytest.mark.parametrize(
    "path",
    [
        "~/.ssh/**",
        "~/.aws/**",
        "~/.config/gh/**",
        "~/.git-credentials",
        "~/AppData/Roaming/Microsoft/Credentials/**",
        "~/AppData/Roaming/Microsoft/Protect/**",
        "~/AppData/Roaming/GitHub CLI/**",
        "**/.env",
        "**/.env.*",
    ],
)
def test_secret_paths_are_denied_to_read_and_edit(path):
    deny = rules(BASE, "deny")
    assert f"Read({path})" in deny
    if not path.startswith("**"):
        assert f"Edit({path})" in deny


@pytest.mark.parametrize(
    "cmd", ["git push", "gh pr create", "rm", "del", "Remove-Item", "winget install"]
)
def test_outward_and_delete_commands_ask(cmd):
    assert f"Bash({cmd}:*)" in rules(BASE, "ask")


@pytest.mark.parametrize("cmd", ["*gh auth token*", "*--show-token*", "sudo:*"])
def test_token_reads_and_sudo_are_denied(cmd):
    assert f"Bash({cmd})" in rules(BASE, "deny")


def test_guards_read_utf8():
    assert BASE["env"]["PYTHONUTF8"] == "1"


def test_every_rule_is_well_formed():
    for settings in (BASE, SANDBOX):
        for kind in ("allow", "ask", "deny"):
            for rule in rules(settings, kind):
                assert rule.count("(") == rule.count(")"), rule
                if "(" in rule:
                    assert rule.endswith(")"), rule


def test_network_allowlist_has_no_wildcard_for_everything():
    domains = SANDBOX["sandbox"]["network"]["allowedDomains"]
    assert domains and "*" not in domains
