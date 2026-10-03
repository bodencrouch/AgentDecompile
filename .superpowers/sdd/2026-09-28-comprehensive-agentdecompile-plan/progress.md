# SDD ledger — plan: docs/plans/2026-09-28-comprehensive-agentdecompile-plan.md

Starting revision: 527b847a8b27a20edd759803325e3e119a35a38e. Current isolated worktree retained.

Ruling: Import the three planning artifacts byte-for-byte from consolidation-20260928 — they are absent here and match the requested megabyte plan — cost if wrong: replace the imported documents, no source loss.
Ruling: Use active U1–U42 as integration owners and mechanically extract them for task-brief — appendix repeats historical Task headings and is evidence, not a second queue — cost if wrong: remap briefs before implementation.
Ruling: Parallelize independent read-only discovery/reviews and serialize implementation writers — this honors both requested skills without shared-file conflicts — cost if wrong: additional elapsed time.
Ruling: Preserve mission restrictions on tests, builds, restarts and publication; record unverified acceptance separately — current explicit repository instructions still govern — cost if wrong: behavioral acceptance remains open until authorized execution.

Preflight tables pending. No unit is marked complete from imported historical status.

## Preflight rulings and tables

Ruling: Treat dependency entries as consumed predicates and retain every final acceptance gate — the master explicitly permits prerequisite slices without whole-unit closure, which resolves U2/U8 and U6/U7/U8 cycles — cost if wrong: additional integration rework; no acceptance is waived.
Ruling: Record implicit producer gates for U8 source projects (U4/U10), U16 storage (U5), U18 BSim (U11), U19 external comparison (U10), U21 final metrics/publication (U3/U4/U8/U9), and U37 live directory (U36) — these follow required actual-consumer evidence — cost if wrong: those final gates wait for more proof.
Ruling: U9 owns continuation substrate and U12 owns M0 product acceptance — one acceptance owner prevents duplicate or missing closure — cost if wrong: remap the evidence owner without changing behavior.
Ruling: Integrate the exact committed consolidation snapshot locally before filling apparent gaps — 423 donor commits contain already-built implementations, while only five conflict paths require semantic reconciliation — cost if wrong: revert the local merge; donor dirty work and live processes remain untouched.


### preflight-1-report.md

# Preflight 1: U1–U21 consistency and shared-seam review

Scope: read-only review of `preflight-1-input.md` (global contract, requirements, decisions, U1–U21 and verification gates), with bounded path/source inventory in this checkout. The six-megabyte source plan, other units' full text, runtime state and external consumer checkouts were not reviewed. This is a plan preflight, not implementation acceptance. No tests, builds, imports, service actions or commits were performed. Existing untracked plan files were left untouched.

Status key: **ruling** means the plan needs a small ownership/dependency/acceptance decision; **boundary** means the text is internally compatible if the named handoff is kept explicit; **open evidence** means source presence or old status cannot close the predicate. A predecessor denotes a consumed predicate, per the unit contract, not wholesale completion of the preceding unit.

## Unit checks

| Unit | Internal consistency against dependencies, acceptance and current file/interface inventory | Status / smallest action |
|---|---|---|
| U1 | `ingest_recovered.py`, `rebuild_ledger.py`, `collect_source.py`, `finish_binary.py`, `package_authoritative.py` and `dashboard/byte_parity.py` exist. The evaluator owns claim semantics while U4 produces comparisons and U9 controls publication. Foo/Bar refusal, changed source digest, zero contribution and policy-race cases keep these axes separate. | Boundary: state the evaluator record/API U4 and U9 must consume; no claim of acceptance from file presence. |
| U2 | `logical.py` and corpus exports exist, but the unit's byte-identical **complete export** acceptance depends on U8, which itself depends on U2 through U5. Closing U2 against U8 creates an acceptance cycle even though U2's own schema/order work can proceed. | **Ruling:** U2 closes canonical semantic rows and a narrow serialization fixture; complete bundle repeatability belongs to U8/V3. |
| U3 | `identity.py`, `match_store.py` and `propagate.py` exist. U3 owns identity/BSim persistence and recipient acceptance; U18 also names `match_store`, features and channel confidence. Donor logical family is insufficient for compatible implementation transfer. | **Ruling:** U3 owns persisted evidence and acceptance API; U18 owns UI workflow and may request producer work without promoting UI review to identity proof. |
| U4 | `collect_source.py` and `finish_binary.py` exist. Region, source contribution and whole-image evidence need U1's claim evaluator; final rebuild cannot be inherited from local or linked proof. | Boundary: U4 produces scoped observations, U1 evaluator adjudicates; U10's external reports cannot self-certify. Fresh rebuild remains open. |
| U5 | `export_types.py` and related corpus modules exist. Exact field rows, ABI storage, RTTI and roots are inputs to U6/U7/U8. It requires independent identity via U3; presence/shape cannot silently become callable readiness. | Boundary: define versioned entity/ABI/layout record supplied to runtime and export; refuse missing storage. |
| U6 | `export_hookpack.py` exists, but the reviewed runtime assessment documents v1 and unverified v2 consumer support. U6 requires v2 version negotiation while U8 owns the v2 bundle and depends on U7, which depends on U6. This is a producer/consumer delivery cycle if full v2 artifacts are a U6 closure gate. | **Ruling:** qualify U6 reader with a versioned conformance fixture and independent runtime receipts; U8 owns production bundle and later consumer integration. |
| U7 | Resolver and learn-build obligations use U5 data and U6 runtime operations. Six ladders' member receipts remain distinct from promoted identity; budget stop differs from exhaustion. U8 consumes these receipts. | Boundary: U7 owns ladder order/outcomes; U6 owns safe execution; U3 owns independent identity promotion. |
| U8 | `export_hookpack.py`, `export_c.py`, `export_types.py`, `export_packages.py` and `package_authoritative.py` exist. The unit requires recovered-source/comparison projects but names U4/U10 only in prose, while the index lists U5/U7. U10 depends on U4/U9; full U8 closure is therefore missing a consumed prerequisite. | **Ruling:** add U4/U10 accepted project-recipe predicate for U8's source-project slice, or explicitly split runtime bundle closure from source-project closure. U21 owns external publication. |
| U9 | `dashboard/preparation.py` and action catalog modules exist. R31 and text call this the M0 foundation, but say full M0 remains open; U12 claims R31/M0–M7. Durable admission, retry ownership and quarantine must have one authority. | **Ruling:** U9 closes substrate/V6; U12 owns end-to-end M0 product acceptance, consuming U9. No double completion. |
| U10 | Its named `corpus/external_execution.py` was not found in the bounded path inventory. U10 uses U1/U4/U9 and external report envelopes; it cannot infer source equality from process exit or GREEN. | Open evidence: locate existing adapter or record missing path before implementation; make actual comparator and source-project receipt input to U8. |
| U11 | Named `agentdecompile_grid` package was not found in the bounded path inventory. It consumes U9 authority but adds independent proposal/log/verification trust; SQLite remains a materialized view in target architecture. | Open evidence: reconcile Phase15/U125 names and source before treating an absent path as no implementation. Grid-of-one cycle precedes remote lanes. |
| U12 | Shared operation schema and KotorPhasor adapters are named, but external consumer was not inspected. M6/M7 research can proceed separately; M1–M5 need qualified U6 operations and U9 lifecycle. The title omits M0 despite R31 and the text's M0 foundation reference. | **Ruling:** make M0 an explicit U12 acceptance child or assign it unambiguously elsewhere, with U9 as substrate. No gameplay claim from catalog/source presence. |
| U13 | `frontend/src/main.tsx`, `vite.config.ts`, `dashboard/react_api.py`, `unified_pages.py` and static `workbench-app.js` exist. Reconciliation is a prerequisite to U14–U21 but should not become a blanket ownership claim over their shared modules. | Boundary: U13 records source/serving/package manifest and owns only concrete root/routing diffs; downstream feature edits have their own owners. Current served identity is unverified here. |
| U14 | `dashboard/workbench.py`, `ghidra_project.py`, `mcp_bridge.py` and static/Vite surfaces exist. Explicit open/admit uses U9 and U29; browsing stays read-only. A saved `.gpr` needs actual project members, not a skeleton file. | Boundary: one admission intent and one active mutation target across tabs; source-only admission does not close live import/export. |
| U15 | Static workbench and Vite CodeBrowser exist. Selection key includes logical entity and exact concrete target, while checked batch selection is separate. U16–U20 consume this state. | Boundary: publish a single selection-key/version contract with stale-response refusal before downstream panels claim parity. |
| U16 | `CodeBrowser.tsx` and `FunctionEditor.tsx` exist. Storage editing demands U5's lossless ABI facts; the index only names U15/U29. UI editing could otherwise be accepted on an incomplete storage backend. | **Ruling:** add U5's accepted storage contract as a consumed predicate for storage-edit acceptance (not for all guide browsing). Enumerate all 16 chapters at closure. |
| U17 | `unified_pages.py`, static workbench and corpus modules exist. It needs U1 proof distinctions and U15 navigation. Donor source presence is explicitly historical; generic build inventory cannot assume mounted KotORXID artifacts. | Boundary: provide source/age/missing states and count-to-set navigation; do not count old donor availability as current live proof. |
| U18 | `match_store.py` exists; U3 owns persisted evidence. U18 acceptance asks for restart-persistent BSim hits, but the unit says an admitted BSim producer is missing and U11 includes a BSim adapter. UI can honestly show absence, but cannot prove hit persistence without a producer. | **Ruling:** split U18 availability/review closure from producer-backed BSim hit closure, or add the accepted U11 producer predicate. |
| U19 | `DiffEvidence.tsx` and `ScratchWorkspace.tsx` exist; exact named `CompareView` was not located in bounded inventory. U19 requires actual backend receipt; U4 provides native comparisons, U10 owns external reccmp/ReAgent reports. | **Ruling:** name U10's accepted report predicate for external comparison views; keep a separate U4-backed native comparison path. Do not treat component presence as backend behavior. |
| U20 | `dashboard/entity_activity.py`, `activity_receipts.py`, `preparation.py` and frontend activity files exist. U9 owns state transitions; U20 shows them and permits only catalog-authorized controls. | Boundary: one coordinator, intent IDs and dated reconnect snapshot; no second UI scheduler or simulated progress. |
| U21 | `export_run_report.py` exists. U21 derives identity/member counts, recovered-C extents and publication from U3/U4/U8/U9, yet the index lists only U17/U1. A source report can exist without accepted denominator, bundle or publish authority. | **Ruling:** add consumed predicates for U3 identity, U4 accepted contribution, U8 same-basis bundle and U9 durable publication; permit a clearly scoped report-only slice earlier. External publication remains a separate approval gate. |

