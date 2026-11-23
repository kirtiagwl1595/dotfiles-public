#!/usr/bin/env bash
# Time a login zsh: 1 warm-up run, then 5 timed runs of `zsh -il -c exit`. Print the median in ms.
#   scripts/bench-shell.sh          shell start: <n> ms (median of 5)
#   scripts/bench-shell.sh --json   {"median_ms": <n>, "runs": 5}
# perl gives ms timing on macOS and Linux (macOS date has no %N).
set -euo pipefail
RUNS=5
json=0
case ${1:-} in
  "") ;;
  --json) json=1 ;;
  *) echo "Unknown option: $1 (use --json or nothing)" >&2; exit 1 ;;
esac
command -v zsh >/dev/null || { echo "zsh not found" >&2; exit 1; }

ms=$(perl -MTime::HiRes=time -e '
  my $runs = shift; my @t;
  for my $i (0 .. $runs) {                      # run 0 is the warm-up
    my $s = time;
    system("zsh -il -c exit </dev/null >/dev/null 2>&1");
    push @t, int((time - $s) * 1000 + 0.5) if $i;
  }
  @t = sort { $a <=> $b } @t;
  print $t[$#t / 2];                            # odd count: the middle value
' "$RUNS")

if (( json )); then echo "{\"median_ms\": $ms, \"runs\": $RUNS}"
else echo "shell start: $ms ms (median of $RUNS)"; fi
