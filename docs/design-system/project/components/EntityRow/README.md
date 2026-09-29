# EntityRow

A dense row in the single Functions list: address, name with its provenance tier, logical identity hint, the compact seven-fact strip, and the OutcomeCell of the latest job whose record names this row's target.

**Consumer provides** the concrete address in the inspected build, the display name and winning name tier, the logical id and counterpart count when accepted, the seven fact states with their receipts, the latest job whose own record names this row's exact target (if any) with its submitter, and selected and checked state.

- Address in `address`, `type-code-small`; the whole address cell is the link. The one primary item uses `row-selected-bg` plus the 3px bar; secondary text on it becomes `ink`.
- The name is the row header and a link; its tier ("debug info") is text, and Alt+↓ on the name peeks NameProvenance.
- **The fact strip is one ≥24px button that opens a Peek**, never a link and never a tooltip. Per-fact receipt links live in that Peek and in the rail's Facts section. It replaces the retired none/asm/C and none/obj/linked bars.
- **OutcomeCell** shows the latest job whose own record names the row's target, and who submitted it: "a3f9 · running · unit 3 of 6 · by you", then a terminal word from the Job outcome vocabulary (finished, failed, cancelled). After HTTP 202 it reads "pending · job c4e1". Nothing is optimistic, client memory is never the source, and lifecycle never merges into the facts. With no such job, no cell is drawn.
- **Narrow widths.** At navigator widths the outcome renders as a wrapped second line under the name, never truncated, and only when a job exists.
- A function without an accepted identity says "no identity"; never invent a counterpart.
- **Checked set.** The batch column is a 24px checkbox cell plus a count chip in the header, never a second fill. Esc never clears the checked set; the count chip's × or Clear checked does, leaving "Checked set cleared (4) · Restore" beside the chip until the next check change. A program change clears it and says so first (Back's description) and after (one polite message).
- **Grid modifier precedence** (Linked views). In this checkable grid, Ctrl/Cmd-click toggles a row and Shift-click extends the checked set anywhere on the row, including its name link. Open beside is Shift+Enter or the link menu; a new browser tab is Ctrl/Cmd+Enter, middle-click or the menu.
- A FilterChip ("Changed by a3f9 ×", `f=changed:a3f9`) above the grid names any filter applied from a link.
- **Coarse pointer.** Each row has one 44px row-menu button carrying the one link menu (and Peek). There is no long-press. Below 700px every target is 44px.

**Linking**

- **Publishes:** `entity`, `build` and `addr` on Enter (Go, one history stop). Arrowing moves focus at once and, after the settle, the selection (replaceState). `f` for FilterChips (replaceState when removed; pushState when applied from a link). The checked set is never in the URL.
- **Follows:** `build` (addresses are in the inspected build), `f`, `q` and the active worklist (`wl`); following panes update after the settle. The list is not holdable.
- **Targets rendered:** address and name → the Code Browser at that build and address · logical id ("#88 · 4 builds") → Compare with the CounterpartMatrix · OutcomeCell job id → the dock Jobs record · a fact named under "finished" → its new receipt card. Link names read "Address 0041b210, build-a" and "Job a3f9, match siblings, running".
- **Peek source:** the fact strip's Peek reads the cached fact rows and receipts; the name's Peek reads cached name candidates (NameProvenance); the job link's Peek reads the stored job record as of the dock's last read. Nothing is decompiled or fetched.
- **Absent copy:** "no identity" · "in batch job a3f9 · per-row outcome not reported" · no OutcomeCell when no job record names the row · "No functions match ‘‹q›’ on build-a · Clear filter" (Clear filter clears `q`) · "No function inventory for build-e" (a StateNotice dead end with at most one prepared reuse action; the empty list never reimports or reanalyzes) · loading, "Reading functions for build-a…" with the previous rows dimmed.
- **Target-size exception:** the OutcomeCell's inline job link is 22px inside a 24px row, relying on the WCAG 2.5.8 inline exception; the whole address cell, the fact button and the checkbox cell are 24px. Everything is 44px below 700px and with a coarse pointer.

**Keyboard**

- APG Grid (row selection), one tab stop: ↑/↓ rows (j/k when focus-scoped keys are on), ←/→ cells, Home/End the first and last cell in the row, Ctrl+Home/End the first and last row. Enter goes; Shift+Enter opens beside; Alt+↓ peeks the focused cell's target; Shift+F10 opens the one link menu.
- Space or x checks the focused row; Shift+↑/↓ and Shift+j/k extend the range. Focus-scoped `.` rebinds the armed ActionStrip action to the focused row and focuses Run; it never posts. `w` collects the filtered rows as a worklist through the MarksList dialog.
- This grid binds single-letter commands, so typeahead starts with `/` into a visible filter field.

**Accessibility**

- `role="grid"` named "Functions, build-a"; the name cell is `th scope="row"`; checkbox cells are labels named "Check ‹entity›". The OutcomeCell is referenced from its row by `aria-describedby`; job transitions are announced once, politely, never per poll.

**Removes switching:** opening the dock after every run, the Corpus workspace to read facts, and the Compare workspace to check identity. J21 (5 → 2) and J22 (7 → 2) are credited to U184.
