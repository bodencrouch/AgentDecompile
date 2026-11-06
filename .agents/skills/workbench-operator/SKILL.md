---
name: workbench-operator
description: "Use this skill when working in /dashboard, dogfooding the workbench, or making the UI feel like IDA, Ghidra, or x64dbg. Apply even if they only say the dashboard is empty, boilerplate, or unusable."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
---

# Workbench operator

Read [AGENTS.md](../../../AGENTS.md) for operations and
[STRATEGY.md](../../../STRATEGY.md) for recovery policy. Use the existing 8080
workbench and its action catalog.

Open the intended existing repository/program. If functions are absent, inspect
selection, Ghidra analysis and corpus program binding before initiating work.
An empty UI does not authorize forced Analyze or BSim regeneration. Reuse valid
analysis and receipts; run only justified missing stages through the catalog.
Inspect real function interactions and resulting evidence; job success or a
screenshot is not recovery proof.

Static workbench source remains `dashboard/static/workbench-app.js`; React
source lives in `dashboard/frontend/` with packaged assets in `static/react/`.
Consult the [interface guide](../../../src/agentdecompile_recovery/corpus/dashboard/frontend/README.md)
and the active 8080 serving mode. React is the strategy; source/asset presence
does not prove a completed migration or runtime parity. Do not restart, kill
on-port or switch ports for validation. Follow AGENTS.md ownership and mission
constraints; [runtime reuse](../../../docs/RUNTIME_REUSE.md) has separate gates.
