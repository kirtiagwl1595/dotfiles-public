#!/usr/bin/env bash
# Runs the checks of .github/workflows/test.yml on this computer, before you push.
# tests/test_scripts.py keeps the first list equal to the one-line run steps of test.yml.
# The second list runs only when its tool is installed (no CI step, extra safety).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

CHECKS=(
  "git ls-files --eol claude/hooks/py.sh | grep -q \"i/lf.*w/lf\""
  "uvx ruff@0.17.2 check . && uvx ruff@0.17.2 format --check ."
  "uv run --no-project --with pytest pytest -q tests"
  "uv run --no-project python install.py --check"
  "bash install.sh --check"
)
# "tool|command": skipped when the tool is missing
OPTIONAL=(
  "shellcheck|shellcheck -S warning install.sh scripts/*.sh claude/*.sh claude/hooks/*.sh"
  "zsh|zsh -n shell/zsh/.zshrc shell/zsh/.zprofile"
)

ruff_pin_check() {  # warn only: a different ruff can format differently from CI
  local pin have
  pin=$(sed -n 's/.*uvx ruff@\([0-9.]*\) .*/\1/p' .github/workflows/test.yml | head -1)
  have=$(ruff --version 2>/dev/null | awk '{print $2}')
  [[ -z $pin || $have == "$pin" ]] || echo "ci-local: ruff ${have:-missing} here, ruff@$pin in test.yml: the checks above use uvx ruff@$pin" >&2
}

# A template: macOS mktemp without one ignores TMPDIR and writes to /var/folders
log=$(mktemp "${TMPDIR:-/tmp}/ci-local.XXXXXX") || { echo "ci-local: cannot make a temp file in ${TMPDIR:-/tmp}" >&2; exit 1; }
trap 'rm -f "$log"' EXIT
ruff_pin_check

run_check() {
  printf '%-60.60s ' "$1"
  # bash -c: a failure anywhere in an && chain fails the step (set -e would miss it)
  if bash -c "$1" >"$log" 2>&1 </dev/null; then
    echo ok
  else
    echo FAILED
    cat "$log"
    echo "ci-local: \"$1\" failed. Fix it, then push again." >&2
    exit 1
  fi
}

for c in "${CHECKS[@]}"; do run_check "$c"; done
for entry in "${OPTIONAL[@]}"; do
  command -v "${entry%%|*}" >/dev/null 2>&1 && run_check "${entry#*|}"
done
echo "ci-local: all checks passed"
