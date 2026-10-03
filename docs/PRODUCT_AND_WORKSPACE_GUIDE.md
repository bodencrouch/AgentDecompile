# AgentDecompile: what it delivers and how the workspaces should explain it

This guide explains the product and translates its recovery diagrams into useful
operator workflows. It supplements the [charter](../VISION.md),
[strategy](../STRATEGY.md), [frontend requirements](FRONTEND_INTENT.md) and
[frontends implementation plan](plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md).
It does not replace those authorities or declare their unfinished work complete.
The [delivery ledger](DELIVERY_STATUS.md) owns historical qualification claims;
new source changes need their own consumer evidence. The [September 28 source status](FRONTEND_IMPLEMENTATION_STATUS.md) records the implemented interfaces and their remaining acceptance boundaries.

## The problem AgentDecompile solves

Compiled software contains much more information than a decompiler's text pane
can express. Instructions, data, calling conventions, resource layouts, debug
symbols, relationships between builds and observed runtime behavior all help
explain what a program does. Usually that information is scattered across tools,
addresses, spreadsheets and individual researchers' notes. A useful discovery in
one release is difficult to transfer to another release without accidentally
carrying over a wrong address, type layout or implementation assumption.

AgentDecompile brings this material into a shared, provenance-bearing workspace.
Its Ghidra/PyGhidra integration supplies analysis and interactive access; the
recovery layer organizes evidence, identifies related entities, produces source
candidates, compares compiled output, and exports reusable knowledge. Humans and
agents should be able to inspect the same facts, follow the same program location
and use the same backend actions. An incomplete recovery should still leave useful
names, source fragments, types, signatures, layouts and explicit unresolved work.

The near-term recovery objective is demanding: recover readable C/C++ and rebuild
an image whose bytes match the original. That objective coexists with earlier
useful results. A verified signature, an evidenced structure field or a supported
call into the original game can be valuable before full source recovery finishes.
Each has its own evidence requirements. None silently becomes proof of the others.

### Deterministic recovery with optional AI

The supplied Wizard account describes the intended shift clearly: much of the
reverse-engineering work should become an automated, deterministic pipeline over
related binaries, with reusable signatures and source replacing repeated manual
address research. This is consistent with the strategy's cheap-first recovery
policy. Existing analysis, authentic symbols, hashes, references, control-flow
relationships, decompiler output, compiler diagnostics and byte comparison should
resolve everything they can before model-based repair is considered.

AI remains an optional way to propose repairs for diagnosed residue. Switching it
off must leave deterministic matching, compilation, repair, candidate propagation
and verification usable. The effective setting and its source belong in the UI;
a generic “AI working” indicator would obscure the actual task and evidence.
An AI proposal is retained as an input to verification, never as proof of identity
or parity. Deterministic replay means the same recorded inputs, options, toolchain,
policy and basis reproduce the same decisions and artifacts. Discovery and live
observations may vary; their recorded results become versioned replay inputs.

### One entity across several builds

Consider a function that hosts a lobby. Related builds may implement the same
logical operation with different addresses, instruction sequences, calling
conventions and object layouts. AgentDecompile should relate the logical entity
to its implementation variants and then to physical instances in each image.
A matching name alone is insufficient to share source or call an instance.

For an exact known build, a recorded module-relative address followed by current
byte and identity checks can be the best route. For another build, a supported
resolver can try masked signatures, identified callers, imports, strings, vtables
or other bounded locators. The result records which method succeeded, what was
verified and where ambiguity remains. Portable identity does not promise that
one byte pattern or one ABI works everywhere. Known-build address resolution is
useful but must remain visibly distinct from successful portable discovery.

A user then works with “host lobby on this build” or a named field rather than
copying an absolute platform address into a script. A runtime adapter still needs
the right arguments, object lifetime, engine thread, permissions and current
state. Missing prerequisites produce a structured refusal and a next step.

### What the multiplayer report establishes

