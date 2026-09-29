# LayoutPresets

Saved task layouts — Read, Compare, Review, Triage and Verify rebuild — each defining which panes are open, their sizes, which panes follow, derive or hold, and the dock tab, switched with g then 1…5 without touching the selection.

**Use it** from the NavigationBar's **Layout ▾** menu button, the View menu, the palette, and `layout.preset` in `keymap.json` (g then 1…5 inside any list, grid or tree). A preset is a way to look, not a way to work: it rearranges panes and nothing else.

**Consumer provides** the five preset definitions (open panes in each region, center split and which pane is primary, following, derived or held slot per pane, navigator, evidence and dock sizes and collapsed state, dock tab) with the viewer's saved changes as a diff; the active preset and whether the current layout differs from it; the current splitter values; and the surface's capabilities (the static 8080 surface has no split panes).

- **Five presets**, in keymap order:
  1. **Read** (g 1) — Functions in the navigator; Listing and Decompile side by side, both following; the evidence rail on References and "Why this name"; dock collapsed.
  2. **Compare** (g 2) — Functions; SplitCompare with the primary listing following and a derived counterpart pane, under the CounterpartStrip in its expanded form; evidence rail at its default width; dock collapsed.
  3. **Review** (g 3) — the review queue in the navigator; MatchReview master-detail (ReviewDetail) with a held endpoint pair beside it; CandidateAlignment in the evidence rail; dock on Problems.
  4. **Triage** (g 4) — a PipelineMap band across the top of the center; FailureRecord and ObjectiveSummary in the evidence rail; the ProblemsList dock expanded. It does not set the navigator or the view under the band; both stay as they were.
  5. **Verify rebuild** (g 5) — navigator collapsed; SourceRepairDiff and ObjectDiff side by side, both following; ImageDeltaMap below them; VariantLedger in the evidence rail; dock on Jobs.
- Sizes not named by a preset use the size tokens' defaults (`navigator-w`, `evidence-w`, `dock-h`); "expanded" and "collapsed" are the region's own states, restored by Enter on its splitter.
- **Switching keeps the selection.** Project, logical entity, inspected build, address, the checked set, marks, the active worklist, drafts and held panes are untouched. The status line says "Layout: Verify rebuild. Selection unchanged … Project unchanged. No work started." Focus stays where it was (g 1…5 is pressed in a list, and that list keeps focus) or moves to the same kind of pane; it is never dropped to the page body.
- **Never changes the project or starts work.** A preset has no action, no admission and no project field. A pane that needs unloaded evidence shows "Not loaded. Open to read it."; nothing is fetched or analyzed because a preset opened it.
- **Following, derived and held stay distinct.** Following panes are a function of the one selection (1px `line` frame, "Follows selection"). A derived pane, like Compare's counterpart pane, follows through the selection's counterpart and says "Counterpart of #88 · derived" (dotted frame in the schematic). A held slot, like Review's endpoint pair, is reserved but never filled by the preset: it reads "Held pair · empty until you hold" in a dashed 2px `ink-strong` frame and fills only when the reviewer presses o (`review.open`) or Open beside on an endpoint. Existing held panes stay held across a switch and keep their target build; if the new preset has no room, they become kept evidence cards, never closed silently. At most two center panes, as the linked-views rules require; Review's pair is one held SplitCompare.
- **Triage's rail shows what you open.** FailureRecord and ObjectiveSummary in the rail show the problem row opened with Enter in the dock, never the row merely focused (WCAG 3.2.1).
- **Per viewer, durable.** Presets and the viewer's changes live in durable workspace state as a diff against the defaults. A changed layout shows "modified" beside the preset name (a dashed-frame word, never color); the menu offers **Save changes to ‹preset›** with what changed ("evidence 260 → 360") and **Reset ‹preset› to default**.
- **Location.** Presets and sizes are never in the URL. A switch pushes one history stop only when it changes the workspace (`ws`); otherwise it replaces `views`, `cmp` and `dock` in place, so Back does not step through layouts.
- **Splitters restore accessibly.** Every splitter is a focusable `role="separator"` whose `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and `aria-valuetext` ("360 pixels, changed from 260") are restored with the preset; bounds come from the size tokens (`navigator-min`…`rail-max`, `evidence-min`…`rail-max`, `dock-min`…`dock-max`, max 46dvh). The View menu sets the same sizes without dragging (WCAG 2.5.7).
- The menu uses `menuitemradio` rows with "g 1"…"g 5" in mono; the preset gallery (the View menu's **Panes and sizes…**) draws each preset as a schematic of its regions in `pane`, `well` and `raised` boxes framed in `line-control`, labelled in words, with the definition as a description list beside it. The current preset takes the selection shape and the word "current".
- **Surfaces.** Both read the same definitions. On the static 8080 surface there are no split panes: the counterpart pane and the held endpoint pair open as a new window at the same link, and rails, sizes and the dock tab still apply (◐ partial, said once). Below 700px a preset chooses the starting pane and dock tab only; NarrowFlow shows one pane at a time.

**Linking**

- Publishes: nothing on its own. A switch may change `ws`, `views`, `cmp` and `dock` in the location; it never changes `project`, `entity`, `build`, `addr`, `hold` or `wl`.
- Follows: the one selection, through the following and derived panes it opens.
- Renders: no entity links; the status line after a switch names the unchanged selection as text.
- Absent: a pane the surface cannot show is named with what happens instead ("opens as a new window"); a region a preset leaves alone says "as it was".

**Keyboard**

- `layout.preset`: g then 1…5 while focus is in a list, grid or tree (composite scope, never in text fields or edit mode); the which-key hint after g lists the five. Ctrl/Cmd+Alt+digit is not used because it types characters on AltGr keyboards. Remappable in KeymapSettings.
- From anywhere else: the NavigationBar's **Layout ▾** (an APG Menu Button: Enter, Space or ↓ opens; ↑/↓ move; Enter or Space picks; Esc closes and returns focus), the View menu or the palette.
- Splitters: arrows 16px (`splitter-step`), Shift+arrows 64px, Enter collapses and restores, Home resets to the preset's value.

**Accessibility**

- A switch is announced once in the polite region: "Layout: Verify rebuild. Selection unchanged." Nothing else is announced.
- `aria-keyshortcuts` cannot express a two-key sequence, so menu items carry "g then 1…5 in any list, grid or tree" as their description and show "g 1" as text.
- Presets change layout only on explicit activation, never on focus or hover (WCAG 3.2.1); the selection and project never change (3.2.2).
- Schematics are `role="img"` with a text alternative that lists panes, following, derived and held slots and the dock state; the description list beside each says the same in words.
- Held, derived, modified and current are words and frames, not color. Targets are 24px, 44px below 700px (2.5.8).

**Removes switching:** J01 "see a function's counterparts on the other builds and return" goes from 5 switches to 1 with Compare (the strip and the derived pane are already open). J07 "review a candidate and check both endpoints' bytes" goes from 8 to 2 with Review (detail and held endpoint pair beside the queue). J04 "why is this blocked and what continues" goes from 5 to 1 with Triage (map band, expanded Problems and the record in the rail). J34 "from a whole-image delta to the object diff" goes from 4 to 1 and J39 "iterate on candidate source repair" from 4 to 1 with Verify rebuild. J10 "relate an instruction to its statement" goes from 6 to 0 with Read. Counts before come from the journeys table; after counts are design targets.
