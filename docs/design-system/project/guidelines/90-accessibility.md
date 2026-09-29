# Accessibility

Accessibility is part of the operating model, not a later pass. A keyboard-only, screen-reader, low-vision or motor-impaired operator must reach every capability the mouse user reaches, on both surfaces, with the same state vocabulary. Most of these rules also remove clicks for everyone.

## Foundations

- **Dark scheme is declared.** `.ad` sets `color-scheme: dark`, so native scrollbars, checkboxes and inputs render on Graphite.
- **Numbers line up.** `.ad` sets `font-variant-numeric: tabular-nums`; live counters never change width.
- **Identifiers are never translated or reordered.** Addresses, symbols, mnemonics, digests and action ids carry `translate="no"` and isolate their direction.
- **Hidden words.** `.sr-only` carries words that are visually implied by a glyph, a column or a legend.

## Selection, focus and links

- **Selection is a shape, not a color.** The one primary selection uses `selection` fill **plus** a 3px `accent` bar at the inline start. On the fill, `ink-muted` is promoted to `ink` automatically, and state words switch to `ink-strong` (glyphs keep their color). The fill alone is 1.6:1 against its surroundings; the bar and the promoted text carry the meaning.
- **Focus** is a solid `focus` outline: 2px at offset 0 on bordered controls, 3px inset on rows, cells, tabs and anything inside an overflow-clipped container (house rule from WCAG 2.4.13). Never a box-shadow ring. 3:1 or better on every surface including `selection`.
- **Focus is never hidden** (WCAG 2.4.11, aiming at 2.4.12 in Listing and the Functions grid): scroll containers set block-start `scroll-padding` to the sticky header plus an armed ActionStrip (`sticky-offset`) and inline-start padding to sticky row headers; focused rows scroll with `block: nearest` inside their own well; Peeks and menus flip so they never cover the focused item; the dock is a grid row, never an overlay.
- **Links look like links.** Anything that navigates (addresses, symbols, counterparts, job ids, receipt ids, logical ids, node ids) is `.ad-link`: its own color token plus a dotted underline at rest and a solid underline on hover and focus. Affordance never depends on color. Items inside composite widgets whose role already says they act (menu items, listbox options, tree items, grid rows) are exempt from the underline; inside a block link only the name is underlined. Inside code wells, token links show their underline on the current, hovered or focused line only, so dense code stays readable; their accessible names still say what they link to.
- **The accent is not a status.** Fresh evidence, the current rail step, the running unit and primary buttons use `ink-strong` and a 2px frame, not the accent.

## Contrast

- Text: 4.5:1 minimum on its ground in every state, including the selected row. The token notes name the grounds each ink is safe on.
- Non-text: 3:1 for control boundaries (`line-control`), focus, glyph frames and any mark that carries meaning. `line` (1.5–1.7:1) is decorative only; interactive boundaries never rely on it. Splitters show a 3:1 grip.
- Data graphics: adjacent segments are separated by 2px `chassis` gaps and patterns, and every graphic has a text key with values.
- `prefers-contrast: more` (and an in-app **Increase contrast** toggle, which is an adaptation, not a theme) raises `line` and `line-node` to `line-control`, `ink-muted` to `ink`, focus to 3px, the selection bar to 4px with a 1px `ink-strong` row outline, shows hover as an outline, and borders family and fault headers in `ink-strong`.
- `forced-colors: active` maps selection to `Highlight`/`HighlightText`, focus to `Highlight`, and all frames and glyph frames to `CanvasText`. Data graphics opt out of forced colors only where their text key carries the values.

## Structure

- **Headings**: h1 is the active project; h2 each region (Navigator, workspace, Evidence, Work view, Activity); h3 each inspector section (Origin, Facts, Conflicts, Edits). Screen-reader users jump by heading instead of clicking through regions.
- **Landmarks**: header = banner (menubar, project and scope, Commands, WorkflowControl, Help); navigator = navigation "Project"; center = the one `main`, labelled by the workspace name; evidence = complementary "Evidence"; work view = region "Work view"; dock = region "Activity"; status line = region "Status" (not live).
- **Bypass**: skip links to Functions, Listing, Evidence and Activity. F6 / Shift+F6 cycle regions in visual order and restore each region's last-focused element. Ctrl/Cmd+B toggles the navigator, Ctrl/Cmd+Alt+B the evidence rail, Ctrl/Cmd+J the dock.
- **Lists as lists**: lifecycle rails, stage rails, ladders and EvidenceRail are `<ol>` with `aria-current="step"` on the current state; readouts (liveness, execution, goal progress; binding predicates) are `<dl>`; legends and keys are tied to their graphic with `aria-describedby`; an absent counterpart is the word "absent", never an empty cell.
- **Focus order and return**: DOM, reading, Tab and F6 order follow the visual order. Focus returns to the invoker; if it is gone, to the same index in the list; never to `body`. Going to a surface focuses its heading or first item; going to an address focuses that listing row. Back and Forward restore the focused element.

