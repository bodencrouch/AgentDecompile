# Workstation layout

Two maintained surfaces share one backend, catalog, project identity, job state and proof semantics: the complete static workbench at `8080/dashboard`, and the optional full workspace (Vite, 5174 or packaged `/react/`). They may differ in richness. They never disagree on the selected target, saved work, actual jobs or proof, and no field exists on only one of them.

## Shell

```
Active project / related-build scope · search / goto · Pause admission
┌─ Navigator ───────┬─ Code Browser · Compare · Recovery · Evidence ─┬─ Evidence ──────┐
│ project/programs  │ shared entity: listing / decompile / hex / diff │ origin, facts,  │
│ one Functions     │ build counterparts and divergences              │ conflicts, edits│
├───────────────────┴─────────────────────────────────────────────────┴─────────────────┤
│ Actual-work view: compare / change / propagate / verify / runtime events               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Activity dock: Activity · Recovery · Logs · Jobs · Problems                             │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Top to bottom: header (name, active project and related-build scope, search, Commands, the one WorkflowControl) → session tabs → workspace tabs (Code Browser · Compare · Recovery · Evidence) → analysis tabs (Disassembly, Decompiler, Hex, Strings, Graph, Xrefs, Imports, Exports, Sections, Info, Matching, then "More…") → navigation bar (Back, Forward, go-to address or symbol, reload, copy link) → workspace → work view → dock → status line.

- **One Functions surface.** Never add a second function sidebar.
- **Listing and Decompile own the center.** Inspectors and the dock are resizable and collapsible. There is no giant blank upper workspace.
- **Corpus first.** The primary selection is a logical entity; the concrete build and address are a drill-down. Compare is a workspace, not a secondary page.
- **One selection owner.** Project, logical entity, inspected build(s) and address own every view. Selection changes invalidate obsolete requests and never silently pick another target. Back and Forward restore selection and viewport.
- **Selection versus batch.** One primary item uses `selection`. The checked set shows as checkboxes and a count chip, never a second fill. Changing program clears it.

## Regions

| Region | Default | Bounds | Collapse |
|---|---|---|---|
| Navigator | `navigator-w` 240px | 180–480px | collapsible; overlay below 700px |
| Evidence rail | `evidence-w` 260px | 200–480px | collapsible; overlay below 700px |
| Activity dock | `dock-h` 170px | 100–420px, max 46dvh | 23dvh below 700px; side rail allowed at ≥1280px |

Splitters: 1px `splitter-rule`, 6px hit zone, `splitter-active` on hover and focus. Arrow keys move 16px, Shift+Arrow 64px, Enter collapses and restores, Home resets.

## Breakpoints

- **≥1280px** (`bp-side-dock`): the dock may move to a side rail.
- **<1100px** (`bp-compact`): rails shrink, keyboard hints hide, search collapses to a button.
- **<700px** (`bp-single-pane`): one primary pane at a time. A rail bar switches Navigate, Analyze, Inspect and Activity. All targets are 44px (`touch-h`). Acceptance is checked at desktop 1440×900 and at 598×912.

## Density

Comfortable (default, `control-h-comfortable` 28px) or compact (`control-h` 24px), remembered per viewer. Density is not a theme.

## Dock

Activity, Recovery, Logs, Jobs and Problems live together at the bottom. There are no toasts; notifications go to the dock. Relevant active work stays visible while reading code; unrelated history does not dominate. Refreshes never steal focus, scroll or editor drafts. Log tails show the latest lines.

## Keyboard

Ctrl/Cmd+K palette · Ctrl/Cmd+P go to anything (addresses, symbols, logical ids, jobs, receipts, pipeline nodes) · Ctrl/Cmd+G go to address · Alt+← / Alt+→ back and forward · F6 cycles regions · Alt+↓ peeks the focused link · Ctrl/Cmd+S save. Inside a focused list, grid or listing only: ↑↓ Enter, j/k move the selection, x or Space checks a row, Shift extends a range, Enter opens the action strip with the last action. Esc closes and returns focus. Single-letter keys never act outside a focused list and can be turned off or remapped (see Accessibility). Every action has a palette path, a menu path and a keyboard path.

## Accessibility

A skip link goes to the Functions list. Menus use menubar roles; the palette is a labelled dialog; confirms are `alertdialog`. A hidden polite live region announces job transitions only (started, failed, cancelled, finished), never each poll. Every state has a glyph and a word.
