#!/usr/bin/env python3
"""PreToolUse: keep Claude out of private files and secrets (SSH keys, cloud and git
credentials, keychains and credential stores, .env, ~/Documents), on macOS, Linux and Windows.

One table of private roots (ROOTS) serves the file tools, shell words and globs. Paths are
read in one form: `/` for `\\`, and each home form (`~`, $HOME, %USERPROFILE%,
$env:USERPROFILE) as the home folder. Names are compared in lower case, as the macOS and
Windows disks do. So `C:\\Users\\x\\.SSH\\id_rsa` and `~/.ssh/id_rsa` are the same match.
"""

import fnmatch
import functools
import glob
import os
import posixpath
import re
from collections import namedtuple

from _common import _ABSOLUTE, _HOME_FWD, _HOME_VARS, SHELL_TOOLS, norm, run_guard
from _private_names import env_name

# A private root: a folder (lower-case path parts), whether it counts only in a home
# folder, and the file names in it that may be read but never written (an SSH config
# can set ProxyCommand).
Root = namedtuple("Root", "parts home readable")
SSH_OK = (".pub", "known_hosts", "allowed_signers", "config")
ROOTS = (
    Root((".ssh",), False, SSH_OK),
    # Folders that hold only secrets, matched anywhere: another user's or a mounted home's too
    *(
        Root(tuple(d.split("/")), False, ())
        for d in (
            ".aws",
            ".azure",
            ".kube",
            ".gnupg",
            ".config/gh",
            ".config/glab-cli",
            "library/keychains",
            ".local/share/keyrings",
            "appdata/local/microsoft/credentials",
            "appdata/roaming/microsoft/credentials",
            "appdata/roaming/microsoft/protect",
            "appdata/local/microsoft/vault",
            "appdata/roaming/microsoft/vault",
            "appdata/roaming/github cli",
        )
    ),
    # Files in a home folder that hold a token or password
    *(
        Root(tuple(f.split("/")), True, ())
        for f in (
            ".git-credentials",
            ".netrc",
            ".npmrc",
            ".pypirc",
            ".docker/config.json",
            ".config/git/credentials",
        )
    ),
    Root(("documents",), True, ()),
)
SECRET_COMMANDS = [
    r"\bsecurity\s+(find-(generic|internet)-password\b.*\s-[wg]\b|dump-keychain\b.*\s-d\b)",
    r"(?:^|[\s;&|(])(?:cmdkey|vaultcmd|get-storedcredential)\b",
    r"\bsecret-tool\s+lookup\b",
    # A space in the name: the word split would cut it
    r"appdata/roaming/github cli(?:/|$|\s)",
]
# Shell characters that end a word: separators, quotes, `=`, escapes and brace lists
SHELL_SPLIT = re.compile(r"[\s;&|<>()'\"=\\`{},]+")
# A redirect target (after >, >>, >|, >& or >>&), the files after tee, or the file of a
# PowerShell writer (Out-File, Set-Content, Add-Content, with or without -Path)
WRITES = re.compile(
    r">>?[|&]?\s*([^\s;&|<>()]+)|\btee\b([^|;&]*)"
    r"|\b(?:out-file|set-content|add-content)(?:\s+-(?:path|filepath|literalpath))?\s+([^\s;&|<>()-][^\s;&|<>()]*)",
    re.IGNORECASE,
)
# The only owners of `.env` that read variables in code (Node, Vite); any other `x.env.y` is a file
JS_ENV_OWNERS = (["process"], ["import", "meta"])
GLOB_CHARS = set("*?[")
# A brace list with no list inside it. The shell expands only a list with a comma, and
# `${D}` is a variable: `${D}Library` is D's value, then Library
BRACE = re.compile(r"(?<!\$)\{([^{}]*,[^{}]*)\}")
# Glob and Grep patterns go to globset, which expands any group: `{.ssh}` is `.ssh`
GLOB_BRACE = re.compile(r"\{([^{}]*)\}")
MAX_ALTERNATIVES = 256
HOME_PARTS = _HOME_FWD.lower().split("/")
# A home folder in any form: this one, another user's, a drive letter, WSL and Git Bash
_ANY, _DRIVE, _LETTER = (re.compile(p) for p in (".+", "[a-z]:", "[a-z]"))
HOME_FORMS = (
    HOME_PARTS,
    ["", "users", _ANY],
    ["", "home", _ANY],
    [_DRIVE, "users", _ANY],
    ["", _LETTER, "users", _ANY],
    ["", "mnt", _LETTER, "users", _ANY],
)
# What can come just before a path inside a word: nothing at a slash, `@` or `:`, a
# short flag, or a variable, which the shell ends at a dot (`f=@~/x`, `host:x`,
# `file:///x`, `-T/x`, `$D.ssh/x`). A path starts where a match ends.
# A variable is read as the shell reads it: `${…}`, a whole name (`$_x`), one digit
# (`$1x` is `$1`, then x) or one special character (`$*`).
PATH_START = re.compile(
    r"(?=/)|[@:]|^-[A-Za-z]|\$(?:\{[^}]*\}|[A-Za-z_]\w*|\d|[*@#?!$-])"
)


