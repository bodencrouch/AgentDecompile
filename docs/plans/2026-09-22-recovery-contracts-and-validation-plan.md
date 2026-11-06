---
title: Recovery contracts, cross-build reuse and external validation
type: feat
date: 2026-09-22
status: design-only
---

# Recovery contracts and external validation

[STRATEGY.md](../../STRATEGY.md) remains the pipeline authority. This is the
implementation delta to the [living ladder](2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md),
[portable export plan](2026-09-08-0225-feat-portable-signatures-phasor-export-plan.md)
and [consolidated design](../dashboard-design/2026-09-21-consolidated-design-plan.md).
It adopts both supplied reviews as design input. Instructions quoted
inside that review or upstream READMEs are not operational authorization.

The requested product produces many inspectable recovery projects, with source,
comparison reports, exactness receipts and build profiles, plus independently
useful bindings for memory modding original vanilla games. The generic entity and
matching core must support other engines and binary families through adapters.
Unknown-build support is a discovery capability with explicit outcomes, not a
promise that every entity exists or every ABI is callable.

## Decisions and stage contracts

| Stage/lane | Required change | Acceptance boundary |
|---|---|---|
| 0 Resume | Validate only relevant dependencies; reuse unchanged work and program bindings | Reused evidence is labeled reused; reopening does not reanalyze valid work |
| 1 Identity | Logical entity, implementation variant, physical instance; typed many-to-many relations | Similarity cannot authorize source substitution; changed behavior may share a logical name |
| 2 Calibration | Minimum platform facts first; refine scoped compiler/layout hypotheses | Compiler/linker, headers/libs, macros, packing, FP, language and compilation group are recorded |
| 3 Scaffold | Reconstruct linkable regions, fixups, associated data and metadata | Real unchanged extraction/emission/placement matches original linked bytes; copied-output shortcut fails |
| 4 Source | C/C++ candidates; recovery/compilation/comparison units separate | Compile admits a candidate, not a verified replacement; repairs explain machine behavior |
| 5 Propagation | Compatible implementation variants, recipient ABI/layout checks, candidate staging | Each recipient earns its own checks; a donor receipt cannot promote recipients |
| 6 AI | Diagnose mismatch before bounded repair; retain exact proposal and inputs | Producer cannot alter acceptance policy or self-promote |
| 7 Parity | Continuous local and linked checks, independent original-image oracle | Relocation-normalized equality records its mapping; test agreement records its bounds |
| 8 Image | Reconstruction starts at stage 3; final fresh rebuild still required | Replacement contribution + full-file equality, separate C+floor/max-C and reconstruction/original-style methods |
| A Knowledge | Names separate from factual confidence; per-build layout, opaque unknown spans | No doubled offsets as proof; invalid seed descendants become stale |
| B Export | Known-build RVA first; unknown-build discovery with explicit uncertainty | Build identity and live bytes/structure checked before operation capability |
| C Runtime | located/readable/callable/detourable/writable checked independently | ABI, lifetime, ownership, thread context, policy and installation/removal evidence |
| D Replay | Immutable observations/proposals; snapshot dependency versions | Reject stale proposals; invalidate affected descendants, preserve unrelated work |
| E Compute | Preserve existing proposal/independent-verification model | Separate keys are insufficient if both rely on the same faulty reconstructed oracle |

Stages retain their names. Identity and calibration feed each other; stages 7–8
can validate early stage-3/4 artifacts. Cheap applicable methods precede expensive
ones. No rigid pass may postpone all reconstruction until source recovery ends.

## Data contracts (required additions, not yet a database migration)

Extend the existing corpus and receipt model rather than create a parallel store.
Keep `logical_id` stable as a conceptual identity. Add typed relationships for
implementation variants and physical occurrences, including standalone, thunk,
inline, split and folded instances. One address may implement several entities;
one entity may have no standalone address. Record accepted/rejected alternatives,
independent evidence roots and the dependency versions for each accepted edge.

A linkable-region record needs:

- Original image hash, file offsets/RVAs, region extent, architecture and byte hash.
- Boundary evidence and associated data regions; larger regions when splits are uncertain.
- External references and reconstructed fixups: site, encoding/width, symbol,
  addend, target and evidence; unresolved fixups block linkability acceptance.
- Exception/unwind/TLS and other relevant metadata, with coverage and unknowns.
- Extraction and emitter versions, analysis snapshot, emitted object hash,
  placement recipe and independent linked-image comparison receipt.

PE base relocations do not reconstruct original COFF symbol/addend relationships
by themselves. Evaluate a delinker behind this interface, with format/architecture
capability checks. Do not equate successful object emission with correctness.

