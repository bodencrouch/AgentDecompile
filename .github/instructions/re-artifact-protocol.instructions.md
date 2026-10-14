---
description: "Optional advisory artifact conventions for the RE Planner, RE Worker, RE Critic, and RE Aggregator workflows."
applyTo: ".agents/skills/re-*/SKILL.md"
---

# Optional RE Artifact Notes

This protocol applies only when a task explicitly uses the RE Planner/Worker/Critic/
Aggregator workflow. It is an optional workspace convention, not a required
product output, corpus authority, recovery pipeline, or approval gate. For the
product contract and inputs/outputs, follow [USER_INTENT](../../docs/USER_INTENT.md);
repository operations follow [AGENTS](../../AGENTS.md), and pipeline, matching,
resource, and proof policy follow [STRATEGY](../../STRATEGY.md). If this file
disagrees with those authorities, follow them.

AgentDecompile's product result is not a collection of isolated function JSON
files. A function artifact is one bounded evidence item in the larger binary-family
workflow: identify each concrete build, cross-match functions/data/types/events,
recover readable C/C++, compile and compare per target, then retain honest
target-bound proof. Related builds remain distinct binaries with their own
addresses, bytes, ABI, layouts, evidence, and divergences.

## Workspace Layout

Use a task-scoped artifact workspace only when useful. Existing corpus and Ghidra
bindings remain authoritative for their claim types. Keep build fingerprint,
program binding, logical identity (when known), per-build address/region, tool
revision, provenance, and conflicts; an address alone is not identity. The
example below is illustrative and does not prescribe a filesystem layout.

```
analysis/
  builds/<build-id>/             # Concrete binary identity and local evidence
    functions/                   # Optional bounded function artifacts
    data-types-events/           # Per-build layouts, events, and witnesses
  cross-build/                   # Candidate identities, matches, divergences
  recovery/                      # Source variants and target-bound compile/objdiff receipts
  runtime/                       # Supported call/hook/cave/memory evidence and state
```

This is a conceptual example, not a mandated directory tree. Use existing
AgentDecompile corpus records and receipts where they already own the evidence;
do not duplicate them into a second authority.

## Artifact Immutability

- Worker raw outputs are NEVER modified after creation. New analysis produces a new file.
- Merged artifacts (`/functions/`) are updated ONLY by the Aggregator.
- Critic reviews are NEVER modified. New reviews produce new files.
- The `runs.jsonl` log is append-only.

## Advisory confidence and review

Confidence is only a human-review aid for semantic hypotheses. It is not a
probability of correctness, source recovery credit, cross-build equivalence,
ABI/call safety, or permission to propagate or mutate. Preserve the underlying
witnesses and unknowns rather than letting a score stand in for evidence.

| Score | Level | Meaning |
|-------|-------|---------|
| 0.9–1.0 | High advisory confidence | String/API evidence, trivial wrapper, well-known pattern |
| 0.7–0.8 | High | Strong circumstantial, Critic-confirmed, caller-consistent |
| 0.5–0.6 | Medium | Plausible, some gaps remain, partial evidence |
| 0.3–0.4 | Low | Educated guess, significant unknowns |
| 0.0–0.2 | Speculative | Minimal evidence, structural inference only |

The optional review labels below describe only whether a bounded analysis item
has received the requested review. They do not define product completion.

These scores and stopping rules guide optional hypothesis review only. They do
not establish corpus identity, safe ABI calls, compiling source, objdiff parity
or whole-image recovery. See [runtime readiness](../../docs/RUNTIME_REUSE.md).

A hypothesis is **review-converged** when:
1. Confidence ≥ 0.6
2. Critic has reviewed and not disputed core hypothesis
3. No `blocking` gaps remain
4. Types are consistent with all callers and callees

An optional review may stop when:
1. All high/medium priority functions are converged
2. No cross-function type inconsistencies exist
3. Call graph is fully consistent
4. Remaining gaps are marked `UNKNOWN` with justification

## Evidence and interfaces

Choose the cheapest sufficient supported evidence path according to
[tiered re-analysis](../../.agents/skills/tiered-re-analysis/SKILL.md), while
reusing Ghidra projects and analysis as a core source of program evidence. Resolve
tool names, schemas, and current capabilities from the live advertised catalog or
the owning schema—not from a duplicated list in this optional protocol.

When in scope, artifacts may capture cross-build function/data/type/event
correspondence and divergence; argument/parameter locations, calling convention,
returns, state, and memory effects; and supported runtime observations. A
runtime call, hook, code-cave, Lua/native shim, DLL, or memory-modification claim
must retain its exact build/process, ABI, evidence, and safety basis. It does not
establish matching C or byte parity. Likewise, a function-slice match or a C file
does not establish full-image recovery; see STRATEGY for each claim's proof bar.

### Naming conventions

Use [AGENTS.md](../../AGENTS.md), the single naming reference.

## Evidence discipline

1. If you cannot find evidence in the binary for a claim, mark it `UNKNOWN`.
2. If the decompiler output looks suspicious, cross-check with disassembly.
3. If a type is inferred from a single call site, confidence ≤ 0.5.
4. If a hypothesis has no supporting constants, strings, or API calls, confidence ≤ 0.4.
5. Never invent function names based on address proximity alone.
6. Never assume two functions are related just because they are adjacent in memory.
