#!/usr/bin/env bash
# SessionStart (snapshot) + Stop: if Python files changed in a uv project with tests/, run pytest.
# Failures go back to Claude (exit 2) so it fixes them before finishing.
# Runs only when the .py changes differ from the session start or the last passing run.
# Skip repos you only read: CLAUDE_TEST_GATE_SKIP="/path/one:/path/two" (path prefixes).
# Off until you opt in: create ~/.config/claude/test-gate (an empty file is enough). Stop hooks
# run outside the sandbox, so the gate would run the repo's tests and uv downloads at each Stop.
# No set -e: a hook must exit 0 or 2, never 1.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_py.sh"
[[ -f ${CLAUDE_TEST_GATE:-$HOME/.config/claude/test-gate} ]] || exit 0
input=$(cat)
IFS=$'\x1f' read -r cwd sid active < <(pyrun -c '
import json, sys
d = json.loads(sys.argv[1])
print("\x1f".join(str(d.get(k) or "") for k in ("cwd", "session_id", "stop_hook_active")))
' "$input") || exit 0
# A running loop of this session judges its own Stop.
# Any other exit, a crash included, means the gate runs as before.
pyrun -B "$(dirname "${BASH_SOURCE[0]}")/_loop.py" running "$cwd" "$sid" 2>/dev/null && exit 0

cd "$cwd" 2>/dev/null || exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
# Other people's repos (read-only clones): their conftest would run outside the sandbox
IFS=: read -ra skip_roots <<<"${CLAUDE_TEST_GATE_SKIP:-}"
for prefix in ${skip_roots[@]+"${skip_roots[@]}"}; do # the + form: bash 3.2 fails on an empty array
  [[ -n $prefix && $root == "${prefix%/}"/* ]] && exit 0
done
cd "$root" || exit 0
[[ -f pyproject.toml && -d tests ]] || exit 0
# No session id: no fingerprint, so every Stop with .py changes runs the tests
state=${sid:+${TMPDIR:-/tmp}/claude-tests-$sid}

fingerprint() { # the .py changes against HEAD, plus untracked .py contents
  {
    git diff HEAD --binary -- '*.py'
    git ls-files -o --exclude-standard -- '*.py' | tee /dev/stderr | git hash-object --stdin-paths
  } 2>&1 | sha | cut -d' ' -f1
}

now=$(fingerprint)
if [[ ${1:-} == snapshot ]]; then
  [[ -n $state ]] && echo "$now" >"$state"
  exit 0
fi
# After a block: check again only when the .py files changed since the failure.
# The same tree (or no session id to compare with) lets Claude stop: no loop.
if [[ $active == True ]]; then
  [[ -n $state && -f $state.fail && "$(cat "$state.fail")" != "$now" ]] || exit 0
fi
[[ -n "$(git status --porcelain -- '*.py' 2>/dev/null)" ]] || exit 0
[[ -n $state && -f $state && "$(cat "$state")" == "$now" ]] && exit 0

UV=$(command -v uv || echo "$HOME/.local/bin/uv")
[[ -x $UV ]] || exit 0
if ! out=$("$UV" run --quiet --with pytest pytest -q -x 2>&1); then
  [[ -n $state ]] && echo "$now" >"$state.fail"
  printf 'Tests failed. Fix them before finishing:\n%s\n' "$(tail -n 30 <<<"$out")" >&2
  exit 2
fi
[[ -n $state ]] && {
  echo "$now" >"$state"
  rm -f "$state.fail"
}
exit 0
