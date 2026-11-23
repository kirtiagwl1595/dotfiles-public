#!/usr/bin/env bash
# Run the safe-lean plugin evals: each case with and without the plugin (WITH / W/OUT / Δ).
# --plugin <dir>: run another own plugin (for example claude/plugins/writing-skills) against
# the cases in its own evals/ folder; `claude plugin eval` runs one plugin at a time.
# Costs model calls on your plan (each case in evals/ × 3 runs × 2 arms). Cheap first try:
#   claude/evals/run.sh --case no-skill-for-questions --runs 1 --ablation none
# The model is the `opus` alias (newest Opus); the report records the exact id.
# The run does not load a CLAUDE.md: the agent sees a rule only if it reads the file (a canary line showed up only after `cat CLAUDE.md`).
# So a rule that lives only in CLAUDE.md, such as a writing style, cannot be graded on a reply that reads no files.
#
# Evals are manual: they cost model calls and need the `claude` CLI, so they never run in CI.
# Platforms: macOS, Linux and WSL2 (bash and the `claude` CLI on PATH). On native Windows run them
# from WSL2: the scaffold scripts need a POSIX shell, and the loop that drives skill evals does not run there.
set -euo pipefail
PLUGIN=$(cd "$(dirname "$0")/.." && pwd -P)
args=()
while (($#)); do
  if [[ $1 == --plugin ]]; then
    [[ -d ${2:-} ]] || { echo "run.sh: --plugin needs a plugin folder, got '${2:-}'" >&2; exit 2; }
    PLUGIN=$(cd "$2" && pwd -P)
    shift 2
  else
    args+=("$1")
    shift
  fi
done
# The caller's claude, found before the PATH change below
claude=$(command -v claude) || { echo "run.sh: claude is not on PATH" >&2; exit 2; }
# On macOS with Homebrew, its tools come first for the scaffold scripts.
# No git-action cases: inside the run sandbox the macOS git shim (xcrun) cannot write its cache, so git fails.
# Branch-before-commit is enforced by the guard_main_branch hook and tested in tests/ instead.
[[ -d /opt/homebrew/bin ]] && export PATH="/opt/homebrew/bin:$PATH"
"$claude" plugin eval "$PLUGIN" --allow-tools Write Edit "Bash(uv *)" "Bash(git *)" "Bash(python3 *)" "Bash(ls *)" "Bash(cat *)" \
  --no-publish --trust-plugin --scaffold --model opus --max-cost-usd "${EVAL_MAX_USD:-10}" ${args[@]+"${args[@]}"}
