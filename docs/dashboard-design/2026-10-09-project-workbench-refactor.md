# Project workbench refactor

This is a bounded implementation specification, not a living plan. Authority:
the user's October 9 dashboard instructions and docs/USER_INTENT.md.

## Global constraints

- Operate and verify the existing static dashboard on 8080, using Playwright CLI.
- Never run filesystem tests, create test files, use systemctl, restart 8080,
  touch 5174, duplicate recovery jobs, or alter existing Ghidra repository data.
- Preserve the dirty checkout and unresolved merges. Do not commit unrelated work.
- Each browser tab represents a project. Opening a project activates its existing
  tab or opens a new tab. Binary focus does not change project ownership.
- Views default to all member binaries across the open projects. Focus is a
  drill-in, never an implicit matching target or a replacement for scope.
- Expensive aggregation is user-triggered. BSim is optional. Stored evidence,
  runtime readiness and fresh byte-identical recovery remain distinct claims.

## Task 1: Shared project data and optional BSim

Add one read-only project-universe API deriving membership from existing project
sessions, inspected repositories and corpus bindings. Return projects, builds,
membership and recorded function/identity/recovery data, with bounded pagination.
Do not invent source bindings or silently include unrelated corpus binaries.
Expose optional BSim configuration through existing durable workspace settings;
an absent BSim database must not block any other matching method. Correct shared
root classification while preserving normal .gpr/.rep folder behavior.

## Task 2: Project tabs and every-view integration

Repair open/create/reopen/save-as tab identity and async races. Keep project
membership separate from optional build/function focus. Consume the shared
project-universe model across views, expose comparison before selecting a binary,
and use grouped functions and existing cross-build identity evidence for drill-in.
Consolidate duplicate navigation and controls while retaining command access.
Remove arbitrary cross-match target fallback. Place optional BSim settings below
the comparative results. Keep current chooser staging fix and handle cancellation,
failures and project changes safely. Audit every exposed view in the report.

## Task 3: Saving, synchronization and import completion

Investigate existing native save/check-in ownership and automate supported
progress checkpoints independently of browser selection. Serialize writers,
preserve provenance and expose actionable pending/error state. Do not claim
server synchronization without an observed native check-in. Finish the requested
swkotor import/protection path based on the actual detected protection and a
versioned non-executing unpacker, preserving the original binary.

## Latest visual priority: Task 2b before Task 3

The user's latest instruction supersedes the broad normal-view taxonomy.
Consolidate to Compare, Recover and Work: show project/build membership and
recorded function relationships visually; put function search/code/calls inside
Compare, source/proof/output paths inside Recover, pipeline/activity inside Work.
Keep expert tools and project management in menus/contextual drawers. No invented
links, progress or readiness. Preserve the reviewed Task 2 safety boundaries.
Detailed bounded visual contract: task-2-visual-brief.md in this specification's
SDD workspace. Root read frontend-design and data-visualization/SVG guidance;
independent review and actual desktop/mobile visual acceptance remain required.

## Verification

Use inline source/diff checks and read-only or authorized product interactions
through Playwright CLI. Independently review each task for requirements and code
quality. Report observed behavior and remaining gaps precisely.

## Follow-on dependency repair identified during implementation

The actual preparation code indexes optional BSim signatures before ordinary
pair matching, although indexing alone does not supply pair-query hits to the
matcher. Move eligible deterministic matching ahead of optional indexing,
preserving captured resource ownership, source/target basis and cached receipts.
If a later explicit BSim query changes a pair's evidence basis, invalidate only
that pair's dependent claim; never call indexing receipt reuse fused matching.
The recorded repository run's tuple error occurred in facts/analysis, not BSim.
Locate its concrete origin before fixing or admitting a resume. Existing member
checkpoints must be salvaged; one failed member should not erase usable peers.
This is bounded follow-on work, not an assertion that pipeline acceptance is done.
