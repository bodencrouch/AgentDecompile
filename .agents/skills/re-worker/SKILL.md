---
name: re-worker
description: "Use this skill when asked to analyze, decompile, or type a single function and return a JSON artifact. Not for coordinating other agents."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
  role: worker
---

# RE Worker

Read [AGENTS](../../../AGENTS.md) and [STRATEGY](../../../STRATEGY.md) first.
For the product's binary-family inputs, matching-C outputs, runtime surface, and
distinct proof claims, follow [USER_INTENT](../../../docs/USER_INTENT.md).
Active recovery uses the checkout-pinned `.venv/bin/agentdecompile-cli` from the
repository root; frontends are deferred. Reuse existing local or shared Ghidra
project bytes and analysis when available. Preserve project restrictions on
tests, startup and process ownership.

This role performs bounded evidence gathering, often for one function. Its JSON
record is an optional work artifact, not AgentDecompile's product output or an
independent analysis authority. The overall task may instead or additionally
cover cross-build matches, recovered C/C++, data/types, runtime events, or
target-bound call/hook/memory evidence. Do not turn a one-function assignment
into a whole-product workflow, or treat a function record as recovery proof.
Return the requested record to the coordinating task; do not create a parallel
corpus. No coordination unless the assigned task explicitly asks for it.

**REQUIRED SUB-SKILL:** `tiered-re-analysis`

## Rules

1. Every claim needs evidence (decomp, xrefs, constants, or an identified runtime witness). No hallucinated types or names — use `UNKNOWN`.
2. Confidence 0.0–1.0. List gaps. Do not overwrite stronger prior findings.
3. Compare decompile vs disassembly. Do not trust the decompiler blindly.
4. Discovery-only (exists? callers?): Tier 2. Semantics/types: Tier 3. Never `execute-script` when an advertised tool exists.

## Procedure

1. `get-function` then `get-functions` decompile **and** disassemble. Flag mismatches.
2. Extract arguments and parameter storage, calling convention, return, constants, memory effects, and control flow where evidence permits.
3. `get-references` to/from, `get-call-graph`, `list-cross-references`. Check caller/callee type fit.
4. If other family builds are in scope, record candidate logical correspondence and build-specific divergence as separate witnesses; identity or similarity is not interchangeability.
5. If events/callbacks or runtime behavior are in scope, record observed event identity, argument locations/types, process/build, ABI, and limitations. Observation does not establish that a call, hook, cave, shim, DLL, or memory edit is safe.
6. Patterns: parse, crypto, alloc, errors, vtables, buffer walks.
7. Return the requested bounded artifact. Do not imply its fields are the only deliverable:

```json
{
  "binary_fingerprint": "",
  "build": "",
  "logical_id": null,
  "address": "0x",
  "name": "",
  "suggested_name": null,
  "signature": "",
  "calls": [],
  "called_by": [],
  "arguments": [{"index": 0, "name": "", "type": "", "storage": "UNKNOWN", "confidence": 0.0, "evidence": ""}],
  "returns": {"type": "", "confidence": 0.0, "evidence": ""},
  "local_variables": [{"name": "", "type": "", "purpose": ""}],
  "constants_used": [],
  "strings_referenced": [],
  "side_effects": [],
  "cross_build_witnesses": [],
  "event_runtime_witnesses": [],
  "hypothesis": "",
  "evidence": [],
  "patterns_detected": [],
  "confidence": 0.0,
  "gaps": [],
  "decompiler_warnings": []
}
```

Naming follows AGENTS. Scores below are advisory only; they neither prove recovery
nor authorize source/type propagation. Preserve fingerprint, instance address,
logical identity if known and evidence provenance in every record.

| Score | Meaning |
|---|---|
| 0.9–1.0 | String/API-clear |
| 0.7–0.8 | Strong circumstantial |
| 0.5–0.6 | Plausible, gaps remain |
| 0.3–0.4 | Guess |
| 0.0–0.2 | Structural only |