The user reports that the original studio's unmodified code can now create a server, host a lobby,
view the lobby and let players join. This is a user-reported original-code
capability, a concrete motivation for runtime reuse. This guide has not observed
that scenario or inspected a matching live receipt. It does not establish full
multiplayer gameplay, protocol compatibility, qualification across all builds,
recovered-source equivalence or a whole-image rebuild.

The useful product response is to make each supported operation discoverable,
show the exact build and prerequisites, expose its binding through the shared
operation contract, and retain independent observations of its result. The UI
should say “reported; awaiting attached scenario evidence” until a qualified
receipt is available, then name precisely what that receipt proves.

## Two different server/client distinctions

AgentDecompile's coordinator, workers and interfaces are product deployment roles.
The coordinator owns durable decisions and acceptance; capable workers carry out
bounded tasks; the static and Vite frontends present shared state. Separating these
responsibilities supports smaller client installations, focused worker
capabilities and remote compute without duplicating the acceptance authority.

A game's server and client are reverse-engineering targets and runtime roles.
Their original functions, data and network behavior are material the product may
identify and expose. Splitting AgentDecompile's coordinator from its clients does
not itself produce a game server, establish a game protocol or make multiplayer
work. The two distinctions need different names in navigation and documentation.

The donated-compute package is a supporting execution layer. Its purpose is to
let a laptop, an idle desktop or a compatible cloud worker contribute useful work
under explicit resource limits. It is not the entire recovery product, and a
large worker count is not a recovery result. The [grid gap assessment](plans/2026-09-28-grid-multi-node-gaps.md)
tracks its own implementation limits. Donation here means compute capacity; no
fundraising workflow is required to explain or use the architecture.

## Reading the pipeline as work that produces evidence

The [recovery overview](dashboard-design/pipeline-diagram/agentdecompile-recovery-pipeline.svg)
is a dependency map. Stages are not nine buttons and not a mandatory single pass.
Identity and calibration refine one another; reconstruction checks start early;
parity runs whenever candidates become available. Valid unchanged receipts are
reused, and only affected descendants are invalidated when evidence changes.

| Stage | Problem solved | Useful output and acceptance boundary |
|---|---|---|
| 0 — Open, add, resume | Recover the actual project state without duplicate work. | Bindings, current ownership, reusable receipts and admission of eligible missing work. Reopening does not imply reanalysis. |
| 1 — Identity | Relate entities across builds without forcing false matches. | Logical entities, variants, instances and evidence lineage. Similarity is a candidate relationship until independently accepted. |
| 2 — Calibration | Determine the platform and compilation context. | Versioned format, architecture, ABI, compiler/linker, libraries, macros and layout facts with build/TU/function scope. |
| 3 — Linkable regions | Preserve enough original structure to reconstruct an image correctly. | Regions, fixups, data, unwind information and placement recipes. An unchanged round trip proves infrastructure, not recovered C. |
| 4 — C/C++ candidates | Turn decompilation into readable compiling material. | Source candidates and compile receipts. Compilation admits a candidate; it does not authorize replacement. |
| 5 — Propagation | Reuse a candidate where the recipient can support it. | Compatible recipient candidates with separate compile, ABI, layout and parity checks. A logical identity alone cannot authorize copying. |
| 6 — Optional targeted AI | Repair diagnosed residue after cheaper applicable methods. | Bounded, recorded source proposals, with the reason AI was needed. Disabled AI never blocks deterministic work. |
| 7 — Continuous parity | Compare emitted regions with trustworthy target material. | Separate local relocation-aware, linked-region and behavioral evidence. Local zero difference is not whole-image identity. |
| 8 — Whole-image identity | Establish the terminal byte-accurate recovery claim. | A fresh compile of current source, proven replacement contribution, complete reconstruction and whole-file byte/hash comparison for the named build and variant. |

The pipeline reports explicit non-success outcomes: absent, inlined-only,
ambiguous, unsupported, insufficient evidence, budget exhausted and contested.
These are useful answers. Forcing a guessed match would make every downstream
export less trustworthy.

