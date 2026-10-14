---
name: agentdecompile-rewrite-worker
description: "Retired legacy rewrite-queue entrypoint. Do not invoke the old /loop workflow; use the current shared source-recovery contract."
license: AGPL-3.0-or-later
compatibility: Requires a recovery work_dir and the Agent/Task tool (no external LLM API)
metadata:
  author: AgentDecompile
  version: "1.0"
  argument-hint: "<work_dir>"
---

# Retired rewrite-queue entrypoint

The former canonical skill is not present in this checkout. Do not run the old
`/loop` rewrite-queue workflow or treat queued model rewrites as accepted source.
Use the current [source-recovery skill](../source-recovery/SKILL.md) and
[proof policy](../../../STRATEGY.md).

This legacy entrypoint is retained only so old references fail safely; it does
not define a current recovery path.
