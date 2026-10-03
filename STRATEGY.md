---
name: AgentDecompile
last_updated: 2026-09-28
charter: VISION.md
active_living_plan: docs/plans/2026-09-27-implementation-progress-and-live-track.md
governing_design_scope: docs/plans/2026-09-27-weekend-design-scope.md
---

# AgentDecompile Strategy

Charter lives in [VISION.md](VISION.md). Operators start at [README.md](README.md). This file is the investment bet under that charter, not a second north star.

## Governing design scope: September 18–21, 2026

This strategy and the [living implementation plan](docs/plans/2026-09-27-implementation-progress-and-live-track.md)
represent the user's September 18–21 designs, diagrams, plans and brainstorms.
The [scope index](docs/plans/2026-09-27-weekend-design-scope.md) preserves the full
[September 21 portable-substrate plan](docs/plans/2026-09-21-portable-signatures-codecaves-generic-plan.md),
its Phases 0–15 and named units, the [distributed design](docs/plans/2026-09-21-distributed-compute-design.md),
and the [consolidated product/workstation design](docs/dashboard-design/2026-09-21-consolidated-design-plan.md).
The September 22 package supplies later contracts and refinements; it is not a
replacement scope. The 110-item later register does not exhaust the weekend units.
The [weekend unit delivery ledger](docs/plans/2026-09-27-weekend-unit-delivery.json)
preserves 193 source-qualified identifiers and their definition/acceptance spans,
including explicit withdrawals and absorbed aliases. Its initial unverified states
require current evidence; historical checkmarks do not establish delivery.
Changes to either this strategy or the living plan must retain traceability to
that baseline: name the affected original plan units and diagram views, record
any explicit supersession, and keep remaining requirements visible. A narrower
implementation slice or newer summary cannot silently redefine completion.

Carry these commitments through delivery:

- A deterministic, model-free path produces usable exports; bounded model help may
  accelerate diagnosed residue but cannot be the only mechanism for continuation.
- Cross-match every supported entity kind and data-access path, preserving per-build
  layouts, divergence and ordered locator fallbacks; pursue applicable strategies
  and learn new builds rather than treating an initial miss as the endpoint.
- Deliver the complete export bundle: portable `hookpack/v2`, generated Lua,
  per-build headers, readiness/divergence and evidence, alongside recovered projects.
  Ambiguous or contested records remain structured outputs and refuse unsafe use;
  they do not wait indefinitely for human triage before the rest can advance.
- Make the dense shared workspace show actual work and its evidence in both the
  static workbench and full React app. Explicit project open/add/resume admits
  eligible work automatically; ordinary browsing remains read-only. Preserve the
  September 21 pause/resume control model and readiness/review/residue views.
  Keep F01–F28, Phase 14 U104–U112 and both guide/donor workflow inventories:
  corpus-first comparison, project lifecycle, synchronized code/data/evidence,
  genuine type/storage editing, accessibility and inspectable work are required.
  The full optional Vite application and packaged `/react/` remain product scope;
  the 8080 recovery-operation rule does not reduce them to development previews.
- Build the reusable bounded-task compute/state foundation, starting with a local
  publish → work → verify → materialize cycle. Independent verification, resumable
  adapters and a materialized local view are architectural requirements. Remote
  fleet growth follows local qualification; it is not permission to postpone the
  foundation or make an unqualified shared SQLite file the permanent authority.

Historical progress marks and operating recipes are not current acceptance or
authorization. Current ownership/catalog constraints still govern execution.
Useful qualified RE/cross-match work and implementation proceed together; missing
unrelated milestones cannot become global gates.

## Purpose

A Ghidra project holds dozens of builds of the same codebase. Each build has its own addresses and may share logical functions and fields while changing their behavior, layout, or physical representation. Without cross-build identity and a propagation path, every recovery pass repeats work and metadata edits on one binary never reach the others. The crux is telling honest source from a wrapper that only compiles because it still contains the original bytes.

The end state is not per-function byte parity — it is a **whole-image byte-identical rebuild**: a source project that recompiles and *relinks* into a file bit-identical to the shipped executable. Per-function objdiff-0 is necessary but not sufficient. A stock linker assigns its own layout — section order, virtual addresses, padding, the PE/ELF headers, the import table, and base relocations — none of which reproduce the original image unless placement is enforced. This exact-placement gap is a first-class, unsolved part of the problem, not a footnote: the goal is a rebuilt binary whose whole-file hash equals the original's.