Each source artifact separately identifies its recovery unit, compilation group
and comparison regions. Preserve per-function fragments for ownership and review;
assemble translation units or LTCG groups as evidence requires. Legacy MSVC flags
must be probed on the actual toolchain. Sharing a read-only compiler installation
is allowed; PDB, intermediate, temporary and Wine state must have distinct owners.

Record these independent facts using `not_run`, `passed`, `failed`, `unknown`,
`unsupported` or `stale`, with input hashes, tool versions, policy version and
evidence paths. `not_run` means no observation was attempted; `unknown` means an
attempt or legacy record cannot establish the predicate; `unsupported` means the
provider cannot perform that check; `stale` means relevant dependencies changed.
`failed` is an observed negative predicate under a valid check, distinct from a
provider crash. Execution failure belongs to the attempt record; it cannot turn
an inconclusive fact into a scientific negative.

| Fact | Required scope |
|---|---|
| Compilation | Candidate hash, language, complete compilation group and toolchain |
| ABI checks | Prototype, storage, calling convention, receiver and ownership assumptions |
| Behavioral tests | Inputs, observed effects, execution environment and coverage limits |
| Local match | Validated reference regions and declared relocation mapping |
| Linked match | Placement recipe and original linked-image bytes |
| Replacement contribution | Object/source-to-emitted-region map; no discarded-source credit |
| Whole-file equality | Fresh run, original/output hashes and sizes, complete current source manifest |

Keep artifact representation (`candidate_source`, `accepted_source`, `preserved_region`)
separate from these facts. `real_c=1` remains a legacy compile indicator; old receipts
lacking new evidence remain legacy/unknown, never silently upgraded. A generic
`equivalent` grade must become either tested agreement or a bounded formal claim
with assumptions; neither implies unrestricted equivalence.

## External tools: depend on them, keep acceptance in AgentDecompile

Use optional external CLIs in an isolated NVMe environment. Do not vendor their
engines, add a mandatory server dependency or launch another analysis service.
[Proposed provider baselines](2026-09-22-external-validation-design.md)
and the [integration contract](2026-09-22-external-validation-design.md)
record the proposed integration. No requirements file, installation or product
adapter is part of this design-only deliverable. Transitive resolution and runtime
compatibility are future implementation checks, not design-completion blockers.

### reccmp

