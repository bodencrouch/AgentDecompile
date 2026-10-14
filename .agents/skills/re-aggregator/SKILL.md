---
name: re-aggregator
description: "Use this skill when asked to merge several function analyses, resolve disagreements, or report RE consensus and remaining gaps."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
  role: aggregator
  argument-hint: "Batch of function artifacts, or all"
---

# RE Aggregator

Read [AGENTS](../../../AGENTS.md), [STRATEGY](../../../STRATEGY.md) and the
[artifact protocol](../../../.github/instructions/re-artifact-protocol.instructions.md).
Follow [USER_INTENT](../../../docs/USER_INTENT.md) for AgentDecompile's product
outputs. Aggregation may combine bounded evidence into a useful family-level
picture, but does not replace the corpus, matching-C pipeline, or target-bound
proof receipts.
Merge findings for the same fingerprint-bound instance or supported logical
identity. Never merge solely because addresses or confidence scores agree.

Preserve evidence and provenance per field and concrete build. Prefer stronger
supported names over placeholders, retain conflicting types and ABI/layout
witnesses, deduplicate xref facts, and keep unresolved gaps explicit. Where
available, summarize cross-build function/data/type/event candidates and their
divergences; retain parameter locations, runtime observations, and safety gaps
without inferring callability. A consensus score is advisory, not proof or
automatic mutation authority.

Return a concise synthesis with source/review locators, field decisions,
build-specific matches/divergences, unresolved conflicts, bounded analysis
convergence, and proposed next actions. Keep these statuses distinct: candidate
cross-match, readable source, freshly compiled matching C, full-image parity,
and runtime/event integration readiness. Do not apply changes unless authorized;
field-level propagation, source compilation, runtime safety, and per-build
verification gates remain governed by STRATEGY. Reassign useful gaps within task
and resource limits. Agreement among workers never substitutes for external
evidence.
