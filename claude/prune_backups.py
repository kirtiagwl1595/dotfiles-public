"""Keep the newest copies of each item in an install backup folder (one folder per run).

plan <root>:  first line is the number of items to delete; each next line is a kept hand-named item.
apply <root>: delete those items and any run folder left empty.
"""

import os
import re
import sys
from pathlib import Path

KEEP = 2
RUN = re.compile(r"\d{4}-\d{2}-\d{2}-\d{6}")


def run_folders(root):
    if not root.is_dir():
        return []
    # The name holds the time, so name order is age order, also after a copy to a new Mac.
    return sorted(p for p in root.iterdir() if p.is_dir() and RUN.fullmatch(p.name))


def items_in(run):
    for folder, dirs, files in os.walk(run):
        if Path(folder) == run and "cleanup" in dirs:
            dirs.remove("cleanup")  # moved old tools: the only copy
        links = [d for d in dirs if Path(folder, d).is_symlink()]
        for name in files + links:
            yield Path(folder, name).relative_to(run)


def old_items(root):
    copies = {}
    for run in run_folders(root):
        for item in items_in(run):
            copies.setdefault(item, []).append(run / item)
    return [p for paths in copies.values() for p in paths[:-KEEP]]


def remove_empty_folders(run):
    for folder, _, _ in os.walk(run, topdown=False):
        path = Path(folder)
        if not path.is_symlink() and not any(path.iterdir()):
            path.rmdir()


def main(argv):
    if len(argv) != 3 or argv[1] not in ("plan", "apply"):
        print("usage: prune_backups.py plan|apply <backup folder>", file=sys.stderr)
        return 2
    root = Path(argv[2])
    old = old_items(root)
    if argv[1] == "plan":
        print(len(old))
        if root.is_dir():
            runs = set(run_folders(root))
            for p in sorted(root.iterdir()):
                if p not in runs:
                    print(p.name)
        return 0
    for path in old:
        path.unlink()  # on a link this removes the link, never its target
    for run in run_folders(root):
        remove_empty_folders(run)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
