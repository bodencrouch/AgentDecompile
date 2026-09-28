---
title: Static CodeBrowser Project Tabs - Plan
type: feat
date: 2026-09-28
topic: static-codebrowser-project-tabs
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# Static CodeBrowser Project Tabs - Plan

## Goal Capsule

**Objective:** An operator reverse-engineering a set of related builds works in one browser tab per project. They see every build, its code, its cross-build matches and its call graph at once, in the layout they already know from Ghidra's CodeBrowser. The recovery pipeline's automatic work shows as state they can read and pause, never as buttons they must press.

**Means:** Rebuild the static dashboard on port 8080 as a CodeBrowser-parity workspace. A tab holds a project, not a binary. Remove every control that triggers pipeline-owned work.

**Product authority:** The user's 2026-09-28 directives, and `docs/FRONTEND_INTENT.md`: the static surface, "no Start button" and one selection and job store. This plan covers the static dashboard only. The Vite workstation and the progress and report spine are not active scope (see How This Work Fits Together).

**Open blockers:** None for planning. Two execution preconditions are listed under Dependencies / Assumptions.

## Product Contract

### Summary

Replace the static dashboard's action tabs and pipeline buttons with Ghidra CodeBrowser parity. A browser tab holds a project whose binaries are peers on one shared cursor. A cross-build map dock shows the call graph and matcher together. Pipeline progress is shown and can be paused. It is never triggered.

### Problem Frame

The static dashboard grew around the pipeline's steps. Its menus mostly offer buttons for work the pipeline already schedules on its own. The same is true of its Listing, Functions, Call trees, Match, Recover and More tabs. The page spends its space on controls the operator should never need, instead of on code, symbols and cross-build evidence.

Ghidra's own model has a second cost. Only one program drives the cursor at a time, so comparing builds means loading and switching between them. The corpus already holds the data that relates builds: identity bindings, match rows and cross-build call reach. The interface hides it behind one active program and a tab switch per lookup.

### Actors

- A1. Operator: a person reading, naming and reviewing code across related builds while the pipeline runs.
- A2. Agent client: an automated caller acting through the same backend. It reads the same state the operator sees.
- A3. Recovery pipeline: admits and runs work on its own. The interface observes it.

### Requirements

**Pipeline-owned work is never a control**

- R1. No menu item, tab, toolbar button or panel button starts, reruns or duplicates work the recovery pipeline schedules on its own. This covers these stages:
  - analysis;
  - protection preparation;
  - fact extraction;
  - similarity indexing;
  - matching;
  - calibration;
  - source recovery;
  - cross-build placement;
  - leftover recovery;
  - byte verification.
- R2. Three events admit the pipeline's eligible missing work without a separate action: opening a project, adding a binary to a project, and registering a binary. Reopening material that already has receipts does not redo that work.
- R3. After admission, the interface shows a one-line receipt naming the admitted run, its generation and its queue position.
- R4. Pause, resume and stop are the only workflow controls. They appear wherever run state is shown, pre-scoped to the run in view.
- R5. Operator edits stay available as explicit user actions:
  - rename;
  - comments;
  - bookmarks;
  - retyping and data-type edits;
  - accept or reject of match candidates, singly and in batches;
  - opening, creating and saving projects;
  - adding binaries.
- R6. An expert command palette stays available for low-level catalog actions. It is not the path for routine pipeline work.
- R7. The backend enforces R1 through its classification of which actions and modes change state. A new pipeline trigger added to a static surface fails that check.
- R8. R1 through R7 apply to every static surface served on 8080, including the explorer page.

**CodeBrowser parity**

- R9. The workspace follows Ghidra's stock CodeBrowser arrangement:
  - the Symbol Tree and Program Trees in the left rail, with the Data Type Manager below them;
  - the Listing and Decompiler in the center, with secondary providers tabbed alongside the Decompiler;
  - Console and Bookmarks at the bottom;
  - Data Type Preview as a thin strip.
- R10. Every CodeBrowser provider that the Ghidra reversing guide uses is present:
  - Listing: address, bytes, mnemonic, operands, cross-reference and comment fields, with a function header;
  - Decompiler;
  - Symbol Tree;
  - Program Trees;
  - Data Type Manager;
  - Memory Map;
  - Bytes;
  - Defined Strings;
  - Symbol Table and References;
  - Functions table;
  - Function Graph;
  - Function Call Trees and Call Graph;
  - Bookmarks;
  - Console;
  - Function Comparison;
  - Equates;
  - Relocations.
- R11. Providers that only show data are read-only views. Providers that edit data do so only through R5's explicit user actions.
- R12. One program location drives every connected provider. Selecting an address, symbol or cross-reference in any provider moves the others. No tab switch or new search is needed.
- R13. Navigation matches Ghidra:
  - back and forward history;
  - go-to by address or name;
  - previous and next function;
  - highlight of the selected token wherever it recurs;
  - an overview strip marking locations across the program.
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

