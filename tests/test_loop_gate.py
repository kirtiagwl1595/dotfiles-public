"""loop_gate: the diff gate rejects band-aids and weakened checks (§15)."""

import json
import os
import shutil
import subprocess

import pytest
from loop_fixtures import (
    CLAUDE,
    LOOP_MARKS,
    git,
    machine_free_git,  # noqa: F401 - an autouse fixture
    python,
)

pytestmark = LOOP_MARKS

GATE = CLAUDE / "loop_gate.py"
SETUP = "refs/loop/setup"  # a plain ref: git config may sign every tag

BASE_FILES = {
    "app.py": "def parse(x):\n    return x.strip()\n",
    "tests/test_app.py": "def test_ticket():\n    assert parse(' ticket-41 ') == 'ticket-41'\n",
    "lib.py": "\n".join(f"line_{i} = {i}" for i in range(10)) + "\n",
    "run.py": "import subprocess\nsubprocess.run(['x'], timeout=5)\n",
    "skills/x/SKILL.md": "# x\n\nOne rule.\n",
    "README.md": "# demo\n",
}


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@example.com")
    for rel, text in BASE_FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fork point")
    # As confirm makes it: commit #0 (setup) on the fork point is the loop's base
    git(root, "commit", "-q", "--allow-empty", "-m", "setup")
    git(root, "update-ref", SETUP, "HEAD")
    return root


def change(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "change")


def setup_commit(root, files):
    """Make these files the content of the setup commit: the setup ref moves to it."""
    change(root, files)
    git(root, "update-ref", SETUP, "HEAD")


def gate(root, *extra, env=None):
    base = git(root, "rev-parse", SETUP)
    p = subprocess.run(
        [python(), "-B", str(GATE), "--root", str(root), "--base", base, *extra],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=root,  # as in the Stop hook: the worktree
    )
    report = json.loads(p.stdout.splitlines()[0]) if p.stdout.strip() else {}
    return p.returncode, report, p.stderr


def rules(report, kind="rejects"):
    return {f["rule"] for f in report.get(kind, [])}


APP = "def parse(x):\n"


@pytest.mark.parametrize(
    "rule, files",
    [
        (
            "special-case",
            {
                "app.py": APP
                + "    if x == 'ticket-41':\n        return 'ticket-41'\n    return x.strip()\n"
            },
        ),
        (
            "swallow",
            {
                "app.py": APP
                + "    try:\n        return x.strip()\n    except Exception: pass\n"
            },
        ),
        (
            "swallow",
            {
                "app.py": APP
                + "    try:\n        return x.strip()\n    except ValueError:\n        return None\n"
            },
        ),
        (
            "swallow",
            {
                "app.py": APP
                + "    try:\n        return x.strip()\n    except:\n        raise\n"
            },
        ),
        (
            "retry",
            {
                "app.py": APP
                + "    import time\n    time.sleep(2)\n    return x.strip()\n"
            },
        ),
        ("retry", {"run.py": "import subprocess\nsubprocess.run(['x'], timeout=60)\n"}),
        ("marker", {"app.py": APP + "    # HACK: strip twice\n    return x.strip()\n"}),
        (
            "operator",
            {
                "app.py": APP
                + "    return x.strip()\n\n\nclass P:\n    def __eq__(self, o):\n        return True\n"
            },
        ),
        (
            "monkeypatch",
            {"app.py": "import os\nos.environ['TZ'] = 'UTC'\n" + BASE_FILES["app.py"]},
        ),
        ("duplicate", {"other.py": BASE_FILES["lib.py"]}),
        ("protected", {"tests/test_app.py": "def test_ticket():\n    assert True\n"}),
        ("skill-growth", {"skills/x/SKILL.md": "# x\n\nOne rule.\nAnd one more.\n"}),
        ("secret", {"conf.py": "KEY = 'AKIA" + "ABCDEFGHIJKLMNOP'\n"}),
    ],
)
def test_each_reject_rule(repo, rule, files):
    change(repo, files)
    code, report, err = gate(repo)
    assert code == 1, err
    assert rule in rules(report), report


@pytest.mark.parametrize(
    "rule, files",
    [
        (
            "hard-coded",
            {"app.py": APP + "    return x.strip().replace('/Users/x', '')\n"},
        ),
        ("design", {f"m{i}.py": "x = 1\n" for i in range(4)}),
        ("design", {"app.py": "def parse_text(x):\n    return x.strip()\n"}),
    ],
)
def test_each_warn_rule(repo, rule, files):
    change(repo, files)
    code, report, _ = gate(repo)
    assert rule in rules(report, "warnings"), report
    assert code == 0


@pytest.mark.parametrize(
    ("gitleaks_exit", "scanner"),
    [(0, "gitleaks"), (2, "regex"), (None, "regex")],
)
def test_the_report_names_the_secret_scanner(repo, tmp_path, gitleaks_exit, scanner):
    """A regex pass must not look like a gitleaks pass: gitleaks may be missing or fail."""
    tools = tmp_path / "bin"
    tools.mkdir()
    if gitleaks_exit is not None:
        stub = tools / "gitleaks"
        stub.write_text(f"#!/bin/sh\nexit {gitleaks_exit}\n")
        stub.chmod(0o755)
    change(repo, {"conf.py": "x = 1\n"})
    env = {**os.environ, "PATH": f"{tools}:/usr/bin:/bin"}
    _, report, err = gate(repo, env=env)
    assert report["secret_scanner"] == scanner, err


