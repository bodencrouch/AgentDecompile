# FactBadge

One named proof fact with its state, glyph and word; in rows, the compact seven-glyph FactStrip.

**Consumer provides** the fact (Compilation, ABI checks, Tested behavior, Local match, Linked match, Replacement contribution, Whole-file equality), its state (`passed`, `failed`, `stale`, `unknown`, `unsupported`, `not_run`) and the receipt link when one exists.

- Glyphs: ✓ passed · ✕ failed · ◷ stale · ? unknown · ⊘ unsupported · ○ not run. Unknown, unsupported and not run use a dashed frame in `fact-unknown`.
- Color touches only the glyph (`fact-passed`, `fact-failed`, `fact-stale`, `fact-unknown`); the word is `ink`, the fact name `ink-muted`.
- The strip (`.ad-facts`) keeps the fixed order above and names each fact and state in its tooltip and accessible label.
- Never sum facts into a score, bar or single "verified" badge. Legacy `real_c=1` shows as Compilation only.
