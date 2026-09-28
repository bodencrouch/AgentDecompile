---
title: Static CodeBrowser Project Tabs - Plan
type: feat
date: 2026-09-28
topic: static-codebrowser-project-tabs
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Static CodeBrowser Project Tabs - Plan

## Goal Capsule

**Objective:** An operator reverse-engineering a set of related builds works in one browser tab per project. They see every build, its code, its cross-build matches and its call graph at once, in the layout they already know from Ghidra's CodeBrowser. The recovery pipeline's automatic work shows as state they can read and pause, never as buttons they must press. Every cross-matching method stays available and visible, targeted AI is one operator-controlled toggle, and both frontends read one honest, reconciled progress picture.

**Means:** Rebuild the static dashboard on port 8080 as a CodeBrowser-parity workspace where a tab holds a project (KTD1-KTD4, KTD9 below). Close the cross-matching availability gaps the research found (KTD1-KTD4). Add one precedence-ruled AI toggle (KTD5-KTD6). Bring the Vite workstation and the report/progress spine into scope, built from the components already live in `frontend/src/workstation` (KTD7-KTD9).

**Product authority:** The user's 2026-09-28 directives, `docs/FRONTEND_INTENT.md`, and the 2026-09-28 scope-change directives recorded under Product Contract Preservation below. This plan now covers the static dashboard, cross-matching availability, the targeted-AI toggle, the Vite workstation and the report/progress spine.

**Execution profile:** Multi-phase implementation plan for `ce-work` or an equivalent executor. Phases are ordered A (static 8080) → B (matching availability) → C (AI toggle) → D (Vite) → E (report spine) → F (tests last). Phases B and C are independent of A and D/E and may run in parallel with them; D depends on A's peer/session-scoping units and E's report shape.

**Stop conditions:** Stop and return to planning if an owner-locked file (see Planning Contract) must be edited to close a requirement, or if a unit's fix requires renumbering the `match` table's primary key or removing a column another live consumer reads.

## Product Contract

### Summary

Replace the static dashboard's action tabs and pipeline buttons with Ghidra CodeBrowser parity. A browser tab holds a project whose binaries are peers on one shared cursor. A cross-build map dock shows the call graph and matcher together, with every matching method's status visible. Pipeline progress is shown and can be paused, never triggered. Targeted AI is one toggle with one precedence rule. The Vite workstation and a shared report/progress spine are now in scope, built from the already-live workstation components.

### Problem Frame

The static dashboard grew around the pipeline's steps. Its menus mostly offer buttons for work the pipeline already schedules on its own. Ghidra's own model has a second cost: only one program drives the cursor at a time, so comparing builds means loading and switching between them.

Research since the first draft narrowed three more gaps. The matcher's channel model looks complete on paper but two channels never contribute in practice (BSim persistence, the ABI veto), one channel is missing metadata it claims to carry (X), and one stage is mislabeled under the wrong channel (the P-code skeleton stage under `M`). Targeted AI has four disagreeing defaults across five entry points and no operator-facing switch. The Vite workstation already has live components for half of what `docs/FRONTEND_INTENT.md` asks for, but the shipped bundle is a week stale and several reusable pieces sit behind dead root components. Progress reporting has at least three disagreeing counts for the same corpus, and no gate stops a mismatched count from reaching an outside publishing step.

### Product Contract Preservation

Scope changed on 2026-09-28. R1-R26, F1-F4, AE1-AE7 keep their IDs and meaning from the prior requirements-only draft. Four changes below extend the contract; they do not narrow or reinterpret an existing R, F or AE.

- changed: Cross-matching methods must have high availability — every method and channel (Z, I, H, X, G, S, T, M, D, donor scheduling, review decisions) is available with an ordered fallback, none blocks matching, and BSim especially never blocks. Reason: research found BSim hits are never persisted so channel S never contributes, X lacks C++/RTTI metadata, the P-code skeleton stage is mislabeled as channel M, the contract veto has no production caller, and match rows carry no queryable kind/confidence/algorithm. Adds R27-R34.
- changed: Targeted AI (stage 6 leftovers, and any LLM rewrite path) becomes one optional implementation, switched by an env var, a CLI flag at 8080 server start, and a dashboard setting, with one documented precedence rule, a visible value source, live application where possible, and no dependency from the deterministic path. Reason: five entry points (frontdoor, `ghidra-bulk --llm-cleanup`, `corpus run --llm`, the MCP recovery provider, the rewrite-worker skill) disagree on defaults and none is operator-switchable. Adds R35-R38.
- changed: The Vite workstation (objdiff-web first; decomp.me scratch, Dogbolt compare, RzWeb/r2web views, an APKMan-style container tree, a pipeline stage DAG with retry-on-failure, a lane E fleet roster, a spectator view) and the report spine (a per-binary-and-version objdiff-shaped `report.json`, a tier-split verified-vs-advisory progress display in both UIs, a count-reconciliation gate before any outside publishing, and publishing as its own approved step) move from Deferred into scope. Reason: `STRATEGY.md`'s "One catalog, two surfaces" track names both as committed, and research found live components (`ScratchWorkspace`, `MatchReview`, `CompareView`, `integration/boundaries.ts`, `PreparationActivity`) that make this buildable now rather than speculative. Adds R39-R50.
- changed: Operator user-research outputs — JTBD-derived acceptance examples and a usability task list per delivered slice, mapped to Ghidra-guide chapters and the 2026-09-28 directives — join the Verification Contract. Reason: the JTBD/journey research (`design:user-research` output) already produced eight usability tasks (T1-T8) with named success criteria; carrying them forward avoids re-deriving verification from scratch. Adds AE8-AE15 and the Usability Test Plan subsection.

### Actors

- A1. Operator: a person reading, naming and reviewing code across related builds while the pipeline runs.
- A2. Agent client: an automated caller acting through the same backend. It reads the same state the operator sees.
- A3. Recovery pipeline: admits and runs work on its own. The interface observes it.
- A4. Spectator: a second viewer following the operator's session read-only (Vite workstation only).

### Requirements

**Pipeline-owned work is never a control**

- R1. No menu item, tab, toolbar button or panel button starts, reruns or duplicates work the recovery pipeline schedules on its own. This covers these stages: analysis; protection preparation; fact extraction; similarity indexing; matching; calibration; source recovery; cross-build placement; leftover recovery; byte verification.
- R2. Three events admit the pipeline's eligible missing work without a separate action: opening a project, adding a binary to a project, and registering a binary. Reopening material that already has receipts does not redo that work.
- R3. After admission, the interface shows a one-line receipt naming the admitted run, its generation and its queue position.
- R4. Pause, resume and stop are the only workflow controls. They appear wherever run state is shown, pre-scoped to the run in view.
- R5. Operator edits stay available as explicit user actions: rename; comments; bookmarks; retyping and data-type edits; accept or reject of match candidates, singly and in batches; opening, creating and saving projects; adding binaries.
- R6. An expert command palette stays available for low-level catalog actions. It is not the path for routine pipeline work.
- R7. The backend enforces R1 through its classification of which actions and modes change state. A new pipeline trigger added to a static surface fails that check.
- R8. R1 through R7 apply to every static surface served on 8080, including the explorer page.

**CodeBrowser parity**

- R9. The workspace follows Ghidra's stock CodeBrowser arrangement: the Symbol Tree and Program Trees in the left rail, with the Data Type Manager below them; the Listing and Decompiler in the center, with secondary providers tabbed alongside the Decompiler; Console and Bookmarks at the bottom; Data Type Preview as a thin strip.
- R10. Every CodeBrowser provider that the Ghidra reversing guide uses is present: Listing (address, bytes, mnemonic, operands, cross-reference and comment fields, with a function header); Decompiler; Symbol Tree; Program Trees; Data Type Manager; Memory Map; Bytes; Defined Strings; Symbol Table and References; Functions table; Function Graph; Function Call Trees and Call Graph; Bookmarks; Console; Function Comparison; Equates; Relocations.
- R11. Providers that only show data are read-only views. Providers that edit data do so only through R5's explicit user actions.
- R12. One program location drives every connected provider. Selecting an address, symbol or cross-reference in any provider moves the others. No tab switch or new search is needed.
- R13. Navigation matches Ghidra: back and forward history; go-to by address or name; previous and next function; highlight of the selected token wherever it recurs; an overview strip marking locations across the program.
- R14. The layout uses the page for content. Providers dock and tab like Ghidra's. No space goes to controls that R1 excludes.

**Project as tab**

- R15. A browser tab holds one project. Every binary in the project is a peer in that tab, not a hidden sibling of one active program.
- R16. Each peer shows whether it is readable locally, loading, or blocked. A blocked peer shows the backend's own next step, for example that server credentials are required.
- R17. Selecting a function in one peer aligns the other peers to the same identity where one is bound. A peer without a binding shows "no identity binding". It is never an empty or hidden lane.
- R18. A project with tens of binaries stays usable, up to the corpus's ninety. Peers not in focus stay light, and the operator can bring any peer into focus.

**Call graph and matcher together**

- R19. A cross-build map is a docked view in the project tab. It shows the call graph across builds and the matcher's results together, on the same selection.
- R20. The map includes a matrix with one cell per pair of builds. Each cell shows match status and counts. A pair the pipeline never scheduled reads "not scheduled", which differs from a pair that failed.
- R21. Match results appear with the function in context. They show as marks at the function header in the Listing and Decompiler, and as edges on the call graph.
- R22. Match review shows status, match kind, score, confidence and algorithm. The operator can accept or reject one candidate, or a batch chosen by build pair and score band.
- R23. A byte-level match from object comparison and a match by name, signature or call graph always carry different labels.

**Pipeline state display**

- R24. Pipeline progress for the project is visible inside the workspace. The bottom activity dock shows the current stage per binary and the run's state.
- R25. A blocked state names its cause and the next step. It never shows a generic error.
- R26. The interface shows only state observed from the backend. It shows no simulated progress and no invented percentages.

**Cross-matching method availability**

- R27. Every cross-match method and channel — Z (identical image), I (authentic symbols), H (hashes), X (rare refs and C++/RTTI metadata), G (call-graph/CFG/SPP), S (BSim), T (ABI/contract veto), M (BinExport/BinDiff), D (emulation), donor scheduling and review decisions — is available with an ordered fallback. None blocks matching; BSim (S) unavailability especially never blocks the pipeline.
- R28. For any candidate pair or function, both frontends show, per method, whether it ran, was skipped (with a named reason), is unavailable, or is not built yet.
- R29. Match rows carry queryable kind, confidence and algorithm rather than only an evidence-JSON blob, so review can filter and sort without parsing evidence.
- R30. The cross-build matrix cell distinguishes a pair the donor scheduler never selected ("not scheduled") from a pair that ran and failed, and shows the scheduling reason (explicit pair, spanning-forest edge, hub-to-anchor link).
- R31. Channel S (BSim) persists its hits to a queryable store, so BSim results reach the matcher's fusion step and the availability display instead of permanently reading unavailable.
- R32. Channel X carries C++/RTTI/vtable/dispatch metadata, not only rare strings and constants.
- R33. The P-code/decompiler-skeleton exact-fingerprint stage carries its own channel label, distinct from channel M (BinExport/BinDiff), so confidence scoring and the availability display do not conflate the two methods.
- R34. The ABI/contract veto (channel T) has a production caller in the identity/propagation path, so a high-score tie with an incompatible calling contract resolves instead of staying ambiguous by default.

**Targeted AI toggle**

