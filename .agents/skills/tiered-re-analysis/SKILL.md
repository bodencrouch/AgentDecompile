---
name: tiered-re-analysis
description: "Use this skill when starting reverse engineering, picking tools for a binary, or before open-project or decompile-function. Apply even if they only say look at this exe or what is in this binary, without naming Ghidra or tiers."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
---

# tiered-re-analysis

Default ladder: Tier 0 shell/static tools → Tier 1 batch `ghidrecomp`, BSim, or
native snapshot replay for JVM-free option sweeps and engine-regression checks →
Tier 2 MCP read-only inspection → Tier 3 decompile/mutation tools.

Use native snapshot replay only for exported savefile snapshots whose manifest
engine matches the native SDK. It is not a replacement for import, analysis, or
first decompile: producing the snapshot still requires Ghidra/Java once.
