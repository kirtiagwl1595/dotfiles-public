#!/usr/bin/env bash
# Start one guard with a working Python 3.9+, on macOS, Linux and Windows (Git Bash).
#   bash py.sh guard_bash.py   (Claude Code sends the tool call as JSON on stdin)
#   bash py.sh ../repo_setup.py plan "$PWD"   (a skill script; its arguments follow)
#   bash py.sh notify.sh   (a shell hook: started with bash, its arguments follow)
#   bash py.sh --advisory coach_prompt.py   (a hook that only advises: see below)
#
# Fail closed: a hook that exits with any code but 2 lets the tool call through. So no
# working Python means exit 2. On Windows, `python3` is often the Microsoft Store stub
# (exit 9009): the version check below skips it. Only bash builtins here: no PATH needed.

export PYTHONUTF8=1 # Windows decodes stdin as cp1252 without it
src="${BASH_SOURCE[0]//\\//}" # C:\x\py.sh → C:/x/py.sh
here="${src%/*}"
[ "$here" = "$src" ] && here=.

advisory=
if [ "$1" = --advisory ]; then
  advisory=1
  shift
fi
script=$1
shift
# A shell hook (advice and gates, not a guard) needs no Python to start: it finds its own
case $script in *.sh) exec bash "$here/$script" "$@" ;; esac
for py in python3 "py -3" python; do
  # $py unquoted on purpose: "py -3" is a program and an option
  if $py -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
    exec $py -B "$here/$script" "$@"
  fi
done

# An advisory hook (UserPromptSubmit, Stop, PostToolUse...) must never block: exit 2 there
# erases a prompt or repeats a Stop without end. With no Python it does nothing.
[ -n "$advisory" ] && exit 0
echo "Blocked: the Claude Code guards found no working Python 3.9 or later." \
  "Install Python 3 (python.org or your package manager), then restart Claude Code." >&2
exit 2
