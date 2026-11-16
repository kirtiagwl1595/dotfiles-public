"""claude/forge.sh: GitHub vs GitLab from the origin remote; PRs/MRs always on origin, never
upstream; no host stored in the repo; no Python needed."""

import os
import subprocess
from pathlib import Path

import pytest
from hookrun import ROOT, env_for
from test_launcher import bash_exe, stub_dir

FORGE = ROOT / "claude" / "forge.sh"
posix_only = pytest.mark.skipif(
    os.name == "nt", reason="hides gh and glab with PATH=/usr/bin:/bin"
)


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def forge(repo, *args, **extra):
    p = subprocess.run(
        [bash_exe(), str(FORGE), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env_for(**extra),
    )
    return p.returncode, p.stdout + p.stderr


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "checkout", "-q", "-b", "chore/x")
    return tmp_path


def body(tmp_path):
    f = tmp_path / "body.md"
    f.write_text("x", encoding="utf-8")
    return f.as_posix()


@pytest.mark.parametrize(
    "url, kind",
    [
        ("https://github.com/a/b.git", "github"),
        ("git@github.com:a/b.git", "github"),
        ("https://gitlab.com/a/b.git", "gitlab"),
        ("git@gitlab.example-corp.com:grp/sub/b.git", "gitlab"),
        ("ssh://git@gitlab.example-corp.com:2222/grp/b.git", "gitlab"),
    ],
)
def test_kind(repo, url, kind):
    git(repo, "remote", "add", "origin", url)
    assert forge(repo, "kind") == (0, kind + "\n")


@posix_only
def test_unknown_host_says_how_to_fix(repo):
    git(repo, "remote", "add", "origin", "https://git.example.org/a/b.git")
    code, out = forge(repo, "kind", PATH="/usr/bin:/bin")
    assert code == 1 and "glab auth login --hostname git.example.org" in out


def test_pr_on_origin_never_upstream(repo, tmp_path):
    git(repo, "remote", "add", "origin", "https://github.com/me/b.git")
    git(repo, "remote", "add", "upstream", "https://github.com/someone/b.git")
    code, out = forge(
        repo, "--dry-run", "pr-create", "--title", "T", "--body-file", body(tmp_path)
    )
    assert code == 0, out
    assert out.startswith("gh pr create -R me/b --head chore/x --base main")
    assert "someone" not in out


def test_mr_on_gitlab_deletes_the_source_branch(repo, tmp_path):
    git(repo, "remote", "add", "origin", "git@gitlab.example-corp.com:grp/sub/b.git")
    code, out = forge(
        repo, "--dry-run", "pr-create", "--title", "T", "--body-file", body(tmp_path)
    )
    assert code == 0, out
    assert out.startswith(
        "glab mr create --repo https://gitlab.example-corp.com/grp/sub/b --source-branch chore/x"
    )
    assert "--remove-source-branch" in out


@posix_only
def test_pr_create_on_unknown_host_stops(repo, tmp_path):
    git(repo, "remote", "add", "origin", "https://git.example.org/a/b.git")
    code, out = forge(
        repo,
        "--dry-run",
        "pr-create",
        "--title",
        "T",
        "--body-file",
        body(tmp_path),
        PATH="/usr/bin:/bin",
    )
    assert code == 1 and "glab mr" not in out and "gh pr" not in out


@posix_only
def test_auth_check_on_unknown_host_names_both_logins(tmp_path):
    code, out = forge(tmp_path, "auth-check", "git.example.org", PATH="/usr/bin:/bin")
    assert code == 1
    assert (
        "glab auth login --hostname git.example.org" in out and "gh auth login" in out
    )


def test_whoami_override_needs_no_network(tmp_path):
    assert forge(tmp_path, "whoami", "github.com", FORGE_GIT_USER="me") == (0, "me\n")


@posix_only
def test_whoami_reads_the_gitlab_username_without_python(tmp_path):
    json_out = '{\n  "id": 7,\n  "username": "me-on-gitlab",\n  "name": "x"\n}'
    stubs = stub_dir(tmp_path, glab=f"cat <<'EOF'\n{json_out}\nEOF")
    code, out = forge(tmp_path, "whoami", "gitlab.com", PATH=f"{stubs}:/usr/bin:/bin")
    assert (code, out) == (0, "me-on-gitlab\n")


def test_no_repo_create_and_no_python_in_forge():
    text = FORGE.read_text(encoding="utf-8")
    assert "repo-create" not in text
    # On Windows python3 can be the Microsoft Store stub: forge.sh calls no Python
    assert "python3" not in text and "python -c" not in text


def test_forge_has_unix_line_ends():
    assert b"\r\n" not in Path(FORGE).read_bytes()
