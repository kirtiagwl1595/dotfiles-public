#!/usr/bin/env bash
# Start one guard with a working Python 3.9+, on macOS, Linux and Windows (Git Bash).
#   bash py.sh guard_bash.py   (Claude Code sends the tool call as JSON on stdin)
#   bash py.sh ../repo_setup.py plan "$PWD"   (a skill script; its arguments follow)
#
# Fail closed: a hook that exits with any code but 2 lets the tool call through. So no
# working Python means exit 2. On Windows, `python3` is often the Microsoft Store stub
# (exit 9009): the version check below skips it. Only bash builtins here: no PATH needed.

export PYTHONUTF8=1 # Windows decodes stdin as cp1252 without it
src="${BASH_SOURCE[0]//\\//}" # C:\x\py.sh → C:/x/py.sh
here="${src%/*}"
[ "$here" = "$src" ] && here=.

script=$1
shift
for py in python3 "py -3" python; do
  # $py unquoted on purpose: "py -3" is a program and an option
  if $py -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
    exec $py -B "$here/$script" "$@"
  fi
done

echo "Blocked: the Claude Code guards found no working Python 3.9 or later." \
  "Install Python 3 (python.org or your package manager), then restart Claude Code." >&2
exit 2