## Pairwise shared-file/interface checks

The rows below enumerate every pair within two explicitly shared seam groups in U1–U21, then the additional cross-group pairs whose unit text names the same exact file or producer/consumer interface. `F` means the explicitly repeated backend/provider + static workbench + Vite seam of U13–U21; it is a broad file group, so these rows request per-file ownership before an edit rather than assuming all pairs will edit every file. `C` means the explicitly repeated `src/agentdecompile_recovery/corpus/` seam of U1/U2/U3/U5/U8. These are integration collision checks, not claims that files were changed or behavior passed.

| Pair | Shared file/interface | Pair-specific handoff or conflict test |
|---|---|---|
| U1–U2 | C: evidence/schema | Evaluator must reject missing/mixed basis from schema without backfilling accepted defaults. |
| U1–U3 | C: identity/claims | Semantic binding needs independent roots; candidate source claim cannot authenticate a label. |
| U1–U5 | C: identity/entity | Qualified identity and operation evidence remain different records. |
| U1–U8 | C: packaging/receipts | Bundle must carry scoped receipt, not promote package existence to whole-image equality. |
| U2–U3 | C: logical keys/migrations | Stable identity keys after membership changes; previous keys retained. |
| U2–U5 | C: entity/schema | Platform and ABI fields migrate without reinterpreting unknown legacy values. |
| U2–U8 | C: serialization/export | U2's local determinism fixture must not depend on closing full U8 bundle. |
| U3–U5 | C: entity/variant | Struct/vtable correspondence needs compatible variants and non-name evidence. |
| U3–U8 | C: identity/export | Contested/absent per-member records survive export without unsafe fallback. |
| U5–U8 | C: ABI/layout/export | Exact storage and opaque field bounds survive headers and hookpack. |
| U1–U4 | `collect_source.py`, `finish_binary.py` | U4 observations feed U1 evaluator; linked bytes and semantic source contribution distinct. |
| U1–U9 | acceptance policy/publication interface | U9 fences stale commits; U1 verifies current source/dependency/policy basis. |
| U1–U10 | external verification/claim interface | Third-party report remains raw observation until central acceptance. |
| U1–U17 | corpus proof projection | Inventory labels distinguish C/ASM/local/whole-image and stale evidence. |
| U1–U21 | corpus proof/metric projection | Every numerator maps to accepted set, with explicit missing denominator. |
| U2–U11 | determinism basis/materialized SQLite | Grid replay cannot turn materialized row order into canonical proof. |
| U3–U18 | `match_store.py`, identity, propagation | U3 persists accepted/rejected roots; U18 review UI cannot self-promote. |
| U3–U21 | identity/member metric | Split/folded/absent members use disjoint logical accounting. |
| U4–U10 | recovery/recipe/comparison | Actual target and rebuilt candidate required; exit status is insufficient. |
| U4–U19 | native comparison receipt | Source/flags/ABI and target selection bind visual diff. |
| U4–U21 | recovered-C/extent metric | ASM floor and overwritten/discarded source earn zero C credit. |
| U5–U6 | ABI/layout/runtime export | Metadata alone cannot authorize a call; unsupported storage refuses. |
| U5–U7 | locator/root input | Ladder records exhausted/budget/unsupported per member and decoder revision. |
| U6–U7 | runtime resolver and learn-build | U6 executes safely, U7 orders fallback; runtime hypothesis cannot certify identity. |
| U6–U8 | v2 consumer/hookpack | Avoid v2 producer/consumer closure cycle through conformance fixture. |
| U6–U12 | qualified operation IDs | Capability requests require current live preflight and behavior receipt. |
| U7–U8 | ordered member receipts/export | Bundle retains failed/contested members and exact ladder reason. |
| U8–U10 | recovered-project recipe | Add U10 accepted recipe predicate to U8 project slice. |
| U8–U21 | bundle/publication | Bundle creation and external publication are separate gates. |
| U9–U10 | ownership/external process | Adapter cannot start overlap or release resource on timeout alone. |
| U9–U11 | durable task proposal/verification | Grid result remains proposal; one acceptance owner and resource fence. |
| U9–U12 | M0 lifecycle/capability | U9 substrate is not M0 user outcome; assign final owner. |
| U9–U14 | admission intent | Explicit open once; passive navigation never schedules. |
| U9–U20 | coordinator/activity projections | UI commands use durable intent IDs; unknown effects reconcile before replay. |
| U10–U19 | external comparison report | View must expose unsupported/not-run/stale reports without false GREEN. |
| U11–U18 | BSim producer/review | Persistence acceptance needs actual admitted producer or scoped deferral. |
| U13–U14 | F: root/routes and project UI | Reconcile serving root before project tabs/admission changes; preserve static. |
| U13–U15 | F: root/routes and selection | Redirects preserve exact selection; U15 owns state semantics. |
| U13–U16 | F: root/routes and CodeBrowser | Root mount must not trigger hidden analysis; U16 owns guide features. |
| U13–U17 | F: routes and corpus panes | Historical donor routes map to one shared backend; no duplicate server. |
| U13–U18 | F: routes and review panes | Source reconciliation cannot infer active BSim producer. |
| U13–U19 | F: routes and compare panes | Asset/package inventory precedes browser claims. |
| U13–U20 | F: routes and activity dock | Root preparation effects must not remount/restart work. |
| U13–U21 | F: routes and report/export | Publication control remains explicit after routing reconciliation. |
| U14–U15 | F: project tabs/selection | Switching tabs clears dangerous target drafts/checks, retains views. |
| U14–U16 | F: project context/editors | Edits bind selected project/program, never stale tab. |
| U14–U17 | F: project/corpus navigation | Project alias and build inventory preserve provenance. |
| U14–U18 | F: target/review | Review token and selection bind current project/build. |
| U14–U19 | F: target/scratch | Compare and scratch receipts bind exact source/target. |
| U14–U20 | F: admission/activity | One admission acknowledgement; reconnect does not double-submit. |
| U14–U21 | F: project/export | Download lists and publish readiness scoped to project/build. |
| U15–U16 | F: selection/CodeBrowser | Token/address navigation refuses stale target responses. |
| U15–U17 | F: selection/corpus | Logical member navigation retains concrete build identity. |
| U15–U18 | F: selection/review | Checked rows separate from active navigation and old cursors. |
| U15–U19 | F: selection/compare | Target switch invalidates old diff and scratch mutations. |
| U15–U20 | F: selection/activity | Event panels inspect target-bound work without moving selection unexpectedly. |
| U15–U21 | F: selection/metrics | Count-to-set navigation preserves measure/scope/basis. |
| U16–U17 | F: CodeBrowser/corpus | Provenance labels and symbol routes do not guess exact identity. |
| U16–U18 | F: CodeBrowser/review | Editing and match-review conflicts share target revision. |
| U16–U19 | F: CodeBrowser/compare | Decompiled source and instructions show same exact target and revision. |
| U16–U20 | F: CodeBrowser/activity | Browsing remains read-only even when work events arrive. |
| U16–U21 | F: CodeBrowser/metric links | Function proof tier shown without promoting displayed C. |
| U17–U18 | F: corpus/match dock | Matrices distinguish missing producer from rejected match. |
| U17–U19 | F: corpus/compare | Candidate pair and build inventory use one identity key. |
| U17–U20 | F: corpus/activity | Liveness and accepted progress retain independent measures. |
| U17–U21 | F: corpus/report | Inventory denominator equals metric's navigable member set. |
| U18–U19 | F: evidence/compare | Match confidence is not byte/source parity. |
| U18–U20 | F: review/activity | Pending review action stays pending until durable terminal outcome. |
| U18–U21 | F: match/metric | Contested candidates cannot count as accepted coverage. |
| U19–U20 | F: compare/activity | Historical attempt and current running attempt have dated basis. |
| U19–U21 | F: compare/metric | Linked/local diff receipts do not close whole-image numerator. |
| U20–U21 | F: activity/metric | Running/executed/accepted progress use separate denominators. |