### Five lanes remain active beside the stages

| Lane | Practical purpose | Workspace consequence |
|---|---|---|
| A — Knowledge fusion | Keep the strongest supported name, comment, type and field information from each build. Preserve provenance and alternatives; gate physical layouts separately. | Show origin and conflicts per field. Editing one name must not wholesale overwrite another build's type evidence. |
| B — Cross-build unification and export | Describe all relevant entity kinds, locators, layouts, divergence, ABI and cave plans. | Navigate functions and data together; inspect entity-by-build readiness and explain each exported capability. |
| C — Runtime reuse and learning | Resolve supported original-code operations, preflight them, observe behavior and return provisional evidence to the corpus. | Keep runtime observations separate from source parity and pack resolution status. |
| D — Verification and determinism | Bind outputs to relevant input and tool versions; reject stale evidence; reproduce artifacts under the same basis. | Every claim links to its basis and receipt. Coverage may decrease after a contradiction without deleting history. |
| E — Distributed compute | Run bounded tasks on qualified machines and independently accept returned proposals. | Show worker capabilities, actual assigned units, resource pressure, acceptance and exact waits. Heartbeats do not increase recovered coverage. |

The overview's entity scope includes functions, patch points, globals, structures,
fields, vtables, strings, tables, dispatch, resources and other kinds. A
function-only viewer or exporter cannot stand in for that broader contract.

## Useful deliverables before full recovery

| Deliverable | What it enables | What the UI must disclose |
|---|---|---|
| Source and comparison projects | Inspect and improve recovered candidates, rebuild and compare named regions. | Candidate versus accepted source; exact toolchain/basis; byte-accurate C+floor and max-C as separate variants. |
| Signatures and entity catalog | Find a logical entity in supported builds without application code carrying fixed absolute addresses. | Identity evidence versus locator evidence; known-build pinning, ambiguity and per-build coverage. |
| Per-build C/C++ headers | Consume evidenced types, offsets and calling conventions. | Unknown spans remain opaque; layouts belong to a particular build; pointers cannot be guessed by width scaling. |
| Hook pack v2 | Carry entity kinds, ordered locators, ABI/storage, caves, integrity information and basis in one consumer contract. | A pack is evidence and plans, not permission to call or patch a process. |
| Generated Lua | Address entities and fields by supported names and handles; share typed operations with other clients. | No literal addresses; structured refusals on unsupported resolution or inadequate ABI confidence. |
| Cave and injection plans | Describe possible detour placement and restoration for a qualified adapter. | Anchor, capacity, relocation rules, originals and architecture support; live install/remove and safe reclamation still require proof. |
| Readiness report | Answer “what can I do on this build?” before downloading artifacts. | Resolved, pinned, degraded, ambiguous, unresolved and contested pack states, with runtime `observed_status` on a separate axis. |
| Divergence report | Explain why related builds cannot share an implementation or layout directly. | One-to-one, split/inlined and diverged relations; field, slot and table changes with evidence. |
| Bundle manifest and receipts | Let a consumer verify exactly what was exported and reproduce it. | Basis, input and artifact hashes, required-artifact verification and explicit `not_in_scope` for optional source variants. |

A partially populated corpus can produce honest exports, but a required artifact
failing its verification gate cannot be hidden by publishing an apparently
complete bundle. Entity uncertainty is data inside a valid export; a broken
artifact contract is an export failure.

WASM has several distinct meanings here: browser-local analysis, donated browser
compute, a WASM-consumable export and a whole game running in the browser. Evidence
for one does not establish another. The frontends plan explicitly records an
unscoped WASM export target; that disclosure is not its implementation. The M7
roadmap separately requires a demonstrated executable route and interactive game
acceptance.

The [export scope receipt](EXPORT_SCOPE.md) records the WASM exclusion explicitly
without removing the independent whole-game browser objective.