## Positioning

Recover from the best available evidence, reuse only what transfers, and verify each result at the level where it will be used. Distinguish logical entities, implementation variants and physical instances. Similarity, logical identity, code equality and behavioral test agreement are separate claims. Prefer authoritative debug/provenance and unique exact evidence, then rare references and neighborhood propagation, structure/BSim, and applicable second opinions on diagnosed residue. Every matching method stays available. Each has an ordered fallback, and an unavailable method narrows the evidence instead of stopping identity. No single method, BSim included, gates the pipeline. Operators see which methods ran, which were unavailable and why. Preserve ambiguity, absent entities, folded bodies, inline occurrences and split regions. A `logical_id` never establishes source interchangeability or ABI/layout compatibility.

Reuse valid unchanged analysis and receipts. Revisit only affected dependencies when bytes, types, callees, toolchain or analysis evidence changes, or when a recorded uncertainty warrants an independent view. Establish minimum platform facts first; identity and calibration refine each other. Start reconstruction infrastructure during scaffolding and verify candidates continuously. Keep one operational catalog on 8080. The [design package](docs/plans/2026-09-22-design-package.md), [recovery contracts](docs/plans/2026-09-22-recovery-contracts-and-validation-plan.md) and [editable diagram](docs/dashboard-design/pipeline-diagram/README.md) carry the concrete contracts and current delivery limits.

### Failure containment and acceptance

The [failure prevention and recovery specification](docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md)
turns historical incidents into mandatory prevention, detection, containment,
recovery, wake and future acceptance contracts, including failures of the control
plane itself. It refines the design; it does not claim deployed resilience.

Missing evidence blocks the claim requiring it; an unhealthy resource blocks its
dependent work. Neither blocks the whole project by default. A byte signature
cannot authenticate the semantic label that selected its address. Binding acceptance
requires distinct presence and independent target identity predicates; each runtime
operation additionally needs current ABI/layout/lifetime/ownership/policy checks.
Original-code capabilities never require reconstructed source unless the requested
operation actually replaces that source.

[Task and acceptance contracts](docs/plans/2026-09-22-task-acceptance-and-continuation-design.md)
define dependency-local scheduling, complete input bundles, task-specific measured
resource budgets, capability-unlock priorities with aging, short acceptance commits
and one persistent retry owner. Actual resource ownership—not a stage name—controls
serialization. Publication generation fencing and mutable-resource quarantine are
separate; expiry and byte equality cannot clear unsafe access. Conditional continuation
requires suitable capacity, valid complete inputs and a compatible available worker.
Worker containment, restart recovery and host-loss failover are distinct claims.

Implementation and useful reverse-engineering/cross-match work advance in parallel
under the user's subsequent build and continuation directives. Do not wait for the
whole architecture to be finished before admitting an eligible target/build pair.
Actual recovery operations still require the authorized 8080 catalog, corroborated
ownership and their own complete prerequisites. Future execution contracts describe
required mechanisms and acceptance; they do not establish checks already passed or
authorize bypassing those operational constraints.

## Users

**Primary:** An operator, or an agent acting as one, finishing byte-accurate, assembly-free source for every program in a multi-build Ghidra corpus, with labels and structures kept in sync across builds.

**Secondary:** Someone who only needs citeable facts or a navigable tree and stops before the recovery bar.

## Key metrics

- **Verified readable C:** source contributions with relocation-aware objdiff 0 against validated targets, plus linked-region checks when needed (with scope and receipts). Can regress on audit. Not the same as `real_c`.
- **Compiling Ghidra C share:** functions whose decompiled C is assembly-free and compiles (`ghidra-bulk` tally, `real_c=1`). Leading indicator, not proof.
- **Cross-placed compiling C:** compiling candidates distributed to compatible recipient implementation variants, with recipient acceptance still separate (`cross-place` receipts).
- **Identity coverage:** inventoried functions bound to a logical function (`identity` table). Must stay high before propagation claims. Auto-accept precision matters more than forcing 100% paired; unresolved/ambiguous counts should stay visible.
- **Runtime capability coverage:** accepted entity × build × operation claims against a named eligible inventory. Report known-build RVA resolution and unknown-build portable discovery separately; both need independent target identity and live operation checks. Preserve absent, unsupported, ambiguous, unclassified and excluded-with-reason counts. New collisions may reduce coverage.
- **Progress:** report liveness, durable distinct execution-unit results and accepted goal progress separately. A file, process, heartbeat or job completion alone is not acceptance.

