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
and resource checks. Active recovery uses the checkout-pinned
`.venv/bin/agentdecompile-cli` from the repository root; frontends are deferred.
Reuse existing local or shared Ghidra project bytes and analysis when available.

Treat the requested scope as a family of concrete builds when the project
contains related binaries: preserve each build's identity and divergence while
planning cross-match, matching-C recovery, and supported runtime/event work as
connected outputs. Follow [USER_INTENT](../../../docs/USER_INTENT.md) for that
product contract. A function-by-function assignment is a bounded tactic, not the
default product boundary; use the shared pipeline and avoid duplicate inventories,
compiler/toolchain work, or independent authorities.

1. Reuse corpus inventory, program bindings, cross-build links and
   provenance-bound receipts.
2. State the selected build set, evidence/output requested, proof scope, and
   dependencies. Bound work to an actual build/region/pair or runtime operation
   only as needed; keep optional artifacts in the existing work context.
3. Assign independent inventory, matching, source, review, or runtime work only
   where branches are genuinely independent and resources permit. Serialize
   writers to shared projects, corpora, compiler state, or target processes.
   Retain contradictions and build-specific unknowns.
4. Report evidence per target and claim type: cross-match candidates, compiled
   source/objdiff results, whole-image proof, and runtime/event readiness must not
   collapse into one confidence or completion status.

Confidence and review convergence are advisory. Neither establishes recovered
source, runtime readiness, full corpus completion or permission to propagate.
STRATEGY owns priorities and acceptance; bounded triage completion is only triage.