## Execution, evidence and recovery in plain language

The [execution companion](dashboard-design/pipeline-diagram/execution-contracts.svg)
requires a task to declare its exact inputs, requested result, proof obligations,
resource needs, retry owner and budget. Admission checks complete prepared inputs,
capacity and actual ownership. Workers compute outside a long database
transaction and return immutable proposals. Artifacts are prepared durably before
a short acceptance transaction checks current dependency versions and ownership
generation and commits references to the accepted evidence.

Runtime use has three independent questions: are the expected bytes present; is
this independently identified as the intended entity; and does current ABI,
layout, lifetime, thread and policy evidence permit this operation? A signature
made from a selected address cannot prove the name used to select it. “Located,”
“readable,” “callable,” “detourable” and “writable” are different capabilities.
Original-code operation acceptance and recovered-source acceptance remain
independent outcomes, not successive rungs of a single readiness ladder.

Fencing rejects publication from an obsolete attempt. Quarantine prevents reuse
of resources an old worker may still access. These solve different problems. If
an expired worker later returns byte-perfect output, those bytes do not restore
its authority, and expiry does not prove its process stopped. A replacement can
continue only on safe resources with complete inputs and current authority.

The [resilience companion](dashboard-design/pipeline-diagram/resilience-contracts.svg)
adds the failure lifecycle: classify the observed problem, durably record the
decision, repair or reroute only justified prerequisites, independently accept
new evidence, resume the affected capability, and use bounded policy experiments
to prevent recurrence. One noisy sample is insufficient to declare a provider
unhealthy. A deterministic negative needs a changed hypothesis, not endless retry.

If a runtime command might have executed before its acknowledgement was lost,
its outcome remains unknown until observed and reconciled. Reconnecting must not
blindly repeat it. If the decision store becomes unavailable, affected mutations
pause and cached evidence remains visibly dated and read-only. The system retains
the objective and unrelated eligible work. Host failover requires both a complete
independent input replica and a capable worker; the mere presence of another host
is insufficient.

## Static 8080: a project-wide CodeBrowser

The static dashboard should feel like an analysis workspace that happens to show
ongoing recovery. It must remain usable without a Node runtime. One workspace tab
contains one project, with related builds as peers. The main navigation is the
program location and logical entity, not the pipeline stage.

The left rail contains Symbol Tree and Program Trees, with Data Type Manager
below. Listing and Decompiler occupy the central workspace; secondary providers
dock or tab beside them. Console, Bookmarks and actual pipeline activity occupy
the bottom dock, with a compact type preview. Memory Map, Bytes, Defined Strings,
Symbol Table, References, Functions, Function Graph, call trees, Function
Comparison, Equates and Relocations remain available without duplicate trees.

Selecting a symbol, address or reference moves every connected provider. Back and
forward, go-to, previous/next function and token highlighting make navigation
predictable. The docked cross-build map shows both call relationships and matching
results on that same selection. Listing and Decompiler function headers carry
match marks; details distinguish a byte comparison from a name or graph match.

For a large corpus, most builds remain lightweight rows showing build identity,
readiness, stage and whether the selected entity is bound. Only the focused peer
in each pane loads expensive live Listing or Decompiler data. A peer can be
loading, queued for a serialized read, locally readable or blocked with the real
backend reason. “No identity binding” stays visible rather than becoming an empty
pane or an invented counterpart.

Opening a project, adding a binary or resuming admits only eligible missing work.
The admission receipt names the run, generation and queue position. Pause, resume
and stop are the workflow controls; stage and export Start buttons are absent.
Renames, comments, bookmarks, type edits and match decisions remain explicit
operator actions, with backend version checks and visible conflicts.

Readiness is encountered before artifact download links. The static surface must
expose project/build exports and their evidence; it is not a reduced landing page
that sends operators to Vite for essential functionality.

## Vite: an evidence and comparison workstation

