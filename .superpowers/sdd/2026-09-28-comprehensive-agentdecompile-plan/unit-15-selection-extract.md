<!-- master lines 23298-23308; frontend-intent:F07 -->
### frontend-intent:F07

**Owner:** U15. **Requirement disposition:** required. **Source:** `docs/FRONTEND_INTENT.md`:111. Apply C01–C24; historical checked status is not fresh acceptance.

```text
- **F07 — Shared entity navigation:** select a logical function/type/module and see
  its implementations across builds together. Keep unmatched functions and
  one-to-many/split/inlined regions representable. Do not invent an equivalent to
  fill a blank cell.
```


<!-- master lines 23309-23319; frontend-intent:F08 -->
### frontend-intent:F08

**Owner:** U15. **Requirement disposition:** required. **Source:** `docs/FRONTEND_INTENT.md`:115. Apply C01–C24; historical checked status is not fresh acceptance.

```text
- **F08 — Concrete coordinates:** a logical identity is not an address. Bytes,
  calling conventions, storage, architecture and edits remain scoped to a concrete
  artifact/program/revision/address. Keep build-specific differences visible beside
  shared identity; never flatten them into a single “universal” ABI.
```


<!-- master lines 23320-23330; frontend-intent:F09 -->
### frontend-intent:F09

**Owner:** U15. **Requirement disposition:** required. **Source:** `docs/FRONTEND_INTENT.md`:119. Apply C01–C24; historical checked status is not fresh acceptance.

```text
- **F09 — Connected views:** code, assembly, hex, CFG, call graph, xrefs, types,
  evidence and diff follow one shared selection. Clicking a reference navigates
  directly; Back/Forward restores selection and viewport. Switching a build keeps
  the logical entity where a counterpart exists, otherwise explains its absence.
```


<!-- master lines 23331-23341; frontend-intent:F10 -->
### frontend-intent:F10

**Owner:** U15. **Requirement disposition:** required. **Source:** `docs/FRONTEND_INTENT.md`:123. Apply C01–C24; historical checked status is not fresh acceptance.

```text
- **F10 — Less chrome:** resizable persistent panes, dense readable rows, useful
  context menus, keyboard alternatives and a command palette. No cards of internal
  commands, redundant “Explore” buttons, nested links that lose context, duplicated
  Functions widgets or raw JSON as the default result.
```


<!-- master lines 23342-23351; frontend-intent:F11 -->
### frontend-intent:F11

**Owner:** U15. **Requirement disposition:** required. **Source:** `docs/FRONTEND_INTENT.md`:127. Apply C01–C24; historical checked status is not fresh acceptance.

```text
- **F11 — Selection versus batch scope:** retain an inspectable primary item and a
  separately visible checked set with range/select-all support. Changing the active
  program cannot silently carry dangerous checked addresses into another binary.
```


<!-- master lines 23352-23362; frontend-intent:F12 -->
### frontend-intent:F12

**Owner:** U15. **Requirement disposition:** required. **Source:** `docs/FRONTEND_INTENT.md`:130. Apply C01–C24; historical checked status is not fresh acceptance.

```text
- **F12 — Persistent activity dock:** Jobs, logs, diagnostics and notifications live
  together at the bottom (resizable/collapsible). Relevant active work remains
  perceptible while reading code; historical unrelated jobs do not dominate it.
  Refreshes do not steal focus, scroll or editor drafts.
```


<!-- master lines 24102-24122; workstation-2026-09-20:Task3 -->
### workstation-2026-09-20:Task3

**Owner:** U15. **Requirement disposition:** required. **Source:** `docs/plans/2026-09-20-unified-reversing-workstation.md`:63. Apply C01–C24; historical checked status is not fresh acceptance.

```text
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
```