## Semantics per pattern

| Component | Pattern | Rules |
|---|---|---|
| SessionTab, workspace tabs, analysis tabs, dock tabs | APG Tabs | `button role="tab"` in named tablists ("Sessions", "Workspaces", "Analysis views", "Activity"); one tab stop, ←/→ move, Home/End. Automatic activation where the panel is cached (sessions, workspaces, dock); manual activation (Enter) for tabs that fetch (Graph, Xrefs, Matching). Close is a separate 24px button named "Close ‹title›"; Delete closes the focused session tab and moves focus to its neighbor; F2 renames. Each session tab restores its own workspace, analysis tab, selection, scroll and focus. |
| EntityRow lists, MatchReview, CounterpartMatrix, ReadinessMatrix | APG Grid | `role="grid"` with a name; row headers `th scope="row"`; one tab stop with roving focus; arrow keys move by cell, Home/End by row; selection with `aria-selected` on rows; checkbox cells are labels named "Select ‹entity›". |
| ContainerTree, navigator | APG Tree view / Treegrid | `aria-expanded`, `aria-level`, typeahead; → opens, ← closes or moves to parent. |
| Listing, Decompile, Hex | Virtualized read-only grid | `role="grid"`, `aria-readonly`, named "Listing, build-b, ‹function›"; columns Address, Label, Bytes, Instruction, Operands, Xrefs/Comment with `aria-colindex`; absolute `aria-rowindex` and `aria-rowcount` (−1 when unknown); the focused row stays mounted. Row names read the cells in order under a **verbosity** setting (address full / last 4 / off; bytes off by default but reachable with →); operands are spoken exactly as displayed. Labels are their own rows ("label ResourceRef::Resolve, 12 xrefs"); flow glyphs are `aria-hidden` and restated as words ("jump target from 0041b230"). Hex rows are 16 byte cells with an offset row header. Find inside a well announces "3 of 12 matches". |
| CommandPalette, go-to field | APG Combobox + Listbox in a modal dialog | `aria-activedescendant`, grouped options, result count in a polite status. |
| ConfirmDialog | APG Alert dialog | Focus starts on Cancel; Esc cancels; focus returns to the invoker. |
| Splitters | APG Window splitter | `role="separator"`, `aria-valuenow/min/max`, `aria-controls`; arrows 16px, Shift 64px, Enter collapse/restore, Home reset. The View menu offers the same sizes and collapse without dragging (WCAG 2.5.7). |
| WorkflowControl, ActionStrip | APG Toolbar | One tab stop, arrows between controls. |
| Job and history lists | APG Feed | `role="feed"`; each ActivityRecord is an `article` named by its title and described by its three readouts; PageDown/PageUp move between records; `aria-busy` while loading. |
| Log tails | ARIA log | `role="log"` with `aria-live="off"`; a per-job "Announce new lines" toggle; "Open in Accessible View". |
| Problems | APG Grid | Enter jumps to the entity or address; F8 / Shift+F8 step to the next or previous problem from anywhere without opening the dock. |
| Breadcrumbs | APG Breadcrumb | `nav` "Location" with an ordered list; `aria-current="location"` on the last item; build and section segments are menu buttons of siblings. |
| Rails, units, meters | Progressbar / img | `role="progressbar"` with `aria-valuetext` in words ("3 of 6 measured units done; unit 4 running"); age bars are `role="img"` with the age in words. Unknown progress has no progressbar, only the words "Progress unknown". |
| Fact strips, capability chips, dense glyph cells | Named image | The strip or cell has an accessible name in words; glyphs are `aria-hidden`. A visible legend is on the same view, and Peek shows the words on focus. |
| Diffs | Text | Added, removed and changed lines carry the words "added", "removed", "differs" for assistive tech, not only color and glyphs. |

## Keyboard and shortcuts (WCAG 2.1.4)

- **Global commands use a modifier**: Ctrl/Cmd+K palette, Ctrl/Cmd+P go to anything, Ctrl/Cmd+G go to address, Alt+← / Alt+→ back and forward, F6 / Shift+F6 cycle regions (header, navigator, center, evidence, dock), Ctrl/Cmd+J toggle dock.
- **Links share one grammar** (see Linked views): Enter goes, Shift+Enter opens beside, Alt+↓ peeks, the Keep button (Shift+K while focus is inside the Peek or card) keeps, Shift+F10 opens the link menu, Ctrl/Cmd+Enter opens a browser tab. Focus never changes workspace, build, dock tab or history, and Alt+←/→ are never intercepted in text fields or edit mode.
- **Single-character keys are focus-scoped**: j/k, x, Space, typeahead and the letter commands work only while focus is inside a list, grid or listing, and never in text fields.
- **Every shortcut can be turned off or remapped** in Keyboard settings. Menus and tooltips show the current binding, and controls expose it with `aria-keyshortcuts`.
- Screen-reader browse modes are respected: letter commands never fire while a virtual cursor mode is plausible (focus on the document body).