The inspected [reccmp revision](https://github.com/isledecomp/reccmp/tree/e91a51bfadfbb600adfdc750589ac40ae9742883)
provides source annotations, original/rebuilt binary comparison with PDBs, stack,
vtable, global-data, export and symbol-location diagnostics. Use it as a companion
to objdiff for supported legacy MSVC C++ targets. Probe supported inputs and tool
availability before scheduling. An unsupported target is `unsupported`, not a
zero score or success. Retain raw reports plus original/rebuilt/PDB/source hashes.
Normalize each tool's actual claims; do not sum percentages across unlike checks.

The adapter must distinguish failed execution, missing inputs, malformed report,
empty comparison, explicit mismatch and supported comparison. Tool exit code alone
is not acceptance. Compare reports must bind to the exact binary/PDB and source
snapshot; never reuse a PDB from another build. Annotation addresses are per-build
analysis coordinates, not literal addresses in generated runtime bindings.

### ReAgent

The inspected [ReAgent revision](https://github.com/Dryxio/reagent/tree/d12cea338c61898b06a86fe8adb25275fa9d5615)
is an independent candidate/checker and validation workflow, not a substitute for
AgentDecompile's test runner or byte oracle. Its heuristic parity and structural
checks can refute a candidate; GREEN/checker PASS does not prove equivalence.
Standalone parity requires `--strict-exit` to make RED affect the exit status.

Use bounded manifests, immutable evidence snapshots and isolated candidate overlays.
Configure genuine target-owned build/test/runtime commands as argument arrays and
require their results. Commands must actually consume the candidate; verify that
its emitted contribution reaches the observed artifact. Do not use dummy commands,
turn verification off, or trust arbitrary model-supplied commands. Capture provider,
model, exact responses, call/round limits and available usage data. Bridge evidence
must be reused from existing analysis; a second Ghidra writer is not admitted.
Missing bridge exports or provider setup is a named blocker.

### isle as an output reference

Use [isle's inspected project](https://github.com/isledecomp/isle/tree/8119bd013645972c72480e4de21529f1e91ce5c7)
as a reference for organized C++ sources, per-target build configuration, reccmp
annotations and readable comparison reports. Its reported exact-rebuild results
are upstream evidence, not AgentDecompile results or proof of other targets.
Keep comparator reports and fresh whole-file reconstruction receipts separately.
Generate a project per selected build/family with source fragments, compilation
groups, headers, dependency/toolchain manifests and evidence; original retail
binaries remain external inputs. Do not copy game-specific source into the generic
core or assume a universal compiler/engine profile.

## Vanilla memory-modding lane

For an exactly recognized build: verify image identity → recorded RVA → live
expected bytes or structure → requested capability preflight. Module-relative
locations are valid for known builds; unknown/changed builds use discovery ladders.
A match may remain located-only. Generated bindings expose capability-specific
refusal reasons, supported prototypes and dynamic-root recipes, not immortal
cached object pointers. Per-instance lifetime and game-thread requirements remain
runtime checks.

Capabilities are independent: located, readable, callable, detourable and writable.
For calls, require a supported ABI adapter plus valid receiver, argument/return
ownership and lifetime. For hooks, require supported instruction relocation,
patch ownership, original bytes and a tested install/remove protocol. Prove no
execution can return into a trampoline before reclaiming it. Avoid a universal
suspend-thread recipe; rollback restores journaled byte patches, not arbitrary
side effects of already-executed code.

Executable allocation is conditional on platform/process policy. Zero-filled
storage, section slack and headers are not automatically expendable caves. A
policy denial yields `unsupported_dynamic_code` or `not_detourable`; do not seek
another writable area to evade it. Unknown builds may remain unresolved, absent,
inlined-only, ambiguous, unsupported, insufficient-evidence or budget-exhausted.
New corpus evidence may reveal collisions and lower previously trusted coverage.

## Cache and acceptance invalidation

Workers consume a stable analysis snapshot and return proposals naming that version.
Central acceptance checks relevant dependency versions again before commit. Scope
cache keys to local compilation inputs, pairwise matching evidence or publication
corpus snapshots as appropriate. Ghidra analysis changes must invalidate affected
native decompiler caches before a new result is recorded. Repeating valid unchanged
work is waste; revisiting changed evidence is necessary.

Retain exact observations and AI responses for deterministic replay. Deterministic
replay does not promise deterministic discovery. A bad seed invalidates its
unsupported descendants; ten copies of one seed are not independent confirmations.
Shuffled completion order must not choose a different winner. Atomic publication
keeps the previous complete export usable until a new manifest is committed.

## Implementation slices and acceptance owner

The coordinator owns acceptance; investigators and tool providers submit proposals.
Independent verification includes independent evidence lineage, not merely a
second process or a differently named agent. Independent design reviewers challenge this document; review agreement is not
software acceptance. The execution design specifies the future coordinator role.

| Slice | Existing seam / work | Completion evidence | Current state |
|---|---|---|---|
| R0 Design package | Strategy, consolidated design, contracts and diagrams | Requirement traceability, resolved design findings, readable synchronized artifacts | Design work only; completion recorded by design review |
| R1 Typed evidence | Existing binding/receipt/catalog consumers | False-label case rejected; capability-specific readiness and descendant withdrawal | Future implementation; design specified below |
| R1a Tools | Optional external CLI adapters | Versioned report ingestion, input identity checks and explicit missing-tool outcomes | Pinned isolated canaries and cached-evidence ReAgent ingestion delivered; full binary-backed execution adapters remain open |
| R2 Region reconstruction | `corpus/asm_seed.py`, workspace emission and full-image receipt verifier | Unchanged region through real extraction/fixup/placement, then a compiled replacement shown in final bytes | Not implemented by this change |
| R3 Candidate propagation | `corpus/cross_place.py`, corpus relationship/receipt storage | Variant compatibility, recipient validation, candidate/accepted separation; changed sibling refused | Planned; existing copies are not recipient verification |
| R4 Claims/invalidation | Receipt consumers and grid acceptance | Independent facts, stale-dependency rejection, seed withdrawal, deterministic replay | Planned; legacy evidence not upgraded |
| R5 Runtime/export | `corpus/export_hookpack.py` and supported runtime consumers | Known-build RVA/live check, per-capability refusal, install/remove/lifetime proof | Planned; existing v1 export is not this complete contract |
| R6 Repeated projects | Existing workspace/export generator | Two held-out builds produce inspectable source+comparison+binding bundles | Planned; no universal coverage claim |

### Required demonstrations

1. Unchanged region extraction → reconstructed object → placement → original-byte
   comparison, including references and metadata. Then a compiled replacement;
   deliberately discard it and ensure recovery credit disappears.
2. Known-source target corpus: unchanged siblings, changed behavior, identical folded
   bodies, inlining, layout and supported optimization changes. Hold out whole
   builds; assess false acceptance as well as coverage.
3. ReAgent checks representative arithmetic, FP/NaN, object methods, global-data,
   indirect-call and exception-sensitive candidates. reccmp checks supported rebuilt
   binaries/PDBs, vtables/data/exports; objdiff and final linked/full-file checks
   retain independent claim boundaries. Report every failed/unsupported/not-run check.
4. Change a type, withdraw a seed, shuffle completion order, interrupt export and
   resume. Only relevant receipts become stale; no invalid descendant survives.
5. Original vanilla runtime: exact build admission, live location checks, supported
   read/call/hook, independent state/event observation, removal and storage lifetime
   verification. Runtime behavior never increases recovered-source coverage.

## Historical design-only scope and completion

During the design phase, the user's correction required the plan, design and
diagrams exclusively. The earlier workbench availability check and dependency
requirements file exceeded that scope. The requirements declaration has been
converted into [documentary integration design](2026-09-22-external-validation-design.md).
Service availability, provider installation and compiler/runtime execution are not
prerequisites or blockers for finishing these artifacts. No product implementation,
service probe, installation, recovery execution, build or test suite belongs to
that completed design goal. The later explicit user build request authorizes
implementation under the repository operational constraints; the active
[session obligation audit](2026-09-22-session-obligation-audit.md) tracks the unfinished
software and verification work.

[The design package](2026-09-22-design-package.md) defines the complete artifact
set, requirement traceability, critique decisions and design acceptance. Future
experiments below and in the execution contract remain **NOT RUN**. A design can
be complete while its engineering hypotheses still require the specified future
measurements; unknown empirical outcomes are not hidden as design delivery.

## Binding acceptance: presence, identity and operation

These predicates are evaluated separately for a proposed binding `b` against an
exact target digest and evidence snapshot. A predicate's result names its evidence
roots, validity scope and limitations. The hypothetical example below is a design
walkthrough, not a runtime observation.

| Predicate | What it proves | What cannot satisfy it |
|---|---|---|
| `presence(b)` | Recorded file↔RVA mapping, region bounds and bytes match the exact original image; live bytes are separately checked for runtime use | A copied label, source filename, or different build's digest |
| `identity(b)` | The target region implements the intended entity under an explicit target-side correspondence rule | A signature/hash generated from the same label-selected address; compile-only cross-placement; agent agreement |
| `operation(b, op, live)` | Requested read/call/write/detour has supported ABI/layout, ownership/lifetime, policy and current runtime preconditions | Located address alone; successful source recovery alone; an old live preflight |

`accepted_binding = presence AND identity AND current_dependencies`.
`runtime_ready(op) = accepted_binding AND operation(op, current_live_state)`.
These are predicates, not a single confidence score or an implied state ladder.
Readable does not imply writable; callable does not imply detourable. A source
candidate may remain unverified while the original-code binding is callable.

**Admissible identity evidence:** choose an explicit rule version, not an arbitrary
vote count. Rule T1 requires authentic target debug/provenance tied to the image
and consistent boundary/call-site evidence. Rule T2 requires a unique target-side
structural/call/data relationship with discriminating semantic anchors and an
independently justified entity association. Rule T3 requires a target runtime
observation that discriminates this entity from named alternatives, with independently
established observation sites. Each rule retains rejected alternatives and must
refuse ambiguity. Unsupported targets/rules yield insufficient evidence. No rule
accepts a label solely because its selected bytes match a derived signature.

Independence is a dependency-graph property. The identity evidence subgraph must
contain a discriminating target fact whose entity association does not descend
from the candidate label/address seed being validated. Sharing the original image
as a ground-truth input is allowed; sharing the unproved semantic assignment as
the root of every witness is not. Two tools consuming the same bad seed count as
one lineage. Rule thresholds and collision checks are versioned with acceptance.

### Worked counterexample: Foo label over Bar bytes

1. A donor candidate proposes `Foo` at target RVA `0x2100`; target region is Bar.
2. A signature is generated from those bytes. Both offline and live comparisons
   match, so `presence=passed`.
3. All identity evidence descends from the donor label. `identity=insufficient_evidence`;
   the generated signature cannot close this gap. Retain the candidate in the
   hypothesis queue, not the accepted catalog. No Foo call/header/pack claim is published.
4. A target-side debug/call-site witness later distinguishes Bar. Reject Foo's edge,
   invalidate its unsupported descendants, and accept Bar only under the applicable
   rule. A new evidence version permits reevaluation; there is no platform-wide ban.
5. An independently supported entity Baz on another build and cached report export
   proceed throughout. The missing Foo identity blocks only Foo-dependent claims.

### Worked reuse counterexamples

- Same logical method, build A returns `x+1`, build B returns `x+2`: separate
  implementation variants. A's compiling source can be investigated as a candidate
  for B but cannot be selected as an accepted replacement without B's checks.
- Two logical methods share one folded body: preserve two entity relationships to
  the physical region. Do not merge conceptual identities solely by address.
- A 32-bit pointer field at offset 4 does not prove an offset of 8 on a 64-bit
  build: per-build layout evidence is required; an unknown span remains opaque.
- Type version changes while a worker compiles: retain its old result as historical,
  reject current acceptance, enqueue only affected work against the new dependency.

## Reconstruction mechanism and evidence route

Select a region-first design with an explicit placement recipe. The diagram's
floor is a preserved-region object/assembly backend, not a C wrapper filled with
byte arrays. A delinker may propose reconstructed COFF references but cannot
certify its own target interpretation. Architecture support is a capability probe
and required-format contract; unsupported emitters do not fall back to fabricated
objects. Larger regions preserve unresolved internal boundaries.

The original image remains the independent byte oracle. The region record above
is converted into a proposed relocatable object plus a fixup map. Placement consumes
that object and associated metadata, validates references at their final addresses,
and compares emitted regions to raw original image ranges. The layout recipe records
section geometry, file alignment, virtual alignment, imports/IAT, base relocations,
TLS, resources, exception data, padding and header fields; unknown metadata is
explicitly preserved and excluded from source-credit accounting. `/ORDER` alone
cannot stand in for this recipe.

A future acceptance example uses a region that references another region and data:
extract original R and associated D → reconstruct references → emit R.obj → place
R.obj/D through the selected layout machinery → compare linked bytes to original.
Then compile an actual C/C++ candidate replacing R and repeat. The contribution
map ties candidate/group/object hashes to exact emitted ranges; an omitted object,
linker-eliminated candidate or fallback-selected region receives no recovered-source
credit. Deliberately discard the replacement as a negative control. Immutable
original bytes may remain in other floor ranges, explicitly counted.

Early unchanged round trips certify reconstruction machinery only. Final source
claims additionally require fresh compilation of the complete selected source,
valid local/linked receipts and source contribution. Maintain the Cartesian axes:
`method = reconstruction | original_style_build` and
`variant = byte_accurate_with_floor | max_c`. Each method/variant has its own input,
layout, contribution and whole-file receipt. Exact reconstruction does not imply
that the historical build process was recovered. Max-C is a measured source mix,
not an automatic claim of zero floor or exactness.

## Future acceptance specifications — NOT RUN

| ID | Setup / negative control | Deciding observation | Scope of evidence |
|---|---|---|---|
| RC-01 | Unchanged region with external code+data fixups; corrupt one reconstructed addend | Correct case matches linked original; corruption fails independent linked check | Reconstruction path only |
| RC-02 | Compiled replacement; deliberately discard it at link/selection | Discarded case earns zero source contribution despite any equal fallback bytes | Source contribution |
| RC-03 | Held-out sibling with x+1→x+2 behavior change | Same logical family allowed; incompatible accepted replacement refused | Variant/recipient acceptance |
| RC-04 | Folded bodies, inline-only and split regions | Entity/physical multiplicity retained; no invented standalone address | Identity representation |
| RC-05 | Arithmetic, FP/NaN, methods, globals, indirect calls, exception metadata | Per-check outcomes retained; compile or ReAgent GREEN never promotes other facts | Scoped source verification |
| RC-06 | Type dependency changes mid-attempt; unrelated build added | Affected result stale; unrelated local compilation cache remains valid | Dependency projection |
| RC-07 | Same evidence/proposals, shuffled discovery/worker completion order | Same accepted state under deterministic policy; tied ambiguity stays unresolved | Replay, not discovery |
| RC-08 | Wrong target label with matching extracted bytes | Presence passes, identity fails, unrelated accepted binding remains usable | Circular-proof rejection |
| RC-09 | Original binding has valid identity/ABI but source is floor | Supported original-code operation may pass; source progress unchanged | Runtime/source independence |
| RC-10 | Genuine negative pair vs absent/inlined/unsupported/budget-limited | Explicit terminal reason; no forced match and no claim of exhaustive failure | Honest coverage |

The execution design adds interruption, ownership, storage and scenario failure
specifications. These are acceptance requirements for later implementation, not
requests to run anything during design authoring.