The Vite application is a full alternative product surface over the same backend,
with `/react/` as its packaged route. Its principal view is an instruction-aligned,
two-column comparison with a symbol tree, register highlighting and navigable
mismatches. A selected entity, build pair, version and region drive all panels.
It must not introduce a second selection store or a separate interpretation of
readiness.

Scratch work extends the existing candidate workflow through catalog-backed
compile and comparison actions. Multiple decompiler outputs can sit side by side
using supported local runners; this does not imply uploading binaries to a public
service. Expert views and container/resource navigation keep the normalized
selection. The pipeline DAG shows dependencies, actual advancing units and
failures; it is an observation surface, not a collection of manual stage buttons.

The distributed view distinguishes source/recipient build decisions from worker
machines. It shows task capability, input availability, owner, checkpoint,
proposal, verifier and accepted result. Spectating is a separate read-only mode,
local and opt-in, with revocable authorization and no mutation capability.

| Shared question | Static presentation | Vite presentation |
|---|---|---|
| Where am I? | Connected Listing/Decompiler cursor across project peers. | Selected entity/build pair/region across aligned comparisons and expert views. |
| Why are these related? | Function-header marks, call graph and build-pair matrix. | Evidence details, candidate alternatives and comparison views. |
| What changed? | Current annotations, source and receipt-linked activity. | Instruction and source differences with exact mismatch navigation. |
| What can I use? | Build readiness summary followed by exports and downloads. | Entity-by-build readiness with artifact and operation details. |
| Why is work waiting? | Inline peer state and bottom activity reason. | Dependency DAG, affected task and exact wake condition. |
| What has been proven? | Shared tiered report and receipts. | The same report basis and claim tiers, expanded for investigation. |

Both surfaces should draw actual work: changed code, completed comparison regions,
new evidence, accepted bindings and invalidations. Movement must correspond to
observed events. Counts and percentages remain secondary and use explicit,
reconciled inventories; animation must not manufacture apparent progress.

### State and error behavior

| Situation | Required behavior |
|---|---|
| Loading or queued read | Retain selection, name the pending provider or serialized resource, and distinguish waiting from absence. |
| Request returns after selection changes | Discard or retain it only under its original selection key; never overwrite the newly selected build. |
| Method unavailable | Show the method and reason; continue applicable fallback methods. BSim availability is not a global gate. |
| Pair not scheduled | Say “not scheduled” with the scheduler reason; do not render it as a failed match. |
| Stale edit/review basis | Explain the changed version and refresh; never silently apply a decision to a different selection. |
| Connection lost | Show the last observation time and read-only stale snapshot. Never claim freshness or queue hidden mutations. |
| Unknown command effect | Show reconciliation state and block conflicting replay, while independent read-only work remains accessible. |
| Resource quarantine | Name the occupied resource and missing release evidence; a lease countdown is not a release promise. |
| Evidence invalidated | Withdraw only dependent readiness, retain history and explain scheduled revalidation. |
| Missing support or credential | Name the precise dependency, affected scope and continuing independent work. Avoid a generic “failed” badge. |

### Three progress measures and honest metrics

Liveness answers whether a process or connection is responding. Execution progress
counts durable, distinct completed work units, including negative results. Goal
progress counts newly accepted predicates or capabilities on the current basis.
These should appear separately. An uninstrumented external worker has unknown
execution progress even if it is alive.

Source metrics distinguish compiling advisory C, accepted readable source,
preserved floor and unclassified material. A report should reconcile disjoint
representation buckets to the exact inventory while allowing capability claims
to overlap. Cross-placed compiling candidates are not accepted recipient source.
Identity coverage includes unresolved/ambiguous outcomes, and runtime coverage is
entity × build × operation over a named eligible inventory. Show known-build
resolution separately from portable discovery. New contradictions can lower
coverage; retaining that decrease is correct behavior.

Generating local `report.json` is separate from publishing statistics. External
publishing remains its own explicitly authorized action.

## From foundations to autonomous capabilities

