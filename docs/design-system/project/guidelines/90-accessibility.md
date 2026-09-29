# Accessibility

Accessibility is part of the operating model, not a later pass. A keyboard-only, screen-reader, low-vision or motor-impaired operator must reach every capability the mouse user reaches, on both surfaces, with the same state vocabulary. Most of these rules also remove clicks for everyone.

## Foundations

- **Dark scheme is declared.** `.ad` sets `color-scheme: dark`, so native scrollbars, checkboxes and inputs render on Graphite.
- **Numbers line up.** `.ad` sets `font-variant-numeric: tabular-nums`; live counters never change width.
- **Identifiers are never translated or reordered.** Addresses, symbols, mnemonics, digests and action ids carry `translate="no"` and isolate their direction.
- **Hidden words.** `.sr-only` carries words that are visually implied by a glyph, a column or a legend.

## Selection, focus and links

- **Selection is a shape, not a color.** The one primary selection uses `selection` fill **plus** a 3px `accent` bar at the inline start. On the fill, `ink-muted` is promoted to `ink` automatically, and state words switch to `ink-strong` (glyphs keep their color). The fill alone is 1.6:1 against its surroundings; the bar and the promoted text carry the meaning.
- **Focus** is a solid 2px `focus` outline inset 2px, 3:1 or better on every surface including `selection`. Scroll containers set `scroll-padding-block` so sticky headers never cover the focused item (WCAG 2.4.11).
- **Links look like links.** Anything that navigates (addresses, symbols, counterparts, job ids, receipt ids, logical ids, node ids) is `.ad-link`: its own color token plus a dotted underline at rest and a solid underline on hover and focus. Affordance never depends on color. Items inside composite widgets whose role already says they act (menu items, listbox options, tree items, grid rows) are exempt from the underline; inside a block link only the name is underlined.
- **The accent is not a status.** Fresh evidence, the current rail step, the running unit and primary buttons use `ink-strong` and a 2px frame, not the accent.

## Contrast

- Text: 4.5:1 minimum on its ground in every state, including the selected row. The token notes name the grounds each ink is safe on.
- Non-text: 3:1 for control boundaries (`line-control`), focus, glyph frames and any mark that carries meaning. `line` (1.5–1.7:1) is decorative only; interactive boundaries never rely on it. Splitters show a 3:1 grip.
- Data graphics: adjacent segments are separated by 2px `chassis` gaps and patterns, and every graphic has a text key with values.
- `prefers-contrast: more` raises `line` to `line-control` and `ink-muted` to `ink`.
- `forced-colors: active` maps selection to `Highlight`/`HighlightText`, focus to `Highlight`, and all frames and glyph frames to `CanvasText`. Data graphics opt out of forced colors only where their text key carries the values.

## Semantics per pattern

| Component | Pattern | Rules |
|---|---|---|
| SessionTab, workspace tabs, analysis tabs, dock tabs | APG Tabs | `button role="tab"` in a named `tablist`; one tab stop, ←/→ move, Home/End; workspace and analysis tabs are two separate tablists. Close is a separate 24px button named "Close ‹title›". |
| EntityRow lists, MatchReview, CounterpartMatrix, ReadinessMatrix | APG Grid | `role="grid"` with a name; row headers `th scope="row"`; one tab stop with roving focus; arrow keys move by cell, Home/End by row; selection with `aria-selected` on rows; checkbox cells are labels named "Select ‹entity›". |
| ContainerTree, navigator | APG Tree view / Treegrid | `aria-expanded`, `aria-level`, typeahead; → opens, ← closes or moves to parent. |
| Listing, Decompile, Hex | Virtualized grid | `aria-rowcount` for the whole function; each row has a readable name: "0041b213, bytes 8b 45 08, mov eax, dword pointer ebp plus 8". Flow glyphs are `aria-hidden`; branches and xrefs are spoken as words. |
| CommandPalette, go-to field | APG Combobox + Listbox in a modal dialog | `aria-activedescendant`, grouped options, result count in a polite status. |
| ConfirmDialog | APG Alert dialog | Focus starts on Cancel; Esc cancels; focus returns to the invoker. |
| Splitters | APG Window splitter | `role="separator"`, `aria-valuenow/min/max`, `aria-controls`; arrows 16px, Shift 64px, Enter collapse/restore, Home reset. The View menu offers the same sizes and collapse without dragging (WCAG 2.5.7). |
| WorkflowControl, ActionStrip | APG Toolbar | One tab stop, arrows between controls. |
| Rails, units, meters | Progressbar / img | `role="progressbar"` with `aria-valuetext` in words ("3 of 6 measured units done; unit 4 running"); age bars are `role="img"` with the age in words. Unknown progress has no progressbar, only the words "Progress unknown". |
| Fact strips, capability chips, dense glyph cells | Named image | The strip or cell has an accessible name in words; glyphs are `aria-hidden`. A visible legend is on the same view, and Peek shows the words on focus. |
| Diffs | Text | Added, removed and changed lines carry the words "added", "removed", "differs" for assistive tech, not only color and glyphs. |

