# XrefPanel

The References section: incoming and outgoing references for the token under the caret or for the whole line, filtered by kind, on this build or on every build's counterpart. It has three modes (References, Calls and Slots) and follows the selection until kept.

**Use it** in one placement, the CodeBrowser rule. When the evidence rail is open, References (with its Calls and Slots modes) and Outline live there as the fifth rail section. With the rail collapsed, References sits beside the code when the Code Browser is at least 880px wide, and under it otherwise. Below 700px it is the "References" tab of the Code Browser's single-view tablist (Listing · Decompile · Hex · Graph · References). It is never in the dock and never an analysis tab.

**Consumer provides** the scope target (token or line) with its build and address; references from existing analysis (direction, kind, from address, containing function, one-line snippet); counts per direction and kind; for All builds, each counterpart's LocatorGlyph, address, count and read time, or its not-loaded or unresolved state; for Slots, the stored ladder E results for the vtable under the cursor; and the index generation and read time.

- **Header**: "References to ‹token›" or "References on line ‹address›", the scope, build, follow state ("Follows · as I move" or "Follows · on Enter") and **Keep** (`aria-pressed`, constant name). A kept section stops following, says "Kept · not following selection" and offers **Follow selection**. Kept sections are cards, never held panes.
- **Modes** are manual-activation tabs, References · Calls · Slots, carried as `f=xref.mode:refs|calls|slots`. Calls is the CallHierarchy treegrid. Slots is described below.
- **Toolbar**: Scope (Token | Line), Direction (Incoming | Outgoing, each with its count), Kind chips (call, jump, pointer, read, write, each with its count; an unchecked chip shows an empty box and `ink-muted` text) and Builds (This build | All builds). Pressed toggles are bold `ink-strong` with a 2px `tab-active-rule`, never color alone.
- Rows are 28px: direction glyph and word (← in, → out), kind, the from address as an `address` link that carries its build, the containing function as a link, and a one-line mono snippet in `ink-muted`. The primary row uses `row-selected-bg` plus the 3px `accent` bar.
- **All builds** groups rows per build under a row-group header with the LocatorGlyph and its word. Counterpart rows exist only through recorded identity edges, and the header shows the edge word (accepted or candidate). A counterpart whose program is not open says "Not loaded. Open build-c to read its references." and fetches nothing. An unresolved counterpart says so in words and lists nothing; ambiguous and contested say the word with a link to the ladder evidence; a blank is never filled with a guess.
- "N more on build-b" is a link that shows the full list filtered in place. Going to another build is always an explicit Go, never a side effect of following the selection.
- **XREF[n] hints** in the Listing are typed links (Linked views): Enter focuses this section at that build and address, Line scope, incoming, without moving the primary location.
- **Stepping** with `]` and `[` (or the section's Previous and Next buttons) moves the code cursor while focus stays in the code well.
  - The first step snapshots the list and keeps the section: "Kept · stepping references to ‹token› · 3 of 12 · as listed 14:02", carried as `keep=xref:‹token›@‹build›`. It stops following while stepping; Follow selection, or Esc inside the section, ends stepping.
  - The first step pushes one history stop from the origin and later steps use replaceState, so one Alt+← returns to the origin.
  - Steps stop at either end and say so. They never wrap, never change build (All builds rows are not stepped; each needs its own Go) and never touch the active worklist.
- **Slots** (ladder E). Rows are vtable slots aligned by stored ladder E results: RTTI, the constructor's vtable-store decode, slot matched by method identity, and dispatch by handler identity. Each build column shows its own slot index, target and caller count, or "slot unresolved on build-c". Rows are never aligned by index.
  - One owner: the ReadinessMatrix slots mode owns slots × builds. This mode renders the same rows at rail width and links "Open slots matrix" (`panel=readiness` with `type=‹Class›::vtable`).
  - When the cursor is not on a vtable, the Slots tab stays listed, `aria-disabled`, with "Cursor is not on a vtable".
  - It reads stored ladder E results only.
- It reads only existing analysis and the stored cross-build index. It never analyzes, imports or opens a program. The footer names the source and the read time.
- **Stale responses never land.** Each read carries the selection generation. When the selection changes, the old rows stay dimmed with "Loading references to ‹token›", and a late response for the old target is dropped. `aria-busy` is set on the section only while it does not hold focus.
- A refresh of the same target keeps focus, scroll and the selected row.
- Narrow: per-build columns collapse to "on 3 of 5 builds" at 320×256, with the list in the row's Peek.
- Both surfaces use the same reference read and the same grid; the static 8080 surface may drop the kind chips' counts, never the words.

**Linking**

- **Publishes:** the primary location on Enter on a row (Go, one history stop; focus lands on the Listing row at the from address). Stepping publishes `keep=xref:…` and one stop from the origin, then replaceState. Keep publishes `keep=xref:…` (replaceState). Mode and direction are `f=xref.mode:` and `f=xref.dir:` (replaceState when toggled); scope, kind and builds are view state of the section.
- **Follows:** the primary selection's token or line after the settle, unless kept or stepping. Not holdable; it is kept as a card.
- **Targets rendered:** from address → the Code Browser at that build and address · containing function → the Code Browser at the function · counterpart group header → Code Browser for that build, with its edge word · "N more" → the list filtered in place · "Open slots matrix" → the ReadinessMatrix slots mode. Link names read "Address 0041a47c, build-a".
- **Peek source:** Alt+↓ on a row reads its cached listing lines (the full snippet), on a slot row the stored ladder E result, and on a group header the counterpart Peek. Nothing is fetched.
- **Absent copy:** "Not loaded. Open build-c to read its references." · "unresolved on build-d" · "ambiguous" or "contested · no winner" with a ladder link · "slot unresolved on build-c" · "Cursor is not on a vtable" · "not indexed here".
- **Target-size exception:** none. Toggles and chips are 24px and rows 28px; 44px below 700px and with a coarse pointer, where each row has one 44px row-menu button.

**Keyboard**

- APG Grid with one tab stop: ↑/↓ rows, ←/→ cells, Home/End row start and end, Ctrl+Home/Ctrl+End first and last row, PageUp/PageDown.
- Enter on a row goes. Shift+Enter opens it beside (a Held pane; "Open beside (new window)" on 8080 without split panes). Alt+↓ peeks. Shift+F10 opens the one link menu.
- While focus is inside the grid only, `i` and `o` switch direction and `t` toggles token and line (`refs.incoming`, `refs.outgoing`, `refs.scope`); after `g`, the next key belongs to the leader. From a code well, `x` focuses this section and `]`/`[` step. All are remappable or can be turned off (WCAG 2.1.4). As in every grid, typeahead starts with `/` into a visible filter field, because plain letters are commands.
- The mode tabs use manual activation (Enter or Space). The toolbar comes before the grid in Tab order. Esc follows the one Esc order in the Keymap section.

**Accessibility**

- `role="grid"` named for its content ("Incoming references to ResourceRef::Resolve, all builds") with `aria-rowcount` when virtualized. Build groups are row groups headed by `th scope="rowgroup"`; columns have `th scope="col"`.
- A row reads as a sentence: "in, call, 0041a47c, Actor::LoadFromTemplate, call ResourceRef::Resolve". Direction glyphs are `aria-hidden`; the word is visible.
- The count is announced once in the polite region when the target or a filter changes ("12 incoming references on build-a"), never on refresh. Each step is announced once ("Reference 3 of 12"), and the end stop once.
- Changing mode, scope, direction, kind or builds changes only this section's rows (WCAG 3.2.2).
- `scroll-padding-block` keeps the focused row clear of the sticky header (2.4.11). Truncated snippets are complete in the row's Peek.

**Removes switching:** J09 (follow a cross-reference and return) goes from 4 view switches to 0, leaving 1 region move and 1 Alt+← back; below 700px, 2 per reference by tab or 0 with `]`/`[`. J14 (a vtable across builds) goes from 6 to 2 through Slots. The ledger credits both to U177.

**Parity extensions (2026-09-29)**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): L09, L30, S07.

