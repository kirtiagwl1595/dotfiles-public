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
HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)(?:\n[ \t]*\2[ \t]*(?=\n|$)|\Z)", re.DOTALL
)
REDIRECT = re.compile(r"[<>]+&?")
SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
# Stdin filter: option flags it may take, those that take a value, words before any file
FILTERS = {
    "head": ("cnq", "cn", 0),
    "tail": ("cnqr", "cn", 0),
    "cat": ("n", "", 0),
    "wc": ("clmw", "", 0),
    "grep": ("EFcinovw", "ABC", 1),
    "sort": ("fnru", "kt", 0),
    "uniq": ("cdiu", "", 0),
    "jq": ("cerS", "", 1),
    "tr": ("cds", "", 2),
    "cut": ("s", "cdf", 0),
    "column": ("t", "s", 0),
    "sed": ("n", "", 1),
    "awk": ("", "F", 1),
}
SED_PRINT = re.compile(r"(\d+|\$)(,(\d+|\$))?p")
AWK_UNSAFE = re.compile(r"system|getline|ARGV|ARGC|[|>]")
JQ_UNSAFE = re.compile(r"import|include")
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


def filters_stdin(words):
    """True for a pipe stage that reads only stdin and writes only stdout. An allowlist:
    an option or a word it does not know makes the stage a real step."""
    if not words or words[0] not in FILTERS:
        return False
    flags, valued, free = FILTERS[words[0]]
    operands, i = [], 1
    while i < len(words):
        w = words[i]
        i += 1
        if len(w) < 2 or not w.startswith("-") or w[1:].isdigit():
            if not w.startswith("-") or len(w) < 2:
                operands.append(w)
            continue
        if w.startswith("--"):
            return False
        if w[1] in valued:
            i += len(w) == 2
        elif not set(w[1:]) <= set(flags):
            return False
    if len(operands) != free and not (words[0] == "tr" and len(operands) == 1):
        return False
    if words[0] == "sed":
        return "-n" in words and bool(SED_PRINT.fullmatch(operands[0]))
    if words[0] == "jq":
        return not JQ_UNSAFE.search(operands[0])
    return not (words[0] == "awk" and AWK_UNSAFE.search(operands[0]))


def pipe_filters(cmd):
    """The top-level stages after a plain `|` that only filter stdin."""
    lex = shlex.shlex(HEREDOC.sub("\n", cmd), posix=True, punctuation_chars=";&|<>()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    found, cur, sep, redirected = [], [], None, False

    def close():
        if sep == "|" and not redirected and filters_stdin(cur):
            found.append(list(cur))

    for tok in lex:
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
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
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

    for tok in lex:
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


def load_rules(cwd):
    """{allow, ask, deny: [rule text]} from the plugin baseline plus user and project settings."""
    files = [
        Path(__file__).resolve().parents[1] / "settings.base.json",
        Path.home() / ".claude" / "settings.json",
        Path(cwd) / ".claude" / "settings.json",
        Path(cwd) / ".claude" / "settings.local.json",
    ]
    rules = {"allow": [], "ask": [], "deny": []}
    for f in files:
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
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    parts, cur = [], []
    for tok in lex:
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
        i = 1
        while i < len(w) and w[i].startswith("-"):
            i += 2 if w[i] in ("-C", "-c") else 1
        w = ["git", *w[i:]]
    return w


def reads_stdin(norm):
    """True for a shell with no -c and no script file: it runs what comes on stdin.
    After -s, words are the arguments of the stdin script, not a script file.
    PowerShell `iex` runs its pipeline input."""
    if norm[:1] and norm[0] in EXPRESSION_RUNNERS:
        return True
    if not norm or norm[0] not in SHELLS or "-c" in norm:
        return False
    return "-s" in norm or all(w.startswith("-") for w in norm[1:])


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


def skips_hooks(words):
    """True for `git -c core.hooksPath=...`, which has the effect of --no-verify."""
    return any(
        words[i] == "-c" and words[i + 1].lower().startswith("core.hookspath=")
        for i in range(len(words) - 1)
    )


def decide(tool_input, rules):
    cmd = windows_paths(tool_input.get("command", ""))
    off = bool(tool_input.get("dangerouslyDisableSandbox"))
    try:
        sources = []
        parts = parts_of(cmd, texts=sources)
        download = any(runs_download(text) for text in sources)
    except ValueError:
        return "ask", "Cannot split this command safely. Ask first."
    texts = [(" ".join(raw), " ".join(norm), norm) for raw, norm in parts]
    extra = next(
        (
            why
            for raw, norm in parts
            for why in (
                "This command turns off git hooks." if skips_hooks(raw) else None,
                "PowerShell -EncodedCommand hides the command."
                if encoded(norm)
                else None,
            )
            if why
        ),
        None,
    )

    def hit(kind):
        # Deny and ask rules also match in any case (`SUDO`, `Git Push`): more matches is the
        # safe side. Allow rules stay exact, so case never widens what runs without a question.
        def found(r, raw, t):
            if matches(r, raw) or matches(r, t):
                return True
            return kind != "allow" and (
                matches(r.lower(), raw.lower()) or matches(r.lower(), t.lower())
            )

        return next(
            (t for raw, t, _ in texts if any(found(r, raw, t) for r in rules[kind])),
            None,
        )

    if seg := hit("deny"):
        return "deny", f"Denied part: `{seg}`."
    if download:
        return "deny", "Do not pipe a download into a shell. Save it and read it first."
    if off:
        carrier = next((t for _, t, norm in texts if hidden(norm)), None)
        if carrier:
            return (
                "deny",
                f"Outside the sandbox, run the command directly, not through `{carrier}`.",
            )
        steps = [x for x in texts if x[2][:1] != ["cd"]]
        for stage in pipe_filters(cmd):
            # One stage removes one step: an equal part elsewhere still counts
            match = next((x for x in steps if x[0] == " ".join(stage)), None)
            if match:
                steps.remove(match)
        if len(steps) > 1:
            for raw, t, _ in steps:
                if not any(matches(r, raw) or matches(r, t) for r in rules["allow"]):
                    return (
                        "deny",
                        f"Outside the sandbox, run one specific command. Split out `{t}`.",
                    )
    # After every deny above, so that this ask never takes the place of a deny
    try:
        coarse = may_run_download(cmd, parts)
    except ValueError:
        coarse = True  # a heredoc line can hold a quote that the split of parts drops
    if coarse:
        return "ask", "A download may run as code here. Ask first."
    if extra:
        return "ask", f"{extra} Ask first."
    if seg := hit("ask"):
        return "ask", f"This command holds `{seg}`, which needs permission. Ask first."
    return None, None


def check(data):
    cwd = data.get("cwd") or os.getcwd()
    decision, reason = decide(data.get("tool_input", {}), load_rules(cwd))
    return (decision, reason) if decision else None


if __name__ == "__main__":
    run_guard(check)
