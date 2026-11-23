#!/usr/bin/env python3
"""PreToolUse Bash: check each part of a compound command against the ask/deny rules.

Permission rules match only the start of the command text, so a step after `cd x &&`
or in the `git -C <dir>` form gets past them. This hook splits the command (quotes,
heredocs, `$(...)` and `bash -c` aware) and matches every part on its own.

- Any part matches a deny rule: deny. Any part matches an ask rule: ask.
- Outside the sandbox (dangerouslyDisableSandbox), a compound command may hold only
  allowed parts (and `cd`); else deny and tell Claude to split it, so each risky
  part gets its own prompt. `bash -c`, `eval`, `xargs` and `find -exec` hide a command,
  so outside the sandbox they always deny. A pipe stage that only filters stdin is not
  a step: `glab auth status | head -8` is one command.
- A curl or wget stage piped into a shell, or `bash <(curl x)`: deny, in and outside the
  sandbox.
- curl or wget in the text with a code runner word in a compound command, or on several
  lines: ask. A coarse check; the sandbox and network allowlist are the real control.
- A command it cannot parse: ask.
"""

import fnmatch
import itertools
import json
import os
import re
import shlex
import shutil
from collections import namedtuple
from pathlib import Path

from _common import run_guard

SEPARATORS = set(";&|\n()")
SHELLS = {"bash", "sh", "zsh"}
CARRIERS = SHELLS | {"eval", "xargs"}
# PowerShell names its download commands and `iex` too
FETCHERS = {"curl", "wget", "iwr", "irm", "invoke-webrequest", "invoke-restmethod"}
EXPRESSION_RUNNERS = {"iex", "invoke-expression"}
SOURCES = {"source", "."}
INLINE = {"python": "-c", "python3": "-c", "py": "-c", "node": "-e", "osascript": "-e"}
POWERSHELLS = {"powershell", "pwsh"}
# A backslash before a path character is a Windows path separator, not a shell escape:
# `\x` and `/x` are both plain text to bash, so the rewrite never moves a word boundary
PATH_BACKSLASH = re.compile(r"\\(?=[\w.~-])")
WRAPPERS = {"sudo", "command", "env", "nohup", "time"}
XARGS_VALUE_OPTS = {"-I", "-J", "-L", "-P", "-R", "-S", "-E", "-n", "-s"}
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
# git global options whose value is the next word (the `--opt=value` form is one word)
GIT_VALUE_OPTS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--config-env",
    "--attr-source",
    "--super-prefix",
}
HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)(?:\n[ \t]*\2[ \t]*(?=\n|$)|\Z)", re.DOTALL
)
REDIRECT = re.compile(r"[<>]+&?")
SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
SED_PRINT = re.compile(r"(\d+|\$)(,(\d+|\$))?p")
AWK_UNSAFE = re.compile(r"system|getline|ARGV|ARGC|[|>]")
JQ_UNSAFE = re.compile(r"import|include")


def _any(_words, _operands):
    return True


# Stdin filter: option flags it may take, those that take a value, the allowed counts
# of words before any file, and a check on the words (a script must not run code)
FILTERS = {
    "head": ("cnq", "cn", {0}, _any),
    "tail": ("cnqr", "cn", {0}, _any),
    "cat": ("n", "", {0}, _any),
    "wc": ("clmw", "", {0}, _any),
    "grep": ("EFcinovw", "ABC", {1}, _any),
    "sort": ("fnru", "kt", {0}, _any),
    "uniq": ("cdiu", "", {0}, _any),
    "jq": ("cerS", "", {1}, lambda _w, ops: not JQ_UNSAFE.search(ops[0])),
    "tr": ("cds", "", {1, 2}, _any),
    "cut": ("s", "cdf", {0}, _any),
    "column": ("t", "s", {0}, _any),
    "sed": (
        "n",
        "",
        {1},
        lambda w, ops: "-n" in w and bool(SED_PRINT.fullmatch(ops[0])),
    ),
    "awk": ("", "F", {1}, lambda _w, ops: not AWK_UNSAFE.search(ops[0])),
}
# Coarse words, on raw text. Edges keep `curl.sh` and `x/python/y` from matching
FETCH_WORD = re.compile(
    r"(?<![\w.-])(curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)(?![\w./-])",
    re.IGNORECASE,
)
RUNNER_WORD = re.compile(
    r"(?<![\w.-])(bash|sh|zsh|dash|ksh|fish|eval|source|python[\d.]*|py|node|ruby|perl"
    r"|php|osascript|xargs|iex|invoke-expression|powershell|pwsh|cmd)(?![\w./-])"
    r"|\$SHELL|\$\{SHELL\}",
    re.IGNORECASE,
)
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
PROCESS_SUBST = re.compile(r"[<=]\(")


