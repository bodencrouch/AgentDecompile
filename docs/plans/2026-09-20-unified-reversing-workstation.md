# Unified reversing workstation implementation plan

Spec: ../dashboard-design/2026-09-20-unified-workstation-spec.md

## Global Constraints

- Operate only the existing 8080 dashboard using playwright-cli; no curl,5174,
  systemctl, server restart, filesystem tests, test fixtures, or duplicate jobs.
- Preserve live K1 worker701843/job50f7fc81e7ab and server616810 while alive.
  Recheck authoritative state; these IDs are observations, not perpetual leases.
- Production edits are reviewed in the isolated worktree; activation is a
  separately verified selective transfer preserving NVMe and canonical changes.
- Existing native catalog, providers, coordinator and data owners remain the
  owners. No independent frontend scheduler, no fixed ABI guesses, no fake data.
- Opening/selecting a project must not automatically submit prepare/reanalysis.
- Maintain two user-facing alternatives over the same backend/state contract:
  the complete static HTML/CSS/JavaScript workbench on8080, and the optional full
  Vite application (standalone default5174 and packaged `/react/`). Do not reduce
  either to a fallback or preview, and do not add another backend, catalog, state
  owner or recovery scheduler. No5174 process is authorized for current recovery.
- Whole-image recovery remains incomplete until fresh compiler/objdiff proof.
- Validation in this session is read-only source/diff/syntax checking and
  permitted live browser interactions; report unverified behavior explicitly.

## Task 1: Make parameter storage genuinely editable

Own frontend/src/FunctionEditor.tsx under
src/agentdecompile_recovery/corpus/dashboard/ and at most one shared storage
editor/helper in that same frontend/src directory if needed to remove duplicate
return/parameter editor logic. Read current FunctionEditor and manage-function
set_storage provider contract. Runtime and isolated FunctionEditor currently
compare equal; no runtime deployment in this task.

Replace the misleading Edit parameter storage button, which submits unchanged
recorded storage, with a real draft editor. Reuse return-storage controls and
validation rather than duplicating register/stack/size rules. Users must edit
ordered register/stack pieces for a specific parameter, see errors and review
the resulting catalog action before mutation. Preserve ordinal, datatype,
customStorage=true, exact project/program/address selection and existing
onAction review semantics. Changing selected target must not submit old drafts
against the new target; use existing draft/conflict mechanisms. Invalid sizes,
unknown registers, incomplete pieces and non-integer stack offsets cannot be
submitted. Derive register availability/widths from server facts, not x86 lists.
Leave provider behavior unchanged unless a concrete contract defect is found
and escalated. Preserve existing return-storage functionality and readable
recorded values. No tests/builds/deploy; use read-only inspection and non-emitting
syntax/type checks only if available without writing artifacts. Commit only
owned production files, hooks disabled to honor no-tests. Report exact limits.

## Task 2: Reconcile delivery without collapsing either alternative

Use the delivery architecture report as source-inspection evidence, not as authority
to replace `/dashboard` or collapse the two frontends. NVMe main.tsx mounts
WorkstationApp with Vite base=/react/; isolated main.tsx mounts older App with a
different base. App/AtlasApp currently auto-submit prepare on selection changes.
Do not transplant those roots. Preserve WorkstationApp's explicit admission and
reuse its child CodeBrowser/GuideWorkflows/evidence surfaces for the optional Vite
application. Independently retain and complete the static8080 workbench. Produce a
reviewed file-by-file reconciliation, retaining session state and package routes.
No wholesale source sync and no shared-source requirement where it would erase a
required alternative.

## Task 3: Unify selection and navigation

Latest spec refinement: logical-entity-first selection across the shared project
codebase; concrete build/address context is a drill-down and mutation/proof target,
not the primary boundary of every view. Show counterparts, divergence, unmatched
and ambiguous instances together. Preserve multiple inspected builds and do not
pretend candidate identity implies accepted equivalence.

Use existing selection/workspace owners, program bindings and URL helpers.
Project/program/address context updates all panes, history and pipeline display;
stale responses cannot replace newer selection. Saved unavailable projects keep
their identity and recovery actions; no silent fallback. No automatic analysis.
Include deep links, navigation back/forward, data-address vs last-function state,
and selection restoration across a browser refresh.

