# Route what the loop learned

Use this in the bundle step, for the Debrief and Lesson sections (R24, R25). Each finding goes to the one place where it changes the next run.

## Where each finding goes

| Kind | Example | Goes to | Who applies it |
|---|---|---|---|
| Repo fact | "the test suite needs `HOME` in a temp folder" | a proposed line for the repo's CLAUDE.md, in the debrief | the operator, after approve |
| Workflow | "write the stub test before the dry-run check" | a proposed change to this skill or a reference file, in the debrief | the operator |
| Deterministic check | "a check for the exit code of the download step" | a proposed check or test, in the debrief: checks and tests are protected during a loop | the operator, or the next loop's setup |
| Mistake | "the first fix patched one input" | the lesson, `.loop/lesson.md` | approve copies it to `.claude/lessons/` |
| Verifier gap | "no check covers the network failure" | the debrief's open risks, and the next `/safe-lean:loop-audit` | the operator |

## The debrief

One table row for each of: goal, result (scores before and after), causes, changes kept, changes reverted, rules added, open risks. Then the findings table above, with the real findings. Write "none" for an empty row: an empty row hides nothing, a missing row does.

## The lesson

- Write `.loop/lesson.md` as a short post with the story, the evidence and what to do next time. If the repo has its own lesson style guide, follow it.
- During a loop you write only inside the worktree. `/safe-lean:loop-approve` copies the lesson to the main checkout.
- Lessons are personal: `repo_setup.py` adds `.claude/lessons/` to each repo's managed `.gitignore` block, so they stay out of commits. Keep credentials, customer data and internal URLs out of them.
- In a team repo, a finding that a teammate needs to use, run or change the code is not a lesson: propose it as a doc change in the debrief.