## Keyboard and shortcuts (WCAG 2.1.4)

- **Global commands use a modifier**: Ctrl/Cmd+K palette, Ctrl/Cmd+P go to anything, Ctrl/Cmd+G go to address, Alt+← / Alt+→ back and forward, F6 / Shift+F6 cycle regions (header, navigator, center, evidence, dock), Ctrl/Cmd+J toggle dock.
- **Links share one grammar** (see Linked views): Enter goes, Shift+Enter opens beside, Alt+↓ peeks, K keeps, Shift+F10 reveals in, Ctrl/Cmd+Enter opens a browser tab.
- **Single-character keys are focus-scoped**: j/k, x, Space, typeahead and the letter commands work only while focus is inside a list, grid or listing, and never in text fields.
- **Every shortcut can be turned off or remapped** in Keyboard settings. Menus and tooltips show the current binding, and controls expose it with `aria-keyshortcuts`.
- Screen-reader browse modes are respected: letter commands never fire while a virtual cursor mode is plausible (focus on the document body).

## Live regions (WCAG 4.1.3)

One polite status region and one assertive alert region per page.

- **Polite**: job transitions (started, finished, failed, cancelled), decision outcomes after their terminal result, import accepted, result counts, stale and reconnecting notices, "N changes since you looked" summaries.
- **Assertive**: only conflicts and ambiguous command outcomes that block the action in hand.
- Never announce each poll, heartbeat or log line. Announce transitions once.

## Content on hover or focus (WCAG 1.4.13)

Peeks and hover cards are **dismissable** (Esc), **hoverable** (the pointer can move onto them) and **persistent** (they stay until dismissed, focus leaves, or the pointer leaves both trigger and card). They open on focus as well as hover, never steal focus, and never contain the only copy of information that is not reachable another way. The `title` attribute is never the only carrier of meaning.

## Targets and reflow

- Every target is at least 24×24 CSS px (WCAG 2.5.8); below 700px, 44px.
- Content reflows to 320 CSS px at 400% zoom by switching to the single-pane layout; only code rows, matrices and diagrams scroll horizontally, each in its own container.
- No fixed heights with `overflow: hidden` around text; text survives WCAG 1.4.12 spacing overrides.

## Motion, time and updates

- `prefers-reduced-motion` removes all motion and shows before/after states.
- Auto-updating regions (dock, log tails, heartbeats) have a **Freeze updates** control (WCAG 2.2.2); frozen regions say "Frozen at 14:02" and resume on request.
- No time limits on reading or deciding. Pending decisions never expire silently.

## Diagrams

- Every diagram SVG has `role="img"`, `lang`, a `<title>` and a 2–4 sentence `<desc>`, and links a generated text outline as its primary accessible form.
- Diagram text colors are all 4.5:1 or better on their grounds. Two pairs are forbidden: identity ink on identity fill (4.48:1) and `ink-muted` on any family fill.
- Family, gate, lock and edge type are always written as words as well as drawn in color, dash or shape.
- In-app renderings of diagram components use the app type scale (≥11px labels, ≥12px body), never the sub-12px `dia-*` sizes, which exist only for the fixed-size print canvas.
