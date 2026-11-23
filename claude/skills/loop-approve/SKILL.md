---
name: loop-approve
description: Approves the bundle of a finished loop. The loop hook creates feature/loop-<slug>, copies the bundle and the lesson into this checkout and archives the loop; this skill shows what was approved. Use when the user types /safe-lean:loop-approve <slug>.
disable-model-invocation: true
argument-hint: "<slug>"
---

# Loop approve

The typed command is the approval. The loop hook acted when the prompt was sent, and its message is in your context. Do not run git writes, and do not copy or move files yourself.

1. If the hook refused (the prompt was blocked, or there is no "Approved loop" message), show its reason and stop.
2. Show the summary from the hook message, in a short table: the goal, the scores before and after, the gate verdict and its secret scanner (`regex` means gitleaks did not run; "not recorded" is a 0.6.0 loop), the reviewer's verdict line, and the final tokens (the bundle stops at the last Stop before it). Do not read the copied bundle for these: a session in the loop worktree often cannot read the main checkout.
3. For the open risks, read the Debrief of the copied `bundle.md` that the message names. If the read is denied, say so, and tell the operator to read that file.
4. Give the next steps. Do not do them:
   1. Review the branch: `git log --oneline main..feature/loop-<slug>` and `git diff main...feature/loop-<slug>`.
   2. In a repo that holds the loop engine (this repo or a fork), if the loop changed `claude/`, bump the version in `claude/.claude-plugin/plugin.json`: the loop could not, because the file is protected.
   3. After review, push the branch and open a PR with `forge.sh pr-create`.
   4. When the PR is merged, remove the loop worktree: `git worktree remove <path>`.
