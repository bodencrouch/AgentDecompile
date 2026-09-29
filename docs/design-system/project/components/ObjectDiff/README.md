# ObjectDiff

Verification drawn as the work: target and rebuilt (candidate) instructions aligned by the comparison receipt, with changed operands, registers, bytes and relocations marked, in one grid of row header, target, candidate and state.

**Use it** in the Recovery workspace beside SourceRepairDiff, as the secondary pane when an ImageDeltaMap region or a SourceRepairDiff line lands on the Listing (35 typed links), and in SplitCompare's target-vs-rebuilt form.

**Consumer provides** the exact object pair (target build and address range, candidate revision and its compile), aligned rows with the target address of each, the alignment anchors, relocation interpretation, and the comparison receipt with its job, basis and the source revision it was compiled from.

- **One grid, four columns:** the target address (row header), the target instruction, the candidate instruction, and a state cell whose word is "same", "differs", "added", "removed" or "unchanged lines". Differing operands are marked bold with the `fact-stale` underline, and a differing row carries `±` plus the word "differs" (SplitCompare vocabulary). Relocation-aware equality is written on the row where it applies ("same · relocation-aware").
- **Claim boundary.** The header says "local zero ≠ full-image or behavior proof". Target rows are labelled "aligned by ObjectDiff receipt 3e10 · aligned ≠ equivalent"; rebuilt rows come from that compile's line table ("rebuilt r15 · line table"). If the source changed since that compile, the header reads "◷ compiled from r14; source is r15" and the rows are marked historical, never shown as current (35 Reflection, proof wells).
- **Linked cursor over anchors.** Moving in the grid keeps the SourceRepairDiff line and the Listing row in step only through the recorded anchors and the line table; between anchors the other view marks the nearest preceding anchor and says "rows between anchors are not paired". Nothing is inferred from order or offset.
- **Differences.** F7 / Shift+F7 step differences ("Difference 1 of 3: 0041b22e differs"), with toolbar buttons and the palette's "Next difference" as the other paths. Runs of equal rows collapse to "▸ 12 unchanged lines · 0041b214–0041b22b · Expand" and expand in place.
- The ObjectDiff row is also where a SourceRepairDiff line and an ImageDeltaMap region land: the linked row is focused and marked.
- Fresh comparisons are distinct from historical receipts (ProvenanceStamp). A local zero is not full-image or behavior proof.
- Both surfaces render the same grid and words from the same stored comparison receipt; nothing is compiled or compared to draw it.

**Linking**

- **Publishes:** nothing by itself. Enter on a target address is Go (the Listing at that build and address, one stop). Open beside holds the pair with its basis (`hold=receipt:3e10@build-a~b7e2`).
- **Follows:** the primary entity and build (the object pair recorded for them), after the settle; holdable.
- **Targets rendered:** a target row's address → the Listing at that build and address · a relocation target → the Code Browser at that symbol · the comparison receipt → its receipt card · the producing job → the dock Jobs record · the basis → the ProvenanceStamp detail · a candidate row → its SourceRepairDiff line (`f=src.line:resource.c:41`).
- **Peek source:** the stored comparison receipt rows; nothing is compiled or compared again.
- **Absent copy:** "not compiled · no generated object" · "no comparison receipt" · "No address mapping for line 7" · "◷ compiled from r14; source is r15".
- **Target-size exception:** address links sit one per 18px code row and use the code-well inline exception; rows are reached by row focus and the 44px row-menu button with a coarse pointer.

**Keyboard**

- A read-only APG Grid with one tab stop and roving focus on the row: ↑/↓ move by row, → enters the row's cells and ←/→ move between them, Home/End go to the first and last cell, Ctrl+Home/Ctrl+End to the first and last row, PageUp/PageDown by a page.
- F7 / Shift+F7 next and previous difference; Enter or Space on "unchanged lines" expands it; Enter on an address link goes; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the one link menu.
- Esc follows the one order in `keymap.json` `escapeOrder`.

**Accessibility**

- `role="grid"` with `aria-readonly="true"`, named "Object diff, ResourceRef::Resolve, target build-a, candidate r15", with columns row header (target address), target, candidate and state. Each row's name is its template: "0041b22e, target jz short 0041b230, candidate jz near 0041b230, differs". Glyphs are `aria-hidden`; the state word is text, so a change reads without color or mark.
- The row template follows the one per-viewer Screen-reader verbosity value in View settings.
- **Accessible View** (Alt+F2, or the palette, the Help menu and the pane-header button) opens the diff as exact text, each line prefixed with its word ("differs", "added", "removed"), with the ProvenanceStamp text of the receipt.
- F7 steps are announced once ("Difference 1 of 3: 0041b22e differs"); nothing is announced on scroll.

**Removes switching:** it serves J34 (from a whole-image delta to its object diff, 4 → 1) and J39 (iterating on a repair, 4 → 1), both credited to typed links (U171) in the plan ledger.