- R35. Targeted AI (stage 6 leftover recovery, and any LLM rewrite path) is switched by exactly three surfaces: an environment variable, a CLI flag on the 8080 server start command, and a dashboard setting.
- R36. One documented precedence rule resolves the three surfaces to a single effective value. The dashboard shows which surface supplied the current value.
- R37. A change to the env var or the dashboard setting applies to the next job without a server restart. The CLI flag is fixed at process start, and the dashboard names that limit.
- R38. The deterministic recovery path (compile, repair, propagate, verify) never depends on targeted AI being enabled.

**Vite workstation**

- R39. The Vite workstation's main view is objdiff-web-first: an instruction-aligned two-column diff with register highlighting, navigable mismatches and a symbol tree.
- R40. A decomp.me-style scratch view lets the operator iterate a candidate against the catalog's compile and objdiff actions, extending the existing scratch workflow.
- R41. A Dogbolt-style compare view shows multiple decompiler outputs side by side, using only optional licensed local runners; it never uploads to the public Dogbolt service.
- R42. RzWeb/r2web-style expert views sit behind the workstation's one normalized selection, never a second selection store.
- R43. An APKMan-style container tree generalizes to any supported container or format, reusing the existing format-provider pattern.
- R44. A pipeline stage graph shows stage dependencies as a DAG with edges, and retries a stage only after that stage fails — never as a manual re-run control.
- R45. A lane E fleet roster shows donor and recipient decisions across a batch, reusing the existing match-review batch-decision contract.
- R46. A spectator view lets a second viewer follow the operator's session read-only.

**Report and progress spine**

- R47. The corpus produces an objdiff-shaped `report.json` per binary and version, generated from the corpus database, not only consumed from an external objdiff run.
- R48. Both frontends show progress as a tier-split bar: verified (byte-exact, relocation-aware objdiff 0) kept separate from advisory (compiling Ghidra C), never merged into one number.
- R49. A count-reconciliation gate runs before any decomp.dev publishing step. It fails closed when the accounting buckets (accepted source, candidate source, preserved region, unclassified, excluded-with-reason) do not exhaustively and exactly cover the inventory.
- R50. Publishing to decomp.dev is its own explicit, separately approved step. It never runs as a side effect of generating `report.json`.

### Key Flows

- F1. Open a project and start reading
  - **Trigger:** The operator opens a project in a new browser tab.
  - **Actors:** A1, A3
  - **Steps:**
    1. The tab shows the project's binaries as peers, each with its readiness (R15, R16).
    2. The pipeline admits missing work, and the admission receipt appears (R2, R3).
    3. The operator selects a function in any peer. The Listing, Decompiler, Symbol Tree and call trees follow (R12).
  - **Outcome:** The operator reads code while the pipeline works. Nothing asked them to start it.
  - **Covered by:** R2, R3, R12, R15, R16

- F2. Compare a function across builds
  - **Trigger:** The operator selects a function that exists in several builds.
  - **Actors:** A1
  - **Steps:**
    1. Bound peers align to the same identity (R17).
    2. The cross-build map shows the function's callers and callees across builds, with match edges (R19, R21).
    3. The matrix shows which build pairs were compared (R20).
  - **Outcome:** The call graph and matcher are visible together for one selection.
  - **Covered by:** R17, R19, R20, R21

- F3. Review matches in bulk
  - **Trigger:** The operator opens review for a build pair.
  - **Actors:** A1
  - **Steps:**
    1. Review lists candidates with status, kind, score, confidence and algorithm (R22).
    2. The operator accepts every candidate above a score band for that pair in one action.
    3. The two match kinds keep their separate labels (R23).
  - **Outcome:** Review scales to large sets of candidates.
  - **Covered by:** R22, R23

- F4. Pause the pipeline
  - **Trigger:** The operator needs the machine for something else.
  - **Actors:** A1, A3
  - **Steps:**
    1. The activity dock shows the run and its stage (R24).
    2. The operator pauses the run in view, then resumes it later (R4).
  - **Outcome:** The pipeline stops and resumes, and no start control exists.
  - **Covered by:** R4, R24

- F5. Inspect a candidate with an unavailable method
  - **Trigger:** The operator opens a match candidate where BSim (or another channel) is unavailable.
  - **Actors:** A1
  - **Steps:**
    1. Each channel's row shows ran / skipped:reason / unavailable / not-built (R28).
    2. The matcher's decision used the available channels; the unavailable one narrowed evidence, it did not stop matching (R27).
    3. The operator can still accept or reject the candidate.
  - **Outcome:** One missing method never blocks review.
  - **Covered by:** R27, R28

- F6. Toggle targeted AI
  - **Trigger:** The operator wants stage 6 leftover recovery to use bounded LLM cleanup on the next run.
  - **Actors:** A1
  - **Steps:**
    1. The operator sets the dashboard setting (or the env var, or restarts with the CLI flag).
    2. The dashboard shows the effective value and which surface supplied it (R36).
    3. The next job picks up the change; the CLI-flag case is named as restart-only (R37).
  - **Outcome:** One switch, one precedence rule, no silent default drift.
  - **Covered by:** R35, R36, R37

- F7. Publish verified progress
  - **Trigger:** The operator wants to publish a binary's progress externally.
  - **Actors:** A1
  - **Steps:**
    1. `report.json` is generated for the binary and version (R47).
    2. The count-reconciliation gate checks the accounting buckets exhaustively cover the inventory (R49).
    3. A gate failure blocks publishing and names the unreconciled count; a pass requires the operator's explicit approval before anything is sent outside (R50).
  - **Outcome:** No published number can silently disagree with the corpus.
  - **Covered by:** R47, R49, R50

### Acceptance Examples

- AE1. **Covers R1, R8.** The redesigned static surfaces are in place. The check lists every menu, tab and button. None of them starts or reruns analysis, matching, recovery, placement or verification. Neither the "Run pipeline" control nor the "Start workflow" control exists.
- AE2. **Covers R2, R3.** A project holds a binary that has no analysis yet. When the operator opens the project, the admission receipt appears. The operator pressed nothing.
- AE3. **Covers R12.** The Listing shows a call. When the operator activates its target, the Decompiler, Symbol Tree and call trees move to the target without a tab switch.
- AE4. **Covers R17.** A function is bound in two of three peers. When the operator selects it, two peers align. The third shows "no identity binding".
- AE5. **Covers R20.** The pipeline compared a spanning subset of build pairs in a project. When the operator views the matrix, the pairs it did not compare read "not scheduled".
- AE6. **Covers R23.** One pair matched on object bytes, and another matched on name only. When both appear in review, their kind labels differ.
- AE7. **Covers R16, R25.** A peer needs server credentials before it can be read. When the tab loads, the peer shows a blocked state that names the credential step.
- AE8. **Covers R27, F5 (JTBD-6).** The BSim database is absent for a project. When the operator opens a match candidate, channel S shows "unavailable: reason", the other channels still decide, and review is not blocked.
- AE9. **Covers R35, R36, F6 (JTBD-7).** The operator toggles targeted AI through the env var, the server flag and the dashboard, in turn. Each time, the effective state and its source are shown; when off, stage 6 reads "disabled by operator", not "pending".
- AE10. **Covers R2 (JTBD-1).** The operator reopens a known project. The same binaries, annotations, receipts, job owners and selection return. No reanalysis job starts and no Start button appears.
- AE11. **Covers R1, R14 (JTBD-2).** The operator counts pipeline-stage buttons across the redesigned surface. The count is zero; only pause/resume/stop and the expert palette remain.
- AE12. **Covers R9, R10 (JTBD-3).** The operator opens a class and its struct from the Symbol Tree or Data Type Manager. The path takes fewer than three gestures and triggers no destructive-action prompt.
- AE13. **Covers R19, R20 (JTBD-4).** The operator opens the call graph and match review for the same entity. Both are visible at once, on one selection, without hiding either.
- AE14. **Covers R48 (JTBD-8).** The operator views a binary's progress. Verified and advisory counts render as separate segments; the export or report never merges them into one recovered number.
- AE15. **Covers R49, R50 (JTBD-8).** A binary's accounting buckets do not exhaustively cover its inventory. Publishing is blocked and names the gap; no report reaches an outside site until the operator approves a passing gate.

### Success Criteria

- The operator can work through every chapter of the Ghidra reversing guide in the static workspace: orient; symbols and types; listing and decompiler; call trees; memory map and bookmarks; signatures; structures and vtables; templates; diagnosis.
- No static surface offers a control for pipeline-owned work, and the backend classification check in R7 passes.
- For any selected function in a multi-build project, the call graph and matcher results are visible together, and every method's status (ran/skipped/unavailable/not-built) is visible for that function.
- The guide's flows produce no console errors and reach no dead controls.
- The operator can complete each usability task in the Usability Test Plan (Verification Contract) against its named success criterion.

### Scope Boundaries

**Deferred to Follow-Up Work**

- Publishing statistics to decomp.dev itself (R50 covers the gate and the approval step; the publishing integration's own delivery, and resolving decomp.dev's license, are follow-up work once R47-R49 land).
- Distributed-compute lane E scheduling beyond the fleet roster's display (`grid_lanes/cascade.py` already exists; scaling it across workers is a separate track).
- Native decompiler tier (JVM-free replay) — tracked separately in `STRATEGY.md`'s own track, not part of this plan.

**Outside this product's identity**

- A second job or selection store in the static surface or the Vite workstation.
- Any control that starts pipeline stages by hand, including run buttons for single stages.
- Uploading binaries or decompiler output to the public Dogbolt service.
- Auto-publishing a report to an outside site as a side effect of generating it.

### Key Decisions

- Builds are peers. This replaces Version Tracking's source and destination pair. Ghidra's limit of one active program is what the project tab removes, so no build drops to a secondary role.
- The cross-build map is a dock inside the CodeBrowser layout, not the tab's landing view. This keeps CodeBrowser parity and adds the one view Ghidra cannot show.
- Full provider parity is required. Delivery may start with the providers the guide's first chapters use: Listing, Decompiler, Symbol Tree, call trees, cross-references and the cross-build map.
- The menubar stays, without an Analysis menu, because analysis belongs to the pipeline. The items that remain follow Ghidra's naming: navigation, search, window, help and file operations on projects.
- Method availability is shown, not hidden or defaulted to "not run". `Governs R27, R28.`
- Targeted AI is a toggle, not a removed capability. `Governs R35-R38.`
- The Vite workstation and the report spine build from live workstation components first, and add net-new views only where research found no reusable component. `Governs R39-R50.`

### Dependencies / Assumptions

- Peers read at the same time only if the backend scopes its live-read path to each project and binary. Today one active locator is shared across the whole process (`src/agentdecompile_recovery/corpus/dashboard/mcp_bridge.py:20-26`, `CONTEXT_LOCK` and the global `_ACTIVE_LOCATOR`). U3 resolves this before R15 and R18 can hold.
- Admission on open and register (R2) is new behavior. Today only adding a program to an open project admits work; `workbench.py:1131-1135` admits prepare only on add-to-project.
- `src/agentdecompile_recovery/corpus/ghidra_project.py:1445` `_dedupe_project_sessions` hides all but one project session; U4 resolves this before multiple peers can stay open.
- Assumption: menubar contents beyond removing Analysis follow Ghidra's naming. The user said the top menu holds useless buttons but did not say what should replace them.
- Assumption: in large projects, peers not in focus render as light tracks rather than full workspaces.
- Live decompiler reads of the shared repository need server credentials. A local copy of the project reads without them.
- The Vite frontend's shipped bundle (`static/react`) is a build behind its source; a bundle rebuild needs the user's explicit permission for `npm install` (execution precondition, not a planning blocker — see Planning Contract).
- Owner-locked files (Planning Contract) cannot be edited by any unit in this plan; units that would otherwise touch them call the existing entry points instead.

### Outstanding Questions

