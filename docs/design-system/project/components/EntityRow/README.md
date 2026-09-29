# EntityRow

A dense row in the single Functions list: address, name with its provenance tier, logical identity hint, the compact seven-fact strip, and the OutcomeCell of the last verb run on it.

**Consumer provides** the concrete address in the inspected build, the display name and winning name tier, the logical id and counterpart count when accepted, the seven fact states with their receipts, the latest job for this row's exact target (if any), and selected/checked state.

- Address in `address`, `type-code-small`; the whole address cell is the link. The one primary item uses `row-selected-bg` plus the 3px bar; secondary text on it becomes `ink`.
- The name is the row header and a link; its tier ("debug info") is text, and Alt+↓ on the name peeks NameProvenance.
- The fact strip is the FactBadge compact form: seven glyphs in fixed order inside **one button that opens a Peek** (no tooltip). It replaces the retired none/asm/C and none/obj/linked bars.
- **OutcomeCell** column: the compact TaskLifecycle for the latest job this viewer submitted for the row's exact bound target, or a job whose own record names it: "a3f9 · running · unit 3 of 6", then the terminal word; under "finished" the facts whose receipts it wrote. After a 202 it reads "pending · job c4e1". Nothing is optimistic; lifecycle never merges into the facts.
- A function without an accepted identity says "no identity"; never invent a counterpart.
- The batch column is a checkbox plus a count chip in the header, never a second fill. Esc never clears the checked set; the count chip's × or Clear checked does, with Undo. A FilterChip ("Changed by a3f9 ×") above the grid names any job filter applied from the dock.

**Linking**

- **Publishes:** `entity`, `build` and `addr` on Enter (Go, one history stop). Arrowing moves focus and, after the settle, the selection (replaceState). `f` for typed filters and FilterChips (replaceState). The checked set is never in the URL.
- **Follows:** `build` (addresses are in the inspected build), `f`, `q` and the active worklist (`wl`); following panes update after the settle. The list is not holdable.
- **Targets rendered:** address and name → the Code Browser at that build and address · logical id ("#88 · 4 builds") → Compare with the CounterpartMatrix · fact strip → a Peek whose facts link to their receipt cards · OutcomeCell job id → the dock Jobs record (Alt+↓ peeks its ActivityRecord) · a name finished under "finished" → its new receipt. Link names read "Address 0041b210, build-a"; "Job a3f9, match siblings, running".
- **Peek source:** the cached listing lines, fact rows, name candidates and job records already loaded for that row; nothing is decompiled on hover.
- **Absent copy:** "no identity" · "outcome in dock · job a3f9" (job record names no bound target) · no OutcomeCell before any verb ran on the row.
- **Target-size exception:** none. Cells are 24px; the fact strip is one 24px button. With a coarse pointer each row adds one 44px row-menu button carrying the link menu.

**Keyboard**

- APG Grid, one tab stop: ↑/↓ rows (j/k when focus-scoped keys are on), ←/→ cells, Home/End, Ctrl+Home/End, PageUp/PageDown. Enter goes; Shift+Enter opens beside; Alt+↓ peeks the focused cell's target; Shift+F10 opens the one link menu.
- Space or x checks the focused row; Shift extends. Focus-scoped `.` repeats the armed ActionStrip action on the focused row; `w` makes a worklist of the filtered rows. Typeahead filters by name.

**Accessibility**

- `role="grid"` named "Functions, build-a"; the name cell is `th scope="row"`; checkbox cells are labels "Select ‹entity›". The OutcomeCell is referenced from its row by `aria-describedby`; job transitions are announced once, politely, never per poll.

**Removes switching:** opening the dock after every run, the Evidence workspace to read facts, and the Compare workspace to check identity (J21, J22).
