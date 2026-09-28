---
name: source-recovery
description: "Use this skill when the user wants recovered C, objdiff, --dump-source, rematch, or reconstruct. Do not treat leftover target/ receipts as this run's source."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
---

# Source recovery

Read [AGENTS.md](../../../AGENTS.md) for operations and
[STRATEGY.md](../../../STRATEGY.md) for the single recovery policy.

Use the existing 8080 catalog. Inventory and corroborate existing analysis,
source and receipts before producing more; resume/import is valid for agents.
Never label reused artifacts as a fresh run. Regenerate only missing, invalid
or explicitly requested work. Terminal acceptance still requires the fresh
whole-image compiler/objdiff/relink checks in STRATEGY, with C+assembly-floor
and max-C variants separately accounted.

[Corpus pipeline](../../../docs/CORPUS_PIPELINE.md) and
[critical-path reference](../../../docs/CRITICAL_PATH.md) explain implementation.
[Runtime reuse](../../../docs/RUNTIME_REUSE.md) is a parallel branch and never
counts original-binary calls as recovered source. Follow AGENTS.md restrictions
on filesystem tests, systemctl, ports and duplicate compiler/Wine/Ghidra writers.
