---
name: step-back
description: Stops patch-on-patch code. Use before you edit a function that already has a special case or ticket comment for one input, also for a quick or urgent fix and also when you already plan a general rewrite; before adding a 2nd special case (branch, flag, guard or test for one input) to the same function or idea; when the churn_watch hook says a file was edited many times, after 3 failed fixes, or when the user says band-aid, patch, hack or step back. Rewrites the code to one general rule and deletes the earlier patches.
---

# Step back

A band-aid passes its test, so a failing test never stops it. A 2nd special case on one idea is the signal.

## Steps
1. Stop editing. List every patch on this idea so far: `git diff`, and the tests added in this session.
2. Write the real rule in 1 to 3 lines. The rule must explain all cases, the new one included, with no case named by its input.
   If no such rule exists, the cases are different features: say so and keep them apart.
3. Give 2 designs that follow the rule (design it twice; the `mattpocock-skills:codebase-design` skill helps, if installed). Pick one and say why.
4. Rewrite the code to the rule. Delete the earlier patches, and the code they made dead.
5. Fold the scenario tests into one parametrized test at the seam.
   Every existing scenario stays as a row, and no assertion is removed or weakened. The test diff must show this.
6. Run the tests. Report the rule, and the lines added and deleted.

If a test stops you from writing the general rule, the test may be wrong. Say so; do not work around it.

## Band-aid smells
Check the diff for these before you report:
- A branch for the input that the bug report or test used.
- A guard where the error showed, not where the bad value was made.
- A flag parameter that switches the behavior of a function.
- A near-copy of a function with one line changed.
- A hard-coded value that matches a test value.
- `try`/`except` that swallows an error or returns a default.
- A comment such as "workaround for", "special case", "hack", or "temporary".
- One test for each scenario where one table would do.
- Error handling for a case that cannot happen. Validate only at system boundaries.
- Code longer than the rule needs: if 200 lines could be 50, rewrite it.

## Verification
Eval case `claude/evals/step-back-on-patches`: the skill fires on a quick-fix prompt, and the final code has one general rule with every test case kept.