- **Display options (L09).** Group by function, the ref-type letter (READ, WRITE, CALL, JUMP, DATA as a word or its first letter), sort order, namespace prefix and the maximum shown in the Listing's XREF hint are per-viewer options in ListingFieldLayout's XREF field settings (OptionsPanel's Cross-reference hints row only links there). The panel and the Listing hint read the same values; the panel's header menu links **Cross-reference options…**.
- **Thunk references (L30).** A **Show thunk references** filter chip adds references that arrive through thunks, each row marked "via thunk ‹name›" (`resolve-thunk`).
- **Instructions from and data from (S07).** Beside incoming and outgoing references, the Outgoing direction splits into "instructions from" and "data from", as Ghidra's Symbol References panel does.
- **Delete reference (L30, S07).** A reference row's link menu has **Delete reference…** (a catalog action). It arms the ActionStrip with that one reference on that build (from, to, kind, operand) and confirms through ConfirmDialog because it is destructive; a checked set of references is one batch dialog with the count. It needs the build's writer, may return a modification conflict, and is never propagated to counterparts. Until the catalog offers it, the item is `aria-disabled` with "Not available on this server yet. References still read. · What this server offers".
- In All builds mode, deletion stays per build: the per-build columns never offer a cross-build delete. The preview is unchanged; the additions are a chip, a direction split and a link-menu item.

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- Key (moved text): "≠: what never happens. Keys: Enter go · Shift+Enter open beside · Alt+↓ peek · Shift+F10 link menu · ] [ step."
- ○ not loaded: "Not loaded. Open build-c to read its references."
- ≠ hover (chip removed): "Nothing is fetched on hover or when this panel follows the selection."
- ◌ tried 7: "unresolved on build-d · nothing to list. Root unresolved on this build; members tried: 7."
- +1 stop: "The first step pushed one stop; later steps replace it, so one Alt+← returns to the origin."
- ≠ wrap, ≠ build (chips removed): "Stops at either end · never wraps · never changes build"
