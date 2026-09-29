# SourceRepairDiff

Source recovery drawn as the work: the actual source change beside the compiler diagnostic or semantic evidence it addresses, as one read-only grid of line, change word and text.

**Use it** in the Recovery workspace, where a compiler diagnostic `file(line)` lands (35 typed links), with ObjectDiff beside it.

**Consumer provides** the candidate revision pair, the diagnostic with its file and line, the exact compiler, flags and ABI, the retry history, the compile receipt and job, the compile's line table (source line → rebuilt rows), and the ObjectDiff alignment receipt (rebuilt rows → target rows) when one exists.

- Diff grid: removed lines on `lane-fault-fill` with "− removed", added lines on `rep-candidate` with "+ added", unchanged lines "same"; the change word is a visible column, not only a glyph or fill. The diagnostic sits above in mono.
- **The path is one chain of links, each labelled with its tier** (35 Reflection, proof wells): the diagnostic's `file(line)` → its line in this diff (`f=src.line:resource.c:41`) → the rebuilt rows through that compile's line table ("rebuilt r15 · line table") → the target rows through the ObjectDiff alignment receipt ("aligned by ObjectDiff receipt 3e10 · aligned ≠ equivalent"). If the source changed since that compile, the mapping reads "◷ compiled from r14; source is r15" and is never shown as current.
- **Linked cursor** with ObjectDiff over the line table and alignment anchors only; F7 / Shift+F7 step changed lines; unchanged runs collapse to "▸ 9 unchanged lines · 38–46 · Expand". The header says "local zero ≠ full-image or behavior proof".
- Edit outcomes in code wells (rename, retype, signature, storage) use BeforeAfterBand, which is its own component; this diff shows candidate source revisions only.
- Repairs explain preserved machine behavior. A cleaner decompile is hypothesis refinement, not validation.
- Retry history lists deterministic helpers first, then one bounded language-model cleanup, with each exact proposal recorded.

**Linking**

- **Publishes:** nothing; following a diagnostic link moves focus to its line inside this view (replaceState on `f=src.line:…` when already here; a Go from Logs pushes).
- **Follows:** the primary entity and build (their candidate revision pair), after the settle; holdable (a held pane keeps its revision pair and basis).
- **Targets rendered:** diagnostic `file(line)` → the SourceRepairDiff line in Recovery · a changed line → the rebuilt rows (line table) and the Listing at its target address in that build with the ObjectDiff row, each labelled · the compile receipt → its receipt card · the job → the dock Jobs record · the helper → its catalog entry in words.
- **Peek source:** the stored candidate revisions, the compile receipt and its line table; nothing is compiled.
- **Absent copy:** "No address mapping for line 42" · "no compile receipt for r15" · "helper not recorded" · "◷ compiled from r14; source is r15".
- **Target-size exception:** one link per diff row, at the row end, inside 18px code rows (the code-well inline exception); rows are reached by row focus.

**Keyboard**

- A read-only APG Grid with one tab stop and roving focus on the row: ↑/↓ by line, → into the row's cells (line, change word, text), ←/→ between them, Ctrl+Home/Ctrl+End to the first and last line, PageUp/PageDown by a page.
- F7 / Shift+F7 next and previous change; Enter on the row's mapping link goes; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the one link menu. Esc follows the one order in `keymap.json` `escapeOrder`.

**Accessibility**

- `role="grid"` with `aria-readonly="true"`, named "‹file›, candidate r14 to r15", with columns line (the row header), change word and text. Each row reads its template under the one per-viewer Screen-reader verbosity value: "Line 41, added, ref = (ResourceRef *)lookup(table, key); maps to target 0008301c". The words "added", "removed" and "same" are text; glyphs and fills are `aria-hidden` or decorative.
- The diagnostic is text, not only the fault glyph.
- **Accessible View** (Alt+F2, or the palette, the Help menu and the pane-header button) opens the diff as exact text with "+ added", "− removed" and "± differs" prefixes and the compile receipt's ProvenanceStamp text.
- F7 steps are announced once ("Change 1 of 1: line 41 added"); nothing is announced on scroll.

**Removes switching:** J39 iterate on candidate source repair, diagnostic → changed line → compile → object diff, 4 → 1, credited to typed links (U171) in the plan ledger.
