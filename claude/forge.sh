#!/usr/bin/env bash
# One place that knows GitHub vs GitLab ("forge" = the git hosting service). The setup-repo skill calls it.
#   forge.sh kind                                   github | gitlab (from `git remote get-url origin`)
#   forge.sh pr-create --title T --body-file F      PR on GitHub / MR on GitLab, from the current branch, on origin
#   forge.sh auth-check [host]                      is gh / glab logged in for that host?
#   forge.sh whoami [host]                          your username there (your own repo or a team repo)
# --dry-run (first argument) prints the command instead of running it.
# PRs/MRs always go to `origin`, never `upstream`. No host is stored in this repo: it comes from the
# remote URL, or from FORGE_GIT_HOST (default github.com). Bash 3.2 compatible; no Python needed.
set -euo pipefail
DRY=""
[[ ${1:-} == --dry-run ]] && { DRY=yes; shift; }
run() { if [[ -n $DRY ]]; then printf '%q ' "$@"; echo; else "$@"; fi; }

origin_url() { git remote get-url origin 2>/dev/null || { echo "No 'origin' remote in $(pwd)" >&2; exit 1; }; }
host_of() {  # https://host/p, ssh://git@host:22/p, git@host:p  →  host
  local u=$1
  u=${u#*://}; u=${u#*@}
  u=${u%%/*}; echo "${u%%:*}"
}
path_of() {  # → group/sub/repo (no .git)
  local u=$1 p
  case $u in
    *://*) p=${u#*://}; p=${p#*/} ;;
    *) p=${u#*:} ;;
  esac
  echo "${p%.git}"
}
kind_of_host() {
  local h=$1
  if [[ $h == github.com || $h == *github* ]]; then echo github
  elif [[ $h == *gitlab* ]]; then echo gitlab
  elif command -v glab >/dev/null && glab auth status --hostname "$h" >/dev/null 2>&1; then echo gitlab
  elif command -v gh >/dev/null && gh auth status --hostname "$h" >/dev/null 2>&1; then echo github
  else echo "Cannot tell whether $h is GitHub or GitLab: log in with 'gh auth login --hostname $h' or 'glab auth login --hostname $h'" >&2; exit 1
  fi
}
default_branch() {
  local b; b=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)
  echo "${b#origin/}" | grep . || echo main
}

cmd=${1:-}; shift || true
case $cmd in
  kind)
    kind_of_host "$(host_of "$(origin_url)")" ;;
  pr-create)
    title="" body=""
    while [[ $# -gt 0 ]]; do
      case $1 in --title) title=$2; shift ;; --body-file) body=$2; shift ;; *) echo "unknown option $1" >&2; exit 1 ;; esac
      shift
    done
    [[ -n $title && -n $body ]] || { echo "usage: forge.sh pr-create --title T --body-file F" >&2; exit 1; }
    # One assignment per line: in `a=$(x) b=$(y)` a failing x does not stop the script
    url=$(origin_url)
    host=$(host_of "$url")
    path=$(path_of "$url")
    branch=$(git symbolic-ref --short HEAD)
    base=$(default_branch)
    kind=$(kind_of_host "$host")  # inside [[ ]] its exit 1 would be lost
    if [[ $kind == github ]]; then
      repo=$path; [[ $host == github.com ]] || repo="$host/$path"
      run gh pr create -R "$repo" --head "$branch" --base "$base" --title "$title" --body-file "$body"
    else
      run glab mr create --repo "https://$host/$path" --source-branch "$branch" --target-branch "$base" \
        --title "$title" --description-file "$body" --remove-source-branch --yes
    fi ;;
  whoami)  # your username on that host (FORGE_GIT_USER overrides, e.g. for tests)
    host=${1:-${FORGE_GIT_HOST:-github.com}}
    [[ -n ${FORGE_GIT_USER:-} ]] && { echo "$FORGE_GIT_USER"; exit 0; }
    if [[ $( (kind_of_host "$host") 2>/dev/null || echo unknown) == gitlab ]]; then
      # sed reads the JSON: on Windows the Python on PATH can be the Microsoft Store stub
      glab api user --hostname "$host" 2>/dev/null | sed -n 's/.*"username"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1
    else
      gh api user --hostname "$host" -q .login 2>/dev/null
    fi ;;
  auth-check)
    host=${1:-${FORGE_GIT_HOST:-github.com}}
    kind=$( (kind_of_host "$host") 2>/dev/null || echo unknown)  # own subshell: its `exit` must not end ours
    if [[ $kind == unknown ]]; then  # e.g. a company GitLab whose name has no "gitlab" in it: known after login
      echo "not logged in to $host yet: GitLab → glab auth login --hostname $host · GitHub Enterprise → gh auth login --hostname $host"
      exit 1
    elif [[ $kind == gitlab ]]; then
      command -v glab >/dev/null && glab auth status --hostname "$host" >/dev/null 2>&1 \
        && echo "glab: logged in to $host" || { echo "glab: not logged in to $host (run: glab auth login --hostname $host)"; exit 1; }
    else
      command -v gh >/dev/null && gh auth status --hostname "$host" >/dev/null 2>&1 \
        && echo "gh: logged in to $host" || { echo "gh: not logged in to $host (run: gh auth login --hostname $host)"; exit 1; }
    fi ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