## Minimum rulings before allocating overlapping implementation

1. Split U2's fixture-level determinism from U8's complete-bundle repeatability; retain V3 as the final integrated gate.
2. Break U6/U7/U8's v2 consumer/producer closure cycle with a versioned conformance fixture, then close the actual U8 bundle against the real qualified consumer.
3. Add U4/U10 to U8's recovered-project slice; add U10 to U19's external comparison slice; add U5 to U16's storage-edit slice. These are consumed predicates, not blanket predecessor completion.
4. Assign M0 product acceptance to U12 and keep U9 as durable substrate, or name a separate unambiguous owner. Split U18 producer-backed BSim proof from an honest availability/review UI until U11 producer admission exists.
5. Give U21 explicit U3/U4/U8/U9 predicates for final metric and publication closure, while permitting a report-only slice. Preserve the user approval boundary for any external publication.

The current AGENTS.md mission allows read-only document/source checks and forbids filesystem tests/builds for documentation validation. V2–V11 remain future acceptance predicates under their own authorization, serving identity and ownership checks. The presence of source paths above is not proof that any unit, runtime consumer, game capability or frontend workflow has passed those gates.


### preflight-2-report.md

# U22–U42 read-only preflight

**Scope and result.** Reviewed `preflight-2-input.md` (requirements, global constraints, U22–U42) against the current checkout's source and the repository's operator/intent/status documents. This is a consistency and integration preflight, **not** implementation or acceptance. U13 source import/reconciliation is the first execution work; this report tests later units' shared seams without moving that priority. No tests, builds, project imports, game runs, service probes, process changes, or commits were made. The three untracked comprehensive plan/living/todo files were left untouched. The repeated unit template saying “backend/provider, static workbench and Vite modules named below” supplies no concrete file ownership; the concrete seams in the tables below are inferred from each unit's detailed clause and existing source. They must be assigned exact owners before parallel editing.

**Authority applied.** Current `AGENTS.md` and `STRATEGY.md` govern recovery; `README.md`, `USAGE.md`, `docs/plans/README.md`, `docs/RUNTIME_REUSE.md`, `docs/FRONTEND_INTENT.md`, `docs/DELIVERY_STATUS.md`, and `docs/PYTHON_HOT_RELOAD.md` provide current interface and evidence boundaries. The input's C03/C05/C07/C08/C17/C18/C21 decisions resolve apparent older-contract conflicts. `docs/solutions/README.md` was consulted for the documented-solution lookup boundary; no MCP/Ghidra edit is proposed here.

## Unit consistency tests

“Open” means the stated acceptance is not established by this read-only inspection. “Conditional” means a dependency is a consumed predicate, not a demand to finish all children of its predecessor. Paths are repository-relative.

