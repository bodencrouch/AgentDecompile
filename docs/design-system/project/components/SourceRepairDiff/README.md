# SourceRepairDiff

Source recovery drawn as the work: the actual source change beside the compiler diagnostic or semantic evidence it addresses.

**Consumer provides** the candidate revision pair, the diagnostic with its file and line, the exact compiler, flags and ABI, the retry history, the compile receipt and job, and the line-to-instruction mapping when one exists.

- Diff well: removed lines on `lane-fault-fill` with − and the hidden word "removed", added lines on `rep-candidate` with + and "added". The diagnostic sits above in mono.
- The diagnostic's `file(line)` is a link to its line in this diff; a changed line links to the target instructions it maps to (Listing) and to its ObjectDiff row, so diagnostic → line → target → object row is one path.
- **Linked cursor** with the ObjectDiff; F7 / Shift+F7 step changed lines; unchanged runs collapse.
- **BeforeAfterBand variant**: after an edit's job reaches its terminal result, the re-read change shows in place as a before/after pair with "changed by job ‹id›"; nothing is shown before the re-read.
- Repairs explain preserved machine behavior. A cleaner decompile is hypothesis refinement, not validation.
- Retry history lists deterministic helpers first, then one bounded LLM cleanup, with each exact proposal recorded.

**Linking**

- **Publishes:** nothing; following a diagnostic link moves focus to its line inside this view (replaceState).
- **Follows:** the primary entity and build (their candidate revision pair), after the settle; holdable (a held pane keeps its revision pair and basis).
- **Targets rendered:** diagnostic `file(line)` → the SourceRepairDiff line in Recovery · a changed line → the Listing at its mapped address in that build and the ObjectDiff row · the compile receipt → its receipt card · the job → the dock Jobs record · the helper → its catalog entry in words.
- **Peek source:** the stored candidate revisions and compile receipt; nothing is compiled.
- **Absent copy:** "No instruction mapping for this line." · "no compile receipt for r15" · "helper not recorded".
- **Target-size exception:** spacing: one link per diff row, at the row end.

**Keyboard**

- F7 / Shift+F7 next and previous change; links follow the linked-views grammar.

**Accessibility**

- Lines carry the words "added", "removed" and "differs" for assistive tech; the diagnostic is text, not only the fault glyph.

**Removes switching:** opening the build log, the source file and the Listing in turn to iterate on a repair (J39).
