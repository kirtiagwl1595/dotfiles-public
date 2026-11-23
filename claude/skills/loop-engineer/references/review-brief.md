# The review brief

Use this in the bundle step. The `safe-lean:loop-reviewer` agent reviews the result once (R12). It must see the result, not the session, so give it only this brief.

## The prompt

```text
Goal: <the LOOP.md goal sentence>
Causes:
<each Cause: line from .loop/loop-progress.md>
Worktree: <absolute path>
Gate warnings to decide: <rule, file:line, text; or "none">
Diff (git diff <base>..HEAD -- . ':(exclude).loop'):
<the diff>
```

- `base` is in `.loop/run.json`.
- A diff of more than about 1500 lines: give `git diff --stat` and the changed paths in its place. The reviewer reads the files in the worktree.
- Do not add your own view of the change, the iteration log or the scores. A reviewer that reads the author's reasons judges the reasons, not the code.

## Gate warnings

The gate only warns about these, and the reviewer decides each one:

- `hard-coded`: a new literal path, host or ID in code.
- `design`: more than 3 code files changed, or a changed public `def` or CLI flag. The bundle's Design note section is then required: the options, the choice, and why.
- A rule added for one example, and rules that contradict each other: the gate cannot see these.

## Into the bundle

In the Reviewer answers section, copy the 3 answers and the verdict line as the reviewer wrote them. Do not soften them.

- `Verdict: reject`: say so first in the debrief, and recommend that the operator does not approve.
- `Verdict: accept with risks`: copy each risk to the debrief's open risks.