| Unit | Internal consistency test against explicit implementation/interface | Result and concrete prerequisite |
|---|---|---|
| U22 AI/context | One resolver must freeze policy at admission while AI-off leaves deterministic work and browser contribution consent independent. Existing `src/agentdecompile_recovery/rewrite_provider.py` is a CLI provider seam; `corpus/dashboard/settings_page.py` currently exposes notification settings, not proof of one policy resolver. | Open: inventory every AI entrypoint and settings route, specify precedence and immutable child basis, then test off/on, CSRF and stale settings through real consumers when allowed. Do not conflate U31 direct provider key with a server-side secret. |
| U23 ABI/types | Collector → batch → export must retain ordered return/parameter storage and target ABI, including explicit unknowns. `src/agentdecompile_cli/mcp_server/providers/_collectors.py` exposes a calling convention and some storage, while `corpus/build_types_header.py` exists; that does not prove the full chain. | Open: trace exact field shape through each lossy seam and pin a build-scoped record before U24/U26 serialization. |
| U24 hookpack v2 | v2 must carry build/identity/ABI/operation prerequisites while v1 readers remain explicit. `src/agentdecompile_recovery/corpus/export_hookpack.py:16` still declares `agentdecompile.hookpack/v1` and exports `sites`, not v2 `entities[]`. `docs/RUNTIME_REUSE.md` documents v1 adapter-key and expected-byte gaps. | Open: version an adapter/reader contract, preserve v1 path, bind every member to exact image and unknown/refusal state. Qualified native reader proof is separate. |
| U25 caves | Image-bound capacity, occupancy, relocation, page/lifetime/reclaim evidence must precede an install plan. `docs/RUNTIME_REUSE.md` identifies raw-write/cave-inventory limits. | Open: establish a verified image producer and evidence schema; a valid empty/no-cave outcome must be an explicit refusal artifact, not inferred discovery. Native install remains external acceptance. |
| U26 Lua/headers | Generate both from U23 ABI and U24 operation IDs, with per-build layout assertions and no portable literal VA. `corpus/build_types_header.py` is a partial seam, not the declared full bundle. | Open: define a common operation/schema version and target adapter; generated-code parsing alone cannot accept native layout or gameplay behavior. |
| U27 readiness/divergence | Full declared denominator and separate observed runtime axis must survive missing graphs and split/inline identity. | Open: choose qualified decoder/graph source and explicit unavailable status; readiness cannot promote a located operation. Coordinate U24 member status with U28 report basis. |
| U28 atomic export | Required pack/Lua/caves/headers/readiness/divergence/receipts must have one dependency closure and atomic publication; selected source ZIP is a separately honest deliverable. Current `corpus/dashboard/source_archive.py` has an independent source ZIP route, but no evidence here of the new same-basis v2 bundle. | Open: settle required versus optional artifacts, scoped WASM target discovery, manifest/hash/content-type rules and both UI download readers. An explicit no-cave/unsupported receipt can satisfy *representation* but not an installable cave claim. |
| U29 MCP dispatch | Omitted program sentinel differs from explicit `None`; response, prerequisites and handlers must stay call-scoped. `mcp_server/tool_providers.py:909–963` has a sentinel, but fallback handlers still call `set_program_info(effective_program_info)` on the shared provider. | **Conflict with intended isolation:** migrate dispatch-reachable handlers before declaring A-paused/B-dispatched/A-resumed safe. Keep activation's future-call default separate and preserve U30 top-level normalization semantics. |
| U30 input/ownership | Thirteen historical source-integrated tasks require exact False/0/empty/None/tuple/JSON and ownership release behavior; old stage launchers are superseded in normal UI by C05. Current `tool_providers.py` preserves normalized top-level last-spelling behavior. | Conditional/open: reconcile branch and live consumer before closure; retain stage metadata/hash keys, remove obsolete launch affordances, and verify DB/pair release on each failure path later. No generic registry rewrite is justified. |
| U31 browser contributor | Opt-in Start is expressly preserved by C21; no client compile/objdiff/identity promotion. `frontend/src/ExchangeContribution.tsx` shows Start and proposal wording, while `exchange/routes.py` exposes submit. | Open: inspect worker packaging/CSP, secret storage, lease/visibility and direct provider adapter end-to-end. Must hand one unchanged idempotency key to U32's durable boundary. External provider verification is separate. |
| U32 exchange lifecycle | Submit/replay durability, per-destination routing and coordinator compile/objdiff must not treat proposals as verified. `exchange/store.py` has worker-scoped receipt keys and persists before submit acknowledgment; `exchange/consumers.py` has forwarded acknowledgment. | Conditional/open: verify crash/restart/destination behavior and exact lease/unit/fingerprint validation. “Every accepted rewrite reaches attempt_candidate” requires qualified queue ownership and a real PE/COFF pair before objdiff economics is claimed. |
| U33 source baseline | Exact binary/Ghidra/toolchain/source/receipt identity and clean original-game source launch precede multiplayer source claims. The checkout has a v1 hookpack and research references in the untracked plan, but `docs/research/swkotor-multiplayer/` is absent here. | **Prerequisite gap:** locate/corroborate research and recovered-engine source/receipts under current checkout authority; do not substitute pseudocode, `_emit` or copied regions for source. Current game launch and link proof unavailable here. |
| U34 local transport | U33's source baseline must support correct ABI/callers/queue framing before changing transport. Referenced `docs/research/swkotor-multiplayer/evidence/*` files are absent in this checkout. | Blocked on locating exact evidence/loaded project and qualified original-process comparison; no new transport assumption from function names. |
| U35 remote gameplay | Transport and server-owned identities require U34 plus U9 identity predicate. “Two clients see one authoritative world” can be demonstrated with a temporary qualified host before U36, but its basis must be explicit. | Open: specify host/server world authority, protocol/content versions, authenticated join and both modes. Real two-client acceptance unavailable in this preflight. |
| U36 dedicated executable | U35 world protocol is consumed; headless simulation must be independent of rendering/audio/window state. | Open: identify shared recovered-engine source and server entrypoint, then prove native headless module/script/AI/combat/save behavior. A source tree or synthetic server is insufficient. |
| U37 directory | Directory API needs a provisioned public provider and U35-compatible mode/build/content metadata; actual heartbeat also needs a server process, so U36 is an acceptance prerequisite even though not listed as a dependency. | **Dependency to clarify:** add U36's running headless server predicate to public-discovery acceptance, or explicitly distinguish directory implementation with a temporary verified registrant. Provider credentials/provisioning and cross-network proof remain external. |
| U38 in-game browser | Join uses U35 transport and U37 directory; real recovered main-menu integration differs from the static/Vite workbench. | Open: identify game UI source/asset insertion seam and prove states, LAN/Internet, password refusal, compatibility and real client navigation. Halo-like appearance cannot be accepted from a web mock. |
| U39 release proof | U36 and U38 plus U35 both-mode and U37 cross-network acceptance must feed one clean-build receipt. C07 correctly limits objdiff to unchanged recovered code after new features alter the image. | Open: exact source/toolchain hashes, clean Windows builds, headless server and two real clients, external directory and video/state receipts. No present local check can close it. |
| U40 semantic findings | Selected program and static/dynamic evidence must ground Atlas/F01–F28 actions. Existing `frontend/src/AtlasAnalysis.tsx`, `GuideWorkflows.tsx`, static workbench and `react_api.py` are consumer seams. | Open: bind finding navigation through U29 program-scoped dispatch and shared backend operations; mark provider-unavailable or missing prerequisites instead of fabricated findings. |
| U41 collaboration/CI | Qualified second reader, revocation and local-only reporting require U1/U13 identity/auth basis; external messages require current authorization. | Open: identify durable share/CI artifact reader and access revocation contract. Generate redacted local reports first; Discord/public reporting cannot be exercised by this plan. |
| U42 packaging/reload | Installed revision, static and packaged React, retained hashed chunks and in-process rejection behavior must be proven on the executing checkout. `docs/PYTHON_HOT_RELOAD.md` describes standalone reload; `react_api.py` and `static/react/` are packaging seams. | Open: reconcile canonical/serving roots, package manifests and asset revision policy. Later verify unchanged PID/state via authorized 8080 consumer; no service probe or reload was done here. |

## Pairwise shared-file/interface review

Each row is one pair with a concrete shared contract. Repeated generic “backend/provider, static workbench and Vite” template wording is excluded because it does not identify a file, endpoint or data shape; treating it as a universal overlap would hide the ownership decision. Pairs in the recovered-engine family are included only where a named source, transport, directory, UI or release interface connects them.

