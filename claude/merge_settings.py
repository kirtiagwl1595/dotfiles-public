"""Merge settings.base.json into a user's ~/.claude/settings.json without losing their entries.

Objects merge key by key; lists are a union (the user's items first, ours added, no duplicates);
for other values the user's value wins. Standard library only.

A union never drops an item, so base has "$remove": {"dotted.path": [items]} for retired entries.
The merge takes those items out of the live lists; "$remove" itself never reaches the live file.

  merge_settings.py BASE USER            print the merged JSON
  merge_settings.py --added BASE USER    print only what the merge would add (for install.py --check)
  merge_settings.py --extra BASE USER    print live entries that base does not have (report only)
"""

import json
import sys
from pathlib import Path

REMOVE = "$remove"


def split(base):
    """Base without "$remove", and the removals as {path: items}."""
    if not isinstance(base, dict):
        return base, {}
    return {k: v for k, v in base.items() if k != REMOVE}, base.get(REMOVE, {})


def node_at(tree, path):
    for key in path.split("."):
        if not isinstance(tree, dict) or key not in tree:
            return None
        tree = tree[key]
    return tree


def retired(user, base):
    """(path, item) for each live item that base retires."""
    _, removals = split(base)
    out = []
    for path, items in removals.items():
        live = node_at(user, path)
        if isinstance(live, list):
            out += [(path, item) for item in items if item in live]
    return out


def merge(user, base):
    base, removals = split(base)
    out = union(user, base)
    for path, items in removals.items():
        live = node_at(out, path)
        if isinstance(live, list):
            live[:] = [item for item in live if item not in items]
    return out


def union(user, base):
    if isinstance(user, dict) and isinstance(base, dict):
        out = dict(user)
        for key, value in base.items():
            out[key] = union(user[key], value) if key in user else value
        return out
    if isinstance(user, list) and isinstance(base, list):
        return user + [item for item in base if item not in user]
    return user


def show(item):
    return item if isinstance(item, str) else json.dumps(item)


def added(user, base):
    """Lines like 'permissions.allow += Bash(ls:*)' or '-= ...' for each thing the merge changes."""
    gone = [f"{path} -= {show(item)}" for path, item in retired(user, base)]
    return _added(user, split(base)[0]) + gone


def _added(user, base, prefix=""):
    lines = []
    for key, value in base.items():
        path = f"{prefix}{key}"
        if key not in user:
            lines.append(f"{path} = {json.dumps(value)}")
        elif isinstance(user[key], dict) and isinstance(value, dict):
            lines += _added(user[key], value, f"{path}.")
        elif isinstance(user[key], list) and isinstance(value, list):
            lines += [f"{path} += {item}" for item in value if item not in user[key]]
    return lines


def extra(user, base):
    """Lines for what only the live file has. Key names only: values can hold secrets.
    Items that "$remove" retires are left out: the next merge drops them."""
    return _extra(merge(user, base), split(base)[0])


def _extra(user, base, prefix=""):
    lines = []
    for key, value in user.items():
        path = f"{prefix}{key}"
        if key not in base:
            lines.append(path)
        elif isinstance(value, dict) and isinstance(base[key], dict):
            lines += _extra(value, base[key], f"{path}.")
        elif isinstance(value, list) and isinstance(base[key], list):
            new = [item for item in value if item not in base[key]]
            lines += [
                f"{path} += {item if isinstance(item, str) else '(object)'}"
                for item in new
            ]
    return lines


def load(path):
    p = Path(path)
    try:
        return (
            json.loads(p.read_text(encoding="utf-8"))
            if p.exists() and p.read_text(encoding="utf-8").strip()
            else {}
        )
    except ValueError:
        sys.exit(f"{path}: not valid JSON")


def main(args):
    report = {"--added": added, "--extra": extra}.get(args[0] if args else "")
    base, user = (load(p) for p in args[bool(report) :])
    if report:
        print("\n".join(report(user, base)))
    else:
        print(json.dumps(merge(user, base), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
