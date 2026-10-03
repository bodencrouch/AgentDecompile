---
title: September 18–21 design scope and continuation authority
type: living-scope-index
date: 2026-09-27
status: active
---

# September 18–21 design scope

The user's current clarification is binding: `STRATEGY.md` and the living
implementation plan must represent the designs, diagrams, plans and brainstorms
from **September 18–21, 2026**. The later September 22 package refines that work;
it does not replace it or make omitted weekend requirements optional. The newest
filename is not a reason to discard the most comprehensive earlier plan.

This file indexes the existing scope. It does not replace the detailed unit
definitions, create another scheduler or claim their implementation is complete.
The [implementation/live-track ledger](2026-09-27-implementation-progress-and-live-track.md)
records delivery; [STRATEGY](../../STRATEGY.md) remains the recovery priority policy.

## Baseline documents to preserve

| Source | Scope carried forward |
|---|---|
| [September 21 consolidated design](../dashboard-design/2026-09-21-consolidated-design-plan.md) | Pipeline, priority order, product appearance/behavior, visible actual work, automatic continuation and minimal resume gates |
| [September 21 portable-signatures/codecaves plan](2026-09-21-portable-signatures-codecaves-generic-plan.md) | Complete Phases 0–15, every named D/U unit and suffix variant, cross-build entity substrate, runtime resolution, export bundle, surfaces and compute adapters |
| [September 21 distributed-compute design](2026-09-21-distributed-compute-design.md) | Reusable grid-of-one foundation, bounded tasks, content-addressed proposals, independent verification, materialized views, capability access and later fleet scaling |
| [September 21 requirements ledger](2026-09-21-user-requirements-ledger.md) and [goal](2026-09-21-goal.md) | User intent, deterministic usable exports, unattended progress and the original unit-level acceptance requirements |
| [September 20 workstation specification](../dashboard-design/2026-09-20-unified-workstation-spec.md), [implementation plan](2026-09-20-unified-reversing-workstation.md) and [frontend intent](../FRONTEND_INTENT.md) | Dense unified workspace, source/history locators, actual-work visibility, two real consumers of shared capabilities/state — narrowed 2026-09-28: the two surfaces are fundamentally different presentations over one backend (static restructures to the Ghidra-guide CodeBrowser by default per a 7-slice spec; Vite stays the differentiated real-time AIO workstation), not a shared CodeBrowser/GuideWorkflows shell; see `docs/FRONTEND_INTENT.md`'s supersessions table |
| [Guide capability inventory](../dashboard-design/2026-09-20-ghidra-guide-capability-inventory.md) and [donor capability inventory](../dashboard-design/2026-09-20-kotorxid-capability-inventory.md) | All substantive workflow families inherited by F01–F28 and the workstation's eight implementation tasks; inventory labels are not current runtime proof |
| [September 21 improvement recommendations](../dashboard-design/2026-09-21-improvement-recommendations.md), [risk register](2026-09-21-risk-register.md), [loop charter](2026-09-21-loop-charter.md) and audits [2](2026-09-21-plan-audit-2.md), [3](2026-09-21-plan-audit-3.md), [4](2026-09-21-plan-audit-4.md) | Failure findings, continuation requirements and explicit corrections to the detailed plan; historical commands and completion marks require current qualification |
| [Diagram sources and companions](../dashboard-design/pipeline-diagram/README.md) | Preserve the recovery stages and all capability lanes, including the extended runtime/entity/distributed scope; overview and companion diagrams are views of the same requirements |

These files contain dated later edits as well as weekend material. Retain those
dates and their source locators. Do not describe a later consolidation as an
untouched September 18–21 snapshot or invent missing September 18/19 filenames.
The bounded provenance audit recovered the September 20–21 documents and their
source ledgers but no independent day-specific September 18/19 artifact. That
remains a provenance gap, not evidence that those days had no design work.

## Full implementation scope

| Workstream | Required outcome | Detailed source |
|---|---|---|
| Recovery and cross-matching | Reuse valid analysis, compile-gated recipient candidates, continuous comparison, per-field knowledge fusion and separate whole-image source variants | Consolidated design §§2–3; STRATEGY stages 0–8 |
| Deterministic portable substrate | Reproducible entity identities, portable locator families, signature/ABI/cave plans, divergence and generic format/platform seams | Portable plan Phases 0–7 and 10–11 |
| Every entity and access path | Structures/fields, globals, vtables, tables, imports, patch sites, data roots and ordered idempotent accessors, including explicit unknown spans | Portable plan Phases 8–9 |
| Complete usable exports | One declared-basis export bundle with `hookpack/v2`, generated Lua, per-build headers and readiness/divergence reports; ambiguous records remain structured and refuse unsafe use | Portable plan Phase 12; September 21 goal |
| Exhaustive resolution and new builds | Ordered fallback ladders, divergence/split/inline outcomes, learn-build feedback and per-member residue reasons; a budget stop is distinct from exhausted applicable strategies | Portable plan Phase 13, ladders A–F |
| Autonomous visible workspace | Eligible work admitted on explicit project open/add/resume; pause/resume control, shared readiness/review/residue and starvation/hang views in both surfaces; browsing remains read-only | Portable plan Phase 14; consolidated design §6 |
| Reusable compute/state foundation | Local publish → work → verify → materialize cycle, independent verification and bounded resumable adapters; local SQLite is a materialized view in the target architecture | Portable plan Phase 15; distributed design |
| Subsequent adopted extensions | reccmp/ReAgent, recovered-project recipes, robust continuation/acceptance, effective scenarios, F12, captures/checkpoints, platform qualification and assessed browser route | September 22 contract package and M0–M7 roadmap |

