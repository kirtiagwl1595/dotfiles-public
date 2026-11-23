#!/usr/bin/env bash
# Pack this repo into one file to carry to another computer (USB stick, file share, mail).
#   scripts/make-bundle.sh            → push main (if origin exists), then ~/Desktop/dotfiles.bundle
#   scripts/make-bundle.sh <out>      → bundle only, at <out> (no push; used by tests)
# On the other computer, put the file in ~/Downloads: scripts/import-bundle.sh applies it.
# (first time: b=$(ls -t ~/Downloads/dotfiles*.bundle | head -1); git clone "$b" <folder>)
set -euo pipefail
cd "$(dirname "$0")/.."
default_out=$HOME/Desktop/dotfiles.bundle
[[ -d $HOME/Desktop ]] || default_out=$HOME/dotfiles.bundle
out=${1:-$default_out}
dirty=$(git status --porcelain)
if [[ $# -eq 0 ]]; then
  [[ -z $dirty ]] || { echo "Commit or stash first; uncommitted changes would not travel:"; echo "$dirty"; exit 1; }
  [[ $(git branch --show-current) == main ]] || { echo "Switch to main first (the bundle carries main)."; exit 1; }
  if git remote get-url origin >/dev/null 2>&1; then
    git push -q origin main && echo "pushed main to origin" || echo "! push to origin failed; the bundle is still made"
  fi
else
  [[ -z $dirty ]] || echo "Note: uncommitted changes are not in the bundle."
fi
git bundle create -q "$out" HEAD main  # HEAD too, or a clone has no branch to check out
git bundle verify -q "$out"
echo "$out: $(git log --oneline -1 main)"
if [[ $# -eq 0 ]]; then
  if command -v open >/dev/null && [[ $OSTYPE == darwin* ]]; then open -R "$out"; fi
  echo "Carry this file to the other computer."
fi
exit 0
