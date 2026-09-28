# LocatorGlyph

Where one logical entity lands in each build, and how its identity edges stand.

**Consumer provides** one lane per build with the locator state: `resolved`, `pinned`, `degraded` (with reason), `ambiguous`, `unresolved` or `contested`, plus the identity-edge state `candidate`, `accepted`, `rejected` or `unresolved`.

- Glyphs: ● resolved, ⌖ pinned (label `module_rva` or `section_offset`), ◑ degraded, ⋯ ambiguous, ○ unresolved, ⇉ contested (two addresses, both evidenced, no winner).
- Edges: accepted is a solid `lane-identity-ink` line, candidate dashed, unresolved dotted in `fact-unknown`, rejected struck in `fact-failed`.
- Locator, observed status and edge state are separate axes. Never fold them into one badge, and never fill an unmatched build with a guess.
