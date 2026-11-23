"""The scripts in scripts/ and claude/statusline.sh, run for real on stubs and a fake home.

No script here touches the real home folder or the network: curl, brew, age, defaults and
osascript are stubs on PATH, and HOME is a temp folder.
"""

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from hookrun import ROOT

SCRIPTS = ROOT / "scripts"
BASH = shutil.which("bash") or "bash"
pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the stubs are shell scripts"
)


def stub(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)
    return path


def sh(args, env=None, cwd=None, stdin=None):
    p = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        input=stdin,
        check=False,
        timeout=120,
    )
    return p.returncode, p.stdout + p.stderr


def all_shell_scripts():
    found = sorted(SCRIPTS.glob("*.sh"))
    found += [ROOT / "install.sh", ROOT / "claude" / "statusline.sh"]
    return found


# ── every script ────────────────────────────────────────────────────────────
def test_the_expected_scripts_exist():
    names = {p.name for p in SCRIPTS.iterdir()}
    for name in (
        "backup-home.sh", "macos-defaults.sh", "make-bundle.sh", "import-bundle.sh",
        "skill-zip.sh", "install-jena.sh", "install-jena.ps1", "bench-shell.sh",
        "check-package-names.sh", "ci-local.sh",
    ):  # fmt: skip
        assert name in names, name
    assert not {"brew-work.sh", "check-brew-names.sh"} & names


@pytest.mark.parametrize("path", all_shell_scripts(), ids=lambda p: p.name)
def test_scripts_are_lf_with_a_bash_shebang(path):
    data = path.read_bytes()
    assert b"\r" not in data
    assert data.startswith(b"#!/usr/bin/env bash")


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="no shellcheck here")
def test_scripts_pass_shellcheck():
    code, out = sh(["shellcheck", "-S", "warning", *map(str, all_shell_scripts())])
    assert code == 0, out


# ── install-jena.sh ─────────────────────────────────────────────────────────
VERSION = "6.2.0"
ARCHIVE = f"apache-jena-{VERSION}.tar.gz"
TOOLS = ("riot", "sparql", "arq")
FAKE_CURL = """#!/bin/sh
echo "$*" >>"$CURL_LOG"
out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out=$2; shift ;;
    http*) url=$1 ;;
  esac
  shift
done
src="$FIXTURES/$(basename "$url")"
[ -f "$src" ] || { echo "curl: (22) 404 $url" >&2; exit 22; }
if [ -n "$out" ]; then cp "$src" "$out"; else cat "$src"; fi
"""


def jena_tarball():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for tool in TOOLS:
            body = f'#!/bin/sh\necho "Jena: VERSION: {VERSION} ({tool}) JAVA_HOME=$JAVA_HOME"\n'.encode()
            info = tarfile.TarInfo(f"apache-jena-{VERSION}/bin/{tool}")
            info.size, info.mode = len(body), 0o755
            tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


@pytest.fixture
def jena(tmp_path):
    bin_dir, fixtures, home, tmp = (
        tmp_path / d for d in ("stubs", "fixtures", "home", "tmp")
    )
    for d in (fixtures, home, tmp):
        d.mkdir()
    stub(bin_dir / "curl", FAKE_CURL)
    java = stub(tmp_path / "java_home", f"#!/bin/sh\necho {tmp_path / 'jdk'}\n")
    archive = jena_tarball()
    (fixtures / ARCHIVE).write_bytes(archive)
    (fixtures / f"{ARCHIVE}.sha512").write_text(
        f"{hashlib.sha512(archive).hexdigest()}  {ARCHIVE}\n"
    )
    return {
        **{k: v for k, v in os.environ.items() if k not in ("JAVA_HOME", "CURL_LOG")},
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "FIXTURES": str(fixtures),
        "CURL_LOG": str(tmp_path / "curl.log"),
        "JAVA_HOME_CMD": str(java),
    }


def jena_run(env, *args):
    return sh([BASH, str(SCRIPTS / "install-jena.sh"), *args], env=env)


def jena_installed(env):
    home = Path(env["HOME"])
    share = home / ".local/share"
    folders = list(share.glob("jena-*")) if share.exists() else []
    return folders, [t for t in TOOLS if (home / ".local/bin" / t).exists()]


