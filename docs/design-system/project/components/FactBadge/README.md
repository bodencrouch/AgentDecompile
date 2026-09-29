# FactBadge

One named proof fact with its state, glyph and word; in rows, the compact seven-glyph FactStrip.

**Consumer provides** the fact (Compilation, ABI checks, Tested behavior, Local match, Linked match, Replacement contribution, Whole-file equality), its state (`passed`, `failed`, `stale`, `unknown`, `unsupported`, `not_run`) and, when one exists, the deciding receipt with its producing job and stage.

- Glyphs: ✓ passed · ✕ failed · ◷ stale · ? unknown · ⊘ unsupported · ○ not run. Unknown, unsupported and not run use a dashed frame in `fact-unknown`.
- Color touches only the glyph (`fact-passed`, `fact-failed`, `fact-stale`, `fact-unknown`); the word is `ink`, the fact name `ink-muted`.
- The strip (`.ad-facts`) keeps the fixed order above. There is no tooltip: the whole strip is **one button that opens a Peek** (WCAG 2.5.8: seven 14px glyphs join one target at least 24px tall). The button's accessible name carries every fact and state in words; the Peek lists each fact with its receipt link, producing job and StageChip.
- A full badge with a deciding receipt is a link to that receipt; the fact name is underlined, the glyph is not. A fact without a receipt is plain text and says "no receipt".
- Never sum facts into a score, bar or single "verified" badge. Legacy `real_c=1` shows as Compilation only. Job lifecycle (OutcomeCell) is never merged into facts.

**Linking**

- **Publishes:** nothing. Facts are derived evidence; activating one never changes the selection.
- **Follows:** the entity × build of its host (row, sticky header, Peek or card), after the settle; holdable only with its host, and a held pane or Kept card keeps its own facts.
- **Targets rendered:** fact → the receipt card that decided it, in the evidence rail (`receipt=`) · in the Peek: the producing job → the dock Jobs record (`job=`), its StageChip → the PipelineMap node, a stale fact's basis → the ProvenanceStamp detail and what changed since. Link names read "Fact Local match, passed, receipt 3e10, build-a".
- **Peek source:** the fact rows and receipt headers already stored for that entity × build; nothing is fetched.
- **Absent copy:** "not run · no receipt" · "unsupported · no receipt" · "unknown · legacy record" · "Stale · basis changed r14 → r15" · "Not loaded. Open to read it."
- **Target-size exception:** none. The strip is one button at least 24px tall; full badges are 24px rows; links inside Peek rows sit on rows 24px apart.

**Keyboard**

- The strip button: Enter, Space or Alt+↓ opens the Peek; Esc closes it and focus returns to the strip. Focus rest (800ms) opens it as well, without moving focus.
- Inside the Peek, receipt, job and stage links follow the linked-views grammar (Enter go, Shift+Enter open beside, Shift+F10 the one link menu); K keeps the Peek as a card.

**Accessibility**

- The strip button has `aria-haspopup="dialog"` and `aria-keyshortcuts="Alt+ArrowDown"`; `aria-expanded` and `aria-controls` are present only while its Peek is open. Its glyphs are `aria-hidden`.
- Keep inside the Peek is an `aria-pressed` button; its K works only while focus is inside the Peek.
- A visible legend of the six glyphs sits on the same view as any strip (Workstation status line or the grid header).
- The Peek follows WCAG 1.4.13 (dismissable, hoverable, persistent) and never holds the only copy: the evidence rail's Facts section shows the same words.

**Removes switching:** opening the Evidence workspace, then the receipt list, then the Jobs dock to learn why one fact is in its state (J02, J35).
