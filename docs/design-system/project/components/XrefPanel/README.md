# XrefPanel

Cross-references for the current selection, always visible: incoming and outgoing references for the token under the caret or for the whole line, filtered by kind, on this build or on every build's counterpart.

**Use it** docked beside or under the Listing and Decompile, not as an analysis tab. It follows the selection until kept.

**Consumer provides** the scope target (token or line) with its build and address; references from existing analysis (direction, kind, from address, containing function, one-line snippet); counts per direction and kind; and for all builds, each counterpart's LocatorGlyph, address, count and read time, or its not-loaded or unresolved state.

- Header: "References to ‹token›" or "References on line ‹address›", the scope, build, sync state and **Keep**. A kept panel stops following, says "Kept · not following selection" with a broken-chain icon, and offers **Follow selection**.
- Toolbar: Scope (Token | Line), Direction (Incoming | Outgoing, each with its count), Kind chips (call, jump, pointer, read, write, each with its count; unchecked chips are dashed), and Builds (This build | All builds). Pressed toggles are bold `ink-strong` with a 2px `tab-active-rule`, never color alone.
- Rows are 28px: direction glyph and word (← in, → out), kind, the from address as an `address` link, the containing function as a link, and a one-line mono snippet in `ink-muted`. The primary row uses `row-selected-bg` plus the 3px `accent` bar.
- All builds groups rows per build under a row-group header with the LocatorGlyph and its word. A counterpart whose program is not open says "○ Not loaded. Open build-c to read its references." and fetches nothing. An unresolved counterpart says so and lists nothing; a blank is never filled with a guess.
- "N more on build-b" is a link. Going to another build is always explicit and announced, never a side effect of following the selection.
- It reads only existing analysis and the stored cross-build index. It never analyzes, imports or opens a program. The footer names the source and the read time.
- Stale responses never land. Each read carries the selection generation. When the selection changes, the old rows go at once, the header names the new target with "… Reading references", and a late response for the old target is dropped.
- A refresh of the same target keeps focus, scroll and the selected row.
- Both surfaces use the same reference read and the same grid; the static 8080 surface may drop the kind chips' counts, never the words.

**Keyboard**

- APG Grid with one tab stop: ↑/↓ rows, ←/→ cells, Home/End row start and end, Ctrl+Home/Ctrl+End first and last row, PageUp/PageDown.
- Enter on a row follows it: the selection moves to the from address, history is pushed and focus goes to the Listing at that line. The panel then follows the new selection unless it is kept.
- Alt+↓ peeks the row's target; Shift+Enter opens it to the side.
- Shift+F10 opens the row menu: Open, Open to the side, Peek, Keep panel, Copy link, Copy address.
- While focus is inside the grid only, `i` and `o` switch direction and `t` toggles token and line. These can be remapped or turned off (WCAG 2.1.4).
- The toolbar comes before the grid in Tab order. Toggles are buttons with `aria-pressed`; Space toggles a kind chip.

**Accessibility**

- `role="grid"` named for its content ("Incoming references to ResourceRef::Resolve, all builds") with `aria-rowcount` when virtualized. Build groups are row groups headed by `th scope="rowgroup"`; columns have `th scope="col"`.
- A row reads as a sentence: "in, call, 0041a47c, Actor::LoadFromTemplate, call ResourceRef::Resolve". Direction glyphs are `aria-hidden`; the word is visible.
- The count is announced once in the polite region when the target or a filter changes ("12 incoming references on build-a"), never on refresh (WCAG 4.1.3).
- Changing scope, direction, kind or builds changes only this panel's rows. It never navigates or switches the build (WCAG 3.2.2).
- Toggles and chips are 24px and rows 28px; 44px below 700px, where the panel becomes a Navigate rail view. `scroll-padding-block` keeps the focused row clear of the sticky header (WCAG 2.4.11).
- Truncated snippets are complete in the row's Peek.

**Removes switching:** the Xrefs analysis tab, the call-tree dialog and the Compare workspace opened only to ask who calls this on the other builds.
