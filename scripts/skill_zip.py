"""Pack claude/skills/<name> into <name>.zip for claude.ai. Used by skill-zip.sh."""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JUNK = {".DS_Store", "Thumbs.db"}


def main(argv):
    if not argv or len(argv) > 2:
        print("usage: scripts/skill-zip.sh <skill> [out.zip]", file=sys.stderr)
        return 2
    name = argv[0]
    src = ROOT / "claude" / "skills" / name
    if not (src / "SKILL.md").is_file():
        print(f"No skill {name} in claude/skills", file=sys.stderr)
        return 1
    desktop = Path.home() / "Desktop"
    out = (
        Path(argv[1])
        if len(argv) > 1
        else (desktop if desktop.is_dir() else Path.home()) / f"{name}.zip"
    )
    out = out.resolve()
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file() and path.name not in JUNK:
                zf.write(path, Path(name, path.relative_to(src)).as_posix())
        count = len(zf.namelist())
    print(f"{out}: {count} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
