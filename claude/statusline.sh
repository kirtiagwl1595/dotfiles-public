#!/usr/bin/env bash
# Claude Code status line: model · context used · git branch/changes · session cost · prompt-cache hits.
# Reads the session JSON on stdin (code.claude.com/docs/en/statusline). Context % tells you when to /clear or /compact.
# It runs on every refresh: one jq call, and git status without the slow untracked-file scan.
# Works in Git Bash on Windows. Without a working jq it prints just "Claude".
input=$(cat)
IFS=$'\t' read -r model dir ctx cost hit < <(jq -r '[
  .model.display_name // "Claude", .workspace.current_dir // ".",
  (.context_window.used_percentage // "" | if . == "" then "-" else floor end),
  (.cost.total_cost_usd // "" | if . == "" then "-" else . end),
  (.prompt_cache.hit_ratio // "" | if . == "" then "-" else . * 100 | round end)
] | @tsv' <<<"$input" 2>/dev/null)
dir=${dir//$'\r'/} hit=${hit//$'\r'/} # jq.exe on Windows ends lines with CRLF

parts=("${model:-Claude}")
[[ ${ctx:--} != - ]] && parts+=("ctx ${ctx}%")
if branch=$(git -C "${dir:-.}" symbolic-ref --short HEAD 2>/dev/null); then
  changed=$(git -C "${dir:-.}" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')
  [[ $changed != 0 ]] && branch+=" ✘$changed"
  parts+=("$branch")
fi
[[ ${cost:--} != - ]] && parts+=("$(printf '$%.2f' "$cost")")
[[ ${hit:--} != - ]] && parts+=("cache ${hit}%")

out=${parts[0]}
for p in "${parts[@]:1}"; do out+=" · $p"; done
echo "$out"
