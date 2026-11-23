"""Every text read and write names its encoding. Without one, Windows Python uses the locale
codec (cp1252): a `§` or `·` in a file reads as two other characters, a split finds nothing,
and a guard can crash on a settings file. ruff's PLW1514 sees only some of these calls."""

import ast

from hookrun import ROOT

TEXT_CALLS = {"read_text", "write_text", "open", "fdopen"}
SKIP = ("claude/plugins/anthropic-skills/",)  # unmodified upstream copies
ARCHIVES = {"tarfile", "zipfile"}  # their open() reads members, not text: no encoding


def own_python_files():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(SKIP) or "/." in "/" + rel:
            continue
        yield rel, path


def name_of(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def mode_of(call):
    """The mode string of an open() call, or None when it is not a literal."""
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    first = (
        0 if isinstance(call.func, ast.Attribute) else 1
    )  # Path.open(mode), open(path, mode)
    if len(call.args) > first and isinstance(call.args[first], ast.Constant):
        return call.args[first].value
    return None


def missing_encoding(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or name_of(node.func) not in TEXT_CALLS:
            continue
        receiver = getattr(node.func, "value", None)
        if isinstance(receiver, ast.Name) and receiver.id in ARCHIVES:
            continue
        if any(kw.arg in ("encoding", None) for kw in node.keywords):  # None: **kwargs
            continue
        mode = mode_of(node) if name_of(node.func) in ("open", "fdopen") else ""
        if isinstance(mode, str) and "b" in mode:
            continue
        yield node.lineno


def test_every_text_read_and_write_names_its_encoding():
    found = [
        f"{rel}:{line}"
        for rel, path in own_python_files()
        for line in missing_encoding(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not found, "add encoding='utf-8':\n" + "\n".join(found)