def test_jena_install_puts_working_wrappers_on_bin(jena):
    code, out = jena_run(jena)
    assert code == 0, out
    for tool in TOOLS:
        wrapper = Path(jena["HOME"]) / ".local/bin" / tool
        assert os.access(wrapper, os.X_OK), tool
        assert jena["JAVA_HOME_CMD"] in wrapper.read_text()
    assert f"VERSION: {VERSION}" in out


def test_jena_dry_run_writes_and_downloads_nothing(jena):
    code, out = jena_run(jena, "--dry-run")
    assert code == 0, out
    assert ARCHIVE in out and ".local/share/jena-" in out
    assert not os.path.exists(jena["CURL_LOG"])
    assert jena_installed(jena) == ([], [])


def test_jena_checksum_mismatch_installs_nothing(jena):
    sha = Path(jena["FIXTURES"], f"{ARCHIVE}.sha512")
    sha.write_text("0" * 128 + "\n")
    code, out = jena_run(jena)
    assert code == 1 and "Checksum mismatch" in out
    assert jena_installed(jena) == ([], [])


def test_jena_without_java_stops_before_the_download(jena, tmp_path):
    jena["JAVA_HOME_CMD"] = str(stub(tmp_path / "no_java", "#!/bin/sh\nexit 1\n"))
    code, out = jena_run(jena)
    assert code == 1 and "No Java" in out
    assert not os.path.exists(jena["CURL_LOG"])


@pytest.mark.parametrize(
    "bad", [["latest"], ["6.2"], ["6.2.0/../../x"], ["--force"], ["6.2.0", "6.1.0"]]
)
def test_jena_bad_version_is_refused_with_usage(jena, bad):
    code, out = jena_run(jena, *bad)
    assert code == 2 and "Usage" in out
    assert not os.path.exists(jena["CURL_LOG"])


def test_jena_unreachable_download_says_what_failed(jena):
    Path(jena["FIXTURES"], ARCHIVE).unlink()
    code, out = jena_run(jena)
    assert code == 1 and "Download failed" in out and ARCHIVE in out
    assert jena_installed(jena) == ([], [])


def test_jena_broken_archive_leaves_no_partial_install(jena):
    junk = b"not a tarball"
    Path(jena["FIXTURES"], ARCHIVE).write_bytes(junk)
    Path(jena["FIXTURES"], f"{ARCHIVE}.sha512").write_text(
        hashlib.sha512(junk).hexdigest() + "\n"
    )
    code, out = jena_run(jena)
    assert code != 0, out
    assert jena_installed(jena) == ([], [])


def test_jena_wrapper_finds_java_in_a_path_with_spaces(jena, tmp_path):
    spaced = tmp_path / "Java Tools"
    jena["JAVA_HOME_CMD"] = str(
        stub(spaced / "java_home", f"#!/bin/sh\necho {tmp_path / 'jdk'}\n")
    )
    code, out = jena_run(jena)
    assert code == 0, out
    assert f"JAVA_HOME={tmp_path / 'jdk'}" in out


def test_jena_failed_swap_keeps_the_old_install(jena):
    old = Path(jena["HOME"], f".local/share/jena-{VERSION}")
    old.mkdir(parents=True)
    (old / "marker").write_text("old install")
    stubs = jena["PATH"].split(":")[0]
    stub(
        Path(stubs, "mv"),
        '#!/bin/sh\ncase "$1" in */stage) exit 1 ;; esac\nexec /bin/mv "$@"\n',
    )
    code, out = jena_run(jena)
    assert code == 1, out
    assert (old / "marker").read_text() == "old install"


def test_jena_has_a_windows_script_that_checks_the_download():
    text = (SCRIPTS / "install-jena.ps1").read_text(encoding="utf-8")
    for needle in ("LOCALAPPDATA", "winget", "Temurin", "sha512", "Get-FileHash"):
        assert needle.lower() in text.lower(), needle


# ── bench-shell.sh ──────────────────────────────────────────────────────────
@pytest.fixture
def fake_zsh(tmp_path):
    d = tmp_path / "fakebin"
    stub(d / "zsh", "#!/bin/sh\nsleep 0.02\n")
    return {**os.environ, "PATH": f"{d}:/usr/bin:/bin"}


@pytest.mark.skipif(not shutil.which("perl"), reason="no perl here")
def test_bench_prints_a_median_line(fake_zsh):
    code, out = sh([BASH, str(SCRIPTS / "bench-shell.sh")], env=fake_zsh)
    m = re.fullmatch(r"shell start: (\d+) ms \(median of 5\)\n", out)
    assert code == 0 and m and 15 <= int(m.group(1)) < 2000, out


