---
name: tiered-re-analysis
description: "Use this skill when starting reverse engineering, picking tools for a binary, or before open-project or decompile-function. Apply even if they only say look at this exe or what is in this binary, without naming Ghidra or tiers."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
---

# Tiered RE analysis

Read [AGENTS](../../../AGENTS.md) before operations and [STRATEGY](../../../STRATEGY.md)
for matcher order and acceptance. Active recovery uses the checkout-pinned
`.venv/bin/agentdecompile-cli` from the repository root; frontends are deferred.
Reuse existing local or shared Ghidra project bytes and analysis when available.

| Tier | Use |
|---|---|
| 0 | Existing metadata, file triage, strings and static witnesses |
| 1 | Stored batch decompilation, BSim, export evidence and compatible native snapshot replay |
| 2 | Read-only queries against existing analyzed Ghidra state |
| 3 | Missing deep analysis or authorized mutations after ownership checks |

Choose the cheapest sufficient evidence. First resolve program bindings and
stored analysis; an empty view or a false session flag alone does not justify
reanalysis. Reuse valid receipts, retain conflicts, and serialize shared writers.
These tiers classify evidence and operations; they do not reorder the corpus
matcher or prove recovery. Inspect the pinned CLI's current help for available
operations. Do not repeat import or analysis already present in a usable project.

Historical [routing research](../../../docs/solutions/architecture-patterns/tiered-re-analysis-knowledgebase.md)
is reference-only where its storage, confidence or operating rules differ.

Use native snapshot replay only for exported savefile snapshots whose manifest
engine matches the native SDK. Producing the snapshot still requires Ghidra and
Java once, so replay does not replace import, analysis or the first decompile.
