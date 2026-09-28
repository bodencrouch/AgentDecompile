# FactBadge

One named proof fact with its state, glyph and word.

**Consumer provides** the fact name (Compiles, ABI, Tested behavior, Local match, Linked match, Contribution, Whole-file equality) and its state: `passed`, `failed`, `stale`, `unknown`, `unsupported` or `not_run`, plus a link to the receipt when one exists.

- Glyphs: ✓ passed, ✕ failed, ◷ stale, ? unknown, ⊘ unsupported, ○ not run. Unknown, unsupported and not run use a dashed frame in `fact-unknown`.
- Color touches only the glyph. The word is `ink`; the fact name is `ink-muted`.
- List facts side by side. Never sum them into a score or a single "verified" badge.