| Pair | Shared file/interface | Ordering, conflict or handoff test |
|---|---|---|
| U22–U31 | AI provider selection and browser contribution policy | Keep server admission settings distinct from transient browser API key; AI-off policy must define whether opted-in contribution is disabled without silently exposing a key. |
| U22–U32 | Rewrite/model job basis | Freeze policy/model/context on admitted proposal; replay cannot pick new defaults. |
| U22–U40 | Semantic provider/context | Provenance-bearing context may inform findings but optional embeddings cannot establish identity. |
| U23–U24 | ABI/storage rows → `corpus/export_hookpack.py` | Version v2 fields without losing ordered pieces or treating missing storage as a generic register. |
| U23–U26 | ABI/types → `corpus/build_types_header.py` and Lua generator | One build-scoped source of storage/layout facts; header and Lua must expose the same supported signature. |
| U23–U27 | ABI prerequisites → readiness | Missing ABI remains an exact blocked call predicate, even if locator is resolved. |
| U23–U28 | Typed export input basis | Hash collector/batch ABI source with bundle; stale type update invalidates dependent artifacts only. |
| U24–U25 | Hookpack injection plan and cave references | Cave candidate is image-bound and optional; a locator cannot confer capacity or installability. |
| U24–U26 | Operation IDs/adapter keys | Lua/header operations and v2 reader must use the same versioned IDs; preserve v1 mapping explicitly. |
| U24–U27 | Per-member identity/operation status | Resolved/pinned/contested is distinct from installed/observed; readiness denominator includes unknowns. |
| U24–U28 | v2 pack + bundle manifest | Pack must be complete, hash-bound and reopenable; v1 fallback is a separate compatibility path. |
| U25–U26 | Injection/call plans → generated APIs | Generated call/install methods must refuse unsupported cave/page/lifetime conditions. |
| U25–U28 | Cave artifact in bundle | “No qualified cave” must serialize as explicit evidence/refusal, not an empty success. |
| U26–U27 | Generated operations → readiness | Report readiness per operation/build; code generation does not create runtime capability. |
| U26–U28 | Lua/headers in bundle | Hash per-build ABI assumptions and compiler manifest under the same basis. |
| U27–U28 | Readiness/divergence reports | Missing graph and unsupported operations retain honest scoped status while the bundle stays structurally complete. |
| U28–U42 | Download routes, manifest, `/react/` assets | Bundle/source ZIP route and packaged readers must agree on content identity and asset revision through atomic rollout. |
| U29–U30 | `mcp_server/tool_providers.py`, registry/CLI input contract | Call-scoped program migration must preserve top-level alias/last-spelling behavior and distinct `None`/omitted handling; shared-provider fallback is a live race risk. |
| U29–U40 | Selected-program MCP dispatch → Atlas findings | Finding navigation and references must carry exact program across async requests; session default is insufficient. |
| U29–U41 | Scoped project sharing/CI tool calls | A second reader's selected program must not mutate another caller's provider target. |
| U30–U40 | Registry operations and guide actions | F01–F28 controls must use canonical operation identity and owner-defined danger/duration, preserving refusal behavior. |
| U30–U42 | Package/CLI and stage presentation | Preserve shortcuts/defaults and 33 stage keys while packaging; remove old UI stage launch controls per C05. |
| U31–U32 | `exchange/routes.py`, `exchange/store.py`, `ExchangeContribution.tsx` | Producer returns only proposal; durable submit acknowledgment, idempotency and verification belong to coordinator. |
| U31–U42 | Packaged browser worker/CSP | Build asset and fixed provider origins must survive `/react/` packaging without persisting secrets. |
| U32–U33 | Accepted rewrite → recovered-source candidate | Queue transfer enters compile/objdiff candidate path, never U33 source baseline merely because proposal was accepted. |
| U32–U39 | Objdiff lane/clean source comparison | Genuine retained PE/COFF pair required for economics; exchange result cannot replace multiplayer clean-build proof. |
| U33–U34 | Recovered engine source and original netlayer evidence | Exact binary/toolchain binding before ABI and queue edits. |
| U33–U35 | Recovered engine source → remote transport | New network code must be separated from unchanged recovered code and source identity retained. |
| U33–U36 | Shared recovered engine → server entrypoint | Headless build cannot be derived from an unlinked/pseudocode-only baseline. |
| U33–U39 | Source/toolchain hashes → release comparison | Compare unchanged regions under C07; U33 original-image proof is a separate claim. |
| U34–U35 | Local dispatch/queue → remote protocol | Preserve callback/ordering/framing semantics and do not infer Internet play from local queue names. |
| U34–U36 | Engine message/tick interface | Server tick must consume validated messages without rendering/player assumptions. |
| U34–U39 | Original netlayer evidence → release | Release receipt must state what recovered logic was reused and what was new. |
| U35–U36 | Authoritative world protocol → headless simulation | U35 two-client proof needs an explicit qualified host basis; U36 then proves dedicated authority. |
| U35–U37 | Authenticated game join and directory metadata | Directory publishes no password/hash/admin secret; join authenticates separately. |
| U35–U38 | Join API/compatibility states | Main-menu Join must enter proven remote gameplay, not a mock/local queue. |
| U35–U39 | Two modes/reconnect/refusal → release | Release matrix must replay both modes and lifecycle cases with real clients. |
| U36–U37 | Headless server heartbeat/session counts | Public acceptance requires real server-owned counts and endpoint ownership; add this acceptance edge. |
| U36–U38 | Server endpoint → browser direct connect | Browser must handle full/incompatible/password states from actual server responses. |
| U36–U39 | `swkotorserver.exe`/headless runtime | Clean build and native behavior are mandatory, not server source presence. |
| U37–U38 | Directory list/expiry/filter protocol | Internet rows use provisioned public provider; LAN and direct connect are separate modes. |
| U37–U39 | Cross-network discovery receipt | Self-hosted fallback does not close requested free public default under C17. |
| U38–U39 | Recovered main-menu UI | Capture real game navigation and Join path; desktop/static/Vite mocks do not count. |
| U40–U41 | Linkable evidence/artifact references | Sharing and CI must resolve selected program plus evidence basis, not an unscoped finding URL. |
| U40–U42 | Static/Vite shared backend and package | Both installed consumers must expose the F01–F28 action/missing-prerequisite inventory. |
| U41–U42 | Shared installed artifact and report routing | Revocation, CI reader and local report need revision-bound routes; packaging cannot auto-publish. |

## Actionable decisions before implementation

1. **Assign exact owners and schemas.** Replace the template “modules named below” for U22–U42 with current paths, route names and versioned producer/consumer fields. In particular settle U23→U28 v2 bundle ownership and U31→U32 proposal acknowledgment.
2. **Fix U29's dispatch boundary before parallel MCP/Atlas work.** The fallback `set_program_info` in `tool_providers.py` contradicts the stated no-dispatch-time-singleton-write acceptance. A migration inventory, including prerequisites and response paths, is a local prerequisite.
3. **Clarify U37's acceptance dependency on U36.** Directory code may be built earlier, but real heartbeat, session counts and cross-network discoverability require a qualified running server; record that consumed predicate without forcing unrelated U36 children.
4. **Rebind multiplayer evidence.** The plan/living/todo cite `docs/research/swkotor-multiplayer/`, absent from this checkout. Locate the exact input binary, research, recovered source and receipts and corroborate hashes before U33/U34 work. Do not copy material from the upstream donor without reconciling read-only authority.
5. **Separate external acceptance.** Real games and native host/build/architecture combinations, headless server plus two real clients, actual provider credentials/public directory, optional external AI provider, and installed 8080 consumers are unverified here. Native/whole-image claims require the current `STRATEGY.md` proof, while publication/messaging needs current authorization. None is implied by this report.

**Read-only verification performed:** source/path searches, relevant file reads and `git status --short` only. The absence of a path is stated only for this checkout. Historical status in `DELIVERY_STATUS.md` and memory was treated as orientation, not current runtime acceptance.


### preflight-cross-pairs.md

| Pair | Shared interface / producer and consumer | Preflight finding |
|---|---|---|
| U1 / U41 | explicit dependency basis; U1 predicate consumed by U41 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U2 / U24 | explicit dependency basis; U2 predicate consumed by U24 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U3 / U27 | explicit dependency basis; U3 predicate consumed by U27 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U4 / U33 | explicit dependency basis; U4 predicate consumed by U33 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U5 / U23 | explicit dependency basis; U5 predicate consumed by U23 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U5 / U25 | explicit dependency basis; U5 predicate consumed by U25 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U9 / U22 | explicit dependency basis; U9 predicate consumed by U22 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U9 / U32 | explicit dependency basis; U9 predicate consumed by U32 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U9 / U35 | explicit dependency basis; U9 predicate consumed by U35 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U11 / U31 | explicit dependency basis; U11 predicate consumed by U31 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U29 | explicit dependency basis; U13 predicate consumed by U29 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U30 | explicit dependency basis; U13 predicate consumed by U30 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U40 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U41 | explicit dependency basis; U13 predicate consumed by U41 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U13 / U42 | explicit dependency basis; U13 predicate consumed by U42 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U22 | explicit dependency basis; U14 predicate consumed by U22 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U29 | explicit dependency basis; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U40 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U14 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U29 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U40 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U15 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U29 | explicit dependency basis; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U40 | explicit dependency basis; U16 predicate consumed by U40 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U16 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U29 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U40 | explicit dependency basis; U17 predicate consumed by U40 | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U17 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U29 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U40 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U18 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U29 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U40 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U19 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U29 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U40 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U20 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U22 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U23 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U24 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U25 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U26 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U27 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U28 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U29 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U30 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U31 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U32 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U40 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U41 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |
| U21 / U42 | shared backend / static / React capability contract; shared contract; distinct implementation ownership | No conflicting value specified in active texts; serialize overlapping writes, consume exact completed predicate rather than entire predecessor. |


