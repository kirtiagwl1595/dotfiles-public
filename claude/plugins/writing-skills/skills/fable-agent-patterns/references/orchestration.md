# Orchestration: how "Claude spins up agents"

## The ground truth

The model itself never spawns anything. Multi-agent behavior in Anthropic products is implemented in the harness, in two main shapes:

1. **Claude Code's Task tool.** The main session (orchestrator) calls a tool that starts a fresh instance of the same model with an empty context window, a written brief, and a restricted tool set. The subagent runs to completion and returns a single final message. The orchestrator never sees the subagent's intermediate steps: only the return. Subagents cannot spawn subagents and cannot talk to each other.

2. **Orchestrator–worker research (Anthropic's Research feature).** A lead agent decomposes a research question, dispatches several search workers in parallel, each worker runs its own search-read-digest loop in isolation, and the lead integrates the digests, dispatching follow-up workers for gaps.

Everything below is a host-agnostic specification of those two patterns. Any platform that can run N independent model calls can implement it; the "subagent" is just a fresh context with a good brief.

## When to spawn a worker (and when not to)

Spawn a worker for exactly three reasons:

1. **Context isolation.** The subtask requires ingesting bulk material (long logs, many search results, a large codebase scan) whose raw form would consume more than ~30% of the orchestrator's context. The worker eats the bulk and returns a digest of 500 tokens or less. The orchestrator never does bulk reading itself.
2. **Parallelism.** Two or more subtasks are independent: neither needs the other's output: and each is read-only or writes to disjoint targets. Independent research threads, per-file analysis, and per-source verification parallelize well.
3. **Role separation.** The subtask must be unbiased by the orchestrator's context. A grader evaluating output should not share context with the writer that produced it; a red-team reviewer should not see the author's justifications.

Do NOT spawn for: sequential steps (the loop handles those), trivial lookups (one tool call is cheaper than one worker), or tasks needing continuous back-and-forth with the user (workers can't talk to the user).

## Concurrency and safety rules

- Default fan-out: up to 4 concurrent workers. Hard cap: 8. Beyond that, coordination overhead and integration errors exceed the parallelism gain.
- Parallelize reads; serialize writes. Never let two workers write to the same file, resource, or record. One writer per target, enforced by the orchestrator's plan, not by hope.
- Spawn all independent workers in the same turn so they finish together, rather than dribbling them out.
- Workers never message each other. All state flows through the orchestrator. If worker B needs worker A's output, that is a sequential dependency: run A, integrate, then brief B with the relevant digest.
- Irreversible actions (send, delete, deploy, purchase) are never delegated to workers. The orchestrator performs them itself, after user confirmation.

## The worker brief

Workers wake up with amnesia: they see nothing except what the brief contains. A vague brief is the number one failure mode of multi-agent systems: workers duplicate each other's work or wander. Every brief has exactly these six fields:

```
OBJECTIVE: One sentence. The single question to answer or artifact to produce.

CONTEXT: Everything the worker needs and nothing else. Relevant file paths,
  prior findings (as digests, not raw dumps), definitions of project-specific
  terms. Assume zero shared memory.

TOOLS ALLOWED: Explicit list. A research worker gets search/fetch, not write.
  A file-fix worker gets read/edit on named paths only.

OUTPUT CONTRACT: Exact format of the return. e.g. "JSON with keys
  {finding, evidence_url, confidence}" or "unified diff only" or
  "digest ≤300 tokens, one claim per line, each with a source".

STOP CONDITIONS: Effort budget (e.g. "max 6 tool calls") and a success
  test ("stop when you have 3 corroborating sources or budget is spent").

DO NOT: The known failure modes for this subtask. e.g. "Do not modify
  tests", "Do not use secondary sources", "Do not summarize: extract verbatim
  field names".
```

## Integration

The orchestrator treats worker returns as claims, not facts:

- Spot-check at least one load-bearing claim per worker against a primary source or by direct read before building on it.
- If two workers conflict, do not average them. Dispatch a targeted verification worker or check directly, and record which one was wrong.
- If a worker returns off-contract output, do not massage it in place. Re-dispatch once with the contract violation named. Second failure → do the subtask yourself.
- After integration, run the orchestrator's own VERIFY step from the core loop on the assembled whole. Worker-level verification does not compose into whole-task correctness.

## Reference topologies

- **Fan-out/fan-in (research):** orchestrator decomposes question → 3–5 search workers in parallel, each briefed with a distinct sub-question and disjoint source types → digests return → orchestrator writes synthesis → one citation-check worker verifies every claim maps to a source.
- **Pipeline (code change):** scout worker (read-only, maps the relevant code, returns file:line map) → orchestrator plans the edit → editor applies surgical changes itself or via one write-scoped worker → test worker runs the suite in a clean context and returns pass/fail with logs digest.
- **Adversarial pair (quality):** producer worker generates the artifact → critic worker, briefed with the original user request and the artifact but not the producer's reasoning, returns a defect list → orchestrator fixes and repeats once. One round of critique captures most of the value; do not loop more than twice.

## Emulation on hosts without subagents

Most chat interfaces (including Claude's own consumer chat) have no spawn capability. Emulate the pattern sequentially inside one context:

1. Run each "worker" as a phase: announce the brief to yourself, execute it with the allowed tools, and end the phase by writing the digest that a real worker would have returned (respect the ≤500-token contract).
2. Immediately after writing the digest, treat the phase's raw material as dead: never quote or reference the raw logs/pages/results again: only the digest. This is the discipline that substitutes for a fresh context window.
3. For role separation, state the role switch explicitly and re-read the original user request (not your own prior output) before critiquing.

Sequential emulation loses wall-clock parallelism and true bias isolation but preserves the decomposition, the contracts, and most of the quality gain.
