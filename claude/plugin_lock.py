"""Hash the hook and MCP config of third-party plugins; compare with a lock file.

Usage: plugin_lock.py check|update <cache_root> <lockfile> [--only <marketplace>/<plugin> ...]

cache_root is ~/.claude/plugins/cache (layout: <marketplace>/<plugin>/<version>/).
The lock file has one line per plugin: "<marketplace>/<plugin> <sha256>".
A plugin with no hooks and no MCP config gets the hash "none".
check prints one line per difference and exits 1; update rewrites the lock.
Exit 2 means bad input. The script only reads the cache.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

# This repo's own marketplace is skipped: its plugins change with the repo. The official
# marketplace also carries third-party authors, so it is locked like any other.
SKIP_MARKETPLACES = {"dotfiles-public"}
TEMP_CLONE = re.compile(r"^temp_git_")  # Claude Code's leftover marketplace clones
PLUGIN_ROOT_PATH = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s\"'`;|&<>)]+)")
HEADER = (
    "# <marketplace>/<plugin> <sha256 of hook and MCP config>, or none.\n"
    "# Update: python3 claude/plugin_lock.py update ~/.claude/plugins/cache"
    " claude/plugin-hooks.lock --only ...\n"
    "# Review the plugin before you lock it.\n"
)


def _version_key(name):
    return [int(p) if p.isdigit() else 0 for p in re.split(r"[.\-+]", name)]


def _inside(path, rel):
    """The file rel names inside the plugin, or None (a path that leaves the plugin is ignored)."""
    f = (path / rel).resolve()
    return f if f.is_file() and f.is_relative_to(path.resolve()) else None


def _custom_hook_paths(data):
    hooks = data.get("hooks") if isinstance(data, dict) else None
    paths = (
        [hooks] if isinstance(hooks, str) else hooks if isinstance(hooks, list) else []
    )
    return [p.removeprefix("./") for p in paths if isinstance(p, str)]


def _custom_hook_files(path, data):
    """A plugin.json "hooks" path names the file that runs: hash its content, not only its name."""
    out = []
    for rel in _custom_hook_paths(data):
        if f := _inside(path, rel):
            out.append((f"custom:{rel}", f.read_bytes()))
    return out


def _commands(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                yield value
            else:
                yield from _commands(value)
    elif isinstance(node, list):
        for item in node:
            yield from _commands(item)


def _scripts_hooks_run(path, data):
    """Files outside hooks/ that a hook command names through ${CLAUDE_PLUGIN_ROOT}."""
    configs = [data.get("hooks") if isinstance(data, dict) else None]
    for rel in ["hooks/hooks.json", *_custom_hook_paths(data)]:
        if f := _inside(path, rel):
            try:
                configs.append(json.loads(f.read_text()))
            except ValueError:
                continue  # the raw bytes are hashed already
    rels = {
        m.group(1)
        for cmd in _commands(configs)
        for m in PLUGIN_ROOT_PATH.finditer(cmd)
        if not m.group(1).startswith("hooks/")
    }
    return [
        (f"ref:{rel}", f.read_bytes())
        for rel in sorted(rels)
        if (f := _inside(path, rel))
    ]


def hash_plugin(path):
    """sha256 of the hook and MCP config of one installed plugin, or 'none'."""
    parts = []
    for rel in ("hooks/hooks.json", ".mcp.json"):
        f = path / rel
        if f.is_file():
            parts.append((rel, f.read_bytes()))
    manifest = path / ".claude-plugin/plugin.json"
    data = {}
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text())
        except ValueError:
            data = {}
        for key in ("hooks", "mcpServers"):
            if isinstance(data, dict) and key in data:
                canon = json.dumps(data[key], sort_keys=True).encode()
                parts.append((f"plugin.json:{key}", canon))
    # New parts are only added when present, so the hash of every older plugin is unchanged
    parts += _custom_hook_files(path, data) + _scripts_hooks_run(path, data)
    hooks = path / "hooks"
    if hooks.is_dir():
        for f in sorted(hooks.rglob("*")):
            rel = f"hooks/{f.relative_to(hooks)}"
            if (
                f.is_file()
                and "__pycache__" not in f.parts
                and rel != "hooks/hooks.json"
            ):
                parts.append((rel, f.read_bytes()))
    if not parts:
        return "none"
    h = hashlib.sha256()
    for name, content in parts:
        h.update(name.encode() + b"\0" + content + b"\0")
    return h.hexdigest()


def collect(cache, only=None):
    """{'marketplace/plugin': hash} for the newest installed version of each plugin."""
    out = {}
    for mp in sorted(p for p in cache.iterdir() if p.is_dir()):
        if mp.name in SKIP_MARKETPLACES or TEMP_CLONE.match(mp.name):
            continue
        for plugin in sorted(p for p in mp.iterdir() if p.is_dir()):
            key = f"{mp.name}/{plugin.name}"
            if only is not None and key not in only:
                continue
            versions = sorted(
                (v for v in plugin.iterdir() if v.is_dir()),
                key=lambda v: _version_key(v.name),
            )
            if versions:
                out[key] = hash_plugin(versions[-1])
    return out


def read_lock(lockfile):
    lock = {}
    if lockfile.is_file():
        for line in lockfile.read_text().splitlines():
            fields = line.split()
            if len(fields) == 2 and not line.startswith("#"):
                lock[fields[0]] = fields[1]
    return lock


def fail(msg):
    print(f"plugin_lock.py: {msg}", file=sys.stderr)
    return 2


def main(argv):
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        only, argv = set(argv[i + 1 :]), argv[:i]
    if len(argv) != 3 or argv[0] not in ("check", "update"):
        return fail(
            "usage: plugin_lock.py check|update <cache_root> <lockfile> [--only <mp>/<plugin> ...]"
        )
    cmd, cache, lockfile = argv[0], Path(argv[1]), Path(argv[2])
    if not cache.is_dir():
        return fail(f"cache folder not found: {cache}")
    try:
        now = collect(cache, only)
        if cmd == "update":
            # With --only, keep the other reviewed lines; a full update rewrites the lock
            kept = read_lock(lockfile) if only is not None and lockfile.exists() else {}
            merged = {**kept, **now}
            lines = "".join(f"{k} {v}\n" for k, v in sorted(merged.items()))
            lockfile.write_text(HEADER + lines)
            print(f"wrote {len(now)} entries to {lockfile}")
            return 0
        lock = read_lock(lockfile)
    except OSError as e:
        return fail(str(e))
    bad = 0
    for key, digest in now.items():
        if key not in lock:
            print(f"{key}: no line in the lock")
            bad = 1
        elif lock[key] != digest:
            print(f"{key}: hooks or MCP config changed since the lock")
            bad = 1
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
