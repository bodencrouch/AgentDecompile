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

Top to bottom: header (name, active project and related-build scope, go to anything, Commands, the one WorkflowControl, Help) → session tabs → workspace tabs (Code Browser · Compare · Recovery · Evidence) → NavigationBar (Back, Forward and the Recent menu, go to anything, breadcrumbs with sibling menus, Update panes, layout, copy link) → the CounterpartStrip and PipelineBreadcrumb for the selection → workspace, whose Code Browser shows a Views toolbar (Listing, Decompile, Hex, Graph as co-visible toggles; Strings, Imports, Exports, Sections, Symbols and Bookmarks are navigator scopes; References, with Calls and Slots modes, and Outline live in the evidence rail; program Info is the build crumb's Peek and the rail's build header) → work view → dock → status line.

- **One Functions surface.** Never add a second function sidebar.
- **Listing and Decompile own the center.** Inspectors and the dock are resizable and collapsible. There is no giant blank upper workspace.
- **Corpus first.** The primary selection is a logical entity; the concrete build and address are a drill-down. Compare is an N-way workspace plus a two-pane split inside the Code Browser, not a secondary page.
- **Build switches keep the place.** The CounterpartStrip, the breadcrumb build menu, go to and Alt+PageDown/PageUp keep the entity and map the cursor only through recorded anchor pairs. Between anchors they land on the nearest preceding anchor's partner and say so. They never interpolate by offset or order. With no counterpart they stay on the current build and say why.
- **Program bookmarks are not marks.** The Bookmarks scope lists the program's own bookmarks read-only: category, comment and an address link. Marks and their notes are per-viewer annotations. They are never input to context fusion, propagation or agent bundles, and never a claim tier.
- **One selection owner.** Project, logical entity, inspected build(s) and address own every view. Selection changes invalidate obsolete requests and never silently pick another target. Back and Forward restore selection and viewport.
- **Selection versus batch.** One primary item uses `selection`. The checked set shows as checkboxes and a count chip, never a second fill. Changing program clears it.

## Regions

| Region | Default | Bounds | Collapse |
|---|---|---|---|
| Navigator | `navigator-w` 240px | 180–480px | collapsible to its strip; the Navigate pane below 700px |
| Evidence rail | `evidence-w` 260px | 200–480px | collapsible to its strip; the Inspect pane below 700px |
| Activity dock | `dock-h` 170px | 100–420px, max 46dvh | collapsible to its strip; the Activity pane plus a one-line status below 700px; side rail allowed at ≥1280px |

Sizes and collapse state persist per viewer in durable workspace state (F23), not in browser storage. A collapsed region leaves a 24px collapse strip: a disclosure button with a stable name (Navigator, Evidence, Activity). Strips are hidden below 700px, where the NarrowFlow rail bar takes over.

Splitters: a 1px `splitter-rule` with a bordered grip in `splitter-grip` (3:1 on every surface), and `splitter-active` on hover, focus and drag. Arrow keys move 16px and Shift+Arrow 64px. Home and End move to the minimum and maximum (APG window splitter), and Enter collapses and restores. Reset is in the pane-header size menu (Narrow, Default, Wide, Collapse, Reset). The hit zone is 6px, below 24px, so it relies on the WCAG 2.5.8 Equivalent exception: the splitter keys, the size menu and the View menu reach every size.

## Evidence rail

Selection-scoped sections, each an APG disclosure (an h3 holding a button), in this order:

1. Kept
2. Pipeline (PipelineBreadcrumb)
3. Why this name (NameProvenance)
4. Facts
5. References, with Calls and Slots modes (XrefPanel)
6. Outline
7. Counterparts
8. Cross-match summary
9. Recovery: facts and latest receipts
10. Timeline (EntityTimeline)

Each corpus section is headed "For ResourceRef::Resolve · build-b" and ends with Show all, which opens the full corpus view (`panel=`) at the same entity and build. Collapsed state is per viewer, in durable workspace state. Expand all and Collapse all are in the rail header menu and the palette. Sections are kept as cards, never held.

## Compiler-aware views and project outputs

Builds are variants of one application, so these views are keyed by logical entity with builds as columns, and every difference carries a variance class and an evidence level (State vocabularies). All of them are read-only.

- **Corpus panels** (`panel=`, each with a rail section and Show all):
  - **OutputsCatalog** (`ws=evidence&panel=outputs`): every export, output and result by artifact × build, with status, claim tier and its ≠ sentence, basis and the 8080 observation. An artifact opens as an **ArtifactCard** beside it or in the rail (`artifact=`).
  - **ToolchainEvidence** (`ws=evidence&panel=toolchain`): compiler, linker and flag facts × builds, each value with its evidence level, and the pinned rebuild toolchain with its mismatch notice.
  - **VariantRelation** (`ws=compare&panel=variants`, with `cmp`): how each pair of builds relates, entity counts by variance class, and a drill-down to the entities.
