---
description: "Reverse engineering artifact protocol: shared schema, workspace layout, confidence scoring, and convergence rules for the multi-agent RE pipeline (RE Planner, RE Worker, RE Critic, RE Aggregator)."
applyTo: "**"
---

# RE Artifact Protocol

## Workspace Layout

This optional analysis protocol uses a task-scoped directory only when needed.
It is an advisory workspace, not another authoritative corpus store. Follow
[AGENTS.md](../../AGENTS.md) for operations and [STRATEGY.md](../../STRATEGY.md)
for evidence, identity and recovery acceptance. Existing corpus/Ghidra bindings
remain authoritative for their claim types. Record binary digest/build, program
binding, logical identity (when known), address/region, tool revision, provenance
and conflicts; an address alone is not identity. The example below is relative
to a chosen task workspace, not a required filesystem-root directory.

```
analysis/
  triage.json                    # Binary triage from Planner
  status.json                    # Current analysis status from Aggregator
  /functions/
    <build>_<logical-or-region>.json # Advisory artifact with full provenance
    <build>_<other-region>.json
  /worker_raw/
    0x401000_worker_1.json       # Raw Worker output (kept for audit)
    0x401000_worker_2.json
  /reviews/
    0x401000_review.json         # Critic review records
  /types/
    structs.json                 # Recovered struct definitions
    enums.json                   # Recovered enum definitions
    globals.json                 # Global variable catalog
  /hypotheses/
    <id>.json                    # Cross-function hypotheses
  /logs/
    runs.jsonl                   # Append-only log of agent runs
```

## Artifact Immutability

- Worker raw outputs are NEVER modified after creation. New analysis produces a new file.
- Merged artifacts (`/functions/`) are updated ONLY by the Aggregator.
- Critic reviews are NEVER modified. New reviews produce new files.
- The `runs.jsonl` log is append-only.

## Confidence Scale

| Score | Level | Meaning |
|-------|-------|---------|
| 0.9–1.0 | High advisory confidence | String/API evidence, trivial wrapper, well-known pattern |
| 0.7–0.8 | High | Strong circumstantial, Critic-confirmed, caller-consistent |
| 0.5–0.6 | Medium | Plausible, some gaps remain, partial evidence |
| 0.3–0.4 | Low | Educated guess, significant unknowns |
| 0.0–0.2 | Speculative | Minimal evidence, structural inference only |

## Convergence Rules

These scores and stopping rules guide optional hypothesis review only. They do
not establish corpus identity, safe ABI calls, compiling source, objdiff parity
or whole-image recovery. See [runtime readiness](../../docs/RUNTIME_REUSE.md).

A hypothesis is **review-converged** when:
1. Confidence ≥ 0.6
2. Critic has reviewed and not disputed core hypothesis
3. No `blocking` gaps remain
4. Types are consistent with all callers and callees

The scoped advisory review may stop when:
1. All high/medium priority functions are converged
2. No cross-function type inconsistencies exist
3. Call graph is fully consistent
4. Remaining gaps are marked `UNKNOWN` with justification

## Tiered tool routing

Use Ghidra MCP **only when necessary**. Full matrix: `docs/solutions/architecture-patterns/tiered-re-analysis-knowledgebase.md` and skill `.cursor/skills/tiered-re-analysis/SKILL.md`.

| Tier | Ghidra session? | Examples |
|------|-----------------|----------|
| 0 | No | MCP `run-file-triage`, `run-external-re-scan`; shell `file`, `strings`, `readelf`, `yara`, `capa`, `binwalk` |
| 1 | Batch/offline | MCP `run-batch-decompile`, `run-batch-export-gzf`, `run-batch-bsim-signatures`, `run-batch-sast-scan`; CLI `agentdecompile-cli ghidrecomp`, export/SARIF |
| 2 | MCP read-only | `list-*`, `search-*`, `get-references`, `get-call-graph` |
| 3 | MCP deep/mutate | `decompile-function`, `analyze-data-flow`, `manage-*`, `match-function` |

**Planner:** Tier 0 triage before `open-project` on cold binaries. **Worker/Critic:** Tier 2 before Tier 3. **Aggregator:** a score alone never authorizes Tier 3 mutation; use field-level evidence, type/layout gates and the ordinary modification-conflict flow.

## MCP Tool Mapping

These are the AgentDecompile MCP tools available for each analysis phase:

### Tier 0 — Static file (no Ghidra session)
- `run-file-triage` — file metadata, sha256, strings; optional `externalScanTools` embeds capa/yara/binwalk under `externalScans`
- `run-external-re-scan` — capa, yara, and/or binwalk (single tool or `tools` bundle)

### Tier 1 — Batch / offline (no long-lived MCP session)
- `run-batch-decompile` — bulk decompile export via ghidrecomp
- `run-batch-export-gzf` — packed Ghidra project snapshot
- `run-batch-bsim-signatures` — BSim signature generation
- `run-batch-sast-scan` — SAST on decompiled output

### Discovery / Read-Only (Tier 2)
- `list-functions` — enumerate functions (pagination: offset/limit)
- `list-imports` / `list-exports` — external symbols
- `list-strings` — embedded strings
- `get-function` — metadata for one function
- `get-functions` — batch metadata/decompile/disassemble
- `get-references` / `list-cross-references` — xref analysis
- `get-call-graph` — call relationships
- `search-everything` — multi-scope keyword search
- `search-strings` / `search-symbols` / `search-constants` — targeted search
- `get-data` — data at address
- `inspect-memory` — raw memory inspection
- `analyze-data-flow` — data flow analysis
- `analyze-vtables` — C++ vtable recovery

### Mutation (Tier 3 — apply findings)
- `manage-function` — rename, set prototype/return type/calling convention
- `manage-comments` — set/get/search comments at addresses
- `manage-symbols` / `create-label` — rename symbols, create labels
- `manage-bookmarks` — bookmark addresses with categories
- `manage-function-tags` — tag functions (crypto, network, etc.)
- `manage-structures` — create/edit recovered struct types
- `apply-data-type` — apply type to address
- `match-function` — cross-binary function matching
- `execute-script` — arbitrary PyGhidra script (last resort)

### Naming conventions

Use [AGENTS.md](../../AGENTS.md), the single naming reference.

## Anti-Hallucination Rules

1. If you cannot find evidence in the binary for a claim, mark it `UNKNOWN`.
2. If the decompiler output looks suspicious, cross-check with disassembly.
3. If a type is inferred from a single call site, confidence ≤ 0.5.
4. If a hypothesis has no supporting constants, strings, or API calls, confidence ≤ 0.4.
5. Never invent function names based on address proximity alone.
6. Never assume two functions are related just because they are adjacent in memory.