## Execution queue

Task 13.1: ready — restore plan and reconcile committed source snapshot; base527b847a; no unit acceptance closed.
U1–U42 remain in docs/plans/agentdecompile-todo.md; historical checkmarks are not current delivery.

Task 13.1: independent spec/quality review in progress at b871b845; implementer /root/implement_source_integration; reviewer /root/review_source_integration; base527b847a. No full-unit completion.
Ruling: Apply a fixed 64-active-container limit at the v2 cave/pack JSON boundary, preserving large flat evidence — recursive JSON/copy consumers need a finite stack-safety policy and the schema is shallow — cost if wrong: a future deeper legitimate schema requires a reviewed policy revision; no decoder or runtime acceptance is inferred.
Ruling: Require an owner-supplied independent cave verifier at production and required-cave consumption, with truthful blocked defaults — serialized caller evidence cannot establish its own decoder completeness or current authority — cost if wrong: previously unqualified v2 bundle production waits for a real provider, while v1 stays compatible.
Task 1.1: ready after integration review; selected corpus target content binding; task-1-brief.md.
Task 25.1: prepared after Task1.1 review; independent cave qualification and bounded recursion; task-25-brief.md.

Task 13.1: fix round 1/5 dispatched from b871b845 — P1 surviving-descendant quarantine permanently retains executor worker capacity; reviewer confirms all five conflict seams and 23 manifest identities, but spec/quality gate is not clean. Original implementer resumes; preserve resource ownership while separating executor completion from clearance.

Task 29.1: prepared — merged source already migrates program-consuming handlers; remove residual pure-control singleton writes and repair stale deterministic-gate fixture; next-dispatch-slice.md and task-29-brief.md. Full live U29 acceptance remains open.

Ruling: Repair authoritative packaging with explicit workspace/recovered/coverage basis and preserve its existing relative layout — required parser arguments never had valid implicit defaults and installation-relative paths select the wrong workspace — cost if wrong: callers of the formerly broken out-only module entrypoint must supply explicit inputs; no live route changes.
Task 8.1: prepared — explicit inputs plus real-C classification, checked target-region address, coherent ledger and copied-byte snapshot; next-packaging-slice.md and task-8-brief.md; full portable/atomic/installed U8 acceptance stays open.

Task 13.1: fix round1 implemented b871b845..d43a86fb; source-only AST/diff checks pass; scoped re-review /root/review_source_integration pending in task-13-fix-r1-review.md. Runner terminalization restores executor capacity while retained quarantine/identity/generation/lease require qualified repair; tests remain unexecuted.
Live read-only recheck: 8080 healthy PID2697197/start1790595674.5226107/startTicks68973313, same NVMe cwd, restarts0/watchedFiles0, serving source HEAD753d7fce unchanged. live-health-continuation.json retains response; no activation.

U1/U21 producer discovery: next-acceptance-adapter.md confirms no complete trusted persisted accepted-source join in scoped source. Current not_connected/null verified counts remain correct. Queue actual raw-image-to-target-object producer under U10/U11 before connecting dashboard; require independently authenticated compile object, full parity and current policy/generation. Runtime inputs unverified, not declared absent. Compile actual-object/receipt binding is receiving a bounded follow-up check.
Ruling: Preserve unavailable accepted-source counts until a complete independently verified producer chain exists — immutable storage or signed fields alone do not bind the selected raw binary/function/source to parity objects — cost if wrong: dashboard verified metrics remain unavailable longer; advisory evidence remains usable.

Task 13.1: fix round 1/5 (1 addressed, 0 open — executor-slot retention; commits b871b845..d43a86fb).
Task 13.1: complete (commits 527b847a..d43a86fb, review clean for bounded source reconciliation only). Full U13 remains open; no tests/builds/live acceptance.
Task 1.1: next implementation; fresh implementer after this ledger commit.

Task 1.1: implementation dispatched to /root/implement_target_binding from base860731e59e6cb1c20ec8f977d5486872b66dbaad; requirements task-1-brief.md; source-only checks; report task-1-report.md. Controller owns this pending ledger edit.

Task 11.1: prepared — default CompileAttempt.verify trusts receipt masked hash without deriving it from the actual advertised object. Framework existence/CAS/envelope checks do not close the relation. next-compile-binding-slice.md confirms gap; task-11-brief.md owns compile.py and focused regression source only. Queue before target-producer/dashboard admission.

Task42.1: prepared — current standard Vite build empties and writes served static/react directly; staged/additive asset publication and last atomic index replacement missing. task-42-brief.md and next-asset-rollout-slice.md retain existing reader/redirect paths and require old-chunk retention. Build/install/browser acceptance remains open.

Task1.1: implemented 860731e5..612e1315, review /root/review_target_binding pending; review package task-1-review.diff; report task-1-report.md. Four ASTs and call-site keyword checks pass; tests unexecuted. Implementer reports inherited unreadable-whole-corpus/missing-func enumeration boundary in matching_status outside owned consumer scope; review evaluates scoped requirement before completion.
Ready source queue after this gate: Task25.1 cave qualification, Task11.1 compile-output binding, Task29.1 call scope, Task8.1 faithful packaging, Task42.1 staged assets; target-object producer follows its prerequisite contract discovery.

Catalog prerequisite check (retained live-actions.json, no submissions): corpus.mkobj exists but accepts caller offset/size/format and has no admitted-selection/independent target-object verification contract. No grid or mkobj-target action appeared in the 233-action snapshot. workbench.match-candidate exists for an operator-owned preset and source draft; it does not itself establish the missing persisted target-object edge. catalog-producer-prerequisites.json records exact fields; current live schema must be refreshed before any admission.

Task1.1: fix round1/5 from612e1315 — C1 matching_status pre-enumeration and C2 source_revalidation count preflight bypass explicit refusal on unavailable/missing func schema. Original implementer owns narrow consumer correction and source regressions; zero qualified credit must retain unavailable inventory, not fabricate total zero.

Task3.1: prepared — retained raw Mach-O STABS N_FUN producer can support a strictly snapshot-bound thin-image semantic witness; existing manifests/DB names do not qualify it. task-3-brief.md and next-identity-root-slice.md define strict extent/name/slice/architecture/candidate-byte binding and scoped package/report readers. Execute after existing refusal/trust/packaging queue; full U1/U3 stays open.

U33–U39 prerequisite audit retained in game-baseline-prerequisites.md: scoped direct-build receipt is failed/timeout, compilerProducedWholeImage/wholeFileByteIdentical/verified false, no candidate/objdiff. Partial observed manifest counts are not current recovery proof. Current catalog discovery followed through read-only; exact source project + successful link/launch receipt remains unestablished. No new recovery job or build admitted.
Task1.1: fix round1 implemented 612e1315..2a16c365, scoped re-review pending final report; source-only AST/diff checks pass.

Task1.1: fix round1/5 (2 addressed, 0 open — C1/C2 explicit unavailable-inventory refusal; commits612e1315..2a16c365).
Task1.1: complete (commits860731e5..2a16c365, review clean for bounded source slice). Full U1 and executable/installed/live acceptance remain open.
Task25.1: next fresh implementation after this evidence checkpoint.

Task25.1: implementation dispatched to /root/implement_cave_qualification from base6e4b313d740380ea4d7af7389ce5dc0b5312643a; brief task-25-brief.md; report task-25-report.md; source-only checks, no real producer fabrication or activation. Parent owns this pending ledger edit.