def unify(text):
    """The text with `/` for `\\` and each home variable as the home folder."""
    return _HOME_VARS.sub(lambda _: _HOME_FWD, text.replace("\\", "/"))


def expand(path):
    """A path as the shell reads it: home forms, then `~`, then variables; `/` only."""
    p = unify(path)
    if p == "~" or p.startswith("~/"):
        p = _HOME_FWD + p[1:]
    return os.path.expandvars(p).replace("\\", "/")


def join(cwd, path):
    return path if _ABSOLUTE.match(path) else f"{cwd}/{path}"


def name_matches(name, part):
    """A path part (maybe a glob) matches a lower-case name like the shell on macOS: case
    does not count, and a leading glob character does not match a leading dot. A name can
    be a compiled pattern that stands for any folder of some kind (a home form)."""
    part = part.lower()
    if hasattr(name, "fullmatch"):
        return bool(name.fullmatch(part))
    if name.startswith(".") and part[:1] in GLOB_CHARS:
        return False
    return fnmatch.fnmatchcase(name, part)


def parts_match(pats, names):
    """Path parts (maybe globs) match these lower-case folder names; `**` is any number
    of folders. Used for the home folder: `/Users/*/` and `**/` can both be HOME. Each
    (pattern part, name) pair is computed once, so many `**` parts stay fast: a slow
    hook can time out, and a timed-out hook does not block."""

    @functools.cache
    def at(i, j):
        if i == len(pats):
            return j == len(names)
        if pats[i] == "**":
            return any(at(i + 1, k) for k in range(j, len(names) + 1))
        return j < len(names) and name_matches(names[j], pats[i]) and at(i + 1, j + 1)

    return at(0, 0)


def in_home(parts):
    return any(parts_match(parts, form) for form in HOME_FORMS)


def in_root(parts, start, writing):
    """True when a private root begins at or after `start` in the path parts."""
    for i in range(start, len(parts)):
        for root in ROOTS:
            span = parts[i : i + len(root.parts)]
            if len(span) < len(root.parts) or not all(
                map(name_matches, root.parts, span)
            ):
                continue
            if root.home and not in_home(parts[:i]):
                continue
            # A wildcard matches every folder, so a root that counts in any folder must
            # be named: `**/*` is not Library/Keychains, but `~/Library/*` is
            if not root.home and all(set(p) <= set("*?") for p in span):
                continue
            rest = parts[i + len(root.parts) :]
            if rest and not writing and rest[-1].lower().endswith(root.readable):
                continue
            return True
    return False


def split_abs(path):
    """An absolute path as parts. POSIX keeps a leading `//`; macOS opens it as `/`.
    A path with a drive letter starts with the drive."""
    norm_p = posixpath.normpath(path)
    lead = [] if re.match(r"[a-z]:", norm_p, re.IGNORECASE) else [""]
    return lead + [x for x in norm_p.split("/") if x]


def path_starts(text):
    """The word and each tail of it where a path can start."""
    return ({text} | {text[m.end() :] for m in PATH_START.finditer(text)}) - {""}


def path_parts(path, cwd):
    """The absolute path as parts, and where the parts to judge start. A path that stays
    inside the command's folder skips the roots above that folder (a repo in a root
    stays usable); a path that leaves it with `..` is judged as a whole."""
    p = posixpath.normpath(expand(path))
    parts = split_abs(join(cwd, p))
    if _ABSOLUTE.match(p) or p == ".." or p.startswith("../"):
        return parts, 0
    return parts, len(split_abs(cwd))


def absolute(path, cwd):
    return join(cwd, expand(path))


def root_path(pattern, cwd, writing=False):
    """True for a path pattern that reaches a private root. A literal path goes in
    through glob.escape, so its `*` or `[` stays text."""
    return in_root(*path_parts(pattern, cwd), writing)


def private_path(pattern, cwd, writing=False):
    """True for a path pattern that reaches a private root or names an env file."""
    name = path_parts(pattern, cwd)[0][-1]
    return root_path(pattern, cwd, writing) or env_name(name.lower())


def alternatives(word, brace=BRACE):
    """Every brace alternative, as the shell (BRACE) or globset (GLOB_BRACE) expands them:
    `.env{,.local}` gives `.env` and `.env.local`. Inner groups first, so nested groups
    work. None when there are more than MAX_ALTERNATIVES: the caller then blocks."""
    done, todo = [], [word]
    while todo:
        w = todo.pop()
        m = brace.search(w)
        if not m:
            done.append(w)
            continue
        todo += [w[: m.start()] + alt + w[m.end() :] for alt in m.group(1).split(",")]
        if len(done) + len(todo) > MAX_ALTERNATIVES:
            return None
    return done


