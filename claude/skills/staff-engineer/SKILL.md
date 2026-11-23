---
name: staff-engineer
description: Staff-engineer workflow for a code change that adds or changes behavior. Use before you read or edit the code when asked to add a command, option, endpoint or feature, to change a design, to edit several files, or to change code that other people or scheduled jobs depend on. Not for questions, one-line fixes, throwaway scripts, docs or config edits.
---

# Staff engineer

## Before code
1. Read the existing code, its tests and its conventions. Follow them.
2. State the problem and the constraints in 2 to 4 lines.
3. Give 2 options with their trade-offs. Pick one and say why.

## Code
4. Work test-first: write a failing test, make it pass, then refactor. If the `mattpocock-skills` plugin is installed, use `mattpocock-skills:tdd`; it is then the only TDD workflow.
5. Fix the cause with the simplest design that covers all valid inputs. A change that replaces 2 patches with 1 rule is the smaller change. Do not add abstractions that nobody asked for.
6. Handle errors, timeouts and retries at system boundaries. Do not add handling for cases that cannot happen. Do not swallow an error.
7. Before you add a 2nd special case to the same function or idea, use `safe-lean:step-back`.

## Operate
8. Name the failure modes of the change.
9. Name the logging or metrics that show each failure.
10. Name the rollback path.

## Before you report
11. Review your own diff as a skeptical reviewer. Check it for the band-aid smells in `safe-lean:step-back`. Fix what you find.
12. Do not say the code works unless you ran it. Show the test output.
13. Before a PR, suggest `/security-review`. Do not run it yourself.

## Verification
Eval case `staff-engineer-on-feature` (`claude/evals/`): a feature request on a small tested project. It checks that this skill fires, that 2 options come before the first edit, that the final report names failure modes, logging and rollback, and that the tests run and show a result.
