---
slug: <slug>
target_type: script
target: <path or goal>
max_iterations: 3
threshold: all
---
## Goal
<One sentence: the business outcome this loop serves.>

## Loop type
goal-based: the loop stops when the checks in loop-features.json pass, at the cap, or after 2 iterations with no gain.

## Verifier
python3 -B .loop/bin/loopctl.py verify; the checks are in loop-features.json.

## Scope
may change: <paths>; must not change: <paths>

## Iteration log