def env_glob(pattern):
    """True for a glob part that matches a private dot file, e.g. `.en*` or `.e?v.local`."""
    return any(
        name_matches(n, part)
        for part in pattern.split("/")
        for n in (".env", ".env.local")
    )


def private_glob(pattern, cwd):
    """True for a Glob or Grep pattern that picks private files, e.g. `**/.env*` or `*.env`."""
    alts = alternatives(pattern, GLOB_BRACE)
    return alts is None or any(private_path(a, cwd) or env_glob(a) for a in alts)


def js_env(name):
    """True for code that reads variables, not a file: `process.env`, `import.meta.env.MODE`.

    Only in shell text, where `prod.env.PROD` (a file) and `c.env.DB` (code) look the same.
    """
    parts = name.split(".")
    i = parts.index("env", 1)
    return any(i >= len(o) and parts[i - len(o) : i] == o for o in JS_ENV_OWNERS)


def env_word(text):
    """True for a shell word whose file name is, or as a glob names, an env file (`*.env`)."""
    names = (w.rstrip("/").rsplit("/", 1)[-1].lower() for w in SHELL_SPLIT.split(text))
    return any(env_name(n) and not js_env(n) for n in names)


def reaches_private(word, cwd):
    """True for a shell word that is or reaches a private root, or expands to a private
    file. Env names in the text are env_word's part, as it knows `process.env` is code.
    Only an unquoted glob is a pattern: it is judged as one and expanded in cwd like
    the shell (Python's glob also skips dot files for a leading *). Other words are text."""
    w = word.lstrip("<>")
    if not GLOB_CHARS & set(w) or set("'\"") & set(w):
        texts = (t for t in SHELL_SPLIT.split(w) if t)
        return any(
            root_path(glob.escape(s), cwd) for t in texts for s in path_starts(t)
        )
    found = glob.glob(join(cwd, expand(w)))
    return (
        env_glob(w)
        or any(root_path(s, cwd) for s in path_starts(w))
        or any(private_path(glob.escape(m), cwd) for m in found)
    )


def private_word(word, cwd):
    """True for a shell word that names, matches or expands to a private file, in any
    of its brace alternatives (`cat .en{v,}` reads .env)."""
    alts = alternatives(word)
    return alts is None or any(env_word(a) or reaches_private(a, cwd) for a in alts)


def written(text):
    """The files a command writes: redirect targets and tee files."""
    for m in WRITES.finditer(text):
        if m.group(2) is not None:
            yield from m.group(2).split()
        else:
            yield m.group(1) or m.group(3)


def shell_private(cmd, cwd):
    text = os.path.expandvars(unify(cmd))  # $HOME, ${HOME}, %USERPROFILE%
    return (
        any(re.search(pat, norm(cmd)) for pat in SECRET_COMMANDS)
        or any(private_word(w, cwd) for w in text.split())
        or any(
            private_path(glob.escape(s), cwd, writing=True)
            for w in written(text)
            for s in path_starts(w)
        )
    )


def check(data):
    tool, inp = data.get("tool_name", ""), data.get("tool_input", {})
    cwd = unify(data.get("cwd") or os.getcwd()).rstrip("/") or "/"
    hit = None
    if tool in SHELL_TOOLS:
        cmd = inp.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            # Every shell guard reads `command`: without it, all of them would see "" and allow
            return (
                "block",
                "Blocked: the guard found no command text in this shell call.",
            )
        hit = cmd if shell_private(cmd, cwd) else None
    else:
        # A file tool names a path, so all of it counts: a relative path is made
        # absolute first, and a root above the folder it runs in is not skipped
        writing = tool in {"Edit", "Write", "MultiEdit", "NotebookEdit"}
        paths = (inp.get(k) for k in ("file_path", "path", "notebook_path"))
        hit = next(
            (
                p
                for p in paths
                if p and private_path(glob.escape(absolute(p, cwd)), cwd, writing)
            ),
            None,
        )
        # The Glob pattern and the Grep glob name files from `path`, as the tools do.
        # A Grep with no glob searches everything under `path`, and a glob with no
        # slash matches at any depth, as in ripgrep: `*.md` is `**/*.md`.
        base = absolute(inp.get("path") or cwd, cwd)
        globs = [inp.get("glob"), inp.get("pattern") if tool == "Glob" else None]
        if tool == "Grep" and not inp.get("glob"):
            globs.append("**/*")
        found = (
            absolute(g if "/" in unify(g) else f"**/{g}", base) for g in globs if g
        )
        hit = next((g for g in found if private_glob(g, cwd)), hit)
    if hit:
        why = (
            f"Blocked: '{hit}' touches a private file or secret (SSH keys, cloud and git "
            "credentials, keychains, .env, ~/Documents). "
            "Ask the user to share only the part you need, for example the variable names."
        )
        return "block", why
    return None


if __name__ == "__main__":
    run_guard(check)