### Acceptance Examples

- AE1. **Covers R1, R8.** The redesigned static surfaces are in place. The check lists every menu, tab and button. None of them starts or reruns analysis, matching, recovery, placement or verification. Neither the "Run pipeline" control nor the "Start workflow" control exists.
- AE2. **Covers R2, R3.** A project holds a binary that has no analysis yet. When the operator opens the project, the admission receipt appears. The operator pressed nothing.
- AE3. **Covers R12.** The Listing shows a call. When the operator activates its target, the Decompiler, Symbol Tree and call trees move to the target without a tab switch.
- AE4. **Covers R17.** A function is bound in two of three peers. When the operator selects it, two peers align. The third shows "no identity binding".
- AE5. **Covers R20.** The pipeline compared a spanning subset of build pairs in a project. When the operator views the matrix, the pairs it did not compare read "not scheduled".
- AE6. **Covers R23.** One pair matched on object bytes, and another matched on name only. When both appear in review, their kind labels differ.
- AE7. **Covers R16, R25.** A peer needs server credentials before it can be read. When the tab loads, the peer shows a blocked state that names the credential step.

### Success Criteria

- The operator can work through every chapter of the Ghidra reversing guide in the static workspace:
  - orient;
  - symbols and types;
  - listing and decompiler;
  - call trees;
  - memory map and bookmarks;
  - signatures;
  - structures and vtables;
  - templates;
  - diagnosis.
- No static surface offers a control for pipeline-owned work, and the backend classification check in R7 passes.
- For any selected function in a multi-build project, the call graph and matcher results are visible together.
- The guide's flows produce no console errors and reach no dead controls.

### Scope Boundaries

**Deferred for later**

- The Vite workstation redesign, with parity to objdiff-web, decomp.me, Dogbolt, RzWeb, r2web and APKMan.
- The progress and report spine, and publishing statistics to an outside site.

**Outside this product's identity**

- A second job or selection store in the static surface.
- Any control that starts pipeline stages by hand, including run buttons for single stages.

### Key Decisions

- Builds are peers. This replaces Version Tracking's source and destination pair. Ghidra's limit of one active program is what the project tab removes, so no build drops to a secondary role.
- The cross-build map is a dock inside the CodeBrowser layout, not the tab's landing view. This keeps CodeBrowser parity and adds the one view Ghidra cannot show.
- Full provider parity is required. Delivery may start with the providers the guide's first chapters use: Listing, Decompiler, Symbol Tree, call trees, cross-references and the cross-build map.
- The menubar stays, without an Analysis menu, because analysis belongs to the pipeline. The items that remain follow Ghidra's naming: navigation, search, window, help and file operations on projects.

### Dependencies / Assumptions

- Peers read at the same time only if the backend scopes its live-read path to each project and binary. Today one active locator is shared across the whole process. Planning must resolve this before R15 and R18 can hold.
- Admission on open and register (R2) is new behavior. Today only adding a program to an open project admits work.
- Assumption: menubar contents beyond removing Analysis follow Ghidra's naming. The user said the top menu holds useless buttons but did not say what should replace them.
- Assumption: in large projects, peers not in focus render as light tracks rather than full workspaces.
- Live decompiler reads of the shared repository need server credentials. A local copy of the project reads without them.

### Outstanding Questions

**Deferred to Planning**

- How the cross-build call graph performs across tens of builds, and whether it loads a piece at a time.
- Which existing static panels are removed, merged or rehomed as CodeBrowser providers, and how existing deep links keep working.
- Whether the explorer page folds into the project-tab workspace or stays a separate view under R8.

<!-- ce-section: work-relationships -->
### How This Work Fits Together

The 2026-09-28 frontend directive covers three areas:

- **Static CodeBrowser workspace.** This plan owns it.
- **Vite workstation.** A separate surface with a different purpose, over the same backend and pipeline.
- **Progress and report spine.** It feeds both surfaces, and later outside publishing.

The static workspace's pipeline-state display (R24–R26) reads the same observed state that the Vite workstation and the report spine will use. The links between the three areas stay tentative until each has its own brainstorm.

### Sources / Research

- `docs/FRONTEND_INTENT.md`: the split between surfaces, "no Start button", and the single store.
- `docs/ideation/2026-09-28-frontends-redesign-ideation.html`: ranked ideas and their evidence.
- `docs/dashboard-design/2026-09-28-static-codebrowser-guide-redesign.md`: earlier redesign slices built on the guide.
- `docs/dashboard-design/pipeline-diagram/README.md`: pipeline stages and lanes.
