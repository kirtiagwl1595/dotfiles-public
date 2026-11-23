#!/usr/bin/env bash
# Fail when a package manager does not know a name in packages/packages.json.
#   scripts/check-package-names.sh <brew|apt|winget> [manifest.json]
# brew: `brew info`; apt: `apt-cache show`; winget: `winget show --exact`. It only reads; it installs nothing.
# Plain names only: a Homebrew tap name (owner/tap/name) fails, because the manifest taps nothing.
set -euo pipefail
here="${BASH_SOURCE[0]%/*}"
manager=${1:-}
manifest=${2:-}
case $manager in
  brew | apt | winget) ;;
  *) echo "Usage: check-package-names.sh <brew|apt|winget> [manifest.json]" >&2; exit 2 ;;
esac

find_python() {
  for py in python3 python "py -3"; do
    # $py unquoted on purpose: "py -3" is a program and an option
    if $py -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then echo "$py"; return 0; fi
  done
  return 1
}
py=$(find_python) || { echo "check-package-names.sh needs Python 3.9 or later." >&2; exit 1; }

export HOMEBREW_NO_AUTO_UPDATE=1
# One "<kind> <name>" line per package: kind is brew, cask, apt or winget
# shellcheck disable=SC2086
lines=$($py "$here/../packages/pkgs.py" names "$manager" ${manifest:+"$manifest"})
lines=${lines//$'\r'/}

known() {  # known <kind> <name>
  case $1 in
    brew) brew info --formula "$2" ;;
    cask) brew info --cask "$2" ;;
    apt) apt-cache show "$2" ;;
    winget) winget show --id "$2" --exact ;;
  esac >/dev/null 2>&1
}

bad=0
while read -r kind name; do
  [[ -n $name ]] || continue
  if [[ $name == */* ]]; then echo "tap name $kind \"$name\" (plain names only)" >&2; bad=1; continue; fi
  known "$kind" "$name" || { echo "unknown $kind \"$name\"" >&2; bad=1; }
done <<<"$lines"
[[ $bad == 0 ]] && echo "all $manager names are known"
exit "$bad"