All prior outstanding questions are resolved for planning purposes below; none blocks `implementation-ready` readiness.

- How the cross-build call graph performs across tens of builds, and whether it loads a piece at a time. **Deferred** — U8's Approach states the default (progressive load past a peer-count threshold); tuning the threshold is an implementation-time detail, not a blocker.
- Which existing static panels are removed, merged or rehomed as CodeBrowser providers, and how existing deep links keep working. **Deferred** — resolved per-provider inside U6's Approach; no product-level ambiguity remains.
- Whether the explorer page folds into the project-tab workspace or stays a separate view under R8. **Deferred** — U2 keeps it a separate view that still satisfies R1-R8; folding it in is a future simplification, not required for this plan's Definition of Done.

<!-- ce-section: work-relationships -->
### How This Work Fits Together

The 2026-09-28 directives, and the 2026-09-28 scope-change directives above, cover four areas, all now owned by this plan:

- **Static CodeBrowser workspace** (Phase A) and **matching availability** (Phase B) share the same backend match store and identity tables.
- **Targeted AI toggle** (Phase C) is read by both the static dashboard's stage-6 leftover recovery and the corpus CLI's LLM cleanup path; it has no UI dependency on Phase A or D.
- **Vite workstation** (Phase D) and **report spine** (Phase E) share the one catalog, one job store and one claim model that Phase A's static surface also reads (`STRATEGY.md`, "One catalog, two surfaces"). Phase D's stage graph and fleet roster read the same activity and match-review contracts Phase A's activity dock and match review use.

Phase B's availability display (R27-R34) is consumed by both Phase A's cross-build map (R19-R23) and Phase D's fleet roster (R45). Phase E's `report.json` (R47) feeds Phase A's and Phase D's progress displays (R24-R26, R48) identically — one producer, two consumers.

### Sources / Research

- `docs/FRONTEND_INTENT.md`: the split between surfaces, "no Start button", and the single store.
- `docs/ideation/2026-09-28-frontends-redesign-ideation.html`: ranked ideas and their evidence, including the decomp.dev progress-card idea (lines 85, 90, 296-312) and the "89 directed pairs" donor-scheduling figure (line 136).
- `docs/dashboard-design/2026-09-28-static-codebrowser-guide-redesign.md`: earlier redesign slices built on the guide, including the wb-sessions "one tab per project" vs. `renderEditorBody` "one pane at a time" conflict (sec 2.1) this plan resolves in U7-U8.
- `docs/dashboard-design/pipeline-diagram/README.md`: pipeline stages and lanes.
- `docs/plans/2026-09-09-0334-feat-evidence-fusion-matcher-plan.md`: the 8-channel cascade (R1, R2), BSim's mutual-best-plus-significance rule (KTD3 there), and R9's optional-tool skip list that omits BSim's own fallback chain — the gap Phase B closes.
- `STRATEGY.md` "One catalog, two surfaces" and "Corpus recovery pipeline" tracks: the two-frontend split, the targeted-AI precedence requirement, and the `report.json` / decomp.dev publishing sequencing this plan's Phase C and E implement.
- Operator user research (JTBD, journey map, affinity themes, usability task list): the eight JTBDs and T1-T8 usability tasks behind AE8-AE15 and the Verification Contract's Usability Test Plan. Two of its citations (JTBD-1's `docs/FRONTEND_INTENT.md:83-88` and the "per-stage buttons stay banned" cite at `:432-433`) failed spot-check on line range; the underlying claims held on independent re-read and are restated here without the unverified line numbers.

---

## Planning Contract

### Planning-time constraints (numbered KTDs)

