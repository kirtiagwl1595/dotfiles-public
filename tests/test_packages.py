"""The package manifest, and the install.py step that installs from it.

Every install runs a stub manager on PATH. Nothing here installs a real package.
"""

import json
import os
import re
import subprocess
import sys

import pytest
from hookrun import ROOT, env_for
from installrun import WIN, calls, fake_managers, home_of, run_install

MANIFEST = ROOT / "packages" / "packages.json"
WINGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][\w+-]*)+$")
BREW_NAME = re.compile(r"^(cask:)?[a-z0-9][a-z0-9@._+-]*$")
APT_NAME = re.compile(r"^[a-z0-9][a-z0-9.+-]+$")
MANAGERS = ("brew", "apt", "winget")
PROFILES = ("minimal", "developer", "full", "work")


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def all_packages(manifest):
    return [
        (group, pkg)
        for group, spec in manifest["groups"].items()
        for pkg in spec["packages"]
    ]


# ── manifest ────────────────────────────────────────────────────────────────
def test_every_package_has_a_name_and_a_manager(manifest):
    for group, pkg in all_packages(manifest):
        assert pkg.get("name"), (group, pkg)
        assert any(pkg.get(m) for m in MANAGERS), f"{pkg['name']} has no manager"
        assert set(pkg) <= {"name", "desc", "note", *MANAGERS}, pkg


def test_a_missing_manager_is_null_and_says_why(manifest):
    for _, pkg in all_packages(manifest):
        for manager in MANAGERS:
            assert manager in pkg, f"{pkg['name']}: write {manager} or null"
        if any(pkg[m] is None for m in MANAGERS):
            assert pkg.get("note"), f"{pkg['name']} has a null manager and no note"


def test_package_names_follow_each_manager_rules(manifest):
    for _, pkg in all_packages(manifest):
        if pkg["winget"]:
            assert WINGET_ID.match(pkg["winget"]), pkg["winget"]
        if pkg["brew"]:
            assert BREW_NAME.match(pkg["brew"]), pkg["brew"]
        if pkg["apt"]:
            assert APT_NAME.match(pkg["apt"]), pkg["apt"]


def test_a_package_is_in_one_group_only(manifest):
    names = [pkg["name"] for _, pkg in all_packages(manifest)]
    assert len(names) == len(set(names))


def test_every_profile_names_existing_groups(manifest):
    assert set(PROFILES) <= set(manifest["profiles"])
    for name, spec in manifest["profiles"].items():
        assert spec["description"], name
        assert spec["groups"] or spec.get("extends"), name
        assert set(spec["groups"]) <= set(manifest["groups"]), name
        if "extends" in spec:
            assert spec["extends"] in manifest["profiles"], name


def test_every_group_is_used_by_a_profile(manifest):
    used = {g for spec in manifest["profiles"].values() for g in spec["groups"]}
    assert used == set(manifest["groups"])


def test_minimal_has_the_basic_tools(manifest):
    names = {
        pkg["name"]
        for g, pkg in all_packages(manifest)
        if g in manifest["profiles"]["minimal"]["groups"]
    }
    assert {"git", "gh", "uv", "starship"} <= names


