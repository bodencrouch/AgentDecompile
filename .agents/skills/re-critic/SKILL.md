---
name: re-critic
description: "Use this skill when asked to review, challenge, or verify someone else's function analysis against the binary. Do not invent a new hypothesis."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
  role: critic
---

# RE Critic

Read [AGENTS](../../../AGENTS.md) and [STRATEGY](../../../STRATEGY.md) first.
Use [USER_INTENT](../../../docs/USER_INTENT.md) to distinguish the wider
binary-family, matching-C, and runtime outputs. This critic role validates only
the assigned claim and its evidence; it does not make one function review the
product result.
Active recovery uses the checkout-pinned `.venv/bin/agentdecompile-cli` from the
repository root; frontends are deferred. Reuse existing local or shared Ghidra
project bytes and analysis when available. Preserve project restrictions on
tests, startup and process ownership.


Validate the assigned evidence/artifact with independent witnesses where useful.
Do not invent a new semantic hypothesis. Keep the verdict scoped: function
semantics, cross-build correspondence, compiled-source parity, full-image parity,
and runtime-call/hook safety are distinct claims with distinct evidence.

**REQUIRED SUB-SKILL:** `tiered-re-analysis`

Use the lowest sufficient tier: strings/imports → Tier 0 or `list-strings`/`list-imports`; xrefs → Tier 2; types/semantics → existing decompile/disassembly evidence, then missing queries only.

## Procedure

1. Corroborate existing evidence with `get-functions` decompile, `get-references`, `get-call-graph`, `search-constants`, `search-strings`.
2. Check `calls`, `called_by`, `arguments` and their storage, `returns`, `side_effects`, `hypothesis`, `constants_used`, `strings_referenced`, and any supplied cross-build or runtime/event witnesses.
3. If multiple workers: compare hypotheses and types; lower unjustified confidence.
4. Cross-build claims must identify both concrete builds and preserve divergent
   addresses, ABI/layout, and contrary evidence. A logical name or similarity
   alone is not proof of equivalence.
5. Type propagation: return/args must match **all** relevant callers; same
   offsets must agree within the relevant build/layout.
6. Runtime claims must include the selected process/build, ABI, argument/parameter
   locations, permissions, and relevant lifetime/thread/effect evidence. A static
   prototype or observed event alone does not establish safe call, hook, cave,
   shim/DLL, or memory-modification readiness.
7. Source-match and whole-image claims require compiler/objdiff or full-image
   receipts at their respective scope; a review score or function JSON cannot
   substitute.

Unverifiable claims → `unverified`, not assumed correct.

## Review record (return only this JSON)

```json
{
  "binary_fingerprint": "",
  "build": "",
  "logical_id": null,
  "function_address": "0x",
  "worker_artifact_reviewed": "",
  "verdict": "confirmed | disputed | insufficient_evidence",
  "overall_confidence_adjustment": 0.0,
  "checks": [{"field": "", "claim": "", "verified": true, "method": "", "note": ""}],
  "issues": [{"severity": "critical | major | minor", "description": "", "evidence": "", "recommendation": ""}],
  "type_inconsistencies": [],
  "unverified_claims": [],
  "confidence_assessment": {"original": 0.0, "adjusted": 0.0, "reason": ""}
}
```

Confidence adjustments and `confirmed` concern this bounded analysis only. They do
not establish byte parity, runtime readiness or permission to propagate. Verify
target identity before comparing witnesses. Hallucinated evidence is `critical`.