- **In the Code Browser and Compare** (secondary pane, rail section, or a layer over the wells; never a new workspace):
  - **CompilerLayer**: an annotation layer over Listing, DecompileView and SplitCompare (`layers=compiler`), toggled from the Views toolbar.
  - **PointerWalk** (`walk=`): the expression at the cursor as a chain of typed steps, one offset cell per build.
  - **TransformTimeline**: one function across a `cmp` pair as an ordered, reconstructed list of transformations.
  - **MatchExplain**: why a candidate does not byte-match its target, by class, beside ObjectDiff in Recovery and Compare.
  - **FrameLayout**: the stack frame per build by logical slot.
  - **VTableBrowser**: the class hierarchy and vftable slots per build by logical method.

## Breakpoints

- **≥1280px** (`bp-side-dock`): the dock may move to a side rail.
- **<1100px** (`bp-compact`): rails shrink, keyboard hints hide, search collapses to a button.
- **<700px** (`bp-single-pane`): one primary pane at a time, as NarrowFlow defines it. A rail bar switches Navigate, Analyze, Inspect and Activity. All targets are 44px (`touch-h`).
- **Coarse pointer** (`@media (pointer: coarse)`): 44px targets at any width.
- **<480px tall** (`bp-short-h`): the header and status line are not sticky, and the Peek sheet opens full height.

Acceptance sizes are 1440×900, 598×912 and 320×256 CSS px, plus a coarse-pointer check at 768×1024, all with the WCAG 1.4.12 text-spacing overrides. They are future checks on 8080 and have not been run.

## Density and View settings

Comfortable (default, `control-h-comfortable` 28px) or compact (`control-h` 24px). Density is the only appearance choice, and it is not a theme.

**View settings** is one group in the View menu that holds every per-viewer setting: Density, Increase contrast, Reduce motion, Screen-reader verbosity and Advance to Analyze after a pick, plus the pointer options Peek on hover and Brush on hover. The settings are stored as a per-viewer diff in durable workspace state beside the keymap overrides, never in the URL or browser storage. Increase contrast and Reduce motion only add to the operating system's preferences; they never switch one off.

## Dock

Activity, Recovery, Logs, Jobs and Problems live together at the bottom. There are no toasts; notifications go to the dock. Relevant active work stays visible while reading code; unrelated history does not dominate. Refreshes never steal focus, scroll or editor drafts. Log tails show the latest lines.

- **Show and go.** Ctrl/Cmd+J only shows or hides the dock. `g j` opens it if needed and focuses the row of the last announced transition.
- **Selection only.** One dock-level toggle (aria-pressed, the stable name "Selection only", state words beside it) filters Jobs, Problems and Logs to the selection: the entity across builds, or the build when the selection is build-scoped. While it is on, a FilterChip "Selection only: ‹entity› · ‹build› ×" shows (`f=scope:selection`). Logs are filtered by job, to the logs of jobs whose records name the target, never by searching log text.
- **Freeze** is per region (Accessibility), with its own "Frozen at 14:02 · 7 events since" indicator. An action taken from a frozen row acts on the current record.

## Keyboard

The Keymap section and `keymap.json` define every binding, scope and profile; the Linked views section defines the link grammar (Enter go, Shift+Enter open beside, Alt+↓ peek, Shift+K or the Keep button inside a Peek or card, Shift+F10 link menu) and the grid modifier precedence. Enter always means Go; `.` rebinds the armed action to the focused row and focuses Run, and never posts. In checkable grids Space checks, and Shift extends a range (Shift+↑↓, Shift+j/k, Shift-click); Ctrl/Cmd-click toggles one row, so Open beside there is Shift+Enter or the link menu. Global commands always carry a modifier (Ctrl/Cmd+K palette, Ctrl/Cmd+P go to anything, Alt+←/→ history, F6 regions, Ctrl/Cmd+J dock); single letters work only inside a focused list, grid or code well and can be remapped or turned off. Where a list binds letter commands, typeahead starts with `/`. Every action has a palette path, a menu path and a keyboard path.

Go to has three entry points and one engine. Ctrl/Cmd+P focuses the go-to field in the NavigationBar. Ctrl/Cmd+G focuses the same field with `:` typed, and its first row is the last address jump. Ctrl/Cmd+K opens the modal palette with `>` typed. Below 1100px, where the field is collapsed, P and G open the same engine in the palette dialog. No typed character opens a dialog.

## Accessibility

See the Accessibility section: landmarks and headings, skip links to Functions, Listing, Evidence and Activity, F6 region cycling with focus memory, APG patterns per component, one live-region policy (transitions and settled results; see Accessibility), and visible focus and selection in every mode.