- KTD1. Match-method status renders from a five-state enum — `ran`, `skipped:<reason>`, `unavailable`, `not-built`, `not-scheduled` (pair-level only) — read from the skip-reason strings `match_store.py` already writes (for example `skipped/missing_bsim_hit_table`, `skipped/no_pairwise_bindiff_adapter`, `skipped/residue_path_not_configured`, `skipped/no_embedding_evidence_store`) plus two new reasons this plan adds for the X-channel metadata gap and the not-yet-wired contract veto. No new state machine; the enum only names states the code already distinguishes. `Governs R27, R28, R30.`
- KTD2. BSim persistence adds a `bsim_hit` table populated by the existing Ghidra BSim ingest/preparation stage (`src/agentdecompile_recovery/corpus/dashboard/preparation.py`'s BSim stage is owner-locked — this unit calls it, it does not edit it). The matcher's already-implemented `_fuse_bsim` (`src/agentdecompile_recovery/corpus/match_store.py:308-375`) reads the new table unchanged; no fusion-logic change is needed once rows exist. `Governs R31.`
- KTD3. The P-code/decompiler-skeleton stage gets its own `primary_channel` value, distinct from `'M'`, with its own `channel_confidence.py` base score (not BinDiff's 66). Existing rows already written with `primary_channel='M'` for this stage need a one-time backfill to the new value so history does not silently split. `Governs R33.`
- KTD4. The contract veto (`_contract_veto`, `src/agentdecompile_recovery/corpus/match_store.py:389,707-760,850-873`) gets a caller in the identity/propagation path (`identity.py` or `propagate.py`, per the actual best/runner-up selection point found during implementation) that passes `contract_features`. It stays opt-in behind a flag until its output on the existing high-score-tie cases is checked; the flag defaults on only after that check passes. `Governs R34.`
- KTD5. Targeted-AI precedence: CLI flag (fixed at 8080 server start) > env var > dashboard setting > compiled default (off). This follows the existing work-exchange tri-state pattern (`src/agentdecompile_cli/server.py:1085-1096,1178-1193`, `_set_env_from_args`), which already resolves a CLI/env pair and re-exports the resolved value to `os.environ` so child jobs see it. (session-settled: user-directed — chosen over leaving the existing 0-vs-1 rewrite-budget default drift unresolved: the user's 2026-09-28 directive requires one documented precedence rule, so this plan states CLI > env > dashboard > default explicitly and reconciles the drift as part of landing it.) `Governs R35, R36, R38.`
- KTD6. The dashboard AI setting persists like the existing notifications settings page: `GET`/`POST /dashboard/api/settings/ai` reads and writes a JSON file under `AGENT_DECOMPILE_CORPUS_WORK_DIR`, read fresh on every call so a change applies without a restart. The CLI flag is the one surface that cannot apply live; the dashboard names that limit per R37. `Governs R36, R37.`
- KTD7. `report.json` generation reuses `decomp_match.py`'s existing objdiff-report parsing shape (`units[].measures.matched_percent` etc.) but as a producer over the corpus database instead of a consumer of an external objdiff project's output. This keeps one schema for both directions. `Governs R47.`
- KTD8. The count-reconciliation gate implements the exhaustive-accounting design already specified in `docs/plans/2026-09-22-task-acceptance-and-continuation-design.md:650-657`: mutually exclusive buckets (accepted source, candidate source, preserved region, unclassified, excluded-with-reason), each corpus member appearing exactly once, fail rather than invent a missing count. `Governs R49.`
- KTD9. Vite views build from the already-live workstation components first: `CompareView`/`DiffEvidence`/`integration/boundaries.ts` for objdiff-web (R39), `ScratchWorkspace` for the decomp.me view (R40), `PreparationActivity`/`activity.ts` extended with `EntityActivity.dependencies[]` edges for the stage graph (R44), `MatchReview` for the fleet roster (R45). Dogbolt compare, RzWeb/r2web views, the APKMan-style tree and the spectator view are net-new (R41-R43, R46); research found no reusable component for any of them. `Governs R39-R46.`

### High-Level Technical Design

**Unit dependency and phase diagram.**

```mermaid
flowchart TB
  subgraph PhaseA["Phase A: Static 8080 CodeBrowser"]
    U1["U1 Landed: trigger removal (af761fe)"]
    U2["U2 actions.js quick actions + R7 check"]
    U3["U3 Per-call locator scoping"]
    U4["U4 Multi-project session support"]
    U5["U5 Admission on open/register"]
    U6["U6 CodeBrowser providers"]
    U7["U7 Project-as-tab layer"]
    U8["U8 Cross-build map dock"]
    U1 --> U2
    U3 --> U4
    U4 --> U7
    U5 --> U7
    U6 --> U8
    U7 --> U8
  end
  subgraph PhaseB["Phase B: Matching availability"]
    U9["U9 BSim hit persistence"]
    U10["U10 X channel C++/RTTI metadata"]
    U11["U11 Relabel P-code skeleton stage"]
    U12["U12 Wire contract veto"]
    U13["U13 Match row kind/confidence/algorithm columns"]
    U14["U14 Per-pair/function availability surface"]
    U9 --> U14
    U10 --> U14
    U11 --> U13
    U12 --> U14
    U13 --> U14
  end
  subgraph PhaseC["Phase C: AI toggle"]
    U15["U15 Config precedence resolver"]
    U16["U16 Wire resolver into rewrite + LLM-cleanup paths"]
    U17["U17 Dashboard AI setting"]
    U15 --> U16
    U15 --> U17
  end
  subgraph PhaseD["Phase D: Vite workstation"]
    U18["U18 objdiff-web main view"]
    U19["U19 decomp.me scratch view"]
    U20["U20 Dogbolt compare view"]
    U21["U21 RzWeb/r2web views"]
    U22["U22 APKMan container tree"]
    U23["U23 Pipeline stage DAG"]
    U24["U24 Lane E fleet roster"]
    U25["U25 Spectator view"]
    U18 --> U19
    U18 --> U20
    U18 --> U21
    U18 --> U25
  end
  subgraph PhaseE["Phase E: Report spine"]
    U26["U26 report.json generation"]
    U27["U27 Tier-split progress bar"]
    U28["U28 Count-reconciliation gate"]
    U29["U29 Explicit publish step"]
    U26 --> U27
    U26 --> U28
    U28 --> U29
  end
  subgraph PhaseF["Phase F: Tests last"]
    U30["U30 Write tests from verification sequences"]
  end
  U7 --> U24
  U14 --> U24
  U27 --> U8
  PhaseA --> PhaseF
  PhaseB --> PhaseF
  PhaseC --> PhaseF
  PhaseD --> PhaseF
  PhaseE --> PhaseF
```

**Per-method availability status flow (Phase B).**

```mermaid
stateDiagram-v2
  [*] --> Considered
  Considered --> NotBuilt: method has no production caller yet
  Considered --> Unavailable: required resource missing (DB, binary, tool)
  Considered --> Skipped: preconditions unmet, reason recorded
  Considered --> Ran: preconditions met
  Ran --> Contributed: channel produced a candidate or veto
  Ran --> RanNoResult: channel ran, found nothing
  NotBuilt --> [*]
  Unavailable --> [*]
  Skipped --> [*]
  Contributed --> [*]
  RanNoResult --> [*]
```

**Targeted-AI precedence flow (Phase C).**

```mermaid
flowchart TB
  Start["Resolve effective AI state"] --> CLI{"CLI flag set\nat 8080 start?"}
  CLI -->|yes| UseCLI["Effective = CLI value\nSource = 'server flag'"]
  CLI -->|no| ENV{"Env var set?"}
  ENV -->|yes| UseENV["Effective = env value\nSource = 'environment'"]
  ENV -->|no| DASH{"Dashboard setting\nfile present?"}
  DASH -->|yes| UseDash["Effective = dashboard value\nSource = 'dashboard'"]
  DASH -->|no| Default["Effective = off (default)\nSource = 'default'"]
  UseCLI --> Show["Dashboard shows effective + source"]
  UseENV --> Show
  UseDash --> Show
  Default --> Show
```

### Execution preconditions (not planning blockers)

- The Vite bundle rebuild (`npm install` under `src/agentdecompile_recovery/corpus/dashboard/frontend`) needs the user's explicit permission before Phase D or E units that touch the frontend run their build step. Ask at unit start, not during planning.
- `docs/dashboard-design/pipeline-diagram/README.md` is the reference diagram for stage names; units that add or relabel a channel (U11) update the generator (`docs/dashboard-design/pipeline-diagram/generate_pipeline_diagram.py`) so the two stay in sync.

### Owner-locked files (must not be edited; call, don't edit)

- `src/agentdecompile_recovery/corpus/dashboard/actions/catalog.py`
- `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py`
- `src/agentdecompile_recovery/corpus/dashboard/preparation.py`
- `src/agentdecompile_recovery/corpus/dashboard/protection.py`
- `src/agentdecompile_recovery/corpus/dashboard/capability_continuation.py`

Every unit below that would otherwise touch one of these calls its existing entry point (an action row, a job launch, a preparation stage, a continuation call) instead of editing the file.

### Hot-reload constraints (served tree; jurigged)

- New callables in `src/agentdecompile_recovery/corpus/dashboard/**` carry no type annotations and no default-value changes on existing signatures.
- No signature changes to existing functions in the hot-reloaded tree.
- No module-level statement changes in hot paths (module-level code runs once at import; changing it does not take effect until a full restart, and can desync state).

### Tests-last constraint

No test files are created or modified during Phase A-E units. Verify each unit with inline commands (Python heredocs against a temp corpus DB, `curl` against the running 8080 server, the real CLI, browser checks against the Vite dev server) and log the command sequence in the unit's own work. Phase F's U30 writes the test files listed in each unit's Files field, sourced from the most-run verification sequences.

---

## Implementation Units

### Unit Index

| U-ID | Title | Files touched | Depends on |
|---|---|---|---|
| U1 | Landed: pipeline-trigger removal | `static/workbench-app.js`, `static/explorer-page.js` | — |
| U2 | Remove remaining quick actions + R7 check | `static/actions.js`, `src/agentdecompile_cli/registry.py`, `src/agentdecompile_cli/mcp_server/program_metadata.py` | U1 |
| U3 | Per-call locator scoping | `src/agentdecompile_recovery/corpus/dashboard/mcp_bridge.py` | — |
| U4 | Multi-project session support | `src/agentdecompile_recovery/corpus/ghidra_project.py` | U3 |
| U5 | Admission on open/register | `src/agentdecompile_recovery/corpus/dashboard/workbench.py` | — |
| U6 | CodeBrowser provider build-out | `src/agentdecompile_recovery/ghidra_db/*`, dashboard panels | — |
| U7 | Project-as-tab layer | `static/workbench-app.js`, `static/workbench.js` | U4, U5 |
| U8 | Cross-build map dock | `static/workbench-app.js`, dashboard panels/callgraph.py | U6, U7, U27 |
| U9 | BSim hit persistence | `src/agentdecompile_recovery/corpus/match_store.py`, new `bsim_hit` schema | — |
| U10 | X channel C++/RTTI metadata | `src/agentdecompile_recovery/corpus/match_store.py`, `features.py` | — |
| U11 | Relabel P-code skeleton stage | `src/agentdecompile_recovery/corpus/match_store.py`, `channel_confidence.py` | — |
| U12 | Wire contract veto | `src/agentdecompile_recovery/corpus/identity.py` or `propagate.py`, `contract_features.py` | — |
| U13 | Match row kind/confidence/algorithm columns | `src/agentdecompile_recovery/corpus/propagate.py`, schema migration | U11 |
| U14 | Per-pair/function availability surface | dashboard panels/callgraph.py, `static/workbench-app.js`, `frontend/src/workstation` | U9, U10, U12, U13 |
| U15 | Config precedence resolver | `src/agentdecompile_cli/server.py` | — |
| U16 | Wire resolver into rewrite + LLM-cleanup paths | `src/agentdecompile_recovery/frontdoor.py`, `rewrite_provider.py`, `plugin_pipeline.py`, `corpus/llm_cleanup.py`, `corpus/cli.py`, `corpus/ghidra_bulk.py`, `autonomy_budget.py`, `autonomous_policy.py` | U15 |
| U17 | Dashboard AI setting | `src/agentdecompile_recovery/corpus/dashboard/settings_page.py`, `router.py` | U15 |
| U18 | objdiff-web main view | `frontend/src/workstation/CompareView.tsx`, `views/DiffEvidence.tsx`, `integration/boundaries.ts` | — |
| U19 | decomp.me scratch view | `frontend/src/scratch/ScratchWorkspace.tsx` | U18 |
| U20 | Dogbolt compare view | `frontend/src/workstation/` (new component) | U18 |
| U21 | RzWeb/r2web expert views | `frontend/src/workstation/` (new component) | U18 |
| U22 | APKMan container tree | `frontend/src/workers/artifactParser.worker.ts`, `runtime/localProject.ts` | — |
| U23 | Pipeline stage DAG | `frontend/src/PreparationActivity.tsx`, `activity.ts` | — |
| U24 | Lane E fleet roster | `frontend/src/workstation/MatchReview.tsx` | U7, U14 |
| U25 | Spectator view | `frontend/src/workstation/WorkstationApp.tsx` (new read-only mode) | U18 |
| U26 | report.json generation | `src/agentdecompile_cli/mcp_utils/decomp_match.py`, new report generator module | — |
| U27 | Tier-split progress bar | `static/workbench-app.js`, `frontend/src/Surfaces.tsx` (or its live successor) | U26 |
| U28 | Count-reconciliation gate | `src/agentdecompile_recovery/corpus/export_run_report.py`, new reconciliation module | U26 |
| U29 | Explicit publish step | dashboard action row (new, catalog-compatible), router.py | U28 |
| U30 | Write tests from verification sequences | test files listed per unit above | U1-U29 |

### U1. Landed: pipeline-trigger removal

**Goal:** Record the already-landed baseline so later units build on it without re-doing it.

**Requirements:** R1, R4, R8

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`, `src/agentdecompile_recovery/corpus/dashboard/static/explorer-page.js`

**Approach:**
- Commit `af761fe` already removed every pipeline-stage trigger from `workbench-app.js` and `explorer-page.js`, and added pause/resume/stop through the `workbench.workflow-control` action.
- This unit's only work is verification: confirm the commit is on the branch this plan builds from, and confirm no later commit reintroduced a trigger.
- The residual gap this commit left — `static/actions.js` still lists `corpus.ghidra-bulk`/`cross-place`/`propagate-source`/`logical-build`/`run` quick actions — is U2, not this unit.

**Test scenarios:**
- Test expectation: none -- verification-only unit; U2's scenarios cover the remaining gap.

**Verification:** `git log --oneline | grep af761fe` shows the commit is present; `grep -n "onRun\|QUICK_ACTION_SETS.pipeline" static/workbench-app.js static/explorer-page.js` returns no pipeline-stage trigger.

---

### U2. Remove remaining quick actions and add the R7 enforcement check

**Goal:** Close the residual gap U1 left and make R7 a real backend check instead of a convention.

**Requirements:** R1, R7, R8

**Dependencies:** U1

**Files:** `src/agentdecompile_recovery/corpus/dashboard/static/actions.js`, `src/agentdecompile_cli/registry.py`, `src/agentdecompile_cli/mcp_server/program_metadata.py`

**Approach:**
1. Remove the `corpus.ghidra-bulk`, `cross-place`, `propagate-source`, `logical-build` and `run` quick-action entries from `static/actions.js`; route any still-needed low-level access through the expert command palette (R6).
2. Implement the R7 check using `registry._STATE_WRITING_TOOLS` (`src/agentdecompile_cli/registry.py`) and `mcp_server/program_metadata.py`, not `dashboard/actions/catalog.py` — `catalog.py` is owner-locked, and the task packet names these two files as the intended classification source.
3. The check classifies each static-surface action by whether it appears in `_STATE_WRITING_TOOLS`; a static action that writes pipeline state and is not one of R5's explicit edits fails the check.
4. Wire the check to run over the full static action inventory (`actions.js`, `workbench-app.js`, `explorer-page.js`) so a new pipeline trigger added later fails it.

**Test scenarios:**
- Happy path: run the check against the current `static/` tree after step 1; it passes with zero violations.
- Edge case: temporarily reintroduce a `corpus.ghidra-bulk` quick action in a scratch copy; the check flags it.
- Edge case: an R5 explicit edit action (rename, comment, bookmark) is correctly excluded from the violation list.

**Verification:** The check runs as a script against `static/actions.js`, `workbench-app.js`, `explorer-page.js` and reports zero violations; manually confirm the five removed quick actions are gone from the rendered palette.

---

### U3. Per-call locator scoping

**Goal:** Let two or more project peers read live state at the same time, which R15 and R18 need.

**Requirements:** R15, R18

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/corpus/dashboard/mcp_bridge.py`

**Approach:**
1. `mcp_bridge.py:20-26` holds `CONTEXT_LOCK` and a single global `_ACTIVE_LOCATOR`, serializing every live read behind one process-wide lock.
2. Scope the locator per (project, binary) pair instead of globally: replace the single global with a dict keyed by that pair, each entry holding its own lock.
3. Keep a narrow global lock only around the dict's own mutation (insert/remove an entry), not around the read itself.
4. Confirm this file is not in the owner-locked list before editing (it is not — only `catalog.py`, `jobs.py`, `preparation.py`, `protection.py` and `capability_continuation.py` are locked).

**Test scenarios:**
- Happy path: two peers in different projects issue concurrent live reads; both complete without blocking on each other.
- Edge case: two peers in the *same* project and binary issue concurrent reads; they still serialize correctly (no corrupted read).
- Error path: a locator for a project/binary pair that was never registered raises the existing not-found behavior, not a new error.

**Verification:** A scripted concurrent-read check (two threads, two distinct project/binary pairs) completes without deadlock or serialization; single-pair behavior is unchanged from before the change.

---

### U4. Multi-project session support

**Goal:** Stop hiding all but one open project so R15's peer model can hold across projects, not just within one.

**Requirements:** R15, R18

**Dependencies:** U3

**Files:** `src/agentdecompile_recovery/corpus/ghidra_project.py`

**Approach:**
1. `ghidra_project.py:1445` `_dedupe_project_sessions` collapses multiple open project sessions to one, which conflicts with a browser tab holding a project while other tabs hold others.
2. Change the dedupe key from "one session total" to "one session per project", so distinct projects keep distinct sessions while a duplicate open of the *same* project still dedupes.
3. Depends on U3's per-pair locator scoping being in place first, since multiple live sessions now need to read concurrently.

**Test scenarios:**
- Happy path: open project A in one tab and project B in another; both sessions stay live and readable.
- Edge case: open project A twice (two tabs, same project); the existing dedupe-to-one behavior still applies within that project.
- Integration: a peer read in project A's tab does not disturb project B's session state.

**Verification:** Manual two-tab check against the running dashboard: both projects' peers show live (not blocked) state at the same time.

---

### U5. Admission on open and register

**Goal:** Make R2's "three events admit work" true for open and register, not only add-to-project.

**Requirements:** R2, R3

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/corpus/dashboard/workbench.py`

**Approach:**
1. `workbench.py:1131-1135` admits prepare work only when a binary is added to an open project; `registerLocator` and plain `open` do not admit.
2. Extend the same admission call to fire on `registerLocator` and `open`, guarded by the existing "has receipts, don't redo" check R2 already requires.
3. `workbench.py` is not in the owner-locked list, so this is a direct edit, not a call-through.
4. Respect the hot-reload constraint: no signature change to the existing admission function; add the new call sites, not a new parameter.

**Test scenarios:**
- Happy path: open a project whose binary has no analysis receipts; the admission receipt (R3) appears without a separate action.
- Happy path: register a new locator; the same admission fires.
- Edge case: reopen a project whose binaries already have receipts; no new admission fires, and no duplicate run starts.

**Verification:** Open a fixture project with a not-yet-analyzed binary; confirm the one-line admission receipt (run, generation, queue position) appears within the same request/response cycle as the open.

---

### U6. CodeBrowser provider build-out

**Goal:** Deliver the CodeBrowser providers R10 requires, including the four ghidra_db readers the task packet flags as missing.

**Requirements:** R9, R10, R11, R13

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/ghidra_db/*` (readers), relevant `src/agentdecompile_recovery/corpus/dashboard/panels/*.py` and `static/workbench-app.js` provider wiring

**Approach:**
1. `ghidra_db` already has readers for symbols, functions, comments, memory blocks and composite data types. It has none for Equates, Relocations, Bookmarks or Defined Strings — add four readers following the existing readers' pattern (`ghidra_db/program.py`, `store.py`).
2. Wire each new reader into its CodeBrowser provider panel: Equates, Relocations, Bookmarks, Defined Strings.
3. For the providers that already have partial coverage (Listing as `<pre>` text, per JTBD-3 research), rebuild as a structured field-per-row view: address, bytes, mnemonic, operands, cross-reference and comment fields, with a function header (R10's Listing requirement).
4. Every provider here is read-only (R11) except where R5 already names an explicit edit action (rename, comment, bookmark, retype); wire those through the existing edit actions, not through a new write path in the provider itself.
5. Function Graph, Function Call Trees, Call Graph, Functions table and Memory Map reuse the existing call-graph and function-table backend endpoints; this unit's new work is the four missing readers and the Listing rebuild.

**Test scenarios:**
- Happy path: open a binary with equates, relocations, bookmarks and defined strings; each provider renders real data, not an empty panel.
- Happy path: the rebuilt Listing shows address/bytes/mnemonic/operands/xref/comment columns and a function header for a known function.
- Edge case: a binary with none of one data kind (for example, no bookmarks) shows an empty state, not an error.
- Integration: selecting an address in the Listing updates the Bytes and Defined Strings providers per R12 (tested fully in U7/U8, but this unit's providers must expose the hook).

**Verification:** Each of the seventeen R10 providers renders real backend data for a fixture binary; the four new readers pass a round-trip read against a binary known to carry equates/relocations/bookmarks/strings.

---

### U7. Project-as-tab layer

**Goal:** Make a browser tab hold a project with its binaries as peers on one shared cursor (R15-R18).

**Requirements:** R15, R16, R17, R18

**Dependencies:** U4, U5

**Files:** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`, `src/agentdecompile_recovery/corpus/dashboard/static/workbench.js`

**Approach:**
1. The existing `wb-sessions` tab strip (`workbench-app.js:5549-5614`) already gives "one tab per open project"; keep it as the outer tab layer.
2. Replace `renderEditorBody`'s single active-pane model (`workbench-app.js:4848-5422`, "one pane at a time, switched by `centerTab`") with a peer-lane layout: every binary in the project renders as a lane inside the tab, not behind a `centerTab` switch.
3. Each peer lane shows its readiness state (readable / loading / blocked, with the backend's named next step for blocked) per R16.
4. Selecting a function in one peer looks up the shared identity binding and aligns bound peers to it; an unbound peer renders "no identity binding" rather than an empty lane (R17).
5. Peers not in focus render as light tracks (per the Key Decisions assumption); bringing a peer into focus expands its full provider set from U6.
6. This is the change that resolves the JTBD-4 conflict the research flagged between "one tab per project" and "one active program drives the cursor" — the project tab now holds the peers, and the cursor is shared, not switched.

**Test scenarios:**
- Happy path: open a project with three binaries; all three render as peer lanes in one tab.
- Happy path: select a function bound in two of three peers; two align, the third reads "no identity binding" (AE4).
- Edge case: a project at the corpus's ninety-binary ceiling stays usable — peers out of focus render light, and bringing any one into focus works.
- Integration: a peer whose live read is blocked (server credentials required) shows the blocked state with the named next step, and does not block the other peers' lanes from rendering (R16, R25).

**Verification:** Manual check against a fixture multi-binary project: all peers visible at once, shared-selection alignment matches AE4's example, no lane silently disappears at the ninety-binary ceiling in a scaled fixture.

---

### U8. Cross-build map dock

**Goal:** Show the call graph and matcher together, on one selection, inside the project tab (R19-R23).

**Requirements:** R19, R20, R21, R22, R23

**Dependencies:** U6, U7, U27

**Files:** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`, `src/agentdecompile_recovery/corpus/dashboard/panels/callgraph.py`

**Approach:**
1. `panels/callgraph.py` already has the identity join needed to relate a function across builds; this unit adds the dock UI, not a new backend join.
2. Dock the cross-build map inside the CodeBrowser layout (Key Decision), not as the tab's landing view.
3. The matrix has one cell per build pair; a pair the donor scheduler never selected reads "not scheduled" (fed by U14's availability surface), distinct from a pair that ran and failed.
4. Match results render as marks at the function header in the Listing/Decompiler (from U6) and as edges on the call graph, for the function currently selected via U7's shared cursor.
5. Review (R22) reuses the existing match-review paging and batch-decision contract (`match_review.py`, `dashboard/actions/match_review.py`) — this unit is the display and batch-selection UI over that existing contract, not a new review backend.
6. Byte-level (object comparison) and name/signature/call-graph matches keep visually distinct labels (R23) — reuse the `kind` column U13 adds rather than inferring the label from evidence JSON.

**Test scenarios:**
- Happy path: select a function present in three builds; the map shows callers/callees across builds with match edges, and the matrix shows which pairs were compared (F2, AE5).
- Happy path: review a build pair's candidates; accept every candidate above a score band in one action (F3).
- Edge case: a byte-level match and a name-only match appear in the same review batch; their kind labels differ (AE6).
- Integration: the matrix's "not scheduled" cells match U14's donor-scheduling reason surface exactly — no cell is unexplained.

**Verification:** Manual check against a fixture multi-build project: F2 and F3's flows both complete as described; AE5 and AE6 hold on real matrix/review data.

---

### U9. BSim hit persistence

**Goal:** Make channel S (BSim) actually contribute, per KTD2.

**Requirements:** R27, R31

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/corpus/match_store.py`, new schema addition for a `bsim_hit` table

**Approach:**
1. `_fuse_bsim` (`match_store.py:308-375,686-705,947-977`) already implements the mutual-best-plus-significance rule against a `bsim_hit` table that no code creates or fills; the live corpus lacks it, so every pair records `skipped/missing_bsim_hit_table`.
2. Add the `bsim_hit` table (schema: at minimum function address, BSim database id, candidate address, significance, self-significance — match the fields `_fuse_bsim` already reads).
3. Populate it from the existing Ghidra BSim ingest/preparation stage (`dashboard/preparation.py`'s BSim stage is owner-locked — call its existing output path, do not edit `preparation.py` itself; if the stage does not currently write a queryable result, add a small writer module outside the locked file that consumes what the stage already produces).
4. `_fuse_bsim` itself needs no logic change — it already implements KTD2's rule; this unit only makes its input exist.

**Test scenarios:**
- Happy path: a project with a populated BSim database and the new `bsim_hit` table; `_fuse_bsim` produces `kind=bsim` verify rows where mutual-best-plus-significance holds.
- Edge case: BSim database present but the significance threshold (30.0) is not met for any pair; no row is forced, and the skip reason changes from `missing_bsim_hit_table` to a threshold-specific reason.
- Edge case: BSim database entirely absent; the pair still records `unavailable`, not a crash, and matching still completes on the other channels (R27).

**Verification:** Query the corpus DB after a matching run on a fixture project with a populated BSim database; confirm rows with `kind=bsim` exist where expected, and `skipped/missing_bsim_hit_table` no longer appears when the table is populated.

---

### U10. X channel C++/RTTI metadata

**Goal:** Give channel X the C++/RTTI/vtable/dispatch metadata the plan's own channel legend already claims it carries.

**Requirements:** R27, R32

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/corpus/match_store.py`, `src/agentdecompile_recovery/corpus/features.py`

**Approach:**
1. Today `match_store.py:502-503` seeds channel X anchors from unique strings and constants only; no RTTI, vtable or C++ dispatch metadata exists anywhere in `match_store.py` or `features.py`.
2. Add extraction of C++/RTTI/vtable metadata as a new feature source (mirroring the existing string/constant anchor pattern in shape: extract once, persist, seed `unique_index_anchors` only when unique).
3. Feed the new metadata into the same X-channel seeding path `match_store.py:502-503` already uses, so it becomes one more anchor source under the existing channel, not a new channel.
4. Until this unit lands, U14's availability surface must show X as partial (metadata subset only) rather than implying full coverage — coordinate the wording with U14.

**Test scenarios:**
- Happy path: a binary with distinguishable RTTI/vtable structures produces new X-channel anchors from that metadata, in addition to the existing string/constant anchors.
- Edge case: a binary with no C++ metadata (pure C) falls back to the existing string/constant behavior unchanged.
- Integration: the new anchors go through the same uniqueness/margin rules as existing X-channel anchors — no new acceptance path is introduced.

**Verification:** Run matching on a fixture binary pair with known C++ vtables; confirm new anchors trace to RTTI/vtable metadata (not just strings) in the evidence JSON.

---

### U11. Relabel the P-code skeleton stage

**Goal:** Stop scoring the P-code/decompiler-skeleton stage with BinDiff's base score under a shared `M` label.

**Requirements:** R27, R33

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/corpus/match_store.py`, `src/agentdecompile_recovery/corpus/channel_confidence.py`

**Approach:**
1. `match_store.py:661-682` tags the P-code skeleton exact-fingerprint stage with `primary_channel='M'`, `kind=structural`, `stage=pcode_il_ast`; `channel_confidence.py:23-24` scores `M`/bindiff at base 66, so this stage inherits BinDiff's score though it is not BinDiff.
2. Add a new `primary_channel` value (for example `'K'` or `'pcode'`) distinct from `'M'`, used only by this stage.
3. Add its own base score in `channel_confidence.py`'s `BASE` table, distinct from `M`'s 66 — pick the value from where the stage actually sits in the cascade (after CFG/SPP, before BSim and fuzzy scoring, per research), roughly between `G`'s 72 and `S`'s 68.
4. Backfill existing `match` rows written with `primary_channel='M'` and `stage='pcode_il_ast'` to the new value, so historical data does not silently misreport as BinDiff.
5. Update `docs/dashboard-design/pipeline-diagram/generate_pipeline_diagram.py` so the diagram's channel legend matches (execution precondition already named in Planning Contract).

**Test scenarios:**
- Happy path: a fresh P-code skeleton match writes the new `primary_channel` value, not `'M'`.
- Happy path: `channel_confidence.py` scores the new channel with its own base, not 66.
- Edge case: an existing row with `primary_channel='M'`, `stage='pcode_il_ast'` is backfilled correctly and does not double-count as both M and the new channel.
- Regression: a true BinDiff/BinExport match (channel M, no `pcode_il_ast` stage) is unaffected — still scores at base 66.

**Verification:** Run matching on a fixture pair that exercises both the P-code skeleton path and a real BinExport/BinDiff import; confirm they now carry distinct `primary_channel` values and distinct base scores.

---

### U12. Wire the contract veto

**Goal:** Give the ABI/contract veto a production caller so R34 holds.

**Requirements:** R27, R34

**Dependencies:** none

**Files:** `src/agentdecompile_recovery/corpus/identity.py` or `src/agentdecompile_recovery/corpus/propagate.py` (whichever owns the actual best/runner-up selection point — confirm during implementation), `src/agentdecompile_recovery/corpus/contract_features.py`

**Approach:**
1. `_contract_veto` (`match_store.py:389,707-760,850-873`) already handles the best/runner-up pair correctly (drops a lone `Unwind@` hard negative, vetoes `ret_cleanup` incompatibility, keeps or promotes the survivor under review) but has no caller passing `contract_features` in `identity.py`, `propagate.py` or `evaluate.py`.
2. Add the call at the point the best/runner-up pair is chosen, passing `contract_features` from the same source `_contract_veto` already expects.
3. Keep it opt-in behind a flag (KTD4) until the existing high-score-tie cases (research found two ties at 0.99 and 0.98 that stay ambiguous today because the matcher cannot see contract differences) are checked against the new veto's output.
4. Flip the flag to default-on only after that check passes; record the check's result in this unit's verification, not as a separate follow-up.

**Test scenarios:**
- Happy path: a known high-score tie with an incompatible calling contract resolves instead of staying ambiguous, once the flag is on.
- Edge case: a lone `Unwind@` hard negative is dropped as designed, not treated as a tie-breaker.
- Regression: a tie with *compatible* contracts on both sides is unaffected — still resolves (or stays ambiguous) exactly as before the veto was wired.

**Verification:** Re-run matching on the fixture pair(s) that produced the 0.99/0.98 ties found in research; confirm the veto resolves them once contract features differ, and leaves them ambiguous when contracts genuinely match.

---

### U13. Match row kind/confidence/algorithm columns

**Goal:** Let review and the availability display filter and sort without parsing evidence JSON.

**Requirements:** R22, R27, R29

**Dependencies:** U11

**Files:** `src/agentdecompile_recovery/corpus/propagate.py`, a schema migration for the `match` table

**Approach:**
1. Today the `match` table has `id, run, src/dst binary+addr, score, margin, evidence TEXT, status, relation, src_end, dst_end`; `kind`, `primary_channel`, `channels`, `status_band` and `alternatives` live only inside the `evidence` JSON blob, which `propagate.py:74-77,114-120,258-261` already writes.
2. Add three columns to `match`: `kind`, `confidence` (numeric, already computed by `channel_confidence.py`), `algorithm` (the `primary_channel` value, post-U11's relabel).
3. Populate them at write time in `propagate.py`, from the same values it already puts into the evidence JSON — this is a column promotion, not a new computation.
4. Backfill existing rows from their evidence JSON in one pass.
5. This depends on U11 landing first so `algorithm` reflects the post-relabel channel values, not the pre-relabel conflated ones.

**Test scenarios:**
- Happy path: a fresh match row has `kind`, `confidence` and `algorithm` populated and matching the same values in its evidence JSON.
- Edge case: a backfilled historical row's new columns match what its evidence JSON already said.
- Integration: review UI (U8) can filter/sort on the new columns without touching evidence JSON.

**Verification:** Query the `match` table after a fresh run and after backfill; spot-check ten rows' new columns against their evidence JSON for exact agreement.

---

### U14. Per-pair and per-function availability surface

**Goal:** Show, for any pair or function, which methods ran, skipped (with reason), are unavailable, or are not built — in both frontends.

**Requirements:** R27, R28, R30

**Dependencies:** U9, U10, U12, U13

**Files:** `src/agentdecompile_recovery/corpus/dashboard/panels/callgraph.py`, `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`, `frontend/src/workstation/coverageMatrix.tsx` (or its live successor)

**Approach:**
1. Build a per-pair, per-function availability response from KTD1's five-state enum, reading the skip-reason strings already written by each channel's code path (`match_store.py:1027` for M, `:1028` for D, `:1030` for embeddings/AI, plus U9's new BSim reasons and U10/U12's new not-built-until-landed reasons where those units have not yet shipped).
2. Surface it in the static dashboard's cross-build map (U8) at the matrix-cell level (R30: "not scheduled" vs. failed) and at the per-function channel-row level (R28).
3. `coverageMatrix.tsx` already renders one row per build for a logical identity but "openly says per-build locator status is not sent by the server" — this unit is the backend gap that component names; extend the server response it already consumes, not the component's rendering logic.
4. Surface the donor-scheduling reason (explicit pair, spanning-forest edge, hub-to-anchor link) alongside "not scheduled", reading `donor_schedule.py`'s existing `spanning_forest_pairs` output.

**Test scenarios:**
- Happy path: a function with BSim unavailable shows `unavailable: reason` for channel S while other channels show their real status (AE8).
- Happy path: a build pair the donor scheduler never selected shows "not scheduled" with its scheduling reason, distinct from a pair that ran and failed (AE5, R30).
- Edge case: a channel this plan has not yet landed (X's metadata subset before U10, or the veto before U12) shows `not-built`, not a false `unavailable` or `skipped`.
- Integration: the static dashboard (U8) and the Vite fleet roster (U24) read the same availability response and render consistent status for the same pair.

**Verification:** Load a fixture project with a known-unavailable BSim database; confirm the per-function channel row and the matrix cell both show correct, consistent status per AE8 and AE5.

---

### U15. Config precedence resolver

**Goal:** Implement one CLI > env > dashboard > default resolution for the AI toggle (KTD5).

**Requirements:** R35, R36, R38

**Dependencies:** none

**Files:** `src/agentdecompile_cli/server.py`

**Approach:**
1. Follow the existing work-exchange tri-state pattern exactly: `server.py:1085-1096` (flags in `build_proxy_parser`), `:1178-1193` (resolve + `os.environ` export), `:433-455` (`_set_env_from_args`, the generic CLI-to-env mapper).
2. Add a CLI flag (for example `--enable-targeted-ai`/`--no-enable-targeted-ai`, default `None`) to the 8080 server's argument parser, resolved against an env var (for example `AGENT_DECOMPILE_TARGETED_AI_ENABLED`), which is resolved against the dashboard setting file (U17), which falls back to compiled-default off.
3. Export the resolved value to `os.environ` so child jobs see the same decision, matching the existing pattern.
4. Both `agentdecompile-server` and `agentdecompile-proxy` mount the dashboard (`mcp_server/server.py:682-684`, `mcp_server/proxy_server.py:353-355`), so the resolver must run in both entry points, not only one.
5. This unit resolves the value; U16 wires it into the actual rewrite and LLM-cleanup call sites.

**Test scenarios:**
- Happy path: CLI flag set to enabled; effective value is enabled regardless of env or dashboard.
- Happy path: no CLI flag, env var set; effective value follows env.
- Happy path: no CLI flag, no env var, dashboard setting present; effective value follows dashboard.
- Edge case: none of the three set; effective value is the compiled default (off).
- Integration: resolved value is present in `os.environ` for a spawned child job.

**Verification:** Start the server with each precedence combination in turn (flag only, env only, dashboard only, none) and confirm the resolved value and its exported env var match KTD5's order.

---

### U16. Wire the resolver into the rewrite and LLM-cleanup paths

**Goal:** Make the resolved AI state actually gate stage-6 leftover recovery and the LLM-cleanup entry points, and fix the 0-vs-1 default drift.

**Requirements:** R35, R38

**Dependencies:** U15

**Files:** `src/agentdecompile_recovery/frontdoor.py`, `src/agentdecompile_recovery/rewrite_provider.py`, `src/agentdecompile_recovery/plugin_pipeline.py`, `src/agentdecompile_recovery/corpus/llm_cleanup.py`, `src/agentdecompile_recovery/corpus/cli.py`, `src/agentdecompile_recovery/corpus/ghidra_bulk.py`, `src/agentdecompile_recovery/autonomy_budget.py`, `src/agentdecompile_recovery/autonomous_policy.py`

**Approach:**
1. Today six entry points disagree: `frontdoor.py` defaults the rewrite budget to 0 (disabled); `autonomy_budget.py:21-26` defaults `DEFAULT_MAX_REWRITE_REQUESTS_PER_FUNCTION` to 1 with a comment against 0; `autonomous_policy.py:223-227` falls back to `or 0`; `ghidra_bulk.py --llm-cleanup` defaults `True`; `corpus/cli.py run --llm` defaults off; the rewrite-worker skill says the default is 1.
2. Make U15's resolved value the single source of truth for whether targeted AI runs at all; keep the *budget* (how many rewrite requests per function) as a separate, still-tunable number that only takes effect when the resolved state is enabled.
3. Reconcile the drift: set every entry point's off-state to mean the same thing (targeted AI does not run), and every on-state to use the same default budget — pick `autonomy_budget.py`'s existing `DEFAULT_MAX_REWRITE_REQUESTS_PER_FUNCTION = 1` as that shared default, since it already carries a documented rationale against 0.
4. `workflow.py`'s hard-coded `'autonomous': True` for leftover-recover stays — that flag means "run leftover recovery," not "run the AI rewrite." Gate the *rewrite* call inside that path on U15's resolved state, not on removing the `autonomous: True` flag.
5. `rewriteFulfillment`'s dead `'queue'` context switch (`plugin_pipeline.py:544`) stays dead — it is out of this plan's scope; do not wire it as part of this unit.
6. The MCP recovery provider (`mcp_server/providers/recovery.py:78-80,153,165`) reads the same resolved state so MCP-triggered runs match dashboard-triggered runs.
7. R38: confirm the deterministic path (compile, repair via supported helpers, propagate, verify) has no code path that branches on the AI state except the rewrite/LLM-cleanup call sites themselves.

**Test scenarios:**
- Happy path: resolved state enabled, default budget; a leftover-recovery run that previously never reached `rewrite_provider.fulfill_rewrite` now reaches it.
- Happy path: resolved state disabled; `corpus run --llm`, `ghidra-bulk --llm-cleanup` and the in-process rewrite path all skip, and `leftover-recover.json` records `ran=false` with a reason naming the operator-disabled state (not a generic "opt-in" message).
- Edge case: MCP-triggered recovery (`autonomous` provider default false) still follows the same resolved state as a dashboard-triggered run.
- Regression: the deterministic path (compile/repair/propagate/verify) produces identical output whether AI is enabled or disabled, when no AI proposal is actually needed (R38).

**Verification:** Run leftover recovery once with the resolved state enabled and once disabled, on the same fixture binary; confirm the enabled run reaches the rewrite provider and the disabled run does not, and confirm the deterministic-only parts of both runs produce identical output.

---

### U17. Dashboard AI setting

**Goal:** Give the operator a dashboard control for the AI toggle, applying live per KTD6.

**Requirements:** R36, R37

**Dependencies:** U15

**Files:** `src/agentdecompile_recovery/corpus/dashboard/settings_page.py`, `src/agentdecompile_recovery/corpus/dashboard/router.py`

**Approach:**
1. Follow the existing notifications settings pattern exactly: `router.py:130-165` and `settings_page.py:10` already implement `GET`/`POST /dashboard/api/settings/notifications`, reading/writing a JSON file under `AGENT_DECOMPILE_CORPUS_WORK_DIR`, read fresh on every call.
2. Add `GET`/`POST /dashboard/api/settings/ai` following the same shape.
3. Render the effective value and its source (`server flag` / `environment` / `dashboard` / `default`) wherever the AI state is shown — the dashboard settings panel itself, and the stage-6 activity dock entry from U8/U24.
4. Name the CLI flag's restart-only limit explicitly in the UI text next to the effective-value display (R37).

**Test scenarios:**
- Happy path: set the dashboard AI setting; the next job (not a running one) picks up the change without a server restart.
- Happy path: the settings panel shows the correct source label for each of the four precedence states.
- Edge case: the dashboard setting is overridden by a higher-precedence CLI flag; the UI shows the CLI flag as the source, not the dashboard value the operator just set (KTD5's precedence, surfaced honestly).

**Verification:** Toggle the dashboard setting with no CLI flag or env var set; confirm the next job picks up the new state and the UI shows `source: dashboard`; then set an env var and confirm the UI now shows `source: environment` even though the dashboard file still holds the old value.

---

### U18. objdiff-web main view

**Goal:** Deliver an objdiff-web-first main view in the Vite workstation (R39).

**Requirements:** R39

**Dependencies:** none

**Files:** `frontend/src/workstation/CompareView.tsx`, `frontend/src/views/DiffEvidence.tsx`, `frontend/src/integration/boundaries.ts`

**Approach:**
1. `CompareView.tsx` today reads `GET {API}/function` and renders only recorded mismatch lists and receipts, with no live diff; `DiffEvidence.tsx` is a flat summary/address/expected-actual/histogram list. Neither has objdiff-web's instruction-aligned two-column rendering, register highlighting or symbol tree — this is net-new work, not a reskin.
2. Build the two-column instruction-aligned diff as a new rendering mode inside `CompareView`, reusing `integration/boundaries.ts`'s existing `MatchPhase` state machine and `parseMatchPayload` (schema `agentdecompile.workbench-match-candidate.v1`) for the underlying data — do not invent a second match-payload schema.
3. Before this lands, move `integration/boundaries.ts`'s `MatchPhase` type import out of the dead `matching/MatchingWorkspace.tsx` (research flagged this as a needed pre-step before the dead roots can be deleted) — relocate the type to `integration/boundaries.ts` itself or a shared types module.
4. Add register highlighting and a symbol tree as new sub-components; source symbol data from the same backend endpoints U6's providers use.

**Test scenarios:**
- Happy path: a function with recorded mismatches renders as a two-column instruction-aligned diff with register differences highlighted.
- Happy path: clicking a mismatch in the diff navigates the symbol tree to the relevant symbol.
- Edge case: a function with `objdiff-verified` status (per `boundaries.ts`'s existing consistency check: differences==0, objdiffExit==0, matching revisions) renders as a clean match, not a diff view.
- Regression: `MatchPhase`'s relocation out of `MatchingWorkspace.tsx` does not break `ScratchWorkspace`'s existing use of the same type (checked again in U19).

**Verification:** Load a fixture function with known mismatches in the Vite dev server; confirm the two-column diff renders correctly and matches `boundaries.ts`'s phase classification.

---

### U19. decomp.me scratch view

**Goal:** Extend the live scratch workflow into a full decomp.me-style view (R40).

**Requirements:** R40

**Dependencies:** U18

**Files:** `frontend/src/scratch/ScratchWorkspace.tsx`

**Approach:**
1. `ScratchWorkspace.tsx` is already live in the Matching tab: it stores scratches locally (`scratch/records.ts`), supports preset/target/revision binding, runs compile+objdiff via `workbench.match-candidate`, and watches the job via `boundaries.ts`.
2. This unit extends its layout and iteration UX toward decomp.me's shape (side-by-side source/target, live recompile-on-edit feedback) without changing its underlying action or schema.
3. Reuse U18's two-column diff rendering for the scratch's compile-result display, so both views share one diff component.

**Test scenarios:**
- Happy path: create a scratch bound to a known preset/target/revision; edit source, trigger compile+objdiff, see the result in U18's diff component.
- Edge case: a scratch with no bound preset shows a clear "no target selected" state rather than a failed compile.
- Integration: the scratch's job polling still uses the existing `/api/v1/jobs/{id}` contract unchanged.

**Verification:** Create and iterate a scratch in the Vite dev server; confirm compile+objdiff results render through the shared diff component from U18.

---

### U20. Dogbolt compare view

**Goal:** Add a Dogbolt-style multi-decompiler compare view, licensed-local-only (R41).

**Requirements:** R41

**Dependencies:** U18

**Files:** `frontend/src/workstation/` (new component)

**Approach:**
1. Research found no existing component for this — it is net new.
2. Build a side-by-side multi-decompiler output view, sourcing each decompiler's output from optional licensed local runners configured by the operator; never call or upload to the public Dogbolt service (R41, Scope Boundaries).
3. Reuse U18's diff rendering primitives for aligning outputs where useful, but this view compares *decompiler outputs* to each other, not to a ground truth — keep it a distinct component from `CompareView`.
4. Gate the view entirely on whether at least one licensed local runner is configured; render an explicit "no local decompiler runner configured" state otherwise, never a silent empty panel.

**Test scenarios:**
- Happy path: two configured local runners produce side-by-side output for the same function.
- Edge case: no runner configured; the view shows the explicit unconfigured state, not an error or empty panel.
- Regression: no network call to any public Dogbolt endpoint occurs, confirmed by inspecting outbound requests during a test session.

**Verification:** Configure one local runner in a fixture environment; confirm output renders and confirm (via network inspection) zero calls to any public Dogbolt host.

---

### U21. RzWeb/r2web expert views

**Goal:** Add RzWeb/r2web-style expert views behind the workstation's one normalized selection (R42).

**Requirements:** R42

**Dependencies:** U18

**Files:** `frontend/src/workstation/` (new component)

**Approach:**
1. Research found no existing component for this — net new.
2. Build the expert view(s) as consumers of the workstation's existing selection state (the same one `CompareView`, `ScratchWorkspace` and U6's providers read) — never introduce a second selection store, per R42 and the FRONTEND_INTENT §8 constraint research cited.
3. RzWeb is LGPL-3.0 licensed; if any RzWeb code or assets are reused rather than reimplemented against its data shapes, review the license obligation before merging (flag explicitly in this unit's PR description, not silently).

**Test scenarios:**
- Happy path: selecting a function in the Listing (or any other provider) updates the expert view to the same function, with no separate selection action needed.
- Edge case: a function with no disassembly data available (for example, a stripped region) shows an explicit empty state.
- License check: if any RzWeb source is reused, the license review is documented before merge; if none is reused, this scenario is not applicable.

**Verification:** Select a function in the Listing; confirm the expert view follows without a separate click, using the shared selection state.

---

### U22. APKMan container tree

**Goal:** Generalize a container/format tree view (R43).

**Requirements:** R43

**Dependencies:** none

**Files:** `frontend/src/workers/artifactParser.worker.ts`, `frontend/src/runtime/localProject.ts`

**Approach:**
1. Reuse the existing `workers/artifactParser.worker.ts` (container/format parsing) and `runtime/localProject.ts` (local container project handling) — research names these as the pieces to reuse for local container parsing.
2. Build the tree view as a new panel reading the parser worker's output; generalize the parser to any container/format it does not yet handle, following its existing provider pattern rather than adding a parallel one-off parser.
3. The hidden `Providers` tab and the unused `providers/registry.ts` `ProviderRegistry` (currently no importers) are candidate integration points — wire the container tree through that registry if it fits the existing provider contract, rather than bypassing it.

**Test scenarios:**
- Happy path: load a supported container format; the tree renders its structure using the existing parser worker.
- Edge case: an unsupported container format shows an explicit "format not supported" state, not a crash.
- Integration: the tree view registers through `providers/registry.ts` if that registry's contract fits; document the decision either way in the unit's PR.

**Verification:** Load a fixture container of a currently-supported format; confirm the tree renders correctly via the existing worker.

---

### U23. Pipeline stage DAG

**Goal:** Show stage dependencies as a DAG with edges, retrying only on failure (R44).

**Requirements:** R44

**Dependencies:** none

**Files:** `frontend/src/PreparationActivity.tsx`, `frontend/src/activity.ts`

**Approach:**
1. `StageTrace.tsx` has a fixed linear 6-stage placeholder but is dead (only `AtlasApp.tsx` imports it, and `AtlasApp.tsx` is itself dead) — do not resurrect it; build the DAG from the live components instead.
2. `PreparationActivity.tsx` is live: it polls `{API}/preparations` every 2s and posts `workbench.workflow-control`. `activity.ts`'s `EntityActivity.dependencies[]` is the only existing dependency data.
3. Extend `PreparationActivity` to render `dependencies[]` as DAG edges between stages, replacing the linear placeholder model entirely.
4. Retry is stage-scoped and fires only after that stage's own failure — reuse the existing `workbench.workflow-control` action for retry, never a manual per-stage run control (this is the same R1/R44 pipeline-owned-work constraint the static surface already enforces).

**Test scenarios:**
- Happy path: a project with stages that have real dependency edges renders them as a DAG, not a flat list.
- Happy path: a failed stage shows a retry control scoped to that stage; retrying re-triggers only that stage via `workflow-control`.
- Edge case: a stage with no dependencies renders as a root node with no incoming edges.
- Regression: no manual "run this stage" control exists anywhere in the DAG view (R1 still applies here).

**Verification:** Load a fixture project mid-pipeline with at least one failed stage; confirm the DAG renders real edges from `dependencies[]` and the retry control only appears on the failed stage.

---

### U24. Lane E fleet roster

**Goal:** Show donor/recipient decisions across a batch, reusing the match-review batch contract (R45).

**Requirements:** R45

**Dependencies:** U7, U14

**Files:** `frontend/src/workstation/MatchReview.tsx`

**Approach:**
1. `MatchReview.tsx` is already live: paged review via `GET {API}/match-review?after_id&limit`, batch decisions via `POST {API}/match-decide-batch` (202 + job polling), typed refusal codes. The static mirror in `workbench-app.js` reuses the same contract.
2. Build the fleet roster as a new view mode over the same `MatchReview` data and actions — one row per donor/recipient decision across the batch, not a new decision backend.
3. Pull per-row method availability from U14's surface so the roster shows, per row, which channels backed that decision.
4. Depends on U7 (project-as-tab, so the roster can scope to the project in view) and U14 (availability data).

**Test scenarios:**
- Happy path: a batch of pending decisions renders as a roster with donor/recipient pairs and their backing channels.
- Happy path: accepting a batch selection by build pair and score band works identically to the existing `MatchReview` batch action.
- Integration: a row's channel-availability display matches U14's per-pair surface for the same pair.

**Verification:** Load a fixture batch of pending review candidates; confirm the roster renders correctly and a batch accept produces the same job/refusal-code behavior as the existing `MatchReview` component.

---

### U25. Spectator view

**Goal:** Let a second viewer follow the operator's session read-only (R46).

**Requirements:** R46

**Dependencies:** U18

**Files:** `frontend/src/workstation/WorkstationApp.tsx` (new read-only mode)

**Approach:**
1. Research found no existing component for this — net new.
2. Add a read-only mode to `WorkstationApp` that subscribes to the same activity SSE stream (`activity.ts`'s `EventSource {API}/activity/events`) the operator's session already uses, and mirrors the operator's current selection without accepting any write action.
3. Disable every action-triggering control in this mode at the component level (not just visually) so a spectator session cannot issue a write even via direct API knowledge — this satisfies the same "no second selection or job store" constraint (FRONTEND_INTENT §8) the rest of the workstation follows.

**Test scenarios:**
- Happy path: a spectator session mirrors the operator's selection changes in near-real-time via the activity stream.
- Edge case: a spectator session attempts a write action (simulated at the component level); the action is disabled/no-op, not merely hidden.
- Integration: multiple spectators can follow the same operator session without conflicting with each other or the operator.

**Verification:** Open an operator session and a spectator session against the same project; confirm the spectator's view follows the operator's selection and that no write control is reachable in spectator mode.

---

### U26. report.json generation

**Goal:** Produce an objdiff-shaped `report.json` per binary and version from the corpus database (R47).

**Requirements:** R47

**Dependencies:** none

**Files:** `src/agentdecompile_cli/mcp_utils/decomp_match.py`, a new report-generator module

**Approach:**
1. `decomp_match.py` today only *consumes* an objdiff project's `report.json` (parsing `units[].measures.matched_percent`/`fuzzy_match_percent`, computing an unweighted mean). Nothing generates a corpus-shaped equivalent.
2. Add a new module that walks the corpus database for a given binary and version, and emits the same `units[].measures` shape `decomp_match.py` already parses — one schema for both directions (KTD7).
3. Keep the corpus-DB-to-report generation separate from `export_run_report.py`'s existing recovery-run-shaped export (`config.promptsDir`, `results[].postMatchPhase`) — that export answers a different question (run summary) and stays as-is; this unit's `report.json` is the objdiff-shaped progress artifact R47 asks for.
4. Weight the overall percentage by unit size to match objdiff/decomp.dev convention, correcting the existing unweighted-mean approach `decomp_match.py:183-184` uses for the *consumption* side (note this as a deliberate improvement over the existing consumer behavior, flagged for the consumer's own follow-up if it should also switch to weighted).

**Test scenarios:**
- Happy path: generate `report.json` for a fixture binary/version with known matched/fuzzy percentages; confirm the shape round-trips through `decomp_match.py`'s existing parser.
- Edge case: a binary with zero recovered units produces a valid (empty-but-well-formed) report, not an error.
- Integration: the size-weighted overall percentage differs correctly from an unweighted mean on a fixture with uneven unit sizes.

**Verification:** Generate `report.json` for a fixture binary; parse it back through `decomp_match.py`'s existing `_parse`/`_summarize_objdiff_report` functions and confirm no shape mismatch.

---

### U27. Tier-split progress bar

**Goal:** Show verified vs. advisory progress as separate segments in both UIs (R48).

**Requirements:** R48

**Dependencies:** U26

**Files:** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`, `frontend/src/Surfaces.tsx` (or its live successor component, since `Surfaces.tsx` itself is currently reachable only through the dead `App.tsx` root — confirm the live equivalent before editing)

**Approach:**
1. Reuse the existing tier vocabulary from `package_readable_index.py:23-32`: verified-byte-exact and advisory-ghidra, already documented as "never merged into a single recovered number."
2. Render `report.json` (U26) as a solid segment for verified and a hatched segment for advisory, per binary and version, in both the static dashboard's headline (`workbench-app.js`'s existing `CorpusHeadline` renderer) and the Vite workstation's equivalent live component.
3. Before editing `Surfaces.tsx`, confirm whether its progress-display responsibilities have moved to a live `WorkstationApp` sub-component (research flagged `Surfaces.tsx` as dead-root-only); if so, edit the live component instead and note the correction in this unit's PR.

**Test scenarios:**
- Happy path: a binary with both verified and advisory contributions renders two visually distinct segments summing correctly.
- Edge case: a binary with only advisory contributions (no verified) renders zero-width verified segment, not a missing bar.
- Regression: no code path merges the two tiers into one combined number anywhere in either renderer (AE14).

**Verification:** Load a fixture binary with mixed verified/advisory contributions in both UIs; confirm the tier split renders correctly and matches AE14.

---

### U28. Count-reconciliation gate

**Goal:** Fail closed before publishing when the accounting buckets do not exhaustively cover the inventory (R49).

**Requirements:** R49

**Dependencies:** U26

**Files:** `src/agentdecompile_recovery/corpus/export_run_report.py`, a new reconciliation module

**Approach:**
1. Implement KTD8's exhaustive-accounting design: mutually exclusive buckets — accepted source, candidate source, preserved region, unclassified, excluded-with-reason — each corpus member appears exactly once, byte extents unioned separately.
2. This closes the gap research found between disagreeing counts for the same corpus (a row-count sum, a stale per-binary receipt union under old rules, and the function-table denominator all disagreeing) — the gate's job is to catch exactly that kind of disagreement before it reaches a report.
3. Run the gate against `report.json` (U26) before any publish action (U29) is enabled; a failing gate blocks the publish action entirely, not just warns.
4. Fail with a named unreconciled count and the bucket(s) involved — never silently invent the missing count (KTD8's explicit rule).

**Test scenarios:**
- Happy path: a binary whose buckets exhaustively and exactly cover its inventory passes the gate.
- Happy path: a binary with a known undercounted bucket (fixture with a deliberately missing entry) fails the gate and names the gap.
- Edge case: a corpus member appearing in two buckets simultaneously (double-count) fails the gate with a distinct "not mutually exclusive" reason.

**Verification:** Run the gate against one fixture that reconciles cleanly and one that does not; confirm the pass/fail outcome and the named-gap message in the failing case (AE15).

---

### U29. Explicit publish step

**Goal:** Make publishing to decomp.dev its own approved step, never a side effect of generating `report.json` (R50).

**Requirements:** R50

**Dependencies:** U28

**Files:** a new dashboard action row (catalog-compatible, not added to the owner-locked `catalog.py` directly — follow the existing pattern for registering a new action outside that file, or route the addition through whatever the catalog's own extension point is), `src/agentdecompile_recovery/corpus/dashboard/router.py`

**Approach:**
1. Add a publish action that only runs after U28's gate passes for the target binary/version; the action itself requires an explicit operator confirmation (mirroring the existing dangerous-action confirm pattern research found in `catalog.py`'s `DANGEROUS_CORPUS`/`DANGEROUS_ARGV_FLAGS` handling, without editing that owner-locked file — call its confirm contract, don't duplicate its logic).
2. The action is disabled (not hidden) when the gate has not passed, with the gate's failure reason shown inline.
3. decomp.dev's own license is unestablished per `FRONTEND_INTENT.md`; this unit implements the gate-and-approve mechanism only — it does not implement the actual outbound network call to decomp.dev (Scope Boundaries: "Deferred to Follow-Up Work").

**Test scenarios:**
- Happy path: with a passing gate, the operator confirms publish; the action records the approval and (per Scope Boundaries) stops short of an actual outbound call until that follow-up work lands.
- Edge case: with a failing gate, the publish action is visibly disabled and shows the gate's failure reason (AE15).
- Regression: no code path reaches this action automatically as a side effect of `report.json` generation (R50).

**Verification:** Attempt publish with a failing gate (disabled, reason shown) and with a passing gate (confirmable, approval recorded) on fixture data; confirm neither path issues an actual outbound network call.

---

### U30. Write tests from verification sequences

**Goal:** Convert the most-run inline verification commands from U1-U29 into the repo's test suites.

**Requirements:** all (test coverage for R1-R50)

**Dependencies:** U1-U29

**Files:** test files under each touched component's existing test layout — for Python units, `tests/` paths mirroring `src/agentdecompile_recovery/corpus/test_match_store.py`-style existing conventions; for frontend units, `frontend/src/**/*.test.tsx` under Vitest, matching `package.json`'s existing `test` script.

**Approach:**
1. This is the only unit that creates test files (Planning Contract's tests-last constraint).
2. For each unit U1-U29, take the verification command sequence actually run during that unit's implementation (heredocs, curl calls, DB queries, browser checks) and convert the most-run ones into permanent tests.
3. Group by phase: Phase A/B (Python, pytest-style), Phase C (Python, config-resolution unit tests), Phase D (Vitest component tests), Phase E (Python, report/reconciliation tests).
4. Prioritize the acceptance examples (AE1-AE15) as integration-level tests, since they already name concrete inputs and expected outcomes.

**Test scenarios:**
- Test expectation: this unit's own scenarios are exactly its Approach — no additional meta-test layer is needed.

**Verification:** The repo's existing test command (`pytest` for Python, `npm run test` / `vitest run` for frontend, per `frontend/package.json`'s scripts) passes with the new tests included; AE1-AE15 each have at least one corresponding test.

---

## Verification Contract

| Area | Command | Applies to | Done signal |
|---|---|---|---|
| Python unit/integration tests | `pytest` (repo-standard invocation) | Phases A, B, C, E, F | All tests pass, including U30's additions |
| Frontend unit tests | `npm run test` (Vitest, per `frontend/package.json`) | Phase D, F | All tests pass |
| Frontend build check | `npm run build` (`tsc --noEmit && vite build`) — requires the user's explicit `npm install` permission first | Phase D | Build succeeds with no type errors |
| Static-surface action classification | The R7 check built in U2 | Phases A, B (any new action) | Zero violations |
| Backend static checks | repo-standard lint/type check for the touched Python modules | All Python-touching units | Passes |
| Manual browser verification | Load the running 8080 dashboard and the Vite dev server against fixture projects; walk F1-F7 and AE1-AE15 | All phases | Each flow completes as described; each AE holds |
| Anonymization check | `python3 /tmp/anon-added.py <repo> docs/plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md` | This plan document itself | Zero hits |

### Usability Test Plan

Per-slice, operator-run, mapped to Ghidra-guide chapters and the 2026-09-28 directives. Run each task against the delivered slice once its units land.

| Task | Guide chapters / directive | Delivered by | Success criterion |
|---|---|---|---|
| T1. Reopen a known project | ch.2, directive on resume | U5, U7 | Same selection and receipts return; no reanalysis job; no Start button (AE10) |
| T2. Find a class and open its struct | ch.4-5 | U6 | Fewer than three gestures; no destructive-action prompt (AE12) |
| T3. Step through a function in the Listing | ch.6-7 | U6, U7 | Per-instruction rows; clickable xrefs; Decompiler follows; Back restores the viewport |
| T4. Open the call graph and Match review for one entity side by side | ch.8, directive 2 | U8 | Both visible at once, one selection (AE13) |
| T5. Count pipeline-stage buttons | directive 1 | U1, U2 | Zero; only pause/resume/stop and the expert palette (AE11) |
| T6. Open a match candidate with BSim's database absent | directives 4, 5 | U9, U14 | Channel S shows `unavailable: reason`; other channels still decide; nothing is blocked (AE8) |
| T7. Toggle targeted AI via env, server flag and dashboard | directive 5 | U15, U16, U17 | Effective state and its source are shown each time; when off, stage 6 reads "disabled by operator" (AE9) |
| T8. Diagnose a residue case, then export | ch.15, export flow | U26, U27, U28 | Evidence-driven diagnosis; export/report discloses floor vs. unverified parts (AE14, AE15) |

Vite- and decomp.dev-specific tasks (multi-decompiler compare, spectator follow, publish approval) are verified separately per unit (U20, U25, U29) rather than folded into the 8080-scoped T1-T8 set, matching the JTBD research's own scope note.

---

## Definition of Done

- Every R1-R50 has at least one implementation unit and at least one verification path (unit test, AE, or usability task) that would fail if the requirement regressed.
- AE1-AE15 all hold against a running fixture environment (static 8080 and, where the AE is Vite-scoped, the Vite dev server).
- The R7 enforcement check (U2) runs clean over the full static action inventory, with no manual exception list.
- No owner-locked file (`catalog.py`, `jobs.py`, `preparation.py`, `protection.py`, `capability_continuation.py`) has a diff against its state at plan start.
- The hot-reload constraints hold: no changed function signature in the served dashboard tree, no new module-level statement in a hot path.
- U30 has landed: the test files named in the Verification Contract exist and pass.
- No dead-end or abandoned-approach code remains from units that changed direction during implementation (for example, if U27's target component turns out to be neither `Surfaces.tsx` nor a single successor, the unit's final PR contains only the component it actually edited, not scaffolding for a path not taken).
- `python3 /tmp/anon-added.py /home/brunner56/ad-wt/consolidation-20260928 docs/plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md` reports zero hits on this plan document.
- Every unit's Approach that cites an owner-locked file states which existing entry point it calls, not a proposed edit to that file.
