# LayoutPresets

Saved task layouts — Review, Read, Verify rebuild, Triage and Compare — each defining which panes are open, their sizes, which panes follow or hold, and the dock tab, switched with g then 1…5 without touching the selection.

**Use it** from the header's **Layout ▾** menu button (also the View menu and the palette), and with `layout.preset` from `keymap.json`. A preset is a way to look, not a way to work: it rearranges panes and nothing else.

**Consumer provides** the five preset definitions (open panes in each region, center split and which pane is primary, following or held slot per pane, navigator, evidence and dock sizes, collapsed state, dock tab) with the viewer's saved changes as a diff; the active preset and whether the current layout differs from it; the current splitter values; and the surface's capabilities (the static 8080 surface has no split panes).

- **Five presets**, in keymap order:
  1. **Review** — review queue in the navigator; listing and counterpart listing side by side, both following the review row; CandidateAlignment in the evidence rail; dock on Problems.
  2. **Read** — Functions; Decompile beside SourceRepairDiff, both following; PipelineBreadcrumb and EntityTimeline in the rail; dock on Recovery.
  3. **Verify rebuild** — navigator collapsed; ObjectDiff following beside one empty held slot; VariantLedger and ImageDeltaMap in the rail; dock on Jobs.
  4. **Triage** — Functions; listing beside the runtime trace; TriageCapabilities in the rail; dock on Activity.
  5. **Compare** — Functions; listing beside Decompile; evidence at its default width; dock collapsed, Jobs when opened.
- **Switching keeps the selection.** Project, logical entity, inspected build, address, the checked set, marks, the active worklist, drafts and held panes are untouched. The status line says "Layout: Verify rebuild. Selection unchanged … Project unchanged. No work started." Focus stays in the pane that had it, or moves to the same kind of pane; it is never dropped to the page body.
- **Never changes the project or starts work.** A preset has no action, no admission and no project field. Opening a pane that needs unloaded evidence shows "Not loaded. Open to read it."; nothing is fetched or analyzed because a preset opened it.
- **Held slots are reserved, never filled.** A preset may declare a held slot (Verify rebuild does); it shows "Held slot · empty until you hold a pane" in a dashed 2px `ink-strong` frame. Holding is always explicit. Existing held panes stay held across a switch and keep their target build; if the new preset has no room, they become kept evidence cards, never closed silently.
- **Following panes** in the new preset recompute from the one selection after the settle delay and drop superseded responses, exactly like any following pane.
- **Per viewer, durable.** Presets and the viewer's changes live in durable workspace state as a diff against the defaults. A changed layout shows "modified" beside the preset name (a dashed-frame word, never color); the menu offers **Save changes to ‹preset›** with what changed ("evidence 320 → 360") and **Reset ‹preset› to default**.
- **Location.** Sizes and presets are never in the URL. A switch that changes the workspace (`ws`) pushes one history stop; otherwise it replaces `v` and `dock` in place, so Back does not step through layouts.
- **Splitters restore accessibly.** Every splitter is a focusable `role="separator"` whose `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and `aria-valuetext` ("360 pixels, changed from 320") are restored with the preset; bounds come from the size tokens (`navigator-min`…`rail-max`, `evidence-min`…`rail-max`, `dock-min`…`dock-max`, max 46dvh). The View menu sets the same sizes without dragging (WCAG 2.5.7).
- The menu uses `menuitemradio` rows with the shortcut in mono; the preset gallery (in the View menu's **Panes and sizes…**) draws each preset as a schematic of its regions in `pane`, `well` and `raised` boxes framed in `line-control`, labelled in words, with the definition as a description list beside it. The current preset takes the selection shape and the word "current".
- **Surfaces.** Both read the same definitions. On the static 8080 surface there are no split panes: the secondary pane opens as a new window at the same link, and rails, sizes and dock tab still apply (◐ partial, said once). Below 700px presets choose the starting pane and dock tab only; NarrowFlow shows one pane at a time.

**Linking**

- Publishes: nothing on its own. A switch may change `ws`, `v` and `dock` in the location; it never changes `p`, `e`, `b`, `a`, `hold` or `wl`.
- Follows: the one selection, through the following panes it opens.
- Renders: no entity links; the status line after a switch names the unchanged selection as text.
- Absent: a pane the surface cannot show is named with what happens instead ("opens as a new window").

**Keyboard**

- `layout.preset`: g then 1…5 from anywhere except text fields and edit mode, where Ctrl+Alt may type characters on AltGr keyboards. Remappable in KeymapSettings.
- **Layout ▾** is an APG Menu Button: Enter, Space or ↓ opens; ↑/↓ move; Enter or Space picks; Esc closes and returns focus to the button.
- Splitters: arrows 16px (`splitter-step`), Shift+arrows 64px, Enter collapses and restores, Home resets to the preset's value.

**Accessibility**

- A switch is announced once in the polite region: "Layout: Verify rebuild. Selection unchanged." Nothing else is announced.
- Presets change layout only on explicit activation, never on focus or hover (WCAG 3.2.1); the selection and project never change (3.2.2).
- Schematics are `role="img"` with a text alternative that lists panes, sizes, following and held slots and the dock tab; the definition beside each says the same in words.
- Held, modified and current are words and frames, not color. Targets are 24px, 44px below 700px (2.5.8).

**Removes switching:** J39 "iterate on candidate source repair" goes from 4 switches to 1: Read puts the diagnostic, the source diff and the pipeline position together. J34 "from a whole-image delta to the object diff" goes from 4 to 2 with Verify rebuild. J07 "review a candidate and check both endpoints' bytes" goes from 8 to 3 with Review. Counts before come from the journeys table; after counts are design targets.
