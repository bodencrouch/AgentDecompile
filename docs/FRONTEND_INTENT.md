# AgentDecompile: consolidated user intent and frontend contract

Consolidated 2026-09-20 from user messages in Claude, Cursor, Codex and Copilot,
the current conversation, the supplied AIO research, and the **current canonical**
[VISION.md](/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/VISION.md)
and [STRATEGY.md](/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/STRATEGY.md).

This is the single reading entry point for what the user wants the product and
frontends to do and feel like. It is a requirements consolidation, **not an
implementation-completion report**. It does not replace the charter or create a
competing recovery priority ladder. Source keys and limitations are at the end.
The evidence-limited implementation ledger and prioritized remaining work are in
[DELIVERY_STATUS.md](DELIVERY_STATUS.md).

## 1. The product in one paragraph

Open compiled software as naturally as a source repository. See its packages,
resources, code, types and relationships; compare related builds as implementations
of a shared codebase; improve understanding once and reuse eligible knowledge
everywhere. Browse, edit, recover, compile, compare and inspect runtime behavior in
one coherent workspace. Watch actual evidence and transformations as work happens.
Do not make the operator manage internal stages, repeat configuration, rediscover
prior work, or infer meaning from a spinner. Every name, relationship, candidate,
source file and proof must retain its origin and exact scope.

The immediate recovery mission is the BioWare corpus, with K1 GOG first. The design
must also work for another game's multiple releases/platforms, and for non-game
compiled and packaged software. Product identities and C/C++ are not generic
platform constants. [D2:33936, H1, H3, C1, C3, C8; VISION §§1–7]

## 2. Delivery contract: two alternatives, one product

**Confirmed directly by the user on September 20: the September 8 request is
correct.**

| Surface | Required role |
|---|---|
| MCP HTTP server, normally `8080/dashboard` and related pages | Complete useful static HTML/CSS/JavaScript alternative, served without a Node runtime. Include every relevant capability that can be delivered this way. Static assets may still be interactive and receive live updates. |
| Optional React/TypeScript Vite application, default `5174` | Rich, desktop-like AIO workspace that can run alongside AgentDecompile; not merely a development-only preview and not a cosmetic copy of the older static dashboard. |
| Served React entry `/react/` | Preserve the explicitly requested route and compatibility navigation when packaging the React application through the backend. It does not eliminate either alternative above. |
| Backend/catalog | Shared capabilities, defaults, project identity, durable work, claims and mutation policy across both frontends and agent clients. No competing recovery implementations. |

The UI implementations may have different layouts and interaction richness; they
must not disagree on selected target identity, saved work, actual jobs or proof.
Do not confuse “static web assets” with “frozen screenshot,” or “Vite” with a second
analysis service. Both can render graphs, editors and live events in the browser.

**2026-09-28 (user, Claude session):** “vite frontend should be fundamentally
different from the static dashboard on 8080.” Static 8080 is the conventional RE
GUI and follows the Ghidra reversing guide's CodeBrowser arrangement (§7). Vite is the
real-time AIO workstation built from the browser-RE references (§7), not a
restyled copy of the static layout. Shared backend identity, jobs, receipts and
claim semantics are unchanged.

Earlier instructions to operate recovery exclusively through 8080 remain relevant
to protecting live work. They are **not** a permanent ban on designing the optional
5174 application: the latest user explicitly reconfirms it. This document does not
authorize starting servers, moving databases, launching recovery, or exposing
services remotely. [D1:9,1420,1551,20841; D2:42243; C2:11; H2:678–680]

## 3. Authority and how to interpret history

1. Current direct user corrections decide conflicts with earlier requests.
2. VISION is the charter; current canonical STRATEGY governs recovery priorities.
3. This document joins product requirements, frontend behavior and their sources.
4. Historical plans/prototypes explain intent, but their “shipped” labels are not
   current runtime proof. Older isolated-checkout strategy files are not current
   policy.
5. Quoted assistant research, handoffs, copied logs, skill bodies, generated worker
   prompts and tool output are evidence/reference material, not automatically
   user-authored instructions. A user request to implement an attached proposal
   brings its desired capabilities into scope, not its unverified factual claims,
   guessed schedule, package choices or external authorizations.

Consolidate duplicate exports of a message, not repeated human corrections. A
request appearing three times often means the implementation repeatedly missed it.
Do not call a requirement complete merely because an assistant once said “done.”

## 4. Workspace and interaction model

### 4.1 Start with the actual project, not a setup ritual

- **F01 — Resume:** opening a known `.gpr`, shared repository folder or supported
  remote locator must reconcile existing program bindings, corpus records, analysis,
  source and valid receipts. Never interpret an empty display as permission to
  analyze everything again. Show unavailable paths as unavailable, not as an empty
  new project. Do not tell someone with a loaded project to open another one.
- **F02 — Project manager:** create/open/save/save-as/import/export; drag and drop
  binaries and supported project/context material; manage existing entries. Preserve
  imported members and selection when saving. A `.gpr` export must contain the
  promised project data, not merely a plausible filename or skeleton.
- **F03 — One active project context:** the library may contain many projects, but
  there is one active project and mutation context. Opening another offers explicit
  switch or merge with both projects identified. Tabs represent views/entities,
  not silently competing active writers. No duplicate project rows caused by path,
  slug or refresh races.
