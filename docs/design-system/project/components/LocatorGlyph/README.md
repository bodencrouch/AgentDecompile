# LocatorGlyph

Where one entity lands in one build: the closed locator status set, with observed status on its own axis.

**Consumer provides** per entity × build the status (`resolved`, `pinned`, `degraded`, `ambiguous`, `unresolved`, `contested`), the member used or reason, the landed address or addresses, and `observed_status` separately.

- ● resolved(member) `ink-strong` · ◎ pinned(member) `address`, labelled `module_rva` or `section_offset` (non-portable) · ◑ degraded(member, reason) and ⋯ ambiguous `fact-stale` · ◌ unresolved `fact-unknown` · ⇉ contested `fact-failed`.
- Contested means two locators land on different addresses in one build, both with evidence, and there is no winner. Both addresses are shown as links; neither is preferred.
- `observed_status` follows a thin rule and never overwrites pack status. Display order: contested, unresolved, ambiguous, pinned, degraded, resolved.
- There is no tooltip. Alt+↓ on a locator (in a matrix cell, the CounterpartStrip, an XrefPanel group header or a Peek) opens a Peek of the ladder run: members tried in family order, each reason, the member used and the terminal OutcomeTag. The glyph always sits beside its word.

**Linking**

- **Publishes:** nothing by itself; its host (CounterpartMatrix, ReadinessMatrix, CounterpartStrip) publishes on Enter.
- **Follows:** the entity and build of its host cell; holdable only with its host.
- **Targets rendered:** a resolved, pinned or degraded address → the Code Browser at that build and address (the counterpart), with its edge word (accepted or candidate) · ambiguous → the word plus a link to its ladder evidence (EvidenceRail) · contested → the word, a ladder link, and both candidate addresses as links marked "no winner"; Enter on the cell opens both as held panes "contested · no winner". Link names read "Counterpart ResourceRef::Resolve, build-c, pinned module_rva, non-portable, candidate".
- **Peek source:** the stored ladder run for that entity × build (members tried, reasons, member used, terminal OutcomeTag).
- **Absent copy:** "unresolved" and "absent" are plain words with no link · "Not loaded. Open build-c to read it."
- **Target-size exception:** in dense cells the whole cell is the target (at least 24px); in lists each locator is a 24px row.

**Accessibility**

- Glyphs are `aria-hidden`; the status word is visible or, in dense cells, in `.sr-only` beside the glyph and in the cell's accessible name ("build-c: pinned, module_rva, non-portable; observed: not run").
