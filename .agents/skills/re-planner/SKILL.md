---
name: re-planner
description: "Use this skill when the user wants a plan for a binary, triage of an executable, or the multi-agent RE pipeline. Do not decompile here; dispatch workers."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
  role: planner
  argument-hint: "Binary path or program name"
---

# RE Planner

Read [AGENTS](../../../AGENTS.md), [STRATEGY](../../../STRATEGY.md) and
[tiered routing](../tiered-re-analysis/SKILL.md). Coordinate only within the
authorized task; independent read-only work may run concurrently after ownership
and resource checks. Recovery actions use the existing 8080 catalog.

1. Reuse corpus inventory, program bindings and provenance-bound receipts.
2. Define bounded work by corpus/build fingerprint, logical identity where known,
   and instance address plus focused question. Do not create a separate mandatory
   `/analysis` authority; attach optional artifacts to the existing work context
   using the [artifact protocol](../../../.github/instructions/re-artifact-protocol.instructions.md).
3. Assign worker analysis, independent critic review and aggregation where useful.
   Retain contradictions and named unknowns.
4. Report evidence, remaining work and next action against the requested outcome.

Confidence and review convergence are advisory. Neither establishes recovered
source, runtime readiness, full corpus completion or permission to propagate.
STRATEGY owns priorities and acceptance; bounded triage completion is only triage.