The [autonomous capabilities diagram](dashboard-design/pipeline-diagram/autonomous-capabilities.svg)
and [roadmap](plans/2026-09-22-autonomous-capability-product-roadmap.md) distinguish
future product delivery from partial software foundations.

| Milestone | Intended useful outcome | Required proof boundary |
|---|---|---|
| M0 — Reliable continuation | Preserve attempts, budgets, unknown outcomes and exact next actions across resume. | Diagram records an implemented, partially verified foundation; broader obligations and native live delivery remain open. |
| M1 — Effective scenario | Prepare a fixture, execute the effective script, observe, capture and clean up without routine user repair. | Actual game receipt, including resumption of mixed passed/blocked work. |
| M2 — Operation bundle | Share ABI, units, ID domains, lifetime and effect/restoration contracts across help, CLI, Lua and harness. | A consumed binding plus an independent game-state oracle; unsupported builds refuse. |
| M3 — F12 workspace | Query objects, execute Lua, edit supported properties, inspect errors and copy operations as Lua. | Real keyboard/focus/input, engine-thread execution and shared operation IDs; a browser mockup is insufficient. |
| M4 — Creative projects | Compose and reopen a meaningful native scene and shot. | Defining native behavior, intact capture and usable presentation, with protected installs and isolated scripts. |
| M5 — Playback/checkpoints | Pause, save, restore and replay supported branches using stable selectors and fresh lifetimes. | Scoped inventory/quest/party/script restoration and explicit exclusions; no arbitrary-memory rewind claim. |
| M6 — Native host matrix | Support exact native builds and compatible execution workers. | ABI, graphics, input and capture evidence per build and architecture; one platform's evidence does not qualify another. |
| M7 — Whole-game browser | Establish a feasible browser runtime route, then useful interactive gameplay. | Rendering, input, audio, saves, main loop, sustained play and shared devtools protocol. A WASM helper or shell does not qualify it. |

A complete product demonstration must connect discovery, binding, UI or Lua,
prepared scenario, independent observation, supported restoration and a useful
recorded clip. Behavior, capture integrity, presentation, source parity and
platform qualification retain separate predicates and receipts.

## Three practical workflows the interfaces should support

These are intended end-to-end workflows, not reports of completed demonstrations.

### Investigate a function across releases

An operator opens a project containing several related builds and selects a
function in the best-understood build. The static workspace synchronizes Listing,
Decompiler, references and the cross-build map. Vite can open the same selection
as a two-build comparison. Both surfaces show whether each proposed counterpart
comes from accepted identity, a name, a signature, a graph relationship or a
still-unreviewed candidate.

For a recipient with different object layout, the operator sees the incompatible
fields and the evidence behind that decision. The pipeline may reuse knowledge
that is valid per field, while refusing incompatible source placement. A source
candidate that compiles appears as compiling; linked comparison and whole-image
results stay separate. The result is useful even when recovery is incomplete:
an explained relationship, reusable names and types, and a precise remaining gap.

### Expose an original-code lobby operation

The starting fact is the user's reported server/lobby/join capability. Select the
exact game build and a named operation, then inspect its identity and runtime
prerequisites before exposing a call. The consumer needs the verified entity,
parameter and return storage, object lifetime, engine-thread rule and supported
state. Finding a signature does not fill those other fields automatically.

The intended operation bundle gives UI, Lua and the scenario harness the same
operation ID and contract. A controlled scenario records the requested effect
and independently observes the server or lobby state. A join operation needs its
own observations; a successful host call cannot stand in for it. If a reply is
lost, show the outcome as unknown and reconcile game state before considering a
retry. Once evidence qualifies an operation, the UI can explain exactly which
build and scenario it supports. Recovered-source parity remains a separate task.

### Contribute an idle machine

A contributor joins with declared capabilities and resource limits. The
coordinator assigns only tasks with complete available inputs and a compatible
worker/toolchain, and preserves the user's ability to pause or stop contribution.
The contribution view shows the actual unit, input basis, resource use, checkpoint
and waiting reason rather than presenting a heartbeat as recovered code.

