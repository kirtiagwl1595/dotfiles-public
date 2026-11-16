"""The doc rules in docs/README.md, checked on every doc in the repo."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
DATED = {
    "results",
    "plans",
    "research",
}  # dated records: never edited to match the code

CODE = re.compile(r"`([^`]+)`")
MODULE = re.compile(r"uv run python -m ([\w.]+)")
SCRIPT = re.compile(r"uv run python ([\w./-]+\.py)")
PATH = re.compile(r"^[\w.-]+(?:/[\w.-]+)+\.(?:py|md|ya?ml|toml|json|sh)$")
CITED = re.compile(r"((?:[\w-]+/)*[\w-]+\.md) §(\d+(?:\.\d+)?)")
BARE = re.compile(r"§(\d+(?:\.\d+)?)")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def doc_files():
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / line for line in out.stdout.splitlines()]


def is_living(path):
    return not (path.is_relative_to(DOCS) and DATED & set(path.relative_to(DOCS).parts))


def has_section(path, number):
    heading = re.compile(rf"^#{{2,3}} {re.escape(number)}[. ]", re.MULTILINE)
    return path.is_file() and bool(heading.search(path.read_text(encoding="utf-8")))


def module_exists(name):
    base = ROOT / "src" / Path(*name.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def test_doc_commands_point_to_real_code():
    missing = []
    for doc in doc_files():
        for snippet in CODE.findall(doc.read_text(encoding="utf-8")):
            missing += [
                f"{doc.name}: {m}"
                for m in MODULE.findall(snippet)
                if not module_exists(m)
            ]
            missing += [
                f"{doc.name}: {s}"
                for s in SCRIPT.findall(snippet)
                if not (ROOT / s).is_file()
            ]
    assert not missing, missing


def test_section_citations_resolve():
    bad = []
    for doc in doc_files():
        text = doc.read_text(encoding="utf-8")
        for name, number in CITED.findall(text):
            if not has_section(DOCS / name, number):
                bad.append(f"{doc.name}: {name} §{number}")
        for number in BARE.findall(CITED.sub("", text)):
            if not has_section(doc, number):
                bad.append(f"{doc.name}: §{number}")
    assert not bad, bad


def test_living_docs_name_paths_that_exist():
    # An unbuilt item is allowed when its line says "Planned".
    bad = []
    for doc in filter(is_living, doc_files()):
        for line in doc.read_text(encoding="utf-8").splitlines():
            if "Planned" in line:
                continue
            for token in CODE.findall(line):
                if PATH.match(token) and not (
                    (ROOT / token).exists()
                    or (DOCS / token).exists()
                    or any((ROOT / "src").glob(f"**/{token}"))
                ):
                    bad.append(f"{doc.name}: {token}")
    assert not bad, bad


def test_dates_stay_out_of_living_docs():
    bad = [
        f"{doc.name}: {date}"
        for doc in doc_files()
        if doc.is_relative_to(DOCS) and is_living(doc) and doc.name != "decisions.md"
        for date in DATE.findall(doc.read_text(encoding="utf-8"))
    ]
    assert not bad, bad


def test_docs_map_lists_every_doc():
    if not (DOCS / "README.md").is_file():
        return
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    missing = []
    for doc in doc_files():
        if not doc.is_relative_to(DOCS) or doc.name == "README.md":
            continue
        rel = doc.relative_to(DOCS)
        if f"({rel.as_posix()})" not in index and f"({rel.parts[0]}/)" not in index:
            missing.append(rel.as_posix())
    assert not missing, missing
