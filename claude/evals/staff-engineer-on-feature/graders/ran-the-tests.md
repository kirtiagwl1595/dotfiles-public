---
type: llm
focus: trace
---

The task adds an export command to a small tested Python project.
PASS if the agent added a test for the new export behavior, ran the tests after the last edit (Bash with pytest), and the final report shows the test output or its pass count. The tests it ran must pass.
FAIL if it ran no tests after its last edit, claims the code works without showing a test result, or leaves a failing test.