# ── --check: the plan, no change, no prompt ─────────────────────────────────
def test_check_with_closed_stdin_prints_the_plan_and_returns(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew", "winget", "apt-get", "sudo")
    code, out = run_install(home, "--check", bin_dir=bin_dir)
    assert code == 0, out
    assert "Packages" in out
    for profile in PROFILES:
        assert profile in out
    assert calls(tmp_path) == []
    assert not (home / ".claude").exists() and not (home / ".gitconfig").exists()


def test_check_with_a_profile_lists_each_group_and_installs_nothing(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home, "--check", "--profile", "developer", "--manager", "brew", bin_dir=bin_dir
    )
    assert code == 0, out
    for group in ("essentials", "core-cli", "shell", "fonts"):
        assert group in out
    assert "git-lfs" in out
    assert calls(tmp_path) == []


def test_an_unknown_profile_is_refused_with_a_message(tmp_path):
    code, out = run_install(home_of(tmp_path), "--profile", "nope")
    assert code != 0
    assert "minimal" in out and "Traceback" not in out


# ── no terminal: every prompt takes the default, No ─────────────────────────
def test_no_terminal_means_no_install(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home, "--profile", "developer", "--manager", "brew", bin_dir=bin_dir
    )
    assert code == 0, out
    assert "Install essentials (" in out and "[y/N]" in out
    assert calls(tmp_path) == []


def test_the_menu_alone_with_closed_stdin_skips(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home, "--manager", "brew", "--yes-packages", bin_dir=bin_dir
    )
    assert code == 0, out
    assert calls(tmp_path) == []


# ── installing: brew ────────────────────────────────────────────────────────
def test_menu_number_picks_a_profile_and_y_installs_the_group(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home,
        "--manager",
        "brew",
        "--only",
        "packages",
        answers="1\ny\n",
        bin_dir=bin_dir,
    )
    assert code == 0, out
    assert "Install essentials (5 packages)? [y/N]" in out
    (line,) = calls(tmp_path)
    assert line.split()[:2] == ["brew", "install"]
    assert {"git", "gh", "uv", "starship", "jq"} <= set(line.split())


def test_n_installs_nothing(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home,
        "--manager",
        "brew",
        "--only",
        "packages",
        answers="1\nn\n",
        bin_dir=bin_dir,
    )
    assert code == 0, out
    assert calls(tmp_path) == []


def test_a_profile_can_be_named_not_numbered(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home,
        "--manager",
        "brew",
        "--only",
        "packages",
        answers="minimal\ny\n",
        bin_dir=bin_dir,
    )
    assert code == 0, out
    assert len(calls(tmp_path)) == 1


def test_a_cask_is_installed_with_the_cask_flag(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home,
        "--manager", "brew", "--profile", "developer", "--yes-packages",
        "--only", "packages", answers="", bin_dir=bin_dir,
    )  # fmt: skip
    assert code == 0, out
    casks = [c for c in calls(tmp_path) if "--cask" in c]
    assert any("font-jetbrains-mono-nerd-font" in c for c in casks)
    assert all("cask:" not in c for c in calls(tmp_path))


def test_a_failed_batch_is_retried_one_package_at_a_time(tmp_path):
    if WIN:
        pytest.skip("the failing stub is a shell script")
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home,
        "--manager", "brew", "--profile", "minimal", "--yes-packages",
        "--only", "packages", answers="", bin_dir=bin_dir,
        extra_env={"FAKE_FAIL": "starship"},
    )  # fmt: skip
    assert code == 1
    assert "FAILED" in out and "starship" in out
    singles = [c for c in calls(tmp_path) if len(c.split()) == 3]
    assert "brew install git" in singles and "brew install gh" in singles


