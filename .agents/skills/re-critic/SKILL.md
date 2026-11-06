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
Current recovery operations use the existing 8080 catalog; CLI, test and startup
recipes below are implementation references subject to the mission restrictions.


Validate Worker artifacts. Independent tool calls. No new hypothesis.

**REQUIRED SUB-SKILL:** `tiered-re-analysis`

Use the lowest sufficient tier: strings/imports → Tier 0 or `list-strings`/`list-imports`; xrefs → Tier 2; types/semantics → existing decompile/disassembly evidence, then missing queries only.

## Procedure

1. Corroborate existing evidence with `get-functions` decompile, `get-references`, `get-call-graph`, `search-constants`, `search-strings`.
2. Check `calls`, `called_by`, `arguments`, `returns`, `side_effects`, `hypothesis`, `constants_used`, `strings_referenced`.
3. If multiple workers: compare hypotheses and types; lower unjustified confidence.
4. Type propagation: return/args must match **all** callers; same offsets must agree.

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