## Tracks

### One catalog, two surfaces

The MCP HTTP server holds one catalog (`/api/v1/actions`), one job store and one claim model. Two frontends read it, with different jobs (user directive, 2026-09-28):

- **Static 8080 (no Node runtime).** Ghidra CodeBrowser parity following the PyKotor reversing guide. One browser tab holds a project, with its builds as peers on one cursor, so the call graph and matcher show together. It has no control for work the pipeline already schedules. Pause, resume and stop are the only workflow controls.
- **Vite (5174, also served at `/react/`).** A real-time workstation modeled first on objdiff-web, then decomp.me, Dogbolt, RzWeb, r2web and APKMan, adapted to the recovery pipeline's stages and lanes, including distributed compute.

A per-binary objdiff-shaped `report.json` feeds progress views in both. Publishing statistics to decomp.dev is a later, separately approved step. Deprecate leftover dashboard ports when the in-tree server runs with corpus env.

_Why it serves the approach:_ Agents and humans must share one catalog and one progress view or they will diverge on what "done" means.

### Corpus recovery pipeline

The named stages describe dependencies, not a rigid one-pass schedule. Identity ↔ calibration → validated linkable-region scaffold → compiling C/C++ candidates → compatible-recipient candidate propagation → diagnosed source repair, with continuous local/linked parity and early reconstruction checks. Terminal acceptance remains a fresh whole-image rebuild and comparison. A receipt is reusable only while its relevant dependency hashes remain valid.

**Cross match pipeline:** `ghidra-bulk` → compile admission → compatible implementation variant and recipient ABI/layout gate → distribute candidate → recipient compile/local/linked verification. Compile success authorizes candidate distribution, not replacement, runtime calls or verified-source credit. Keep candidate storage separate from accepted replacement selection; legacy `real_c=1` records compilation only. A failed compile routes through behavior-preserving deterministic repair and then bounded AI when it is enabled. Targeted AI is one optional implementation. It is switched on or off through an environment variable, a flag when starting the 8080 server, or a dashboard setting. One precedence rule decides between them, and the dashboard shows where the current value came from. The deterministic path never depends on it. Diagnose behavior/types, ABI, compilation context, code generation and placement before source search or permutation.

Recovery units, compilation units and comparison units are distinct. Per-function fragments may be assembled into translation units or LTCG groups; compare the final emitted region when an intermediate object is insufficient. Toolchain records include compiler/linker hashes, headers/libraries, language, macros, packing, floating-point mode, grouping and scoped overrides. Probe legacy toolchain support instead of copying modern switches.

Knowledge fusion remains bidirectional and per field. The best donor may differ for every field or function. Human naming preference changes the display name, not physical-layout evidence. Logical field correspondence is separate from each build's physical layout; pointer-width scaling is only a search hint. Export known offsets and opaque unknown spans. Track evidence lineage: withdrawing an identity seed invalidates unsupported descendants, not independent corroboration. New evidence may reduce accepted coverage.

Workers read versioned snapshots and return proposals against those versions. Acceptance rechecks relevant dependencies, commits once, and rejects stale proposals. Local compilation keys exclude unrelated corpus additions; matching keys include their comparison evidence; publication keys include the corpus snapshot. Record exact AI proposals and runtime observations as immutable replay inputs. Shared read-only compiler installations are allowed; mutable compiler/PDB/temp output and Wine state require isolated ownership.

### Ghidra shared state

Name precedence is human-authored annotations → STABS/original source paths →
symbol-table/demangled names → meaningful Ghidra-derived names → placeholders.
Preserve the winning tier, provenance, rejected alternatives and conflicts. This
ordering applies to names; types/layouts/source retain their own compatibility
and verification gates. No placeholder may replace a stronger name.