@pytest.mark.skipif(not shutil.which("perl"), reason="no perl here")
def test_bench_json(fake_zsh):
    data = json.loads(
        sh([BASH, str(SCRIPTS / "bench-shell.sh"), "--json"], env=fake_zsh)[1]
    )
    assert data["runs"] == 5 and data["median_ms"] >= 15


def test_bench_bad_option_exits_with_a_message(fake_zsh):
    code, out = sh([BASH, str(SCRIPTS / "bench-shell.sh"), "--nope"], env=fake_zsh)
    assert code != 0 and out.strip() and "Traceback" not in out


# ── ci-local.sh ─────────────────────────────────────────────────────────────
TEST_YML = ROOT / ".github" / "workflows" / "test.yml"
CI_LOCAL = SCRIPTS / "ci-local.sh"


def yml_checks():
    """The one-line `run:` steps of test.yml."""
    out = []
    for line in TEST_YML.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s+(?:- )?run:\s*(.+?)\s*$", line)
        if m:
            out.append(m.group(1))
    return out


def test_ci_local_runs_every_test_yml_check():
    text = CI_LOCAL.read_text(encoding="utf-8")
    checks = yml_checks()
    assert len(checks) >= 4, checks
    quoted = ['"' + c.replace('"', '\\"') + '"' for c in checks]  # inside a bash string
    missing = [c for c, q in zip(checks, quoted) if q not in text]
    assert not missing, f"scripts/ci-local.sh does not run: {missing}"


def test_ci_local_names_a_temp_file_failure_not_a_check(tmp_path):
    code, out = sh(
        [BASH, str(CI_LOCAL)], env={**os.environ, "TMPDIR": str(tmp_path / "missing")}
    )
    assert code != 0
    assert "temp file" in out and "ruff" not in out and "pin" not in out


def test_ci_local_warns_when_local_ruff_differs_from_the_ci_pin(tmp_path):
    stub(tmp_path / "ruff", "#!/bin/sh\necho 'ruff 0.0.1'\n")
    _, out = sh(
        [
            BASH,
            "-c",
            f'eval "$(sed -n "/^ruff_pin_check()/,/^}}/p" {CI_LOCAL})"; ruff_pin_check',
        ],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        cwd=ROOT,
    )
    assert "0.0.1" in out and "test.yml" in out


# ── macos-defaults.sh ───────────────────────────────────────────────────────
def test_macos_defaults_refuses_without_the_flag_the_installer_sets(tmp_path):
    code, out = sh(
        [BASH, str(SCRIPTS / "macos-defaults.sh")],
        env={**os.environ, "HOME": str(tmp_path), "DOTFILES_MACOS_OK": ""},
    )
    assert code == 1 and "install.py" in out


def test_macos_defaults_saves_each_domain_before_it_writes(tmp_path):
    log, bin_dir = tmp_path / "calls.log", tmp_path / "bin"
    for tool in ("defaults", "killall"):
        stub(bin_dir / tool, f'#!/bin/sh\necho "{tool} $*" >> {log}\n')
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "DOTFILES_MACOS_OK": "1",
    }
    code, out = sh([BASH, str(SCRIPTS / "macos-defaults.sh")], env=env)
    assert code == 0, out
    exported = set()
    for call in log.read_text().splitlines():
        words = call.split()
        if words[:2] == ["defaults", "export"]:
            exported.add(words[2])
        if words[:2] == ["defaults", "write"]:
            assert words[2] in exported, f"{words[2]} written before it was saved"
    assert "defaults import" in out  # says how to restore


# ── check-package-names.sh ──────────────────────────────────────────────────
def names_manifest(tmp_path, names):
    path = tmp_path / "m.json"
    pkgs = [
        {"name": n, "brew": n, "apt": n, "winget": f"Pub.{n}", "desc": "x"}
        for n in names
    ]
    path.write_text(
        json.dumps(
            {
                "groups": {"g": {"title": "g", "packages": pkgs}},
                "profiles": {"p": {"description": "p", "groups": ["g"]}},
            }
        )
    )
    return path


def names_env(tmp_path, tool="brew"):
    # The stub fails for a name that holds "bad", like a manager that does not know it
    stub(
        tmp_path / "bin" / tool,
        '#!/bin/sh\ncase "$*" in *bad*) exit 1 ;; esac\nexit 0\n',
    )
    return {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}


