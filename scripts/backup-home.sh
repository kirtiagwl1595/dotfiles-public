#!/usr/bin/env bash
# Full home-folder archive before big changes. macOS and Linux.
#   scripts/backup-home.sh <destination folder> [--include-photos]
# Builds a file list with find, archives exactly that list (plain tar recursion silently skips folders
# after a permission error), then checks entry count == list count. Writes a README.
# The archive holds ~/.ssh and ~/.gnupg, so it is encrypted with age to the public keys in
# $BACKUP_AGE_RECIPIENTS (default ~/.config/dotfiles-public/backup-recipients.txt). Only public keys
# are needed here; keep the private identity outside this computer (password manager or paper).
# Leaves out caches, Trash, node_modules, .venv, the destination itself and (unless asked) the macOS Photos library.
# Works with bash 3.2 (macOS), with bsdtar and with GNU tar.
set -euo pipefail
DEST=${1:?usage: backup-home.sh <destination folder> [--include-photos]}
PHOTOS=${2:-}
[[ -d $DEST && -w $DEST ]] || { echo "Destination is not a writable folder: $DEST"; exit 1; }
RECIPIENTS=${BACKUP_AGE_RECIPIENTS:-$HOME/.config/dotfiles-public/backup-recipients.txt}
command -v age >/dev/null || { echo "age is missing: install it with your package manager (profile full has it)"; exit 1; }
if [[ ! -s $RECIPIENTS ]]; then
  echo "No age recipient file at $RECIPIENTS: the archive would hold SSH keys unencrypted."
  echo "Once: age-keygen -o <a safe place outside ~>, then put its 'public key: age1...' value in $RECIPIENTS."
  exit 1
fi

NAME=$(hostname -s 2>/dev/null || hostname)
OUT="$DEST/home-$NAME-$(date +%Y-%m-%d-%H%M)"
mkdir -p "$OUT"
LIST="$OUT/files.txt"

cd "$HOME"
prune_photos=(-path "./Pictures/Photos Library.photoslibrary")
[[ $PHOTOS == --include-photos ]] && prune_photos=(-path ./__no_such_path__)
# A destination inside home would archive the earlier archives (and this one) again
home_real=$(pwd -P) dest_real=$(cd "$DEST" && pwd -P)
prune_dest=(-path ./__no_such_path__)
[[ $dest_real == "$home_real"/* ]] && prune_dest=(-path "./${dest_real#"$home_real"/}")
echo "Listing files in $HOME …"
find . \( -path ./Library/Caches -o -path ./.Trash -o -path ./.cache -o -path ./.npm \
  -o -name node_modules -o -name .venv -o -name __pycache__ -o "${prune_photos[@]}" -o "${prune_dest[@]}" \) -prune \
  -o \( -type f -o -type l \) -print 2>"$OUT/find-errors.txt" >"$LIST" || true
listed=$(wc -l <"$LIST" | tr -d ' ')
need_kb=$(du -sk "$HOME" 2>/dev/null | cut -f1 || echo 0)
free_kb=$(df -k "$DEST" | awk 'NR==2 {print $4}')
echo "$listed files; home is about $((need_kb / 1048576)) GB before compression, $((free_kb / 1048576)) GB free at the destination."
[[ $free_kb -gt $((need_kb / 2)) ]] || { echo "Probably not enough space at $DEST. Stopping."; exit 1; }

echo "Archiving and encrypting (this can take a long time; keep the computer awake) …"
# tar's verbose list counts what went in (bsdtar: "a ./file", GNU tar: "./file", both on stderr);
# the plain archive never touches the disk. tar may fail on single unreadable files (counted below);
# an age failure stops the backup. caffeinate (macOS) keeps the Mac awake.
keep_awake=()
command -v caffeinate >/dev/null && keep_awake=(caffeinate -i)
set +e
"${keep_awake[@]}" tar -czvf - -T "$LIST" 2>"$OUT/tar-log.txt" | age -R "$RECIPIENTS" -o "$OUT/home.tar.gz.age"
status=("${PIPESTATUS[@]}")
set -e
[[ ${status[1]} == 0 ]] || { echo "age failed (exit ${status[1]}): no usable archive in $OUT"; exit 1; }
archived=$(grep -cE '^(a )?\./' "$OUT/tar-log.txt" || true)
grep -vE '^(a )?\./' "$OUT/tar-log.txt" >"$OUT/tar-errors.txt" || true
rm -f "$OUT/tar-log.txt"
missing=$((listed - archived))
cat >"$OUT/README.md" <<EOF
# Home backup of $NAME, $(date '+%Y-%m-%d %H:%M')

- Archive: \`home.tar.gz.age\` (age, to the keys in $RECIPIENTS), $archived of $listed listed files ($missing missing; see tar-errors.txt)
- Left out: caches, Trash, node_modules, .venv, __pycache__, the destination$([[ $PHOTOS == --include-photos ]] || echo ", Photos library")
- Check it: \`age -d -i <identity file> "$OUT/home.tar.gz.age" | tar -tzf - | wc -l\` (should print $archived)
- Restore one file: \`age -d -i <identity file> "$OUT/home.tar.gz.age" | tar -xzf - -C ~ ./path/to/file\`
EOF
echo "Done: $OUT ($archived of $listed files; $missing missing, usually protected system files)."
[[ $missing -le $((listed / 100)) ]] || { echo "More than 1% of files are missing: check $OUT/tar-errors.txt before changing anything."; exit 1; }
