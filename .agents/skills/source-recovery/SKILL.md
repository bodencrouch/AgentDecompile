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
For the product inputs, binary-family cross-matching, and distinct recovery and
runtime outputs, follow [USER_INTENT](../../../docs/USER_INTENT.md). This skill
covers source recovery within that wider workbench; it does not reduce the
product to a decompiler or a collection of function-slice results.

Use the checkout-pinned `.venv/bin/agentdecompile-cli` from the repository root
for active recovery; frontends are deferred. Reuse existing local or shared
Ghidra project bytes and analysis when available rather than importing or
reanalyzing them unnecessarily. Treat related executables as separate concrete
builds in one family: inventory and reuse their analysis, cross-match candidate
functions/data/types, and preserve per-build identity and divergence. Use those
matches to guide recovery, but revalidate source, ABI, layout, and bytes for each
recipient before claiming a transferable result.

Corroborate existing source and receipts before producing more; resume/import is
valid for agents. Never label reused artifacts as fresh. Regenerate only missing,
invalid, dependency-affected, or explicitly requested work. Keep byte-accurate
C plus its explicit assembly/original-byte floor separate from max-C readable
source. Function-region compile/objdiff evidence is useful partial progress, not
whole-target completion. Terminal acceptance still requires the fresh whole-image
compiler/objdiff/relink checks in STRATEGY, with variants and receipts separately
accounted per target.

Runtime/event work is a connected but distinct output: where supported, preserve
build-bound event/callback identity, argument/parameter storage, ABI, state and
memory effects for Lua/native shim/DLL, calls, hooks, code caves or memory
modification. Runtime observations or a working intervention never prove
source parity; a source/objdiff receipt never proves runtime safety.

[Corpus pipeline](../../../docs/CORPUS_PIPELINE.md) and
[critical-path reference](../../../docs/CRITICAL_PATH.md) explain implementation.
[Runtime reuse](../../../docs/RUNTIME_REUSE.md) is a parallel branch and never
counts original-binary calls as recovered source. Follow AGENTS.md restrictions
on filesystem tests, systemctl, ports and duplicate compiler/Wine/Ghidra writers.
