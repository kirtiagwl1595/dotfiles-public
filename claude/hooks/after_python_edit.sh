#!/usr/bin/env bash
# PostToolUse Edit|Write: format and lint the .py file Claude just changed.
# Remaining lint errors go back to Claude (exit 2). No ruff: nothing happens.
. "$(dirname "${BASH_SOURCE[0]}")/_py.sh"
input=$(cat)
[[ $input == *'.py"'* ]] || exit 0 # most edits are not Python: skip the Python start
file=$(pyrun -c "import json,sys; print(json.loads(sys.argv[1]).get('tool_input',{}).get('file_path',''))" "$input") || exit 0
file=${file//\\//} # a Windows path
[[ "$file" == *.py && -f "$file" ]] || exit 0
[[ "$file" == */scratchpad/* ]] && exit 0 # throwaway scripts, not repo code

RUFF=$(command -v ruff || echo "$HOME/.local/bin/ruff")
[[ -x "$RUFF" ]] || exit 0
"$RUFF" format --quiet "$file"
if ! out=$("$RUFF" check --fix --quiet "$file" 2>&1); then
  printf 'ruff found problems in %s:\n%s\n' "$file" "$out" >&2
  exit 2
fi
