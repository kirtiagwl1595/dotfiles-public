#!/usr/bin/env bash
# Apache Jena from the official archive, run by Temurin (the brew jena formula forces openjdk).
# macOS and Linux. Windows: scripts/install-jena.ps1.
# Usage: install-jena.sh [--dry-run] [X.Y.Z]   (--dry-run prints the plan and changes nothing)
# Needs a Java: package temurin (profile full), or any JDK. Writes ~/.local/share/jena-<version>
# and wrappers in ~/.local/bin.
# JAVA_HOME_CMD overrides the Java finder (default: /usr/libexec/java_home on macOS, else $JAVA_HOME
# or the folder of `java`); the tests use it.
# Undo: rm -rf ~/.local/share/jena-* ~/.local/bin/riot ~/.local/bin/sparql ~/.local/bin/arq
set -euo pipefail

usage() {
  echo "Usage: install-jena.sh [--dry-run] [X.Y.Z]" >&2
  exit 2
}

dry_run=0
versions=()
for arg in "$@"; do
  case $arg in
    --dry-run) dry_run=1 ;;
    *) versions+=("$arg") ;;
  esac
done
((${#versions[@]} <= 1)) || usage
VERSION=${versions[0]:-6.2.0}
# The version goes into a URL and a folder name: accept only digits and dots.
[[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || usage

NAME=apache-jena-$VERSION
URL=https://archive.apache.org/dist/jena/binaries/$NAME.tar.gz
DEST=$HOME/.local/share/jena-$VERSION
BIN=$HOME/.local/bin
JAVA_FINDER=${JAVA_HOME_CMD:-}
[[ -z $JAVA_FINDER && -x /usr/libexec/java_home ]] && JAVA_FINDER=/usr/libexec/java_home

if [[ -n $JAVA_FINDER ]]; then
  "$JAVA_FINDER" >/dev/null 2>&1 || { echo "No Java: install the temurin package first." >&2; exit 1; }
else
  command -v java >/dev/null 2>&1 || [[ -n ${JAVA_HOME:-} ]] || { echo "No Java: install the temurin package first." >&2; exit 1; }
fi

if ((dry_run)); then
  echo "Dry run: would download $URL"
  echo "Dry run: would install into $DEST and write wrappers in $BIN"
  exit 0
fi

# An explicit template: bare `mktemp -d` on macOS ignores TMPDIR.
tmp=$(mktemp -d "${TMPDIR:-/tmp}/install-jena.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
fetch() { curl -fsSL "$@" || { echo "Download failed: $URL" >&2; exit 1; }; }
sha512_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 512 "$1" | awk '{print $1}'
  else sha512sum "$1" | awk '{print $1}'; fi
}

fetch "$URL" -o "$tmp/jena.tar.gz"
want=$(fetch "$URL.sha512" | awk '{print $1}')
have=$(sha512_of "$tmp/jena.tar.gz")
[[ -n $want && $want == "$have" ]] || { echo "Checksum mismatch: nothing installed." >&2; exit 1; }

# Unpack into a staging folder first, so a broken archive leaves no half install.
mkdir -p "$tmp/stage"
tar xzf "$tmp/jena.tar.gz" -C "$tmp/stage" --strip-components=1 || { echo "Unpack failed: nothing installed." >&2; exit 1; }
[[ -d $tmp/stage/bin ]] || { echo "Unpack failed: no bin folder in $NAME. Nothing installed." >&2; exit 1; }

mkdir -p "$(dirname "$DEST")" "$BIN"
# Move the old install aside, not away: if the new one cannot take its place, put the old one back.
old=$DEST.old.$$
[[ -e $DEST ]] && mv "$DEST" "$old"
if ! mv "$tmp/stage" "$DEST"; then
  [[ -e $old ]] && mv "$old" "$DEST"
  echo "Install failed: the old install is unchanged." >&2
  exit 1
fi
rm -rf "$old"
for tool in riot sparql arq; do
  [[ -x $DEST/bin/$tool ]] || continue
  if [[ -n $JAVA_FINDER ]]; then
    # %q quotes each path for the shell, so a folder name with spaces still works.
    printf '#!/bin/sh\nexport JAVA_HOME="$(%q)"\nexec %q "$@"\n' "$JAVA_FINDER" "$DEST/bin/$tool" >"$BIN/$tool"
  else
    # No finder (Linux): use $JAVA_HOME, else the folder two levels above the real java
    printf '#!/bin/sh\nif [ -z "$JAVA_HOME" ]; then JAVA_HOME=$(dirname "$(dirname "$(readlink -f "$(command -v java)")")"); export JAVA_HOME; fi\nexec %q "$@"\n' "$DEST/bin/$tool" >"$BIN/$tool"
  fi
  chmod +x "$BIN/$tool"
done
"$BIN/sparql" --version
