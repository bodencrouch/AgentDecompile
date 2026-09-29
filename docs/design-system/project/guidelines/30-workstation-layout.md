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

Top to bottom: header (name, active project and related-build scope, go to anything, Commands, the one WorkflowControl, Help) → session tabs → workspace tabs (Code Browser · Compare · Recovery · Evidence) → NavigationBar (Back and Forward with history, go to anything, breadcrumbs with sibling menus, Link panes, layout, copy link) → the CounterpartStrip and PipelineBreadcrumb for the selection → workspace, whose Code Browser shows a Views toolbar (Listing, Decompile, Hex, Graph as co-visible toggles; Strings, Imports, Exports and Sections are navigator scopes; References, Calls and Outline live in the evidence rail) → work view → dock → status line.

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

The Keymap section and `keymap.json` define every binding, scope and profile; the Linked views section defines the link grammar (Enter go, Shift+Enter open beside, Alt+↓ peek, K keep, Shift+F10 reveal in). Global commands always carry a modifier (Ctrl/Cmd+K palette, Ctrl/Cmd+P go to anything, Alt+←/→ history, F6 regions, Ctrl/Cmd+J dock); single letters work only inside a focused list, grid or code well and can be remapped or turned off. Every action has a palette path, a menu path and a keyboard path.

## Accessibility

See the Accessibility section: landmarks and headings, skip links to Functions, Listing, Evidence and Activity, F6 region cycling with focus memory, APG patterns per component, one live-region policy (transitions only), and visible focus and selection in every mode.