Returned artifacts are proposals. An independent verifier checks their required
predicates under the current basis and ownership generation before acceptance.
Late output retains its history but cannot replace current accepted work; resource
release still needs proof that the old worker stopped accessing it. The donor
therefore contributes measurable accepted work without becoming the authority
that declares its own result correct.

## Traceability and remaining delivery scope

Requirement and unit IDs below are scoped to the
[September 28 frontends plan](plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md).
That plan's U30, for example, is not the older portable-plan U30. The
[weekend delivery ledger](plans/2026-09-27-weekend-unit-delivery.json) preserves all
193 original identifiers; the newer frontend/export slice does not retire them.

| Diagram/product obligation | Frontends plan coverage | Broader obligation that remains independently required |
|---|---|---|
| Open/resume without duplicate work; visible ownership | R1–R8, R15–R18, R24–R26; U1–U7 | Full admission/resource ownership and durable continuation across backend providers. |
| Entity relationships and available matching methods | R19–R34; U8–U14, U43 | Evidence lineage, independent identity acceptance and all entity kinds in the weekend scope. |
| Deterministic path with optional AI residue | R35–R38; U15–U17 | Every producer and nested retry path respects the same effective policy and budget. |
| Comparison workstation, activity, compute and spectator views | R39–R46; U18–U25 | Real provider execution, distributed acceptance, local authorization and qualified runtime consumers. |
| Honest progress and publication separation | R47–R50; U26–U29, U43 | Scoped receipts, exact inventory reconciliation and fresh terminal whole-image acceptance. |
| ABI, pack, Lua, cave/header/readiness/divergence bundle | R51–R63, R66–R70; U31–U39, U41–U42 | All required underlying entity/locator/decoder/adapter contracts and live operation proof. |
| WASM scope made explicit | R64–R65; U40 | A selected export/runtime target and the independent M7 feasibility and interactive acceptance work. |
| Verification | U30 and the plan's acceptance/usability examples | Actual checks under current operating authority; a written test scenario is not a passed receipt. |

The inspected source includes a v1 hook-pack emitter in
[`export_hookpack.py`](../src/agentdecompile_recovery/corpus/export_hookpack.py)
(`FORMAT = "agentdecompile.hookpack/v1"`). It carries instances, signatures and
observed image bytes, and has a separate ABI helper intended for v2 consumers;
that helper explicitly does not change v1 emission. Its presence is not a
complete v2 bundle or live ABI qualification. The inspected
[`runtime_lifecycle.py`](../src/agentdecompile_recovery/runtime_lifecycle.py)
contains owner-record and reconciliation functions; a source module alone does
not establish that the executing consumer uses it or that a game scenario passed.

The [delivery ledger](DELIVERY_STATUS.md) records bounded historical source and
package qualification, while explicitly retaining integration and live gaps.
Its dated port/process observations are historical snapshots and must not be
repeated as current host facts without a fresh check. The frontends plan's
research observations similarly identify work to verify, not permanent claims
that a particular defect still exists after subsequent edits.

Full delivery therefore requires more than connecting panels: complete export
contracts and ABI storage flow, recipient compatibility and acceptance, validated
reconstruction and contribution proof, durable retry/resource ownership, generic
entity and adapter coverage, independently verified worker results, and the
runtime milestones above. These remain visible in their existing plans and
ledgers. This guide does not mark them done or introduce a second completion
checklist with weaker criteria.

The diagrams' “DESIGN ONLY” and “NOT RUN” labels describe their evidence status.
They do not negate a subsequent user authorization to implement the designs.
Likewise, implementation authorization does not turn the diagrams into observed
runtime results. This document was prepared from the linked authorities, all four
SVG text sources and bounded source inspection. No tests, builds, diagram
generation, server changes, live recovery operations or game scenarios were run
as part of authoring it.
