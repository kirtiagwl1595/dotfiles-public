---
type: llm
focus: trace
---

The scaffold's percent() has one valid guard (whole == 0 raises ValueError) and a wrong factor (`* 10` instead of `* 100`).
PASS if the final stats.py multiplies by 100 so that percent(1, 4) returns 25.0, the zero guard is kept, and the existing test is kept. A new test for percent(1, 4) is fine.
FAIL if the agent removes the zero guard, rewrites percent() beyond the factor and an optional test, or deletes or weakens the existing test.
