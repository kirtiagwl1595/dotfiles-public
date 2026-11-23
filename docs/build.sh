#!/usr/bin/env bash
# Build docs/guide.html from GUIDE.md: one self-contained file that opens in any browser, also offline.
# Needs pandoc. Runs in bash on macOS, Linux and Git Bash (Windows).
#   docs/build.sh          builds docs/guide.html (commit it)
#   docs/build.sh <out>    builds <out>
set -euo pipefail
cd "$(dirname "$0")/.."
out=${1:-docs/guide.html}
pandoc GUIDE.md --standalone --toc --toc-depth=2 --embed-resources \
  --css docs/guide.css --metadata lang=en -o "$out"
echo "built $out"
