"""coach_prompt (UserPromptSubmit): a tip for risky prompt habits, a hint for a disabled plugin."""

import json
import os
import subprocess
import sys

import pytest
from hookrun import HOOKS, env_for

PY = [sys.executable, "-B"]


def run(cmd, payload, env=None):
    p = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env if env is not None else env_for(),
        check=False,
    )
    return p.returncode, p.stdout, p.stderr


# ── coach_prompt ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "prompt,tip",
    [
        ("just quickly fix the parser", "test"),
        ("skip tests for now and ship it", "test"),
        ("x " * 1200, "plan mode"),
    ],
)
def test_coach_tips(prompt, tip):
    code, out, _ = run([*PY, str(HOOKS / "coach_prompt.py")], {"prompt": prompt})
    assert code == 0
    assert tip in out.lower()


def pasted(text):
    return f'\n\n<pasted_content id="ab12">\n{text}\n</pasted_content id="ab12">'


@pytest.mark.parametrize(
    "prompt",
    [
        "pull done" + pasted("Receiving objects: 100% (463/463), done.\n" * 100),
        "see log" + pasted("WARN: just quickly retrying the request"),
    ],
    ids=["big-paste", "keyword-in-paste"],
)
def test_coach_ignores_pasted_material(prompt):
    code, out, _ = run([*PY, str(HOOKS / "coach_prompt.py")], {"prompt": prompt})
    assert code == 0 and out == ""


def test_coach_counts_own_words_next_to_a_paste():
    prompt = "build the pipeline step " * 55 + pasted("a,b\n1,2")
    code, out, _ = run([*PY, str(HOOKS / "coach_prompt.py")], {"prompt": prompt})
    assert code == 0 and "plan mode" in out.lower()


def test_coach_quiet_on_normal_prompt():
    code, out, _ = run(
        [*PY, str(HOOKS / "coach_prompt.py")],
        {"prompt": "add a histogram of ages"},
    )
    assert code == 0 and out == ""


# ── coach_prompt: dormant-plugin hints ──────────────────────────────────────
@pytest.fixture
def dormant_env(tmp_path):
    def make(enabled):
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps({"enabledPlugins": {"ecc-picks@dotfiles-public": enabled}}),
            encoding="utf-8",
        )
        return {**env_for(), "COACH_SETTINGS": str(settings), "TMPDIR": str(tmp_path)}

    return make


def coach(prompt, env, session="s1"):
    return run(
        [*PY, str(HOOKS / "coach_prompt.py")],
        {"prompt": prompt, "session_id": session},
        env=env,
    )


EVAL_ASK = "set up an eval harness with pass@k"


def test_dormant_hint_when_plugin_off(dormant_env):
    code, out, _ = coach(EVAL_ASK, dormant_env(False))
    assert (
        code == 0
        and "Dormant: ecc-picks" in out
        and "Ask the user first" in out
        and "claude plugin enable ecc-picks@dotfiles-public" in out
    )


def test_dormant_hints_name_only_plugins_this_repo_ships():
    sys.path.insert(0, str(HOOKS))
    from coach_prompt import DORMANT, PER_REPO

    assert set(DORMANT) == {"ecc-picks", "hf-picks", "addy-picks", "writing-skills"}
    assert PER_REPO <= set(DORMANT)


@pytest.mark.parametrize(
    "key, prompt",
    [
        ("hf-picks@any-market", "upload this model to Hugging Face"),
        ("addy-picks@dotfiles-public", "give this plan a doubt-driven review"),
    ],
)
def test_off_plugin_hint_enables_per_repo(tmp_path, key, prompt):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"enabledPlugins": {key: False}}), encoding="utf-8")
    env = {**env_for(), "COACH_SETTINGS": str(settings), "TMPDIR": str(tmp_path)}
    out = coach(prompt, env)[1]
    assert f"claude plugin enable {key} --scope local" in out


def test_no_hint_for_a_plugin_that_is_not_installed(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"enabledPlugins": {"other@x": False}}), encoding="utf-8"
    )
    env = {**env_for(), "COACH_SETTINGS": str(settings), "TMPDIR": str(tmp_path)}
    assert coach("upload this model to Hugging Face", env) == (0, "", "")


def test_no_dormant_hint_when_the_repo_enabled_it(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"enabledPlugins": {"hf-picks@x": False}}), encoding="utf-8"
    )
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude/settings.local.json").write_text(
        json.dumps({"enabledPlugins": {"hf-picks@x": True}}), encoding="utf-8"
    )
    env = {**env_for(), "COACH_SETTINGS": str(settings), "TMPDIR": str(tmp_path)}
    out = run(
        [*PY, str(HOOKS / "coach_prompt.py")],
        {"prompt": "upload to hugging face", "session_id": "s", "cwd": str(repo)},
        env=env,
    )[1]
    assert out == ""


def test_no_dormant_hint_when_plugin_on(dormant_env):
    assert coach(EVAL_ASK, dormant_env(True)) == (0, "", "")


def test_no_dormant_hint_inside_paste(dormant_env):
    prompt = f'look <pasted_content id="a">{EVAL_ASK}</pasted_content id="a">'
    assert coach(prompt, dormant_env(False)) == (0, "", "")


def test_no_dormant_hint_on_task_notification(dormant_env):
    assert coach("<task-notification>" + EVAL_ASK, dormant_env(False)) == (0, "", "")


def test_dormant_hint_once_per_session(dormant_env):
    env = dormant_env(False)
    assert "Dormant" in coach(EVAL_ASK, env)[1]
    assert coach(EVAL_ASK, env)[1] == ""
    assert "Dormant" in coach(EVAL_ASK, env, session="s2")[1]


def test_coach_tip_and_dormant_hint_together(dormant_env):
    _, out, _ = coach("just quickly " + EVAL_ASK, dormant_env(False))
    assert "Coach:" in out and "Dormant:" in out


def test_dormant_quiet_without_settings_file(tmp_path):
    env = {
        **os.environ,
        "COACH_SETTINGS": str(tmp_path / "missing.json"),
        "TMPDIR": str(tmp_path),
    }
    assert coach(EVAL_ASK, env) == (0, "", "")