Ruling: Use the local CaveEvidenceError code independent_cave_verifier_unavailable as the explicit provider-unavailability signal; wrap unexpected callback errors as cave_verifier_failed with cause — the brief requires distinct expected-unavailable/failure outcomes but leaves exception type unspecified — cost if wrong: future provider adapters must adopt or translate this narrow exception contract; acceptance still fails closed.

Ruling: Supersede serialized implementation with up to three concurrent workers on disjoint owned paths, as explicitly requested by the user in the current continuation — maximize completion throughput while keeping reviews task-scoped and serializing shared-index commits — cost if wrong: cross-interface integration may require extra reconciliation; overlapping file writers remain prohibited.
Parallel commit protocol: Task25.1 holds current commit slot; new Task11.1 and29.1 may edit/check/report owned files but request controller commit slot before staging/commit. Scope-filter review packages by task-owned paths against recorded base/head so unrelated concurrent commits do not contaminate task review.

Task11.1: parallel implementation dispatched /root/implement_compile_binding, base6e4b313d740380ea4d7af7389ce5dc0b5312643a; exclusive compile.py + test_grid_compile_binding.py; commit permission pending.
Task29.1: parallel implementation dispatched /root/implement_dispatch_scope, base6e4b313d740380ea4d7af7389ce5dc0b5312643a; exclusive tool_providers.py and two focused tests/solution note; commit permission pending.

Task25.1: implemented 6e4b313d..f059c0bb; independent spec/quality review /root/review_cave_qualification active with task-25-review.diff. AST/source checks only; full U25/U28 still open. Commit slot released; Task11.1 and29.1 must request it before staging.

Ruling: Controller performs all staging and local commits for the concurrent shared-workspace wave; workers stop at READY_TO_COMMIT with an owned-path report — CE work shared-workspace policy gives the shared index one authority, which also preserves the SDD owned-commit/review contract — cost if wrong: a small controller integration delay; no worker edits are lost. This supersedes worker commit-slot grants for Task11.1,29.1 and subsequent parallel work. Task25.1 already completed its previously authorized serialized commit.

Task11.2: producer packet prepared (task-11-target-brief.md), not yet implementation-ready: resolve pinned bounded decoder injection and snapshot-derived selection contract before dispatch. Existing mkobj uses PATH objdump without timeout; no permissive callback or fabricated producer identity may close that prerequisite. Other ready source work proceeds.

Task29.1: controller committed owned paths bdbb4ef7; /root/review_dispatch_scope performs spec/quality gate against path-filtered task-29-review.diff, base6e4b313d. No tests/live acceptance.
Task11.1: controller committed owned paths d966fefc; /root/review_compile_binding performs spec/quality gate against path-filtered task-11-review.diff, base6e4b313d. No tests/real compiler acceptance.
Task25.1: spec compliant and quality approved in task-25-review.md; one minor Q25-1 fixture mutates only after scanner. Original implementer resumed to strengthen that source-only fixture before closing slice, fix round1 fromf059c0bb. Production reviewed clean; real provider remains unavailable.

Task29.1: complete (commits6e4b313d..bdbb4ef7 owned paths; independent spec/quality review clean in task-29-review.md). Full U29 and all execution/installed/live predicates remain open.
Task11.1: complete (commits6e4b313d..d966fefc owned paths; independent spec/quality review clean in task-11-review.md). Full U11, real compiler and accepted-source gates remain open.
Task8.1: implementation dispatched /root/implement_authoritative_packaging from d966fefc; exclusive package_authoritative and optional minimal ingest snapshot seam. No competing Task3 parser writer.
Task42.1: implementation dispatched /root/implement_staged_react_assets from c5c191e0; exclusive frontend build/publisher/test paths, no served assets.
Task25.1: Q25-1 fix committed c5c191e0; source-only scoped re-review /root/review_cave_snapshot_fix pending (task-25-fix-r1.diff).
Runtime recheck: live-health-parallel-wave.json and /proc confirm same healthy8080 PID/start/cwd/startticks/restarts0; no activation/action submitted.

Task25.1: fix round1/5 (Q25-1 addressed, 0 open, 0 introduced; source-only re-review task-25-fix-r1-review.md).
Task25.1: complete (owned source commits6e4b313d..f059c0bb and fixf059c0bb..c5c191e0; spec and quality approved). Full U25/U28 and executable/producer/live gates remain open.
Task11.2: bounded architectural contract investigation dispatched /root/resolve_target_producer_contract; owns next-target-object-contract.md only. No implementation yet.

Ruling: Implement Task11.2 as reference-free-only mkobj-target v1, correcting conservative C7/XBEGIN screening and executing no external decoder — no qualified external decoder closure exists in the inspected integration; a bounded real producer can still bind supported raw image functions to actual objects — cost if wrong: conservative false refusals and later decoder-mode work; no general target coverage, source acceptance or live qualification is claimed.
Ruling: Adopt explicit v1 admission caps (snapshot256MiB, raw128MiB, function64KiB, receipt32KiB, SMALL60s) and fixed lane-local loaded-source consistency manifest — bound owned work and prevent current disk hashes labeling stale loaded code — cost if wrong: larger supported targets require a reviewed revision; these limits are not measurements or hermetic-runtime claims.
Task8.1: source commit2590e25a; /root/review_authoritative_packaging reviews scoped diff against based966fefc. Parser ownership remains reserved until review/fix loop closes.

Task11.2: implementation dispatched /root/implement_target_object_producer from base2590e25a; requirements task-11-target-brief.md; report task-11-target-report.md. Exclusive new target lane/registry/planner and narrow mkobj predicate/keyword paths; no compile or parser overlap. Source-only, controller owns Git.

Task8.1: complete (owned source commitsd966fefc..2590e25a; task-8-review.md spec/quality approved, 0 findings). Full U8/U21 and executable/installed/portable/atomic acceptance remain open. Parser ownership released to Task3.1.
Ruling: Task11.2 initially supports bounded LocalDirStore reads and refuses adapters without an enforceable bounded read route — size()+get() cannot prevent allocation if an adapter lies; path-based chunked copies can stop at the cap — cost if wrong: other transports require later adapter qualification; no current grid-wide transport coverage is claimed.

Task3.1: implementation dispatched /root/implement_macho_stabs_witness from2a6f49a2; exclusive semantic witness/consumer/accounting paths; preserve reviewed Task8 coverage_index parser seam. Source-only; task-3-report.md.

Task42.1: source committed1cdfe463; /root/review_staged_react_assets reviews task-42-review.diff against basec5c191e0. Both JS syntax checks/package JSON/scoped diff pass; actual Vite/typecheck/build/filesystem/browser execution unrun.
Ruling: Task3.1 requires explicit known selected architecture and records parsed subtype/width/endian from the same digest-bound thin image; it never invents a selected CPU-subtype field — binary inventory has no such field — cost if wrong: stricter future subtype admission needs a reviewed input contract; any existing selected width/format contradiction still refuses.

Task42.1: fix round1/5 from1cdfe463 — two Important review findings T42-R1 asset URL postfix identity and T42-R2 Node/Vitest discovery integration; original implementer resumed, source-only. Both review gates remain open until scoped re-review.

Ruling: Scope matrix report queries with optional logicalId and an explicit hash-bound selection descriptor; return unbound=null/not_requested for that subset — whole-binary reads are redundant and global zero cannot be inferred from selected membership — cost if wrong: scoped clients and validators require coordinated updates; full-report callers retain compatibility, no speedup is claimed without execution.
Task21.1: source brief prepared after controller contract check; task-21-brief.md resolves SQL filtering, exact scope, genuine zero membership and unknown global counts. Dispatch when a review slot frees, preserving target-chain priority.