One store, BSim, prompt evidence from this tree's venv CLI, session-stable `ensure-program`. Label/type edits flow through identity, not per-address copies. Ghidra Server is RMI over SSL, not HTTP.

_Why it serves the approach:_ Cross-match metadata only works if Ghidra state and recovery receipts share the same program binding.

### Portable identity / hook-pack export

The implemented `corpus.export-hookpack` is advertised through the 8080 catalog. It exports identities, signature strings and per-build instances; it does not prove a ready-to-call adapter. KotorPhasor already loads v1 packs and overlays, admits known builds and can fall back from a stale address hint to a unique executable-region byte scan. Matching hints and instances without expected bytes retain weaker checks. Export site names/build slugs must map to native adapter keys/profiles; raw export is not automatically drop-in.

Runtime reuse is a parallel branch after sufficient identity/ABI evidence, not a mandatory stage after full recovery. Shared corpus → runtime pack and target bindings → supported typed adapter or cave plan → preflight → controlled install/call → independently observed behavior → provenance feedback. KotorPhasor consumes original binaries; it does not replace recovery or turn original bytes into recovered C. Feed names, types, fields and behavioral observations back through the same field-level evidence gates.

[Runtime reuse](docs/RUNTIME_REUSE.md) records source pointers, architecture/ABI limits and missing readiness proof. Keep the core generic with target adapters and build profiles: all BioWare corpus builds remain in scope, with future other-game support requiring adapter work. A resolved address is not a universal C-call interface.

### Native decompiler tier (JVM-free replay)

Export a program once from Ghidra as per-function decompiler savefiles with a manifest. Re-decompile those savefiles with Ghidra's own native engine and no JVM. Use that for option sweeps, engine-upgrade regression checks, and consumers that cannot host Java. The export itself still needs one Java decompile per function. Native output is checked against the Java decompile of the same program on the same engine version. A mismatch is a bug, not a tolerance. The priority ladder below is unchanged. This tier feeds stage 4 (readable C) and sits at Tier 1 next to `ghidrecomp` in the tiered-re-analysis skill. Living plan: `docs/plans/2026-09-08-2330-feat-ghidra-native-sdk-plan.md`.

_Why it serves the approach:_ Bulk C is the step the corpus repeats most. Decompiling from a saved snapshot lets a worker run without Ghidra and lets an engine change be checked before it touches the corpus.

## Priority ladder (preserve prerequisites; allow feedback)

### Per-target loop and corpus roll-up

The ladder below describes stages within recovery, not a single global pass that
finishes the prototype. Drive one target through its requested byte-accurate source
outcome; enrich/replace its Ghidra knowledge with justified recovered information;
cross-match and apply eligible knowledge to sibling builds; repeat for the next
target using that accumulated evidence. Keep a per-binary ladder and a corpus
roll-up. Identity and field-level knowledge work may proceed concurrently, and
compile-gated source may cross-place before full-image completion; this target
loop must not block those useful branches or runtime reuse.

Within a target, reuse STABS-derived workspace/templates where available, then
Ghidra decompilation and deterministic preparse/sanitizer/helpers, compile, and
distribute candidates only on compile success and recipient compatibility. Retry supported helpers on failures, then a
bounded LLM cleanup and recompile. Byte verification, applicable m2c/permuter,
Mizuchi and other recovery plugins address measured residue under cheap-first,
LLM-last policy. Continue safe independent lanes when one tool/provider fails;
never let orchestration consume the recovery work or relax acceptance.

The user's “priorities 1–9” describes continuing the complete mission. This stage
list has eight named stages; no ninth stage is inferred from that shorthand.
[Unfinished outcomes](docs/PROTOTYPE_OUTCOMES.md) preserves the requested results
and evidence gaps without becoming a separate priority authority.

### Stages

