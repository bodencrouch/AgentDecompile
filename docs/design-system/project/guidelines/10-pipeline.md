# Pipeline and lanes

**One model, one address space.** Everything below is also data in `docs/dashboard-design/pipeline-diagram/pipeline-model.json`: stable node ids (`stage-0`…`stage-8`, `gate-0`…`gate-8`, `lane-A`…`lane-E`, `ladder-A`…`ladder-F` with members `ladder-A-1`…, `lock-1`…`lock-5`, `failover-rule`, `export-*`, the companion contracts and `milestone-M0`…`M7`) and typed edges (depends_on, feedback, failover, gates, consumes, feeds, wraps, produces, consumed_by, serialized_by). The diagrams, their text outlines and both frontends render from it, and every node id is a deep-link target: the PipelineMap, PipelineBreadcrumb, go-to field and diagram outlines all address the same ids.

The recovery pipeline is the product's organizing structure. The app and the diagrams draw the same stages, lanes, ladders and export targets, with the same names and family colors. Stage order and prerequisites follow STRATEGY; the UI presents actual state and never reimplements the ladder.

## Main pipeline: stage 0 plus eight named stages

Left to right is dependency order. Feedback is allowed: identity and calibration refine each other (dashed `dash-feedback` arrow labelled "↺ feedback · 1 ↔ 2 refine scoped hypotheses"), and parity runs continuously ("↺ feedback · 7–8 verify early scaffold and candidates"). There is no ninth stage.

| # | Stage | Family | Gate (drawn with `gate`) |
|---|---|---|---|
| 0 | Open · add · resume (priority-zero) | intake | mutation-admission only (real owner state) |
| 1 | Identity | identity | candidate ≠ acceptance |
| 2 | Incremental calibration | recovery | (none) |
| 3 | Validated linkable regions | recovery | round trip + independent linked-image oracle |
| 4 | C/C++ candidates | recovery | compile admits candidate, not replacement |
| 5 | Propagation (cross-place) | recovery | candidate distribution ≠ accepted source |
| 6 | Targeted AI (leftovers only) | recovery | candidate only |
| 7 | Continuous parity | verify | local zero ≠ full-image or behavior proof |
| 8 | Whole-image byte identity | verify | whole-file hash equality |

- Stage 0 gates **writes only**. Browsing, search, cached reads and independent indexing never wait on it.
- Stage 4's failover loop is drawn dashed in `lock`/FAIL salmon: "compile fails → helpers → bounded LLM → retry (dashed = failover, never blocks siblings)".
- The gate diamond between stages 4 and 5 is labelled "candidate", sub "compile + compatibility".
- Stage 8 records two variants separately: **byte-accurate C+assembly-floor** and **max-C**, and two methods: **reconstruction** and **original-style rebuild**. Use VariantLedger; never borrow a receipt between cells.

## Concurrent lanes A–E

Drawn below the main row with a `gate`-amber concurrency bracket: "RUNS CONCURRENTLY WITH STAGES 1–8 (where ownership permits)".

| Lane | Title | Family | Connects |
|---|---|---|---|
| A | Knowledge fusion — bidirectional, per field | unify | consumes stage 1 identity · runs beside stages 4–5 · feeds every sibling build |
| B | Cross-build entity unification & export — every entity, not just functions | unify | consumes stages 1–2 (+ raw images) · feeds lane C and the export bundle |
| C | Runtime reuse & learn-the-build — branches after identity/ABI evidence, before whole-image recovery | runtime | branches after stages 1–2 evidence · consumes lane B's pack · feeds evidence back into stage 1 |
| D | Verification & determinism — same inputs → byte-identical outputs, under a declared basis | verify | wraps every stage and lane · gates every export |
| E | Distributed compute — laptop → concurrency → donated idle compute and free cloud nodes | intake | wraps every stage and lane · one-command join · fleet of free cloud nodes |

Each lane ends with a dashed `dash-outputs` box headed "OUTPUTS → who consumes them".

In the app, lanes appear as separately owned activity. The single workflow control owns only the active project's mutation-admission boundary. It surfaces lanes C and E and independent reads, but never starts or stops them.

## Bounded resolution ladders A–F

"Try applicable methods; stop with absent / inlined-only / ambiguous / unsupported / insufficient evidence / budget exhausted." Each ladder is a numbered list of methods tried in order (ResolutionLadder) and ends in named outcomes drawn in `fact-failed` bold. The EvidenceRail in the app shows the same members, in the same order, with a per-member reason.

| Ladder | Problem | Family | Terminal outcomes |
|---|---|---|---|
| A | Function whose bytes changed (11 members, anchor_rel … annotation) | identity | unresolved (per-member reasons); two verified hits disagree → contested |
| B | Cave missing or too small (6) | unify | no_placement / unsupported_dynamic_code |
| C | Data root unresolved (10) | unify | unresolved — never a silent zero |
| D | Struct field moved / stripped build (6) | unify | ambiguous / insufficient_evidence / absent |
| E | VTable / dispatch slots (4) | unify | per-slot unresolved |
| F | Unknown build (5) | runtime | coverage may regress when collisions are found |

An annotation (ladder A step 11) is "a claim, never resolved".

## Ownership and failover

Ownership is resource-scoped: eligible independent work overlaps. The five one-owner serialization points are drawn with a `lock`:

1. writes to one Ghidra program's analysis DB
2. shared corpus mutation / conflict resolution
3. shared mutable compiler outputs / Wine context (private outputs may overlap)
4. one scenario bundle: staged tree + saves + Wine + display + ports + harness
5. short acceptance commit: current basis + generation + independent proof

**Failover rule** (dashed `dash-failover` box): the affected branch stops **visibly** at its real unmet dependency, and every eligible sibling lane continues. Show the named owner or provider failure, the last evidence, the chosen fallback, one retry owner and its persistent budget. A deadline ends an attempt, not the objective. Expired ownership does not free resources.

## Export target

Seven outputs, drawn as amber-outlined cards (ExportTargetCard): **hookpack v2**, **Generated Lua bindings**, **Per-build C/C++ headers**, **Readiness report**, **Divergence report**, **Receipts**, **Source + comparison projects**. "Re-run under the same basis → byte-identical bundle." Ambiguous and contested records ship as structured outputs and refuse unsafe use; they never block the rest of the export.