Task11.2: source committed24d3547f; spec/quality review package task-11-target-review.diff against base2590e25a; five ASTs, 59 fixed-closure source locators and call-site/diff checks pass. Runtime manifest/receipt sizing, reproducibility, real inputs/independent admission and catalog integration remain unrun.

Task42.1: fix round1 committed1d468be5; scoped review task-42-fix-r1.diff addresses URL postfix dependency identity and Vitest runner lifecycle; syntax/diff checks only, locked-version bundler/browser behavior unrun.

Task42.1: fix round1/5 (2 addressed, 0 open, 0 introduced — T42-R1 disk URL identity and T42-R2 Vitest lifecycle; commits1cdfe463..1d468be5).
Task42.1: complete (owned source commitsc5c191e0..1cdfe463 and fix1cdfe463..1d468be5; spec/quality source review approved). Full U13/U42 and locked-version build/filesystem/browser/installed/reloader gates remain open.

Task21.1: implementation dispatched /root/implement_filtered_matrix from1d468be5; brief task-21-brief.md. Exact logical subset SQL and both current matrix consumers only, no provider/cache or executing changes.
Task3.1: source committed000d400a; task-3-review.diff records owned paths from2a6f49a2 for independent spec/quality review. Seven AST/source checks pass, real-image/regression/runtime/consumer behavior unrun.

Task11.2: fix round1/5 from24d3547f — Important I1 fixed loaded helper closure omits ObjectRef.hex accessor; original implementer resumes narrow closure plus property/source-only mismatch regression source. Both source review gates remain open; execution/current admission gates remain separate.

Live source-wave read-only check: live-health-source-wave.json corroborates healthy8080 PID2697197/start1790595674.5226107/NVMe roots/restarts0/watchedFiles0; /proc startticks68973313 and cwd unchanged. Health revision remains blank; retained catalog loaded-module provenance is still historical, not a new activation receipt. No recovery action or restart.

Task11.2: fix round1 committed2472d02b; accessor closure plus loaded-property/source-only mismatch regression source; task-11-target-fix-r1.diff prepares scoped re-review. No behavioral or runtime acceptance.

Task3.1: minor (deferred): M1 identity withdrawal fixture deletes an empty table; original worker may strengthen it with the adjacent I1 regression edits, without extending the blocking loop.
Task3.1: fix round1/5 from000d400a — Important I1 SG_HIGHVM ignored while VA mapping assumes low-backed segment. Original worker resumes explicit unsupported-layout refusal and 32/64-bit regression sources. Narrow bounded scope stays unchanged; no high-VM mapper expansion.

Task11.2: fix round1/5 (1 addressed, 0 open, 0 introduced — consumed ObjectRef.hex closure; commits24d3547f..2472d02b).
Task11.2: complete (owned source commits2590e25a..24d3547f plus fix24d3547f..2472d02b; spec/quality approved). Full U11 remains open, including runtime/manifest sizing/reproducibility, independent current admission/key lineage, catalog and complete accepted-source chain.
Task11.3 contract investigation: dispatched /root/resolve_parity_binding_contract; bounded parity-contract-investigation-brief.md, source-only next-parity-binding-contract.md ownership.
Task3.1: fix round1 source committed81f819c3; SG_HIGHVM refusal and actual unrelated-edge withdrawal fixture, task-3-fix-r1.diff prepared for scoped review.

Task3.1: fix round1/5 (I1 and adjacent Minor M1 addressed, 0 open, 0 introduced — SG_HIGHVM refusal and actual unrelated-edge withdrawal; commits000d400a..81f819c3). Prior M1 deferred marker resolved by this reviewed fixture.
Task3.1: complete (owned source commits2a6f49a2..000d400a plus fix000d400a..81f819c3; spec/quality approved). Full U1/U3, executable/real-image/installed/live and recovery gates remain open.
U4/U33 prerequisite discovery: /root/inspect_reconstruction_prerequisite owns next-reconstruction-prerequisite.md; read-only actual source-chain check, no historical receipt rescan or compilerProducedWholeImage flag promotion.

Ruling: Adopt parity P1 as a versioned authenticated checker-observation verification method, preserving v1 task/receipt/view identities and explicitly declaring incomplete target-region and runtime admission — retained parsers only establish weaker reported code/row observations — cost if wrong: historical verification does not automatically acquire the stronger predicate and complete accepted-source delivery needs P2/P3; no raw whole-COFF equality shortcut.
Ruling: Apply fixed bounded LocalDirStore/capture/artifact limits and one shared parity operation deadline from next-parity-binding-contract.md — the existing unbounded materialization/communicate path cannot support the promised evidence boundary — cost if wrong: oversized/remote/unsupported-platform tasks become unavailable until a reviewed extension, with no fabricated negative parity.

Task11.3: P1 implementation dispatched /root/implement_parity_binding from1f29d91d; task-11-parity-brief.md and adopted next-parity-binding-contract.md. Exclusive parity lane and focused regressions; P2/P3 and full U11 stay open.
U4 contract investigation: /root/resolve_linked_contribution_contract owns next-linked-contribution-contract.md; next-reconstruction-prerequisite.md records actual compile/link/hash machinery but missing same-build terminal contribution and specific catalog resource premises. No report or summary flag promoted.

Task21.1: source committedbb414041; task-21-review.diff reviews exact owned paths from1d468be5. AST/no-shadowing source guard/static JS syntax/diff checks pass; SQL/Vitest/browser/performance execution unrun.
Ruling: Parity strong resolution must use bounded/deadline-aware artifact hashing on cache miss while preserving public default discovery, and refuse GC-enabled capped LocalDirStore configurations — unbounded discovery and put-triggered GC violate the bounded operation contract — cost if wrong: some configured local stores require a later qualified bounded publication route; no capacity policy is bypassed.

Ruling: Direct full-image runner must retain diagnostic build and measured whole-file equality but refuse terminal recovery until an actual same-build linked-contribution producer exists — generic link success and separately recompiled masked counts do not prove compiled final ownership — cost if wrong: former apparent successes now explicitly fail terminal acceptance; this honesty correction is not a positive recovery implementation.
Ruling: Correct only direct action mutating/long-running metadata and action-specific work-dir lookup now; do not add external-contract release allowlist membership — arbitrary wrappers, source sibling staging and Wine writers lack audited effective resource/lifetime closure — cost if wrong: full safe admission waits for a concrete guarded producer/profile; generic ownership policy is preserved.

Task4.1: implementation dispatched /root/implement_direct_acceptance_boundary frombb414041; task-4-brief.md adopts narrow refusal-only terminal correction and exact action metadata/work-dir lookup. Actual same-build producer, complete source/toolchain/variant and safe wrapper/Wine lifetime remain open, no activation.

Task21.1: spec and quality approved atbb414041 in task-21-review.md; 0 Critical/Important, one Minor M1 deferred: omitted-vs-None compatibility fixture compares the new implementation to itself, so future fixed pre-slice digest/unknown-extent fixtures would strengthen regression coverage. Source diff preserves compatibility; this is not a demonstrated defect or blocking fix loop. Full U21/execution/consumer/performance/current-source acceptance remain open.
Task21.1: complete bounded source slice (base1d468be5..bb414041, source-only); carry deferred M1 into final whole-branch review.
Ruling: Record Matrix M1 as nonblocking deferred work while advancing the producer chain — reviewer found no current compatibility defect — cost if wrong: future legacy payload/hash regressions have weaker fixed-fixture coverage until final-review triage.

Task4.1: source committed1c74b9c5; scoped task-4-review.diff covers exact owned paths frombb414041. Four ASTs and static literal/metadata/diff checks pass; nine regression functions unrun. Independent spec/quality review pending; no positive contribution or action runtime qualification.

U2 schema prerequisite: controller source inspection confirmed db.py still owns duplicate baseline DDL and five direct importers, while store.connect and migrations already provide the authoritative ledger path. Prepared schema-unification-contract-brief.md and exact U22/U82/U21a source extracts; contract investigation queued behind current reviews. No database access or source changes.