0. **Open/resume:** reconcile bindings and actual ownership; reuse receipts with unchanged relevant dependencies. No blanket reanalysis.
1. **Identity:** evidence-fusion cascade; logical entity → implementation variant → physical instance relationships. Similarity proposes; independent evidence accepts. Quarantine bad seeds and invalidate unsupported descendants.
2. **Calibration:** establish format, architecture and ABI minima, then refine toolchain/layout hypotheses with stage 1 and function evidence. Record build/library/translation-unit/function scope.
3. **Scaffolding:** reconstruct linkable regions with bytes, boundaries, external references, reconstructed fixups, associated data, exception/unwind metadata and provenance. Image base relocations are not original COFF relocations. Preserve larger regions when splitting is uncertain. Use architecture-appropriate objects or external assembly, not universal inline asm. Prove an unchanged extract → emit → place → compare round trip early, then prove a compiled replacement actually contributes.
4. **Readable C/C++:** admit compiling candidates; preserve the floor until the required acceptance checks pass. Repairs explain preserved machine behavior. Compilation is not source verification.
5. **Propagation:** distribute compiled candidates only to compatible recipient implementation variants. Each recipient has its own compile, ABI, local and linked checks; identity alone is insufficient.
6. **Targeted AI:** bounded diagnosed tasks after cheaper applicable methods, leaves before callers where useful. Record exact proposals, limits and evidence; outputs never establish trusted identity or parity by assertion.
7. **Parity:** run as candidates arrive. Separate compilation, ABI checks, tested behavior, local relocation-aware match and linked-region match. Validate reconstructed comparison objects independently against the original linked image. reccmp is an optional diagnostic companion to objdiff; neither a similarity percentage nor ReAgent GREEN is whole-file equality.
8. **Whole image:** develop placement/reconstruction alongside stage 3; final acceptance freshly compiles the current source, proves replacement contribution, and compares the entire output against the original. Distinguish reconstruction with preserved regions from original-style rebuilding. Record C+floor and max-C separately.

Named non-success outcomes include `absent`, `inlined_only`, `ambiguous`, `unsupported`, `insufficient_evidence`, `budget_exhausted` and `contested`. Try applicable methods within the declared budget; do not force a winner or run every method on a nonexistent standalone function.

## Whole-image byte identity (dedicated track)

Per-function objdiff-0 and a whole-image byte-identical rebuild are **separate claims** — the second is the project's terminal deliverable and the harder one. A source project can have every function compile byte-exact and still relink to a different file, because the linker owns layout: virtual addresses, section order and padding, the PE/ELF header fields, the import table / IAT, TLS, resources, and the base-relocation table. Closing this needs an exact-placement link: a layout spec derived from the original image (per-symbol VA, section geometry, header bytes, reloc sites) that the link honors, plus a rebuild-validation stage that compares whole-file hashes and localizes any residual byte delta back to the owning function/section. The floor preserves machine-code regions, associated data and required metadata through a supported object/assembly backend; placement and reconstructed fixups require independent verification. An unchanged round trip proves infrastructure only. Link maps and emitted-byte provenance must show that compiled replacements reach the checked image despite elimination, folding or preserved fallback code. An ordering directive alone is not exact placement. Each accepted C/C++ contribution must pass the relevant local/linked gate and the whole-image reconstruction. Record reconstruction and original-style compiler/linker rebuilding as different methods, even if both reach byte equality. Until a build produces a file whose hash equals the shipped binary, whole-image recovery is unproven — say so plainly and keep the exact-placement work visible on the ladder.

_Why it serves the approach:_ "Decompiled" means rebuildable to the original artifact, not just readable per function. Without this tier the corpus can look 100% recovered while no build reproduces the shipped file — the exact gap the mission audit flagged as never proven.

Maintain two separately measured variants: **byte-accurate C+assembly-floor**, with every assembly/original-byte contribution explicitly counted, and **max-C**, maximizing readable assembly-free C. Never count floor bytes toward recovered-C coverage or borrow one variant's receipt for the other. Final acceptance needs a fresh compiler/toolchain run on the complete current source, per-function relocation-aware objdiff and an exact-placement whole-image relink/hash comparison for each claimed build. Cached receipts guide reuse; they do not substitute for this terminal fresh rebuild. Cheap deterministic compile/repair/verification comes first; permuter next where applicable; LLM/Mizuchi last on measured residue.

## Brand

**Key message:** Recover from the best available evidence, reuse only what transfers, and verify each result at the level where it will be used. One catalog; separate source, identity and runtime claims.
