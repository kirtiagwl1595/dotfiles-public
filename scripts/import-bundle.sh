#!/usr/bin/env bash
# Apply a bundle made by scripts/make-bundle.sh: fast-forward main, push it to origin (if there is one),
# say when install.py must run again, then delete the bundle. Run it by hand when a
# ~/Downloads/dotfiles*.bundle file has arrived.
# It asks first: a bundle changes hooks and rules. With no terminal it stops, unless DOTFILES_IMPORT_YES=1.
# It never merges or resets: a dirty repo, another branch or a diverged history stops it, bundle kept.
set -euo pipefail
DOT=${DOTFILES:-$(cd "$(dirname "$0")/.." && pwd)}
DOWNLOADS=${DOWNLOADS:-$HOME/Downloads}
LOCK=${TMPDIR:-/tmp}/dotfiles-import.lock
SETUP_FILES="install.py packages/packages.json claude/settings.base.json claude/merge_settings.py"

shopt -s nullglob
bundles=("$DOWNLOADS"/dotfiles*.bundle)
(( ${#bundles[@]} )) || exit 0
mkdir "$LOCK" 2>/dev/null || exit 0  # another terminal is importing
trap 'rmdir "$LOCK"' EXIT

newest=$(ls -t "${bundles[@]}" | head -1)
echo "dotfiles: importing $(basename "$newest")"
stop() { echo "  ! $*"; echo "  bundle kept in $DOWNLOADS; fix this, then run $DOT/scripts/import-bundle.sh"; exit 1; }

cd "$DOT" || stop "no repo at $DOT"
git bundle verify -q "$newest" 2>/dev/null || stop "$(basename "$newest") is not a complete bundle (copy it again?)"
[[ $(git branch --show-current) == main ]] || stop "$DOT is not on main"
[[ -z $(git status --porcelain) ]] || stop "$DOT has uncommitted changes"
before=$(git rev-parse HEAD)
head=$(git bundle list-heads "$newest" refs/heads/main | cut -d' ' -f1)
if [[ $head != "$before" ]]; then
  # Fetch only (no branch moves) so the commits and files are on screen before the question
  git fetch -q "$newest" main 2>/dev/null || stop "cannot read main from $(basename "$newest")"
  echo "  incoming commits:"
  git log --stat --format='%h %s' "$before..$head" | sed 's/^/      /'
fi
if [[ $head != "$before" && ${DOTFILES_IMPORT_YES:-} != 1 ]]; then
  [[ -t 0 ]] || stop "no terminal to confirm the import"
  read -r -p "  Fast-forward main to ${head:0:7}? [y/N] " answer
  [[ $answer == [yY] ]] || stop "import declined"
fi
git pull -q --ff-only "$newest" main 2>/dev/null \
  || stop "this computer has commits the bundle does not have. Bundle them back first (make-bundle.sh), or: git pull --rebase $newest main"
after=$(git rev-parse HEAD)

if [[ $before == "$after" ]]; then echo "  ✓ already up to date ($(git log --oneline -1))"
else
  echo "  ✓ updated: $(git log --oneline -1)"
  git log --oneline "$before..$after" | sed 's/^/      /'
  if git remote get-url origin >/dev/null 2>&1; then
    GIT_TERMINAL_PROMPT=0 git push -q origin main 2>/dev/null && echo "  ✓ pushed main to origin" \
      || echo "  ! push to origin failed (VPN or login?); run: git -C $DOT push origin main"
  fi
  echo "  → restart Claude Code to load the new rules, hooks and skills"
  # shellcheck disable=SC2086 # SETUP_FILES is a list of paths without spaces
  setup=$(git diff --name-only "$before" "$after" -- $SETUP_FILES)  # files install.py copies or acts on
  [[ -z $setup ]] || { echo "  changed setup files:"; echo "$setup" | sed 's/^/      /'; echo "  → run: python3 $DOT/install.py"; }
  [[ -z $(git diff --name-only "$before" "$after" -- shell) ]] \
    || echo "  → new shell config: open a new terminal (or: exec zsh -l)"
fi

rm -f "${bundles[@]}"
if command -v osascript >/dev/null; then
  osascript -e "display notification \"$(git log --oneline -1 | sed 's/"//g')\" with title \"dotfiles updated\"" 2>/dev/null || true
fi