FIXED_APP = "def parse(x):\n    return ' '.join(x.split())\n"
# Built at run time, so this file holds no key; gitleaks's aws-access-token rule finds it
AWS_KEY = "AKIA" + "QYLPMTMXQ7ABCDEF"


def gitleaks_found(report):
    """A secret finding of gitleaks itself: the regex fallback must not hide a bypass."""
    return any(
        f["rule"] == "secret" and "gitleaks" in f["text"] for f in report["rejects"]
    )


def allow_comment(repo):
    change(repo, {"conf.py": f'KEY = "{AWS_KEY}"  # gitleaks:allow\n'})


def allowlist_config(repo):
    change(
        repo,
        {
            ".gitleaks.toml": '[extend]\nuseDefault = true\n\n[allowlist]\npaths = ["conf.py"]\n',
            "conf.py": f'KEY = "{AWS_KEY}"\n',
        },
    )


def ignore_file(repo):
    change(repo, {"conf.py": f'KEY = "{AWS_KEY}"\n'})
    sha = git(repo, "rev-parse", "HEAD")
    (repo / ".gitleaksignore").write_text(f"{sha}:conf.py:aws-access-token:1\n")


@pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks is not installed")
@pytest.mark.parametrize("bypass", [allow_comment, allowlist_config, ignore_file])
def test_the_repo_cannot_switch_off_gitleaks(repo, bypass):
    # The agent writes the repo: its gitleaks config, ignore file and comments are not trusted
    bypass(repo)
    code, report, err = gate(repo)
    assert code == 1 and gitleaks_found(report), (report, err)
    assert report["secret_scanner"] == "gitleaks"


def test_a_stray_setup_file_is_rejected(repo):
    # Pilot 2: `add -A` put a shell here-document temp file into the setup commit
    setup_commit(
        repo,
        {"tests/test_new.py": "def test_new():\n    assert True\n", "sh-thd-1": ""},
    )
    change(repo, {"app.py": FIXED_APP})
    code, report, err = gate(repo, "--target", "app.py")
    assert code == 1, err
    found = [f for f in report["rejects"] if f["rule"] == "setup-file"]
    assert [f["file"] for f in found] == ["sh-thd-1"], report
    assert "sh-thd-1" in report["files"]


def test_a_secret_in_the_setup_commit_is_found(repo):
    setup_commit(repo, {"tests/test_keys.py": "KEY = 'AKIA" + "ABCDEFGHIJKLMNOP'\n"})
    change(repo, {"app.py": FIXED_APP})
    code, report, err = gate(repo)
    assert code == 1, err
    assert "secret" in rules(report), report


def test_setup_tests_and_the_target_verification_pass(repo):
    # The setup adds checks and the skill's ## Verification text: both by design
    setup_commit(
        repo,
        {
            "tests/test_new.py": "def test_new():\n    assert True\n",
            "skills/x/SKILL.md": "# x\n\nOne rule.\n\n## Verification\nThe eval.\n",
        },
    )
    change(repo, {"app.py": FIXED_APP})
    code, report, err = gate(repo, "--target", "skills/x/SKILL.md")
    assert (code, report["rejects"]) == (0, []), (report, err)
    assert "tests/test_new.py" in report["files"]


def test_pilot_shaped_fix_passes(repo):
    # The tests name the new flag and small numbers; a URL may say "temporary". None is a band-aid.
    git(repo, "rm", "-q", "tests/test_app.py")
    tests = "def test_dry_run():\n    out = run(['bash', 'x.sh', '--dry-run'])\n    assert len(out) > 3\n"
    change(repo, {"tests/test_x.py": tests})
    base = git(repo, "rev-parse", "HEAD")
    change(
        repo,
        {
            "x.sh": '#!/bin/bash\nif [[ "$1" == "--dry-run" ]]; then echo would download; exit 0; fi\n',
            "app.py": APP
            + "    if len(x) > 3:\n        return x.strip()\n    return x\n",
            "links.py": 'DOCS = "https://example.org/temporary-workaround"\n',
        },
    )
    p = subprocess.run(
        [python(), "-B", str(GATE), "--root", str(repo), "--base", base],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(p.stdout.splitlines()[0])
    assert report["rejects"] == [], report


def test_clean_root_cause_fix_passes(repo):
    fixed = "def parse(x):\n    return ' '.join(x.split())\n"
    change(repo, {"app.py": fixed})
    code, report, err = gate(repo)
    assert (code, report["verdict"]) == (0, "pass"), (report, err)
    assert report["rejects"] == [] and report["warnings"] == []


def test_markdown_markers_and_a_failing_baseline_skill_pass(repo):
    change(
        repo,
        {
            "README.md": "# demo\n\nA workaround for TODO lists.\n",
            "skills/x/SKILL.md": "# x\n\nOne rule.\nAnd one more.\n",
        },
    )
    code, report, _ = gate(repo, "--baseline-failed")
    assert code == 0, report


def test_approved_protected_path_passes(repo):
    change(repo, {"tests/test_app.py": "def test_ticket():\n    assert True\n"})
    _, report, _ = gate(repo, "--approved", "tests/test_app.py")
    assert "protected" not in rules(report)


def test_loop_folder_is_ignored(repo):
    change(repo, {".loop/notes.py": "except Exception: pass\n"})
    code, report, _ = gate(repo)
    assert code == 0, report


def test_bad_input_is_a_message(repo):
    p = subprocess.run(
        [python(), "-B", str(GATE), "--root", str(repo), "--base", "nope"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 2 and "Traceback" not in p.stderr
