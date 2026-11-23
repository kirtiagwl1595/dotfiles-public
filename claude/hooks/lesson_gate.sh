#!/usr/bin/env bash
# SessionStart (snapshot) + Stop (check): after real work, ask once for a lesson.
# Off until you opt in: create ~/.config/claude/lesson-gate (an empty file is enough).
# Real work = since the session started, the start root's content changed or got your own commits,
# or a worktree of the same repo (where the session now is) has changes or your own commits.
# A tree that was already dirty at start does not count; .claude/lessons/ and .claude/worktrees/ are ignored.
. "$(dirname "${BASH_SOURCE[0]}")/_py.sh"
[[ -f ${CLAUDE_LESSON_GATE:-$HOME/.config/claude/lesson-gate} ]] || exit 0
input=$(cat)
# One Python start reads every field (\x1f keeps empty fields in place)
IFS=$'\x1f' read -r cwd sid active source < <(pyrun -c '
import json, sys
d = json.loads(sys.argv[1])
print("\x1f".join(str(d.get(k) or "") for k in ("cwd", "session_id", "stop_hook_active", "source")))
' "$input") || exit 0
# A running loop of this session writes its lesson in its bundle step.
# Any other exit, a crash included, means the gate runs as before.
pyrun -B "$(dirname "${BASH_SOURCE[0]}")/_loop.py" running "$cwd" "$sid" 2>/dev/null && exit 0

[[ -n $sid ]] || exit 0 # no id: sessions would share one state file
cd "$cwd" 2>/dev/null || exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root" || exit 0
# A worktree shares the main checkout's .git; lessons live there (removing a worktree deletes its ignored files)
common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
main=$root
[[ ${common##*/} == .git ]] && main=${common%/.git}
# A git-tracked home is not a project: Claude's own writes under ~ (.claude, caches) would look like real work.
[[ "$(pwd -P)" == "$(cd "$HOME" 2>/dev/null && pwd -P)" ]] && exit 0
state="${TMPDIR:-/tmp}/claude-lesson-$sid"
skip=(':(exclude).claude/lessons' ':(exclude).claude/worktrees')

fingerprint() { # hash of every change against HEAD, plus untracked file contents
  local base
  base=$(git rev-parse --verify -q HEAD || git hash-object -t tree /dev/null)
  {
    git diff "$base" --binary -- . "${skip[@]}"
    # one git process hashes all untracked files; their names go in the hash too
    git ls-files -o --exclude-standard -- . "${skip[@]}" | tee /dev/stderr | git hash-object --stdin-paths
  } 2>&1 | sha | cut -d' ' -f1
}

own_commits() { # 0 when HEAD has commits you authored, committed since the start
  # Author, not committer: a GitHub squash merge of your PR keeps you as author (the committer is then a GitHub no-reply address).
  # --since filters by commit time, so PRs merged before the session do not count.
  local range=HEAD filter=()
  [[ -n $head ]] && range="$head..HEAD"
  [[ -n $email ]] && filter=(--fixed-strings "--author=$email")
  [[ -n $start ]] && filter+=("--since=@$start")
  (($(git rev-list --count "${filter[@]}" "$range" 2>/dev/null || echo 0) > 0))
}

case "$1" in
snapshot)
  # /compact starts the same session again: keep its baseline and its "asked" line
  [[ $source == compact && -f $state ]] && exit 0
  {
    fingerprint
    echo "root=$root"
    echo "head=$(git rev-parse --verify -q HEAD)"
    echo "start=$(date +%s)"
  } >"$state"
  ;;
check)
  [[ $active == True ]] && exit 0
  [[ -f "$state" ]] || exit 0
  snap=$(head -n1 "$state")
  start_root=$(sed -n 's/^root=//p' "$state")
  head=$(sed -n 's/^head=//p' "$state")
  start=$(sed -n 's/^start=//p' "$state")
  email=$(git config user.email)
  work=""
  if [[ -z $start_root ]]; then # state from an older version: compare in this root only
    [[ $snap != "$(fingerprint)" ]] && work=1
  else
    if cd "$start_root" 2>/dev/null; then
      { [[ $snap != "$(fingerprint)" ]] || own_commits; } && work=1
      cd "$root" || exit 0
    fi
    # A worktree made in this session has no baseline: any change or own commit in it is work
    if [[ -z $work && $root != "$start_root" ]] &&
      [[ $(git -C "$start_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) == "$common" ]]; then
      { [[ -n $(git status --porcelain -- . "${skip[@]}") ]] || own_commits; } && work=1
    fi
  fi
  [[ -n $work ]] || exit 0
  compgen -G "$main/.claude/lessons/$(date +%F)-*.md" >/dev/null && exit 0
  grep -qx asked "$state" && exit 0
  echo asked >>"$state"
  echo "Real work changed files in this repo: write the lesson to $main/.claude/lessons/$(date +%F)-<topic>.md before the final message." >&2
  exit 2
  ;;
esac