def test_check_names_passes_when_the_manager_knows_every_name(tmp_path):
    m = names_manifest(tmp_path, ["good", "fine"])
    code, out = sh(
        [BASH, str(SCRIPTS / "check-package-names.sh"), "brew", str(m)],
        env=names_env(tmp_path),
    )
    assert code == 0 and "known" in out, out


def test_check_names_names_the_unknown_package(tmp_path):
    m = names_manifest(tmp_path, ["good", "badone"])
    code, out = sh(
        [BASH, str(SCRIPTS / "check-package-names.sh"), "brew", str(m)],
        env=names_env(tmp_path),
    )
    assert (
        code == 1
        and 'unknown brew "badone"' in out
        and "good" not in out.split("unknown")[-1]
    )


def test_check_names_works_for_the_real_manifest_with_a_stub_brew(tmp_path):
    code, out = sh(
        [BASH, str(SCRIPTS / "check-package-names.sh"), "brew"], env=names_env(tmp_path)
    )
    assert code == 0, out


def test_check_names_refuses_an_unknown_manager(tmp_path):
    code, out = sh([BASH, str(SCRIPTS / "check-package-names.sh"), "pip"])
    assert code == 2 and "brew" in out and "winget" in out


# ── make-bundle.sh and import-bundle.sh ─────────────────────────────────────
def git(repo, *args, check=True):
    p = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            *args,
        ],
        capture_output=True,
        text=True,
        check=check,
    )
    return p.stdout.strip()


