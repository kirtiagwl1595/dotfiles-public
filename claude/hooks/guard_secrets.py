#!/usr/bin/env python3
"""PreToolUse: keep Claude out of private files and secrets (SSH keys, cloud and git
credentials, keychains and credential stores, .env, ~/Documents), on macOS, Linux and Windows.

Every path and command is matched in the norm() form: `/` for `\\`, lower case, `~` for
each home form. So `C:\\Users\\x\\.SSH\\id_rsa` and `~/.ssh/id_rsa` are the same match.
"""

import fnmatch
import re

from _common import SHELL_TOOLS, norm, norm_path, run_guard

# One list for the shells and the file tools, so both agree on what is private
SSH_OK = (".pub", "known_hosts", "allowed_signers", "config")
ENV_OK = (".env.example", ".env.sample", ".env.template")
# The file tools may read these SSH files, but never write them: config can set ProxyCommand
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# Folders that hold only secrets, matched anywhere: another user's or a mounted home's too
SECRET_DIRS = (
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
# Files in the home folder that hold a token or password
SECRET_FILES = (
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".docker/config.json",
    ".config/git/credentials",
)

_ssh_ok = "|".join(re.escape(x) for x in SSH_OK)
_env_ok = "|".join(re.escape(x.removeprefix(".env.")) for x in ENV_OK)
# A shell separator ends a path; else `id_rsa;config` would pass as config
_word = r"[^\s;&|<>()'\"]"
_end = r"(?:$|[\s;&|<>()'\"])"
_start = r"(?:^|[\s/'\"=:])"
_dirs = "|".join(re.escape(d) for d in SECRET_DIRS)
_files = "|".join(re.escape(f) for f in SECRET_FILES)
SHELL_PATTERNS = [
    rf"\.ssh/(?!{_word}*(?:{_ssh_ok}){_end})\S+",
    rf"{_start}\.ssh/?{_end}",  # the folder itself: `cd ~/.ssh` then a bare key name
    rf"{_start}(?:{_dirs})(?:/|{_end})",
    rf"~/(?:{_files}){_end}",
    r"\w(?<!\bprocess)\.env($|[\s'\"|;&)<>])",  # prod.env, but not process.env
    rf"{_start}\.env(?!\.(?:{_env_ok})\b)(\.[\w-]+)?($|[\s'\"|;&)<>])",
    r"~/documents\b",
    r"\bsecurity\s+(find-(generic|internet)-password\b.*\s-[wg]\b|dump-keychain\b.*\s-d\b)",
    r"(?:^|[\s;&|(])(?:cmdkey|vaultcmd|get-storedcredential)\b",
    r"\bsecret-tool\s+lookup\b",
    r"(>|\btee\b[^|;&]*\s)\s*\S*\.ssh/",  # also config: it can set ProxyCommand
]
GLOB_CHARS = set("*?[")


def private_path(path):
    p = norm_path(path)
    name = p.rsplit("/", 1)[-1]
    padded = f"/{p}/"
    if "/.ssh/" in padded and not name.endswith(SSH_OK):
        return True
    if any(f"/{d}/" in padded for d in SECRET_DIRS):
        return True
    if any(p == f"~/{f}" for f in SECRET_FILES):
        return True
    if (
        name == ".env" or name.startswith(".env.") or name.endswith(".env")
    ) and name not in ENV_OK:
        return True
    return p == "~/documents" or p.startswith("~/documents/")


def ssh_path(path):
    return "/.ssh/" in f"/{norm_path(path)}/"


def private_glob(pattern):
    """True for a glob that picks .env files, e.g. `**/.env*` or `.env.local`."""
    name = norm(pattern).rstrip("/").rsplit("/", 1)[-1]
    return private_path(pattern) or (
        name.startswith(".env") and name.rstrip("*") not in ENV_OK
    )


def glob_word_private(word):
    """True for an unquoted shell glob that can reach a private file, e.g. `.en*`."""
    if not GLOB_CHARS & set(word) or set("'\"") & set(word):
        return False
    parts = word.lstrip("<>").split("/")
    for i, part in enumerate(parts):
        # A leading glob char does not match a dot file, and `*.py` is ordinary
        if not GLOB_CHARS & set(part) or part[:1] in GLOB_CHARS:
            continue
        if fnmatch.fnmatchcase(".env", part) or fnmatch.fnmatchcase(".env.local", part):
            return True
        if fnmatch.fnmatchcase(".ssh", part):
            return not parts[-1].endswith(SSH_OK)
        if fnmatch.fnmatchcase("documents", part):
            return "/".join(parts[:i]) == "~"
    return False


def check(data):
    tool, inp = data.get("tool_name", ""), data.get("tool_input", {})
    hit = None
    if tool in SHELL_TOOLS:
        cmd = inp.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            # Every shell guard reads `command`: without it, all of them would see "" and allow
            return (
                "block",
                "Blocked: the guard found no command text in this shell call.",
            )
        text = norm(cmd)
        if any(re.search(pat, text) for pat in SHELL_PATTERNS) or any(
            glob_word_private(w) for w in text.split()
        ):
            hit = cmd
    else:
        for key in ("file_path", "path", "notebook_path"):
            path = inp.get(key)
            if path and (
                private_path(path) or (tool in WRITE_TOOLS and ssh_path(path))
            ):
                hit = path
        # The Glob pattern and the Grep glob filter name files too
        globs = [inp.get("glob"), inp.get("pattern") if tool == "Glob" else None]
        hit = next((g for g in globs if g and private_glob(g)), hit)
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