def lexer(cmd):
    """Shell words and separators; a newline is a separator, not white space."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    return lex


def filters_stdin(words):
    """True for a pipe stage that reads only stdin and writes only stdout. An allowlist:
    an option or a word it does not know makes the stage a real step."""
    if not words or words[0] not in FILTERS:
        return False
    flags, valued, counts, safe = FILTERS[words[0]]
    operands, i = [], 1
    while i < len(words):
        w = words[i]
        i += 1
        if w == "-" or not w.startswith("-"):
            operands.append(w)
        elif w.startswith("--") or not (
            w[1:].isdigit() or w[1] in valued or set(w[1:]) <= set(flags)
        ):
            return False
        elif w[1] in valued:
            i += len(w) == 2  # the value is the next word
    return len(operands) in counts and safe(words, operands)


def pipe_filters(cmd):
    """The top-level stages after a plain `|` that only filter stdin."""
    found, cur, sep, redirected = [], [], None, False

    def close():
        if sep == "|" and not redirected and filters_stdin(cur):
            found.append(list(cur))

    for tok in lexer(HEREDOC.sub("\n", cmd)):
        if tok and set(tok) <= SEPARATORS:
            close()
            cur, sep, redirected = [], tok, False
        elif REDIRECT.fullmatch(tok):
            redirected = True
        else:
            cur.append(tok)
    close()
    return found


def pipelines(cmd):
    """Each pipeline as its stages, in data-flow order. `bash <(curl x)` counts as
    `curl x | bash`. Parentheses do not end a stage, so `(curl x) | bash` stays one pipeline."""
    lines, line, cur = [], [], []

    def close_stage():
        nonlocal cur
        words = command_words(cur)
        if "<(" in words:
            cut = words.index("<(")
            line.extend([words[cut + 1 :], words[:cut]])
        elif words:
            line.append(words)
        cur = []

    for tok in lexer(cmd):
        if not tok or not set(tok) <= SEPARATORS:
            cur.append(tok)
            continue
        sep = tok.replace("(", "").replace(")", "")
        if not sep:
            continue
        close_stage()
        if sep.strip("\n") not in ("|", "|&"):
            lines.append(line)
            line = []
    close_stage()
    return [*lines, line]


def runs_download(cmd):
    """True when a curl or wget stage feeds a later stage that runs its input as code."""
    for line in pipelines(cmd):
        norms = [normalize(stage) for stage in line]
        first = next(
            (i for i, n in enumerate(norms) if n[:1] and n[0] in FETCHERS), None
        )
        if first is not None and any(
            reads_stdin(n) or n[:1] and n[0] in SOURCES for n in norms[first + 1 :]
        ):
            return True
    return False


def may_run_download(cmd, parts):
    """Coarse check on the raw text, quotes left in place: a download and a code runner
    in more than one command, or `<(` or `=(` outside quotes. It sees text, not data flow, so it asks; it does not deny."""
    if not FETCH_WORD.search(cmd):
        return False
    if "\n" in cmd.strip():
        return True
    if PROCESS_SUBST.search(QUOTED.sub("", cmd)):
        return True
    several = max(len(parts), len(words_of(cmd))) > 1
    return bool(RUNNER_WORD.search(cmd)) and several


def settings_files(cwd):
    """The plugin baseline and its sandbox rules, then the user and project settings."""
    return [
        Path(__file__).resolve().parents[1] / "settings.base.json",
        Path(__file__).resolve().parents[1] / "settings.sandbox.json",
        Path.home() / ".claude" / "settings.json",
        Path(cwd) / ".claude" / "settings.json",
        Path(cwd) / ".claude" / "settings.local.json",
    ]


def load_rules(cwd):
    """{allow, ask, deny: [rule text]} from the settings files."""
    rules = {"allow": [], "ask": [], "deny": []}
    for f in settings_files(cwd):
        try:
            perms = json.loads(f.read_text()).get("permissions", {})
        except (OSError, ValueError, AttributeError):
            continue
        for kind in rules:
            rules[kind] += [
                r[5:-1]
                for r in perms.get(kind, [])
                if r.startswith("Bash(") and r.endswith(")")
            ]
    return rules


def matches(rule, text):
    if rule.endswith(":*"):
        prefix = rule[:-2]
        return text == prefix or text.startswith(prefix + " ")
    if "*" in rule:
        return fnmatch.fnmatchcase(text, rule.replace("[", "[[]"))
    return text == rule


def command_words(words):
    """A redirect (>, >>, 2>&1, <) ends the command words; the rest are file names."""
    cut = next((i for i, w in enumerate(words) if REDIRECT.fullmatch(w)), len(words))
    if 0 < cut < len(words) and words[cut - 1].isdigit():
        cut -= 1  # the 2 in 2>&1
    return words[:cut]


def words_of(cmd):
    """Split into parts (lists of words). Raises ValueError on an unclosed quote."""
    parts, cur = [], []
    for tok in lexer(cmd):
        if tok and set(tok) <= SEPARATORS:
            parts.append(cur)
            cur = []
        else:
            cur.append(tok)
    parts.append(cur)
    return [words for words in map(command_words, parts) if words]


def program(word):
    """The program a word names: no folder, lower case, no .exe (`C:/Git/bin/GIT.EXE` → git).
    Windows finds programs in any case; matching too much is the safe side."""
    name = os.path.basename(word.replace("\\", "/")).lower()
    return name.removesuffix(".exe")


def normalize(words):
    """Drop VAR=value, wrappers like sudo (and their options), a path, case and .exe on
    the program, and git global options."""
    w = list(words)
    while w and (re.match(r"^\w+=", w[0]) or program(w[0]) in WRAPPERS):
        w.pop(0)
        while w and w[0].startswith("-"):
            del w[: 2 if w[0] in ("-u", "-g") else 1]  # sudo -u user takes a value
    if w:
        w[0] = program(w[0])
    if w and w[0] == "git":
        w = ["git", *w[git_options(w)[0] :]]
    return w


def git_options(words):
    """For words that start with git: (index of the subcommand, the -C folders in order)."""
    i, folders = 1, []
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "-C" and i + 1 < len(words):
            folders.append(words[i + 1])
        i += 2 if words[i] in GIT_VALUE_OPTS else 1
    return i, folders


def reads_stdin(norm):
    """True for a shell with no -c and no script file: it runs what comes on stdin.
    After -s, words are the arguments of the stdin script, not a script file.
    PowerShell `iex` runs its pipeline input."""
    if norm[:1] and norm[0] in EXPRESSION_RUNNERS:
        return True
    if not norm or norm[0] not in SHELLS or "-c" in norm:
        return False
    return "-s" in norm or all(w.startswith("-") for w in norm[1:])


def _switch(word):
    """`/c`, `-Command` → `c`, `command`: cmd and PowerShell take both `/` and `-`."""
    return word[1:].lower() if word[:1] in "-/" and len(word) > 1 else None


def carried(norm):
    """The command text that `cmd /c` or `powershell -Command` runs, else None."""
    if norm[0] == "cmd":
        keys = ("c", "k", "r")
    elif norm[0] in POWERSHELLS:
        keys = ("c", "co", "com", "comm", "comma", "comman", "command")
    else:
        return None
    i = next((i for i, w in enumerate(norm) if i and _switch(w) in keys), None)
    return None if i is None else " ".join(norm[i + 1 :])


def encoded(norm):
    """True for `powershell -EncodedCommand`: base64 text that no guard can read."""
    return norm[0] in POWERSHELLS and any(
        (s := _switch(w)) and (s == "ec" or "encodedcommand".startswith(s))
        for w in norm[1:]
    )


def windows_paths(cmd):
    return PATH_BACKSLASH.sub("/", cmd)


def inner_commands(norm):
    """The commands that xargs and find run, so the rules see them in the sandbox too."""
    if norm[0] == "xargs":
        i = 1
        while i < len(norm) and norm[i].startswith("-"):
            i += 2 if norm[i] in XARGS_VALUE_OPTS else 1
        return [norm[i:]] if norm[i:] else []
    if norm[0] != "find":
        return []
    found = [["rm"]] if "-delete" in norm else []
    for i, w in enumerate(norm):
        if w in FIND_EXEC:
            found.append(
                list(itertools.takewhile(lambda x: x not in (";", "+"), norm[i + 1 :]))
            )
    return [c for c in found if c]


def parts_of(cmd, depth=0, texts=None):
    """Every part to check, as (raw words, normalized words), including hidden commands.
    `texts` collects each command text, also those hidden in `bash -c` and `$(...)`."""
    found = []
    texts = [] if texts is None else texts
    cmd = windows_paths(cmd)
    for m in HEREDOC.finditer(cmd):
        # The body is code only when a shell reads it; for cat, git commit etc. it is text
        line = cmd[cmd.rfind("\n", 0, m.start()) + 1 : m.start()]
        try:
            heads = words_of(line)
        except ValueError:
            continue
        if depth < 3 and heads and reads_stdin(normalize(heads[-1])):
            found += parts_of(m.group(3), depth + 1, texts)
    cmd = HEREDOC.sub("\n", cmd)
    texts.append(cmd)
    for m in SUBST.finditer(cmd):
        found += parts_of(m.group(1) or m.group(2) or "", depth + 1, texts)
    for words in words_of(cmd):
        norm = normalize(words)
        if not norm:
            continue  # only VAR=value: nothing runs
        found.append((words, norm))
        found += [(c, n) for c in inner_commands(norm) if (n := normalize(c))]
        if depth < 3 and norm and norm[0] in SHELLS and "-c" in norm[:-1]:
            found += parts_of(norm[norm.index("-c") + 1], depth + 1, texts)
        elif depth < 3 and norm and norm[0] == "eval":
            found += parts_of(" ".join(norm[1:]), depth + 1, texts)
        elif depth < 3 and (inner := carried(norm)) is not None:
            found += parts_of(inner, depth + 1, texts)
    return found


def hidden(norm):
    """True for a part that runs a command given as text: bash -c, a shell reading stdin,
    python -c, eval, xargs, find -exec, cmd /c, powershell -Command."""
    return bool(norm) and (
        (norm[0] in SHELLS and "-c" in norm)
        or carried(norm) is not None
        or encoded(norm)
        or reads_stdin(norm)
        or INLINE.get(norm[0]) in norm
        or norm[0] in CARRIERS - SHELLS
        or (norm[0] == "find" and ("-exec" in norm or "-delete" in norm))
    )


# Kept for guard_loop.py, which imports it; guard_compound itself does not call it.
def trusted_forge(raw, norm, cwd):
    """False when a part runs a forge.sh that is not ours: the allow rules match by name.
    Ours is the forge.sh of this plugin, and the one of the clone this plugin comes from."""
    args = [w for w in norm[1:] if not w.startswith("-")]
    if norm[0] == "forge.sh":
        word = next(w for w in raw if os.path.basename(w) == "forge.sh")
        word = (shutil.which(word) or "") if word == "forge.sh" else word
    elif norm[0] in SHELLS and "-c" not in norm and args:
        word = args[0]
        if os.path.basename(word) != "forge.sh":
            return True
    else:
        return True
    root = str(Path(__file__).resolve().parents[1])
    for var in ("${CLAUDE_PLUGIN_ROOT}", "$CLAUDE_PLUGIN_ROOT"):
        word = word.replace(var, root)
    path = os.path.realpath(
        os.path.join(cwd, os.path.expanduser(os.path.expandvars(word)))
    )
    trusted = {os.path.realpath(os.path.join(root, "forge.sh"))}
    return bool(word) and os.path.isfile(path) and path in trusted


def skips_hooks(words):
    """True for `git -c core.hooksPath=...`, which has the effect of --no-verify."""
    return any(
        words[i] == "-c" and words[i + 1].lower().startswith("core.hookspath=")
        for i in range(len(words) - 1)
    )


# What every check sees. texts: (raw text, normalized text, normalized words) per part
Command = namedtuple("Command", "cmd off parts texts download rules cwd")


def in_rules(rules, raw, text, loose=False):
    """Deny and ask rules also match in any case (`SUDO`, `Git Push`): more matches is the
    safe side. Allow rules stay exact, so case never widens what runs without a question."""
    return any(
        matches(r, raw)
        or matches(r, text)
        or (
            loose
            and (matches(r.lower(), raw.lower()) or matches(r.lower(), text.lower()))
        )
        for r in rules
    )


def first_rule_hit(c, kind):
    loose = kind != "allow"
    return next(
        (t for raw, t, _ in c.texts if in_rules(c.rules[kind], raw, t, loose)), None
    )


def denied_part(c):
    seg = first_rule_hit(c, "deny")
    return seg and f"Denied part: `{seg}`."


def piped_download(c):
    return (
        c.download and "Do not pipe a download into a shell. Save it and read it first."
    )


def carrier_outside(c):
    t = c.off and next((t for _, t, norm in c.texts if hidden(norm)), None)
    return t and f"Outside the sandbox, run the command directly, not through `{t}`."


def chain_outside(c):
    if not c.off:
        return None
    steps = [x for x in c.texts if x[2][:1] != ["cd"]]
    for stage in pipe_filters(c.cmd):
        # One stage removes one step: an equal part elsewhere still counts
        match = next((x for x in steps if x[0] == " ".join(stage)), None)
        if match:
            steps.remove(match)
    unallowed = (t for raw, t, _ in steps if not in_rules(c.rules["allow"], raw, t))
    t = len(steps) > 1 and next(unallowed, None)
    return t and f"Outside the sandbox, run one specific command. Split out `{t}`."


def coarse_download(c):
    try:
        risky = may_run_download(c.cmd, c.parts)
    except ValueError:
        risky = True  # a heredoc line can hold a quote that the split of parts drops
    return risky and "A download may run as code here. Ask first."


def part_warnings(raw, norm):
    if skips_hooks(raw):
        yield "This command turns off git hooks."
    if encoded(norm):
        yield "PowerShell -EncodedCommand hides the command."


def untrusted_part(c):
    why = next((w for raw, norm in c.parts for w in part_warnings(raw, norm)), None)
    return why and f"{why} Ask first."


def asked_part(c):
    seg = first_rule_hit(c, "ask")
    return seg and f"This command holds `{seg}`, which needs permission. Ask first."


# Each check returns its reason, or a false value when it does not hit. The first reason
# decides. Every deny comes before every ask, so an ask never takes the place of a deny.
CHECKS = (
    ("deny", denied_part),
    ("deny", piped_download),
    ("deny", carrier_outside),
    ("deny", chain_outside),
    ("ask", coarse_download),
    ("ask", untrusted_part),
    ("ask", asked_part),
)


def decide(tool_input, rules, cwd="."):
    cmd = windows_paths(tool_input.get("command", ""))
    try:
        sources = []
        parts = parts_of(cmd, texts=sources)
        download = any(runs_download(text) for text in sources)
    except ValueError:
        return "ask", "Cannot split this command safely. Ask first."
    texts = [(" ".join(raw), " ".join(norm), norm) for raw, norm in parts]
    off = bool(tool_input.get("dangerouslyDisableSandbox"))
    c = Command(cmd, off, parts, texts, download, rules, cwd)
    return next(
        ((kind, why) for kind, test in CHECKS if (why := test(c))), (None, None)
    )


def check(data):
    cwd = data.get("cwd") or os.getcwd()
    decision, reason = decide(data.get("tool_input", {}), load_rules(cwd), cwd)
    return (decision, reason) if decision else None


if __name__ == "__main__":
    run_guard(check)