The **110-item September 22 register is a later contract/acceptance register**, not
an exhaustive count of this whole program. It does not subsume or close the
weekend plan's D/U units. Preserve their original identifiers and acceptance
definitions; qualify completion against current source and appropriate evidence.
The [unit delivery ledger](2026-09-27-weekend-unit-delivery.json) now enumerates
193 source-qualified identifiers (9 D and 184 U, including 20 suffix variants).
It retains U0 as withdrawn and U127/U128 as absorbed, leaving 190 required records.
These are requirement dispositions, not implementation counts. All initial delivery
states are unverified pending per-unit current evidence; missing numeric IDs are
not invented requirements. Source hashes and complete definition/acceptance spans
preserve the original basis, including shared Phase 15 definitions.
Identifiers are source-qualified: a portable-plan `U`/`D` unit is not the
similarly numbered session directive or September 22 contract row. Completion
reports must name the source plan as well as the identifier rather than merging
those independent namespaces.
Old checkmarks, commits, source presence and reports are reuse leads, not fresh
installed/live acceptance. Grid architecture is required scope; increasing remote
worker count waits for a qualified local lane rather than making the architecture
an optional final feature.

Frontend scope includes all F01–F28 and Phase 14 U104–U112: project lifecycle and
deduplication, corpus-first multi-build selection and comparison, synchronized
listing/decompile/hex/graphs/xrefs, real symbols/types/storage/structure editing,
the complete guide/donor workflow inventories, inspectable actual-work visuals,
derive/backfill evidence, accessibility and narrow layouts, agent context,
collaboration/CI and extensibility. Static 8080, packaged `/react/` and the optional
full Vite app share capabilities and data; current operational port restrictions
do not turn Vite into a preview or remove a frontend from the done definition.
A 2026-09-28 user directive makes the two surfaces' presentation fundamentally
different rather than parallel views: static 8080 follows the reversing guide's
conventional browsing layout, and Vite is the real-time all-in-one workstation.
Shared backend identity, jobs, receipts and claim semantics are unchanged by
that split.

## Precedence and delivery order

1. Current direct user instructions and current operational constraints govern.
2. Weekend requirements define the baseline scope; later explicit user changes
   and recorded conflict resolutions refine it. No silent omission by summary.
3. Later contracts strengthen evidence, ownership, bounded execution and recovery
   semantics without removing an output, workflow, entity class or platform goal.
4. Current receipts determine delivery state independently of the design's age.

Historical statements about lifted guards, launching extra ports, tests, source
tree reconciliation or publication are not fresh operating instructions. The
required static workbench and full React application remain product scope; current
recovery uses the authorized existing 8080 catalog. The September 21 automatic
continuation design does not authorize recovery from ordinary selection/navigation
or permit uncertain writes to bypass admission.

The active session goal covers this full baseline plus subsequent adopted work.
Its immediate priority is useful RE/cross-match work **alongside** implementation:
start with existing evidence and a qualified target/build pair, implement its
actual missing prerequisites in parallel, and continue unrelated eligible work.
Neither unfinished grid/fleet work nor the complete M0–M7 roadmap is a universal
gate on a safe local operation. A missing 8080 owner blocks catalog mutation,
not read-only evidence work or disjoint implementation.

## Current continuation anchors

The accepted `.14` native ownership artifact is a bounded supporting increment,
not completion of the weekend substrate or workspace. The current operational
readiness audit selected one existing GOG-to-Amazon build pair from the NVMe
corpus. The first read-only packet for match `1008017` now corroborates the cached
instruction bytes against both original images and supports a rejection proposal;
the stored review state remains unchanged.
Further bounded evidence corroborates two historical recovered rows to physical
addresses with different current logical IDs, and a second high-score match has
receiver-layout/return differences requiring variant-specific treatment. Their
source lineage, unique semantic identity and acceptance remain separate open
questions; the living ledger links the concrete packets. The active cross-place
repair preserves this distinction while preparing useful recipient candidates.
Actual catalog matching and writes remain blocked by the absent 8080 owner and
unreconciled serving/source bindings. These concrete targets are verification
fixtures/provenance; generic core defaults and contracts remain engine-independent.
