#!/usr/bin/env bash
# Pack one skill from claude/skills into a zip to upload to claude.ai (Settings → Skills).
#   scripts/skill-zip.sh setup-repo      → ~/Desktop/setup-repo.zip (or ~ if there is no Desktop)
# The repo is the master copy: change the skill here, then upload the zip so claude.ai matches.
# The work is in skill_zip.py (Python's zipfile): it runs the same on macOS, Linux and Git Bash.
here="${BASH_SOURCE[0]%/*}"
for py in python3 python "py -3"; do
  # $py unquoted on purpose: "py -3" is a program and an option
  if $py -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
    exec $py "$here/skill_zip.py" "$@"
  fi
done
echo "skill-zip.sh needs Python 3.9 or later." >&2
exit 1