def test_an_explicit_profile_with_no_manager_is_an_error(tmp_path):
    home = home_of(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    code, out = run_install(
        home, "--manager", "brew", "--profile", "minimal", "--yes-packages",
        "--only", "packages", answers="", bin_dir=empty, only_bin=True,
    )  # fmt: skip
    assert code != 0
    assert "brew" in out and "not found" in out and "Traceback" not in out


def test_no_manager_and_no_profile_is_a_message_not_an_error(tmp_path):
    home = home_of(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    code, out = run_install(
        home, "--manager", "brew", "--only", "packages", answers="",
        bin_dir=empty, only_bin=True,
    )  # fmt: skip
    assert code == 0 and "not found" in out


def test_a_menu_skip_exits_zero(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = run_install(
        home, "--manager", "brew", "--only", "packages", answers="0\n", bin_dir=bin_dir
    )
    assert code == 0, out
    assert calls(tmp_path) == []


# ── installing: apt-get and winget ──────────────────────────────────────────
@pytest.mark.skipif(WIN, reason="apt-get needs a Unix shell stub")
def test_apt_installs_only_the_packages_that_apt_has(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "apt-get", "sudo")
    code, out = run_install(
        home, "--manager", "apt", "--profile", "minimal", "--yes-packages",
        "--only", "packages", answers="", bin_dir=bin_dir,
    )  # fmt: skip
    assert code == 0, out
    update, line = calls(tmp_path)
    assert "apt-get update" in update
    assert "apt-get install -y" in line
    assert "git" in line.split() and "starship" not in line.split()
    assert "starship" in out and "no apt package" in out


def test_winget_gets_one_exact_id_per_call_with_the_agreements(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "winget")
    code, out = run_install(
        home, "--manager", "winget", "--profile", "minimal", "--yes-packages",
        "--only", "packages", answers="", bin_dir=bin_dir,
    )  # fmt: skip
    assert code == 0, out
    got = calls(tmp_path)
    assert len(got) == 5
    first = got[0].split()
    assert first[:3] == ["winget", "install", "--id"]
    for flag in (
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ):
        assert flag in first
    assert any("Git.Git" in c for c in got)


def test_winget_shows_a_package_with_no_winget_id_and_why(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "winget")
    code, out = run_install(
        home,
        "--check",
        "--profile",
        "developer",
        "--manager",
        "winget",
        bin_dir=bin_dir,
    )
    assert code == 0, out
    assert "zsh-autosuggestions" in out and "no winget package" in out


# ── local packages: pkg add / keep ──────────────────────────────────────────
def pkg(tmp_path, *args, **kw):
    home = home_of(tmp_path)
    cmd = [sys.executable, str(ROOT / "install.py"), "pkg", *args]
    env = env_for(home=home)
    env["FAKE_LOG"] = str(tmp_path / "fake.log")
    env["DOTFILES_PACKAGES_DIR"] = str(tmp_path / "pkgdir")
    env["PATH"] = str(kw["bin_dir"]) + os.pathsep + env["PATH"]
    p = subprocess.run(
        cmd, capture_output=True, text=True, env=env, check=False, timeout=60,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip
    return p.returncode, p.stdout + p.stderr


def test_pkg_add_installs_and_records_a_trial(tmp_path):
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = pkg(tmp_path, "add", "--manager", "brew", "cowsay", bin_dir=bin_dir)
    assert code == 0, out
    assert calls(tmp_path) == ["brew install cowsay"]
    trials = json.loads(
        (tmp_path / "pkgdir" / "trials.json").read_text(encoding="utf-8")
    )
    assert [t["name"] for t in trials["packages"]] == ["cowsay"]
    code, out = pkg(tmp_path, "list", bin_dir=bin_dir)
    assert "cowsay" in out


def test_pkg_add_refuses_a_url_or_a_tap(tmp_path):
    bin_dir = fake_managers(tmp_path, "brew")
    for bad in ("https://x.example/a", "owner/tap/name", "a b", "../x"):
        code, out = pkg(tmp_path, "add", "--manager", "brew", bad, bin_dir=bin_dir)
        assert code == 2, bad
        assert "plain package name" in out
    assert calls(tmp_path) == []


def test_pkg_keep_moves_the_trial_into_the_local_file(tmp_path):
    bin_dir = fake_managers(tmp_path, "brew")
    pkg(tmp_path, "add", "--manager", "brew", "cowsay", bin_dir=bin_dir)
    code, out = pkg(tmp_path, "keep", "cowsay", bin_dir=bin_dir)
    assert code == 0, out
    pkgdir = tmp_path / "pkgdir"
    local = json.loads((pkgdir / "local.json").read_text(encoding="utf-8"))
    assert local["packages"][0]["brew"] == "cowsay"
    assert (
        json.loads((pkgdir / "trials.json").read_text(encoding="utf-8"))["packages"]
        == []
    )


def test_pkg_keep_of_a_name_that_is_not_a_trial_fails_with_a_message(tmp_path):
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = pkg(tmp_path, "keep", "cowsay", bin_dir=bin_dir)
    assert code == 1 and "not a trial" in out and "Traceback" not in out


def test_a_kept_package_shows_up_as_the_local_group(tmp_path):
    bin_dir = fake_managers(tmp_path, "brew")
    pkg(tmp_path, "add", "--manager", "brew", "cowsay", bin_dir=bin_dir)
    pkg(tmp_path, "keep", "cowsay", bin_dir=bin_dir)
    home = home_of(tmp_path)
    code, out = run_install(
        home, "--check", "--profile", "minimal", "--manager", "brew", bin_dir=bin_dir
    )
    assert code == 0, out
    assert "local" in out and "cowsay" in out


def test_pkg_brewfile_is_generated_from_the_manifest(tmp_path):
    bin_dir = fake_managers(tmp_path, "brew")
    code, out = pkg(tmp_path, "brewfile", "developer", bin_dir=bin_dir)
    assert code == 0, out
    assert 'brew "git"' in out and 'cask "font-jetbrains-mono-nerd-font"' in out
    assert "winget" not in out.lower()


# ── apt: refresh the package index once, after the yes ──────────────────────
@pytest.mark.skipif(WIN, reason="apt-get needs a Unix shell stub")
def test_apt_updates_the_index_once_before_the_first_install(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "apt-get", "sudo")
    code, out = run_install(
        home, "--manager", "apt", "--profile", "developer", "--yes-packages",
        "--only", "packages", answers="", bin_dir=bin_dir,
    )  # fmt: skip
    assert code == 0, out
    got = calls(tmp_path)
    updates = [i for i, c in enumerate(got) if "apt-get update" in c]
    installs = [i for i, c in enumerate(got) if "apt-get install" in c]
    assert len(updates) == 1 and len(installs) >= 2
    assert updates[0] < min(installs)


@pytest.mark.skipif(WIN, reason="apt-get needs a Unix shell stub")
def test_apt_does_not_update_when_the_answer_is_no(tmp_path):
    home = home_of(tmp_path)
    bin_dir = fake_managers(tmp_path, "apt-get", "sudo")
    code, out = run_install(
        home,
        "--manager",
        "apt",
        "--only",
        "packages",
        answers="1\nn\n",
        bin_dir=bin_dir,
    )
    assert code == 0, out
    assert calls(tmp_path) == []
