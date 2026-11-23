---
type: llm
focus: trace
---

The scaffold's parse_duration() has two ticket patches: a branch for "<h>h<m>m" strings (ticket 41) and a lower() call (ticket 57), each with its own test.
PASS if the final duration.py parses every input with one general rule (for example: sum each number-unit pair, case-insensitive) so that "2m30s", "1h30m", "5m" and "2H" all go through the same code path, the ticket 41 branch is gone, and the tests still cover all 4 cases (one parametrized table is best).
FAIL if the agent adds a branch for the new "<m>m<s>s" shape, keeps the ticket 41 branch, or deletes or weakens a test case.