## Task 4: Compose the primary Code Browser shell

Initial binary-first concept IA is superseded. Compose a corpus-first workspace
from revised references: shared logical entity navigation and multi-build
counterpart/difference inspection are fundamental, not a secondary Compare app.

Complete primary and narrow visual references before composition. Implement
project/program selector, one pipeline controller, Code Browser/Compare/Recovery/
Evidence navigation, synchronized Listing/Decompile and one inspector area.
No duplicate Functions sidebar or individual pipeline-stage launch buttons.
Reuse existing native components and tokens; no new parallel app root. Preserve
keyboard selection, filtering, bookmarks, symbols/types and accessibility.

## Task 5: Close guide interaction gaps

Use all16 rows in guide inventory as acceptance requirements. Add instruction
and data rows with addresses/bytes/operands/xrefs; listing/decompile navigation;
local-variable rename/type using existing provider; structure field editing
and vtable evidence inspection. Preserve function/custom-storage edits, template
instances, memory, bookmarks, advanced scripting/export and inference caveats.
No invented automatic fixes or generic ABI/layout constants.

## Task 6: Integrate all KotORXID analysis/evidence workflows

Use every implemented inventory row: corpus/build overview, function/logical
identity detail and search, sibling navigation, bounded call graphs, recovery,
variant and full-image evidence, candidate review, STABS, merged knowledge,
artifact/database browsing and operations. Retain bounded queries, provenance,
freshness, selection and deep links. Raw output is optional detail, not the main
UX. Identify missing backend support explicitly rather than inert controls.

## Task 7: Connect one durable pipeline controller

Feedback must show the operation, involved builds/entities, completed/remaining
work when known, outcomes, constraints and last observation. Spinner+Running is
insufficient. Place concise progress and changes in the relevant entity/build
rows, with stage/receipt details available on demand; no fabricated ETA/counts.

Latest user correction supersedes text-first status: primary feedback must draw
and animate the actual matching, source transformation, instruction comparison
and gated propagation. Instrument evidence-bound backend events where absent;
existing counters/logs are insufficient to invent those transitions. Reuse the
current activity/event owner rather than add a competing scheduler. Every visual
entity/change is inspectable; motion supports reduced-motion, pause/step/history.
See spec Show the work section. Statistics are secondary only.

Start/pause/resume uses the coordinator and backend resource admission. Display
selected program versus project-wide scope. Adopt/resume existing work only
with verified owner/input compatibility; never equate cancel with pause. The
current bulk job has mutating=false metadata despite write=true, so mutation
classification alone cannot prove admission safety. Retain cheap-first matching,
compile gates and full canonical recovery/failover policy. Poll/SSE updates must
remain accurate after refresh, disconnect, stale receipts and target switches.
Remove redundant manual stage launch affordances throughout normal GUI; keep
explicit expert data edits and diagnostic evidence accessible.

## Task 8: Package, activate and validate each delivery boundary

Reconcile source/build identity before selective activation; do not restart or
start/touch a5174 process during current recovery. Browser navigation cannot start
work. Maintain the existing worker, server, DB and receipts. Verify every
inventory/spec row on the static8080 alternative with current live evidence or
mark it incomplete; collect desktop/narrow screenshots and real interaction proof
through Playwright CLI. Separately, when authorized, verify the packaged `/react/`
entry and the full standalone Vite application against the same backend/state
semantics. Run independent per-task reviews and a final whole-change review. A
build, source presence or screenshot alone closes none of these runtime rows.

## Completion ledger

No implementation task is complete at plan creation. Bounded source discovery is
recorded separately; it is not exhaustive archive review or runtime acceptance.
Task1 is independent of delivery reconciliation; Tasks2–8 depend on source
reconciliation and reviewed interfaces, not invented UI functionality. This is
the full scope, not a promise that one editor fix or one frontend completes the
redesign. Current status and the prioritized remaining checklist are in
`../DELIVERY_STATUS.md`.