## Editing without traps (WCAG 2.1.2)

Editable wells enter edit mode on Enter; Tab indents only in edit mode; Esc leaves it. Ctrl+M toggles "Tab moves focus" and the status line shows the state. F6 always leaves the region. Overlay rails close on Esc or when focus leaves and return focus to their rail-bar button.

## Accessible View

Alt+F2 (and a pane-header button) opens a modal with a read-only text area holding the exact text of the current function, range, log, peek or receipt, following the verbosity setting, caret on the focused line. Diffs prefix lines with "+ added", "− removed", "≠ differs"; evidence includes its ProvenanceStamp text. Esc returns to the same row. Sighted users get exact copyable text too.

## Help that stays put (WCAG 3.2.6) and no retyping (WCAG 3.3.7)

- Help is always the last menubar item on both surfaces: Keyboard shortcuts (Ctrl/Cmd+/; shows the current, remapped keymap), Accessibility help for this view (Alt+F1; the keys of the focused component), Catalog docs. The palette answers "help", "keys" and "shortcuts". Help text comes from the shared keymap document, so it cannot drift.
- ActionStrip fields prefill in this order: the bound target from the selection, then the fields last used for this action on this program, then catalog defaults; each prefilled field says where it came from ("from last run 14:02"). Refusals keep every entered field. Go-to and palette keep their history (↑ in an empty field). Drafts persist per function across navigation. Password fields allow paste and password managers.

## Live regions (WCAG 4.1.3)

One polite status region and one assertive alert region per page.

- **Polite**: job transitions (started, finished, failed, cancelled), decision outcomes after their terminal result, import accepted, result counts, stale and reconnecting notices, "N changes since you looked" summaries.
- **Assertive**: only conflicts and ambiguous command outcomes that block the action in hand.
- Never announce each poll, heartbeat or log line. Announce transitions once; coalesce within 1s (one message per job transition, one per selection settle, one per batch: "4 of 4 finished: 3 accepted, 1 negative").
- An inline StateNotice is `role=status` only when the user's own action caused it. Freezing a region freezes its announcements and later reports "N events since frozen".

## Content on hover or focus (WCAG 1.4.13)

Peeks and hover cards are **dismissable** (Esc), **hoverable** (the pointer can move onto them) and **persistent** (they stay until dismissed, focus leaves, or the pointer leaves both trigger and card). They open on focus as well as hover, never steal focus, and never contain the only copy of information that is not reachable another way. The `title` attribute is never the only carrier of meaning.

## Targets, dragging and reflow

- Every target is at least 24×24 CSS px (WCAG 2.5.8); below 700px, 44px. Small marks join a larger target: the whole fact strip is one button that opens Peek, the capability row is one button, the whole address cell is the link. Each component README names the exception it relies on.
- Nothing requires dragging (WCAG 2.5.7): clicking a splitter grip toggles collapse and restore, and the pane-header menu offers Narrow / Default / Wide / Collapse / Reset; tabs move with Ctrl+Shift+PageUp/PageDown or their context menu; grid headers offer Fit to content / Default width; the dock moves via View; diagrams have zoom and pan buttons; the WorkTimeline track is clickable and has step buttons; import has "Choose files…"; layout presets set every splitter at once.
- Content reflows at 320×256 CSS px (1280×1024 at 400% zoom) by switching to the single-pane layout; only code wells, matrices and diagrams scroll in two dimensions, each in its own focusable, labelled container. Switching panes keeps each pane's scroll and focused row.
- Size tokens are minimums; rows grow. No fixed heights with `overflow: hidden` around text; text survives WCAG 1.4.12 spacing overrides. Every truncation has a reveal path that is not `title`: the full text is in the accessible name, in Peek on focus, and in the evidence rail header.

## Motion, time and updates

- `prefers-reduced-motion` (and an in-app **Reduce motion** toggle) removes all motion: scrolling is instant, the arrival flash becomes a static 2px outline held until the next interaction, and animated edges and transfers become a before/after pair plus the event sentence.
- Auto-updating regions (dock, log tails, heartbeats) have a **Freeze updates** control (WCAG 2.2.2); frozen regions say "Frozen at 14:02 · 7 events since", queue events without dropping them, and resume on request.
- No time limits on reading or deciding. Pending decisions never expire silently.

## Diagrams

- Every diagram SVG has `role="img"`, `lang`, a `<title>` and a 2–4 sentence `<desc>`, and links a generated text outline as its primary accessible form.
- Diagram text colors are all 4.5:1 or better on their grounds. Two pairs are forbidden: identity ink on identity fill (4.48:1) and `ink-muted` on any family fill.
- Family, gate, lock and edge type are always written as words as well as drawn in color, dash or shape.
- In-app renderings of diagram components use the app type scale (≥11px labels, ≥12px body), never the sub-12px `dia-*` sizes, which exist only for the fixed-size print canvas.