def make_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "scripts").mkdir()
    for name in ("make-bundle.sh", "import-bundle.sh"):
        shutil.copy(SCRIPTS / name, path / "scripts" / name)
    (path / "a.txt").write_text("one\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "first")
    return path


def test_make_bundle_writes_a_verifiable_bundle(tmp_path):
    repo = make_repo(tmp_path / "repo")
    out = tmp_path / "x.bundle"
    code, text = sh([BASH, str(repo / "scripts" / "make-bundle.sh"), str(out)])
    assert code == 0, text
    verify = subprocess.run(
        ["git", "-C", str(repo), "bundle", "verify", "-q", str(out)],
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 0
    assert str(out) in text


def import_env(tmp_path, dot, downloads):
    bin_dir = tmp_path / "stubs"
    stub(bin_dir / "osascript", "#!/bin/sh\nexit 0\n")  # no real notification
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOTFILES": str(dot),
        "DOWNLOADS": str(downloads),
        "TMPDIR": str(tmp_path),
        "DOTFILES_IMPORT_YES": "1",
    }


def bundle_scene(tmp_path):
    source = make_repo(tmp_path / "source")
    target = tmp_path / "target"
    git(tmp_path, "clone", "-q", str(source), str(target))
    git(target, "remote", "remove", "origin")
    (source / "a.txt").write_text("two\n")
    git(source, "commit", "-qam", "second")
    downloads = tmp_path / "dl"
    downloads.mkdir()
    sh(
        [
            BASH,
            str(source / "scripts" / "make-bundle.sh"),
            str(downloads / "dotfiles.bundle"),
        ]
    )
    return source, target, downloads


def test_import_bundle_fast_forwards_main_and_removes_the_bundle(tmp_path):
    _, target, downloads = bundle_scene(tmp_path)
    code, out = sh(
        [BASH, str(target / "scripts" / "import-bundle.sh")],
        env=import_env(tmp_path, target, downloads),
    )
    assert code == 0, out
    assert (target / "a.txt").read_text() == "two\n"
    assert not list(downloads.glob("*.bundle"))


def test_import_bundle_stops_on_a_dirty_repo_and_keeps_the_bundle(tmp_path):
    _, target, downloads = bundle_scene(tmp_path)
    (target / "a.txt").write_text("mine\n")
    code, out = sh(
        [BASH, str(target / "scripts" / "import-bundle.sh")],
        env=import_env(tmp_path, target, downloads),
    )
    assert code == 1 and "uncommitted" in out
    assert list(downloads.glob("*.bundle"))
    assert (target / "a.txt").read_text() == "mine\n"


def test_import_bundle_asks_before_it_changes_anything_without_a_terminal(tmp_path):
    _, target, downloads = bundle_scene(tmp_path)
    env = import_env(tmp_path, target, downloads)
    env.pop("DOTFILES_IMPORT_YES")
    code, out = sh(
        [BASH, str(target / "scripts" / "import-bundle.sh")], env=env, stdin=""
    )
    assert code == 1 and "no terminal" in out
    assert (target / "a.txt").read_text() == "one\n"


# ── skill-zip.sh ────────────────────────────────────────────────────────────
def skill_scene(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for name in ("skill-zip.sh", "skill_zip.py"):
        shutil.copy(SCRIPTS / name, root / "scripts" / name)
    skill = root / "claude" / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n")
    (skill / ".DS_Store").write_text("x")
    return root


def test_skill_zip_packs_one_skill_without_junk_files(tmp_path):
    root = skill_scene(tmp_path)
    out = tmp_path / "demo.zip"
    code, text = sh([BASH, str(root / "scripts" / "skill-zip.sh"), "demo", str(out)])
    assert code == 0, text
    assert zipfile.ZipFile(out).namelist() == ["demo/SKILL.md"]


def test_skill_zip_names_a_missing_skill(tmp_path):
    root = skill_scene(tmp_path)
    code, text = sh([BASH, str(root / "scripts" / "skill-zip.sh"), "nope"])
    assert code == 1 and "No skill nope" in text and "Traceback" not in text


# ── backup-home.sh ──────────────────────────────────────────────────────────
FAKE_AGE = """#!/bin/sh
# age -R <recipients> -o <out>: keep stdin as the "encrypted" file
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift ;; esac; shift; done
cat > "$out"
"""


def backup_scene(tmp_path, with_recipients=True):
    home, dest, bin_dir = tmp_path / "home", tmp_path / "dest", tmp_path / "bin"
    for d in (home / "docs", home / "node_modules", home / ".cache", dest):
        d.mkdir(parents=True)
    (home / "docs" / "a.txt").write_text("keep")
    (home / "node_modules" / "b.js").write_text("skip")
    (home / ".cache" / "c").write_text("skip")
    stub(bin_dir / "age", FAKE_AGE)
    recipients = tmp_path / "recipients.txt"
    if with_recipients:
        recipients.write_text("age1examplepublickey\n")
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "BACKUP_AGE_RECIPIENTS": str(recipients),
    }
    return dest, env


def test_backup_home_archives_the_listed_files_and_counts_them(tmp_path):
    dest, env = backup_scene(tmp_path)
    code, out = sh([BASH, str(SCRIPTS / "backup-home.sh"), str(dest)], env=env)
    assert code == 0, out
    (folder,) = dest.iterdir()
    members = subprocess.run(
        ["tar", "-tzf", str(folder / "home.tar.gz.age")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert "./docs/a.txt" in members
    assert not [m for m in members if "node_modules" in m or ".cache" in m]
    assert "README.md" in {p.name for p in folder.iterdir()}


def test_backup_home_refuses_to_run_without_a_recipient_file(tmp_path):
    dest, env = backup_scene(tmp_path, with_recipients=False)
    code, out = sh([BASH, str(SCRIPTS / "backup-home.sh"), str(dest)], env=env)
    assert code == 1 and "No age recipient" in out
    assert list(dest.iterdir()) == []


# ── claude/statusline.sh ────────────────────────────────────────────────────
STATUS = ROOT / "claude" / "statusline.sh"


@pytest.mark.skipif(not shutil.which("jq"), reason="no jq here")
def test_statusline_shows_model_context_and_cost(tmp_path):
    payload = {
        "model": {"display_name": "Opus"},
        "context_window": {"used_percentage": 42.7},
        "cost": {"total_cost_usd": 1.234},
        "workspace": {"current_dir": str(tmp_path)},
    }
    code, out = sh([BASH, str(STATUS)], stdin=json.dumps(payload))
    assert code == 0 and out.strip() == "Opus · ctx 42% · $1.23", out


def test_statusline_without_a_working_jq_still_prints_a_line(tmp_path):
    stub(tmp_path / "bin" / "jq", "#!/bin/sh\nexit 1\n")
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}
    code, out = sh([BASH, str(STATUS)], env=env, stdin="{}")
    assert code == 0 and out.strip().startswith("Claude")


def test_statusline_writes_no_file_outside_a_temp_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    sh([BASH, str(STATUS)], env={**os.environ, "HOME": str(home)}, stdin="{}")
    assert list(home.iterdir()) == []