- **F04 — Merge:** show a file-manager-like merge review. Match actual artifact
  identity, retain richer compatible fields, preserve conflicts and human edits.
  Afterwards show which binaries, names, types, comments and relationships were
  added, reused, skipped or conflicting—not just “Project data combined.”
  (Reworded 2026-09-21 from “contested”: that word now names one status in the
  cross-build plan's closed locator set and is reserved for it.)
- **F05 — Deduplicate and group:** SHA-256 identifies identical input artifacts;
  retain aliases/provenance rather than delete unrelated files. Group related
  variants from match evidence, not filename guesses. Insufficient evidence means
  unresolved grouping, not proof that builds are unrelated. Split incompatible or
  genuinely unrelated families without hiding them.
- **F06 — Nonblocking admission:** validate and durably accept an import, then close
  the modal and show its work in the workspace. Do not keep “Working…” over the
  whole application. Discovery/default resolution is automatic; explicit overrides
  are available without mandatory environment-variable setup.

Sources: D1:1420,5259,5638,10139,11181,12700,14347,39928,50894;
C5:26,33–34; C6:11; H1:1721–1726.

### 4.2 Shared codebase first; concrete builds always available

- **F07 — Shared entity navigation:** select a logical function/type/module and see
  its implementations across builds together. Keep unmatched functions and
  one-to-many/split/inlined regions representable. Do not invent an equivalent to
  fill a blank cell.
- **F08 — Concrete coordinates:** a logical identity is not an address. Bytes,
  calling conventions, storage, architecture and edits remain scoped to a concrete
  artifact/program/revision/address. Keep build-specific differences visible beside
  shared identity; never flatten them into a single “universal” ABI.
- **F09 — Connected views:** code, assembly, hex, CFG, call graph, xrefs, types,
  evidence and diff follow one shared selection. Clicking a reference navigates
  directly; Back/Forward restores selection and viewport. Switching a build keeps
  the logical entity where a counterpart exists, otherwise explains its absence.
- **F10 — Less chrome:** resizable persistent panes, dense readable rows, useful
  context menus, keyboard alternatives and a command palette. No cards of internal
  commands, redundant “Explore” buttons, nested links that lose context, duplicated
  Functions widgets or raw JSON as the default result.
- **F11 — Selection versus batch scope:** retain an inspectable primary item and a
  separately visible checked set with range/select-all support. Changing the active
  program cannot silently carry dangerous checked addresses into another binary.
- **F12 — Persistent activity dock:** Jobs, logs, diagnostics and notifications live
  together at the bottom (resizable/collapsible). Relevant active work remains
  perceptible while reading code; historical unrelated jobs do not dominate it.
  Refreshes do not steal focus, scroll or editor drafts.

The earlier prototype called cross-match a secondary panel. The current user
explicitly makes it the organizing relationship of the workspace. Likewise, the
September 8 left-hand Functions tree is superseded by the current request to remove
the duplicate sidebar widget; maintain one coherent Functions surface.
[D2:41315–41960; C2:11; C3:1,42; VISION §§4–6]

### Status note — match-review (2026-09-27, source-only)

This is source-only: it describes what the code does, not what the mounted
8080 workbench does. See `docs/DELIVERY_STATUS.md` for the acceptance evidence.

- Select-all is added to the match-review surfaces covered by F11: a checkbox
  selects every decidable row on the current page, in the workstation, the
  static `/dashboard` window and the full app.
- Every decision now carries a token and a selection value; a decision missing
  either is refused.
- A successful decision returns HTTP 202. That means the decision is pending,
  not applied yet. The UI shows an outcome only once the job's terminal result
  says so.
- Score-ordered review paging is retired. Every surface pages the review queue
  by match ID instead. An old score-shaped cursor is refused by name, not
  silently misread as a match-ID cursor.
- Deciding one or more rows now opens a confirm step first ("Move ... to
  verification? This cannot be undone here.") before the decision is sent.

### 4.3 Draw the work, not a decorative indication of work

The following visual design is a synthesis of the explicit request to show *what*
is being done and the strategy's actual mechanisms. It is not a claim that the
required event instrumentation already exists.

| Work | Primary visual feedback | Inspectable truth |
|---|---|---|
| Extract/parse/unpack | Actual container tree expands with discovered members; section/overlay map resolves into identified regions | Input/member offsets, parser, content identity; unsupported or protected region remains marked |
| Candidate comparison | Selected counterpart blocks align across build lanes; matching strings, references and structural anchors highlight | Evidence channel, candidate alternatives, uniqueness/margin, rejection/conflict |
| Identity acceptance | An evidence-backed edge changes from candidate to accepted; split/merged regions remain explicit | Decision and supporting witnesses; not an unexplained confidence animation |
| Name/type/comment propagation | Exact field before/after shown from donor to eligible recipient; blocked recipients retain the conflicting field | Per-field origin, precedence and compatibility gate; no global donor overwrite |
| Source repair | Actual source diff beside the diagnostic that motivated it; compiler output links to the changed region | Candidate revision, compiler/flags/ABI, result and retry history |
| Object verification | Original and generated instructions/data align; changed operands, registers, bytes and relocations highlighted | Exact object pair and comparison receipt; byte equality distinct from semantic identity |
| Whole-image rebuild | Image/section map shows remaining deltas in headers, layout, imports, relocations, resources or function/data regions | Fresh complete build identity, hashes and actual differing ranges |
| Runtime reuse | Actual call/event trace and arguments/returns/state changes link to the selected function and typed adapter | Target process/build, preflight, observed behavior; never a recovery-proof badge |
| Waiting/failover | The affected branch visibly stops at its real unmet dependency while eligible branches continue | Named owner/resource/provider failure, last evidence, chosen fallback and retry eligibility |

Animation follows observed transitions. No simulated packet travel, random graph
motion or timer-driven “compiling” decoration. When a provider exposes only start
and finish, show those states honestly and add instrumentation before claiming to
show its internals. Keep a freeze/step/history view so fast changes are inspectable;
do not auto-pan away from the operator. Reduced-motion and keyboard-accessible
representations convey the same information. Numbers, logs, timestamps and measured
ETAs remain secondary detail; they are not replacements for the visual work.

The user's rejection of “unmeasured” means implement the measurement and expose its
cause/results, **not fabricate a measurement**. Use an explicit missing-evidence
state when reality requires it. [D1:5983,6372,12394; D2:41938,41960]

## 5. Complete functional scope

These are desired capabilities, not a claim every format/engine is implemented.
Availability must derive from actual providers. Missing support narrows the action,
not the whole workspace. Do not silently remove these requirements to ship a shell.

| ID | Capability family | Required user experience |
|---|---|---|
| F13 | Acquisition and dismantling | Open files, folders, packages, installer payloads, nested archives, image sections, resources and sidecars as navigable context. Preserve hierarchy, origin and bounded extraction. Show encryption/DRM/packing state alongside platform; apply supported preparation implicitly and explain unavailable support. |
| F14 | Context fusion | Add partial source, notes, structured facts, GZF and supported project snapshots as puzzle pieces. Place procedurally by identity/address/provenance; keep unplaced, skipped and conflicting evidence inspectable. No invented addresses or promotion of notes to proof. |
| F15 | Code browser | Virtualized listing and hex, decompiler/editor, synchronized cursor/reference navigation, functions, symbols, namespaces/classes, strings, imports/exports, sections/memory, bookmarks and search. Genuine edits save through the shared backend. |
| F16 | Ghidra guide coverage | Project/program lifecycle; listing/decompiler navigation; xrefs/call trees; data types/archives and uses; signatures/parameters/conventions; custom register/stack storage; structures/fields/arrays/pointers/unions/enums; C++ classes/vtables/inheritance; concrete template layouts; dataflow and decompile repair. No hardcoded guide-example ABI sizes or register assignments. |
| F17 | Comparison | Cross-build counterpart/difference alignment, bounded CFG/caller/callee graphs, code and metadata differences, ambiguous matches and rejected alternatives, object diff and whole-image delta inspection. One view can compare multiple decompiler witnesses without calling agreement proof. |
| F18 | Recovery workspace | Editable candidate source, exact historical compiler and flags, diagnostics, compile/diff/retry history and artifact linkage; automatic eligible pipeline work with expert overrides. Source and object receipts remain revision-bound. |
| F19 | Atlas/project intelligence | Function discovery/index, deterministic search, dependency/neighborhood exploration, evidence-based prioritization, similarity/function-cloud view where supported, reusable context/prompt assembly and recovery reports. Embeddings optional; geometric proximity is not identity acceptance. |
| F20 | Semantic findings | Capability/rule/match hierarchy with locations that jump into code, evidence and conflicts. Differentiate static inference from dynamic observation. |
| F21 | Agent context | Bounded provenance-preserving bundles containing selected function plus relevant callers/callees, types, strings, diagnostics and witnesses; inspect generated prompt/payload before authorized external transmission. Answers cite actually retrieved evidence. Small models must benefit from better context. |
| F22 | Expert operations | Catalog/MCP/API parity, scripts/console, capability-derived controls and optional overrides. Preserve low-level tools without exposing each automatic recovery stage as a normal workflow button. No separate hand-maintained argument/default/alias lists per frontend. |
| F23 | Durable workspace | Save/check-in semantic changes, drafts, selection, layout, filters, snapshots and job receipts; expose conflict/revision state. Crash/reconnect resumes acknowledged work. Never promise arbitrary unsaved RAM survives a kill; make durable acknowledgement observable. |
| F24 | Exports | Download a complete named source variant as ZIP with manifest, provenance, build instructions and precise verification status; project/snapshot/evidence/report/hook-pack exports where supported. Export without pretending missing files or ASM floors are recovered C. |
| F25 | Runtime reuse | KotorPhasor-style portable signatures, typed adapters, codecave/call plans, preflight and controlled invocation against original binaries; observe behavior and feed eligible evidence back. Original-byte calls are not source recovery. |
| F26 | Distributed contribution | Optional explicit opt-in for other machines/browser visitors to contribute suitable compute. Show leased work, resource limits, ownership, cancellation and returned evidence. A browser visit is not consent to consume resources or upload proprietary data. Native toolchain/Ghidra writers require appropriate workers and serialized ownership, not arbitrary browser execution. |
| F27 | Collaboration and CI | Retain requested linkable analysis/scratch, annotation collaboration, project event/history and Git/CI-report direction. Sharing/publishing is opt-in; no automatic upstream PR, public binary upload or public service exposure. |
| F28 | Language/engine extensibility | C/C++ is the current recovery target, not a universal language assumption. Normalize actual provider outputs behind existing contracts; expose supported operations and gaps without forcing one engine or an entirely new generic framework. |

Sources: VISION §§2,5–9; H1:1453,1663; H2:525,530,713; C1–C9; D1:8079;
current user-attached AIO reference [A1]; current Ghidra guide [R14].

### KotORXID is substantive scope, not just a visual theme

Carry over the useful behavior of its corpus/build inventory, logical-function
membership, concrete function evidence, cross-build transfer provenance, bounded
call graph, recovery/report coverage, candidate review, STABS/source paths, knowledge
inspection, contained artifact viewing and operational history. Preserve distinctions
between real C, compiling C, ASM floor, per-function equality and rebuilt-image proof.
Integrate these in the shared entity workspace rather than embed a second dashboard
with another database, navigation model and server.

The existing donor and guide inventories remain supporting implementation evidence:
[KotORXID inventory](dashboard-design/2026-09-20-kotorxid-capability-inventory.md),
[guide inventory](dashboard-design/2026-09-20-ghidra-guide-capability-inventory.md).
Their existence does not close any missing capability.

## 6. Pipeline, failover and concurrency represented by the UI

**Use current STRATEGY for prerequisites and feedback.** The UI presents its actual state,
not an independently reimplemented ladder.

```text
Reconcile existing artifact/project/evidence/owners; reuse valid work
  → identity evidence cascade
  ↔ scoped compiler / ABI / layout hypotheses
  → validated linkable regions + early unchanged reconstruction round trip
  → C/C++ candidates from Ghidra / authoritative context
       compile fails → deterministic helpers → retry
                       → bounded LLM cleanup only when needed → recompile
       compile passes → compatible recipient candidate distribution
                       → verify → applicable permuter / residue tools → LLM last
  ↔ continuous local / linked parity; source contribution checked
  → fresh exact-placement whole-image rebuild + comparison
  → enrich eligible shared knowledge, continue next target

Concurrent branches where ownership permits:
  field-level knowledge fusion ↔ every eligible related build
  identity extraction / bounded read-only evidence and indexing
  runtime export → typed adapter / cave preflight → observed behavior → evidence
```

The [task/acceptance design](plans/2026-09-22-task-acceptance-and-continuation-design.md)
defines the shared states consumed by both UIs: separate liveness, execution and
goal progress; evidence-specific refusal and wake conditions; current publication
authority versus quarantined resources; per-operation capability/readiness; and
exhaustive inventory accounting. Correct bytes under a false semantic label must
remain a hypothesis, not animate an accepted binding. A source-floor badge cannot
hide a separately usable original-code capability. Partial behavior evidence with
failed recording remains visible without becoming video-qualified success.

### Identity is not source propagation

Identity channels proceed cheap-first: authentic symbols/provenance, unique exact
or relocation-normalized evidence, rare references/C++ metadata, neighborhood
propagation, structural/CFG/SPP evidence, BSim significance and ABI checks, then
optional second-opinion engines and emulation on unresolved residue. Extract once,
reuse, maintain uniqueness/margins, quarantine bad seeds, retain ambiguity and
one-to-many relationships. Do not repeat the historical research's unsupported
“100% confidence” or “40–60% instantly” assertions as guarantees.

Source propagation requires compiled candidates, compatible implementation variants
and recipient-specific validation. Compilation, ABI checks, tested behavior, local
match, linked match and whole-file equality are separate facts; runtime capability
states are located/readable/callable/detourable/writable with their own evidence.
A shared logical ID alone does not make source, structure layout or calling
convention portable. Name precedence is human annotations, original debug/STABS
provenance, authentic symbols, meaningful analysis names, then placeholders.
Strongest **per field** wins; no single build is donor for every field.

### Start/pause/resume without stage babysitting

> **Superseded 2026-09-21 (user directive):** there is no Start button. Analysis —
> admission of eligible missing work — begins on its own when a project is opened,
> binaries are added, or prior work is resumed; reopening known material still admits
> nothing that already has a receipt. The single control is **pause/resume and its
> scope**, never start. The paragraphs below are kept as written for history; read
> “start/resume” as the automatic admission they describe. Plan: Phase 14, U105.
> The same directive makes the pipeline unattended end to end: review is an override
> applied afterwards, never a gate on progress (plan “Autonomy rule”).

There is one context-aware workflow control, with truthful state and a clear scope.
Routine stage transitions, supported repair and eligible resume are automatic.
Adding new material can admit the authorized default workflow after deduplication
and ownership checks; merely selecting or reopening known material must not
reimport/reanalyze it or start a duplicate recovery session. Read-only hydration is
not the same thing as mutation admission. Preserve independent expert capabilities
because VISION explicitly forbids a compulsory recovery funnel for every task.

Pause means stop admitting subsequent work and acknowledge the actual safe boundary;
it is not a misleading label for killing a compiler. Stop/cancel and pause are
different. Resume validates source/target/toolchain/dependency identity and reuses
only valid work. A stale durable “running” record is not a live owner.

Default execution budget is unlimited as requested later on September 8, with
explicit opt-in budgets. That does **not** mean unbounded RAM, unchecked retry loops,
unlimited native workers or permanent repeated attempts without new evidence.
[D1:6431 superseded by10121; D2:41315; STRATEGY]

### What can run together

| Can overlap subject to resources | Must serialize or have separate isolated ownership |
|---|---|
| Browsing, searches, cached evidence reads; independent extraction/index work | Writes to the same Ghidra project/program or logical identity store |
| Field-level knowledge work and source recovery when transactions/resources do not collide | Shared corpus mutation and conflict resolution |
| Independent compile/objdiff work in distinct proven toolchain environments | The same compiler/Wine environment or generated output tree |
| Runtime evidence branch after sufficient identity/ABI evidence | One live game/harness target, saves and cave-installation state |
| Optional distributed workers on leased independent units | Central acceptance of results and authoritative receipt/identity writes |

Resource admission uses actual ownership and measured memory/swap. A configured
worker count is not permission for overlapping writers. Failed providers leave
their error/evidence visible while safe independent lanes continue; no silent
retry storm, stale-state reset or server restart. Priority-zero repair is the
minimum needed to safely resume useful work, not a new recurring bureaucracy.

### What “done” means

Keep byte-accurate C+assembly-floor and max-C as separately measured variants.
Do not borrow a receipt between them. No copied-byte body counts as recovered C.
A finished job, source ZIP, compiling function, accepted identity, function-level
objdiff zero, runtime call or screenshot is not full-image acceptance. Terminal
recovery requires a fresh complete source/toolchain build, appropriate object
comparison, exact-placement relink and whole-file equality for the claimed target.

The broader product still provides useful browsing, acquisition and advisory
evidence before or without that recovery outcome. [VISION §§7,12; STRATEGY]

## 7. Reference projects: what belongs in this product

These are concrete design inputs, **not instructions to clone thirteen applications
or add every dependency they use**. The supplied popularity/version/date table is a
historical research snapshot, not a current integration contract. Primary README
and selected source documentation were inspected on September 20; functionality
below is documented upstream, not independently runtime-validated here.

| Reference | Design/capability to carry into AgentDecompile | Boundary |
|---|---|---|
| [RzWeb](https://github.com/IndAlok/rzweb) | Connected disassembly/decompiler/CFG/hex/xref views, command palette, persistent artifact contexts, snapshots; browser worker isolation for local analysis | Current README explicitly notes unavailable decompiler plugins and non-interruptible commands. Rizin WASM is a requested local-provider direction, not a reason to replace working Ghidra state. LICENSE file identifies LGPL-3.0-only; review before code reuse. |
| [Mizuchi / Decomp Atlas](https://github.com/macabeus/mizuchi) | Function discovery, similarity exploration, context/prompt building, source/assembly correlation, compiler/objdiff/plugin iteration and reports | Reuse native AgentDecompile capabilities already assimilated. Respect deterministic-first policy; don't route every function to AI. |
| [decomp.me](https://github.com/decompme/decomp.me) | A focused source/target-assembly scratch with compiler settings, compile/diff iteration and linkable collaboration | Workflow inspiration against our catalog, not a second Django application. Remote submission requires explicit consent. |
| [Dogbolt](https://github.com/decompiler-explorer/decompiler-explorer) | Side-by-side named decompiler witnesses for the same target | Optional supported/licensed runners; no automatic upload to its public service or assumption a public API exists. |
| [r2web](https://github.com/radareorg/r2web) | Lightweight expert terminal, search/goto, graph navigation and browser analysis | Commands remain provider-specific expert tools behind normalized selection; do not make users learn r2 syntax for ordinary work. |
| [objdiff](https://github.com/encounter/objdiff) / [objdiff-web](https://github.com/encounter/objdiff-web) | Actual symbol/instruction/data diff, register/value highlighting, navigable mismatch details; optional WASM comparison | Object-level comparison is not whole-image proof. Reuse existing integration before adding another engine or renderer. |
| [decomp.dev](https://github.com/encounter/decomp.dev) | Revision-aware project history, build/report and Git/CI integration | Secondary to actual-work visualization. Root license not established in this pass; no source copying on assumption. |
| [APKMan](https://github.com/jiusanzhou/apkman) | Container/resource tree, format-specific inspectors, grouped search, worker parsing, hash-keyed reuse, export and optional offline use | Generalize format-provider behavior. Its README distinguishes Smali export from future Java-source export; do not promise parity with headline claims alone. |
| [capa / Explorer](https://github.com/mandiant/capa) | Hierarchical capabilities/rules with supporting feature locations and drill-through into code | A semantic witness, not recovered-source or runtime proof. Reports can be browsed without rerunning analysis. |
| [idarem](https://github.com/xsslize/idarem) | Synchronized address/view navigation, optional follow/drive semantics, responsive virtualized panes and event-driven updates | IDA/Hex-Rays are optional licensed dependencies. Never force native application navigation or enable write-back implicitly. |
| [Rev·Deck](https://github.com/biniamf/ai-reverse-engineering) | Evidence-linked questions, bounded sub-investigations, checked citations and explicit provider boundaries | Model output cannot authorize writes or execution. License not established here; use concepts until source reuse is cleared. |
| [Grapefruit](https://github.com/ChiChou/grapefruit) | Runtime module/symbol/memory browsing; inspectable calls/events, structured arguments/returns, crash/backtrace and file/database views | Optional isolated dynamic provider with explicit target/permission state. Do not import its mobile-only assumptions into the BioWare workflow. |
| [rev.ng](https://github.com/revng/revng) | Coherent editable analysis model; type edits reflected in dependent code; connected artifact/analysis views and graph/code navigation | Primary docs describe model/type round trips. Do not claim its complete commercial/browser UI is reusable from the core repository; core/components have distinct licenses. |
| [PyKotor Ghidra guide](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide) | Complete supported code-browser/type/storage/C++ workflows in both frontends | Guide examples are illustrative, not universal architecture/ABI rules. |

Relevant rev.ng primary details:
[model](https://github.com/revng/revng/blob/develop/share/doc/revng/user-manual/key-concepts/model.md),
[editing types in C](https://github.com/revng/revng/blob/develop/share/doc/revng/user-manual/tutorial/editing-types-in-c.md).
No remote binaries, code, evidence or credentials were uploaded in this research.

## 8. Implementation direction and visual feel

This section translates requirements into design; it is not a mandate to build a
new framework. Inspect and reuse existing owners first.

```text
Active project / related-build scope · search / goto · one workflow control
┌────────────────────┬────────────────────────────────────┬──────────────────┐
│ Project/artifacts  │ Shared entity: actual code/graph    │ Evidence / types │
│ Variant groups     │ Build counterparts and divergences│ Origin/conflicts │
│ Containers/files  │ Synchronized assembly / hex / diff │ Contextual edits │
├────────────────────┴────────────────────────────────────┴──────────────────┤
│ Actual-work view: compare / change / propagate / verify / runtime events  │
├───────────────────────────────────────────────────────────────────────────┤
│ Activity dock: Jobs · diagnostics · logs · history                         │
└───────────────────────────────────────────────────────────────────────────┘
```

This is a compositional sketch, not a fixed four-pane quota. Collapse/rearrange for
small screens and focused work. One Functions view belongs in the main workspace,
not a duplicated sidebar list. Code and actual differences receive the area;
large statistical cards and slogans do not. One gesture should reach a counterpart,
its provenance or the failing instruction without resetting the current workspace.

Existing code discovered during this session already contains a Workstation shell,
CodeBrowser, guide workflows, storage editor, scratch workflow, durable workspace
state and action catalog. Extend/reconcile those; do not nest the older App/Atlas
roots or create another selection/default/job store. Source presence is not live
feature proof. The isolated entry reconciliation remains separately review-pending.

Dynamic design means deriving interfaces from authoritative capability/schema and
resource contracts, preserving explicit false/opt-outs, and invalidating only
dependent state. It does not mean guessing write safety from action names or
auto-discovering arbitrary executable code. Keep the engine-specific details in
adapters and the provider's real capabilities visible. Defaults discover legitimate
state; ambiguous databases/projects require a meaningful choice, never a silent
wrong-context fallback.

Continuous updates must preserve state: HMR for the frontend; compatible in-process
Python reload with explicit rejected-change reporting; long-running worker version
identity visible. No claim that every edit can migrate every active stack/native
extension/object without exceptions. Standalone pip-installable hot-reload capability
remains a requested outcome, but the user redirected further escalation toward
simplification after accepting diminishing returns. [D2:35561–36106]

## 9. Conflicts and supersessions retained explicitly

| Earlier request/reference | Current interpretation and evidence |
|---|---|
| Multiple old dashboard ports; later “8080 only / don't touch 5174” | Preserve live-operation safety; the user now explicitly reconfirms optional Vite5174 and static8080 alternatives. Do not resurrect 3000/5173/8791 as separate products. |
| Vite merely a development server | Incorrect reduction, corrected by current user and Sep8 source. Optional application is required. |
| “None… static, all React” | Refined by explicit dual-surface request. Static-served HTML/JS can still be interactive/reactive. |
| Convergence of 8080 and Vite onto one shell/route (2026-09-09 plan P3, AE8) | 2026-09-28: the two surfaces must be fundamentally different presentations over one backend; static follows the Ghidra-guide CodeBrowser, Vite is the real-time reference-inspired workstation. |
| Every input automatically starts everything | New imports admit authorized missing work; reopening/selection reuses and inspects existing state. One workflow owner, no duplicate analysis. |
| One context-aware start/pause/resume control (2026-09-16) | 2026-09-21: no Start button. Open / add / resume admits eligible work by itself; the one control is pause/resume + scope. Per-stage buttons stay banned; admission still gates only mutation. |
| Review lane as a gate before propagation or export | 2026-09-21: review is an override applied afterwards; ambiguous/contested entities export with evidence and refuse at use time. Nothing waits on a person. |
| Two left trees including Functions | Current explicit duplicate-widget removal wins; retain functionality once in the main workspace. |
| Numeric bars/ETA and “Running” as main feedback | Current user requires drawing actual work. Preserve numbers as secondary detail, not primary experience. |
| 24-hour default workflow budget | D1:10121 explicitly changes default to unlimited. Resource limits and bounded per-attempt behavior remain. |
| Eight named stages versus user shorthand “priorities1–9” | STRATEGY has eight named stages; don't invent a ninth or reorder it. Minimize priority-zero friction. |
| No assembly whatsoever | Current strategy and Sep15 user allow honest intermediary assembly floor. It never counts toward recovered C or substitutes for final readable-source work. |
| “Only code matters, not data” in June | Current whole-image contract includes data, placement and headers; function-only equality is insufficient. |
| Global metadata donor / forced1↔1 matching | Strongest per field with compatibility/provenance; ambiguity and split/merged regions remain first-class. |
| 80,000 lines, later one-fifth file target | Do not optimize to either quota. Current explicit correction asks for less duplication and shared authoritative mechanisms, not an arbitrary count. |
| KotorPhasor excluded in one older task | Current direct request includes it as a runtime-reuse branch. This does not make every unrelated KotorPhasor/ModSync task part of dashboard delivery. |
| Historical permission to push, delete repos or change account state | Historical task authorization is not renewed by archive consolidation. No publication/destructive actions inferred. |
| Pasted roadmap's mandatory local Rizin-first implementation order | Retain browser-local provider direction and capability coverage; current recovery priority is STRATEGY and existing useful Ghidra analysis must not be replaced/recomputed for architectural uniformity. |
| Old prototype says secondary corpus panels, manual stage buttons and quiet status text | Current corpus-first navigation and actual-work visual feedback supersede that presentation; retain useful parity/durability principles. |

## 10. Acceptance and unfinished-outcome ledger

Do not mark any row complete from this document. Implementation acceptance needs
observed behavior tied to target/revision and the relevant artifact, not a screenshot
or a successful compile alone.

| Scenario | Observable acceptance |
|---|---|
| Reopen known project | Same binaries, annotations, receipts, job owners and selection; no automatic destructive reset/reanalysis |
| Import duplicate/new input | Duplicate aliases existing identity; new input durably admitted once; dialog closes; actual work observable |
| Merge projects | Explicit overlap/conflict review, field-level outcomes, no lost human metadata or hidden original locations |
| Switch logical entity/build | All linked panes update correctly; stale responses cannot overwrite current view; absent counterpart stays absent |
| Inspect cross-match | See candidate evidence, alternatives, accepted relation and build divergence; no similarity-as-proof shortcut |
| Edit a signature/type/storage | Actual new value reaches correct program; dependent views update; draft/transaction conflicts stay visible |
| Watch recovery/failover | Actual code/evidence transformations visible; independent branches continue; pause/resume reflects real ownership |
| Export ZIP | Requested variant's complete available source/build manifest; missing/unverified/floor contributions disclosed |
| Use either frontend | Same backend work, artifacts and claim semantics; optional Vite is not required for8080 pages |
| Reload/disconnect | Durable acknowledged state survives; no duplicate writer; rejected incompatible reload does not restart jobs |
| Distributed/runtime mode | Explicit admission, supported environment and ownership; returned evidence distinct from source proof |
| Claim full recovery | Fresh source/toolchain/object/whole-image receipts meet STRATEGY, separately for each claimed build/variant |

Unfinished requests retained rather than silently dropped:

- Complete guide/KotORXID/AIO functionality and visual redesign, not just shell work.
- Full corpus ingestion/analysis/identity/knowledge/source/verification, with K1 first
  and explicit support gaps for sibling formats/architectures. Historical target
  counts and Witcher/DragonAge/Sonic deferrals are snapshots, not permanent exclusions.
- Maintain and package the max-C and byte-accurate variants; prior ZIP request needs
  an actual artifact receipt before being marked delivered.
- Durable resume, truthful current project binding, stale-queue cleanup and less
  orchestration overhead; optimize observed bottlenecks throughout the mission.
- Portable runtime reuse and behavioral evidence integration; distributed compute,
  additional providers, collaboration and CI remain visible scope, not implied done.
- Standalone hot-reload packaging and broad code/docs/plugin consolidation require
  their own evidence. Do not rename a partial cleanup “the entire thing complete.”
- Reporting integrations (including previously paused Discord reporting) remain
  operational follow-ups; do not post externally without current authorization.

Session constraints remain: no filesystem tests/test fixtures/test suites; no
systemctl; no curl for dashboard work; browser interactions through Playwright CLI;
GitHub research through gh; preserve dirty work, ledgers, raw archives and live
owners. Reading history is not permission to replay old commands. Validation in
this documentation task is read-only source/quote/link/diff review, not runtime
or recovery acceptance.

## 11. Source ledger and research coverage

### Primary user sources

All Cursor indices below are zero-based JSON-array positions. Cursor file mtimes
are not message timestamps. Codex JSONL locations are physical line numbers;
migrated sessions may retain import timestamps rather than original send times.

- **D1:** [Codex dashboard session](/home/brunner56/.codex/sessions/2026/09/08/rollout-2026-09-08T06-42-18-01a080d3-7a48-7cf3-be7b-72e79532ae4b.jsonl).
  Key user lines:9 delivery;91 prior conversations/feel;247 approved plan;
  630 browser-only verification;1420 distinct Vite/project manager/automatic work;
  1448 preserve functionality;1551 guide on both;5259 grouping/protection;
  5638 dedup/select;6372 visible state/precedence;6431 earlier24-hour plan;
  8079 editor/ZIP;8739 context menu/reorder;10121 unlimited;10139 import/export;
  11181 merge;12394 real measurement;12700 one active project/merge;
  14347 merge details;20841 static migration;30830 pipeline/hotreload/persistence;
  39928 missing previous recovery;46201 assembly-floor then C;
  48052/49325 donor reuse;50894 reuse before work;51330 browser instead of curl.
- **D2:** [Current Codex recovery/redesign session](/home/brunner56/.codex/sessions/2026/09/16/rollout-2026-09-16T18-55-33-01a0aca5-acc2-7011-abdf-aba17449c646.jsonl).
  Key lines:33378 priority-zero/bottlenecks;33936 generic multi-build prototype;
  33996 no systemctl;34026 runtime reuse;34287 archive-informed continuity;
  35561 diminishing-return standalone hotreload;36106 simplification;
  36832 implicit defaults;37902 retract file quota;38060 broad intent beyond aliases;
  41315 project binding/one controller/no curl;41553 guide/KotORXID;
  41938 corpus-first;41960 actual-work animation;42005 consolidation;
  42243 explicit confirmation of Sep8 delivery. Browser-comment duplicate-Functions
  removal is also present in this conversation; do not mistake its screenshot text
  for the instruction.
- **H1:** [Claude prompt history](/home/brunner56/.claude/history.jsonl).
  1184 (2026-08-22, session7e5a0694-ed24-41ff-9b03-d38b372016ca): five-build mission;
  1453 (2026-08-30, c36fc397-b44d-4652-ae0a-39eee31f50c6): compile-gated reuse/fallback;
  1663 (2026-09-08,6abcf9a1-0f1f-46a8-924c-ca0b38038ec2): contribute compute;
  1721–1730 (2026-09-09,f2e9837c-09f2-48b2-a03c-00abf0f0be09): optional defaults,
  DB selection, usable frontend, hotreload and no filesystem tests.
- **H2:** [Codex prompt history](/home/brunner56/.codex/history.jsonl).
  160–161 (June29): original compiler round-trip goal;466/486 (July7): integrate
  Mizuchi into AgentDecompile;510/512: autonomous shared tools, documented functionality;
  525/530 (July8/12): context puzzle pieces;652–659 (August23/24): generic visual UI,
  broken navigation, ASM only intermediary;678–680 (September8/9): dual delivery;
  713/766: AIO reference/design request;767–771: functional full cross-match/hotreload;
  793: automatically resolve legitimate prerequisites instead of opaque errors.
- **H3:** Claude Aug11 semantic-matching request, raw user record line3 in
  [session 5b082fe3](/home/brunner56/.claude/projects/-run-media-brunner56-MyBook-Workspaces-agentdecompile/5b082fe3-0e6b-4932-a583-35e2a7154899.jsonl:3)
  (message `7999194b-9f13-4174-bb1c-115a93da379f`) and its mission-command copy in
  [session 5c087816](/home/brunner56/.claude/projects/-run-media-brunner56-MyBook-Workspaces-agentdecompile/5c087816-8588-4902-b8b5-58434b26399e.jsonl:3)
  (message `4292d031-82c9-41e4-9a1c-2c303e7d32d5`). Whole binaries, precision before
  recall, multiple evidence channels, split/merged relationships and preserved
  annotations. These duplicate submissions are one originating request, not two
  independent corroborations.
- **C1:** [Cursor25d4434a](/home/brunner56/.cursor/chats/11d8cc83fb53a73a56c3414c3a702fcc/25d4434a-7ebf-4d77-b3f3-1094b3621ccc/prompt_history.json), indices4,8,18.
- **C2:** [Cursor74f6348d](/home/brunner56/.cursor/chats/11d8cc83fb53a73a56c3414c3a702fcc/74f6348d-67a6-4f8f-abe7-dc810ca188d9/prompt_history.json), indices11 (dual delivery/resizing/activity),17 (portable runtime signatures).
- **C3:** [Cursor955d2c64](/home/brunner56/.cursor/chats/b3ef1b8d481db89ad32a0b54671dc79f/955d2c64-08fc-4884-bf7e-9fc1832ef7b1/prompt_history.json), indices1,14,28,33,36,42 (corpus/validation/genericity/context).
- **C4:** [Cursor63c56579](/home/brunner56/.cursor/chats/b3ef1b8d481db89ad32a0b54671dc79f/63c56579-f949-4f60-b7bd-ab707a96f741/prompt_history.json), indices7,9,10 (KotORXID consolidation).
- **C5:** [Cursorb6c775ed](/home/brunner56/.cursor/chats/b3ef1b8d481db89ad32a0b54671dc79f/b6c775ed-7a7e-4265-b9ce-c0a1e8316334/prompt_history.json), indices26,33,34 (load/save/API parity; task-local runtime exclusion).
- **C6:** [Cursora5028a3f](/home/brunner56/.cursor/chats/b3ef1b8d481db89ad32a0b54671dc79f/a5028a3f-4bfa-45bd-a0f7-9e8e79db7f96/prompt_history.json), indices11,15 (editing and usable RE workbench).
- **C7:** [Cursorc6524bea](/home/brunner56/.cursor/chats/b3ef1b8d481db89ad32a0b54671dc79f/c6524bea-1f3c-47eb-bbe7-e8417b035e68/prompt_history.json), index4 (useful reactions/pipeline-led design).
- **C8:** [Cursorf1e5d74c](/home/brunner56/.cursor/chats/b3ef1b8d481db89ad32a0b54671dc79f/f1e5d74c-b0a1-41c6-a02d-bb361577fef7/prompt_history.json), index43 (C/C++ one of supported languages).
- **C9:** [Cursor6ad18552](/home/brunner56/.cursor/chats/f82fcaf4e65ab215fe4a3db82ecbe728/6ad18552-2c59-4bc7-a73a-4d77e7f12473/prompt_history.json), index15 (target-derived runtime API names).
- **P1:** [Copilot session store](/home/brunner56/.copilot/session-store.db), table
  `turns`, `session_id=f437a830-34a9-4875-890c-4d6ea80d4af3`, `turn_index=8`,
  `user_message`, timestamp2026-09-09T11:27:21.456Z: replace Vite design from RE references.
  Related implementation requests: sessione7b1c769-92d4-49fd-8b36-0073f87f5dc0 turn3,
  session33b0d663-1e0b-43e1-8330-366729380127 turn0. These are not proof of delivery.
- **A1:** [Supplied AIO research](/home/brunner56/.codex/attachments/f8ba7cd0-912f-4208-9d2e-d3dfa9333209/pasted-text.txt), all356 lines read. Its embedded citation IDs and malformed `https:$$` URLs are historical artifacts; use the actual primary links in §7. Its implementation direction is relevant; its claims and effort estimates are not independently established here.
- **R14:** [Ghidra guide](https://github.com/OpenKotOR/PyKotor/wiki/Ghidra-Reversing-Guide), plus the detailed guide inventory above.

### Coverage and limitations — not an “all history exhausted” claim

- **Claude:** researcher enumerated3 live top-level AgentDecompile JSONLs (5,513
  records),116 archived top-level JSONLs (241 including subagents/sidecars), and168
  AgentDecompile-project history entries across25 sessions. Relevant sibling-project
  prompts were considered when explicitly about this mission. Authored prompts were
  prioritized; not every assistant/tool byte in every archive was read.
- **Cursor/Copilot:** keyword enumeration across live Cursor `chats/**/prompt_history.json`
  and Copilot `turns.user_message` returned99 matches (91 Cursor,8 Copilot),97 distinct
  texts across36 source sessions/files. Terms included AgentDecompile, KotORXID,
  KotorPhasor, Mizuchi, Decomp Atlas and ghidra_bulk. Injected skills/reviewer prompts
  were excluded from product requirements; indirect pronouns may escape keyword recall.
- **Codex:** enumerated1,347 session files at that point in this live session;
  bounded metadata scan found93 project-path/non-subagent-source candidates with one
  header beyond the parsing bound. A role-level scan produced2,150 candidate user
  records, but these include migrated agent prompts, skills and automatic continuation
  messages—**not2,150 human requirements**. Detailed review focused on the major
  Sep8–15 dashboard session, current recovery session,810-entry prompt history
  (78 keyword hits), and relevant imported records. Oversized/truncated output was
  not counted as reviewed; selected user records were reread separately.
- **Boden archive:** relevant Claude originals and normalized Cursor/Copilot corpus
  locations were investigated. Giant single-line normalized records and unrecovered
  `[Pasted text #N]` references limit completeness. Raw private archives are preserved;
  no mass transcript copy is included in this repository document.
- **External references:** primary documentation for all13 named project families
  plus the Ghidra guide was consulted; selected APIs/docs were checked through gh.
  No claim of a full source/license audit, runtime benchmark or pixel-level inspection
  of every reference interface. Follow-up implementation must verify specific donor
  code, licensing, backend support and real browser behavior.

Remaining historical gaps do not erase known requirements. Add newly recovered
requirements here with sources and explicit supersession; do not create another
competing vision document or silently restore old presentation/port policies.


## Failure handling and unattended progress — required design

The [prevention and recovery contracts](plans/2026-09-22-failure-prevention-and-recovery-contracts.md)
define required behavior; this section is not an implementation claim. The same
projection drives both frontends, CLI and agent consumers.

Every objective shows accepted capabilities, active attempts, independent eligible
work, unmet required predicates and the next automatic action. A failure record
shows a stable reason, affected scope, evidence freshness, attempts/budget spent,
recovery action, wake condition and the authority needed only if an external
intervention is unavoidable. Diagnosis details expand in place; users must not need
to correlate several logs just to learn whether work is progressing.

| Situation | Required presentation and interaction |
|---|---|
| Deterministic worker error | “Provider paused for this input revision”; show diagnostic/repair dependency, continuing tasks and conditions for automatic resumption. Retry cannot bypass budget or ownership. |
| Slow but advancing attempt | Display actual durable units and last checkpoint with separate heartbeat. No invented percent or premature no-progress alarm. |
| Ambiguous command outcome | “Checking whether the operation completed”; mutation/retry controls disabled for that conflicting operation until reconciled. Read-only observations remain available where supported. |
| Resource quarantine | Name occupied resource and unresolved access evidence; lease countdown is never presented as a guaranteed release time. Show independent ready work. |
| Coordinator/store unavailable | Last verified snapshot visibly dated and read-only. Clearly show disconnected/unknown freshness. Do not queue hidden offline mutations or show a successful launch. |
| Missing fixture or capability | Show the exact missing predicate and planned compatible producer/alternative. Absent support remains explicit; it never becomes a generic red gameplay failure. |
| Evidence invalidation | Remove dependent readiness, retain history, explain changed basis and scheduled revalidation; coverage can fall without erasing prior receipts. |
| External action required | One deduplicated actionable item with impact and available independent work. Repeat notification only for material changes under notification policy; dismissing is not resolution. |
| Policy rollout | Show revision and affected scope. Rollback preserves command/acceptance history and never resurrects stale claims or spent budget. |

Operator actions use versioned intent IDs through the same admission path as agent
actions. Double-click, reconnect and stale-tab requests must not create duplicate
commands. Stale-version responses refresh the view with an explanation. Pause stops
new admission and asks owned workers to checkpoint; it does not claim immediate
process termination or freed memory. Resume reconciles durable state. Cancellation
applies to a named scope, preserves independently accepted outputs, and reports
unresolved side effects/access rather than pretending rollback occurred.

Future UX acceptance pairs each historical failure with a healthy independent task:
within the declared freshness contract, all surfaces must show the same reason,
automatic next step and accepted capability set. No user action should be necessary
for a policy-authorized routine retry, checkpoint resume or compatible fixture
selection. These acceptance checks have not been run.
