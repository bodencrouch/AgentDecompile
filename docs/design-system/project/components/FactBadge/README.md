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
- **Follows:** the entity × build of its host (row, sticky header, Peek or evidence card). In a held pane or kept card it shows that pane's target, labelled Held or Kept.
- **Targets rendered:** fact → the receipt card that decided it, in the evidence rail (`receipt=`); inside the Peek, the receipt's producing job → the dock Jobs record (`job=`) and its StageChip → the PipelineMap node (`node=stage-7`); a stale fact's basis digest → the ProvenanceStamp detail and what changed since. Link names read type, target and state: "Fact Local match, passed, receipt 3e10, build-a".
- **Absent copy:** "not run · no receipt" · "unsupported · no receipt" · "unknown · legacy record" · "Stale · basis changed r14 → r15". Unloaded facts in a Peek say "Not loaded. Open to read it."

**Keyboard**

- The strip button: Enter, Space or Alt+↓ opens the Peek; Esc closes it and focus returns to the strip. Focus rest (800ms) opens it as well, without moving focus.
- Inside the Peek, receipt, job and stage links follow the grammar (Enter go, Shift+Enter open beside, K keep).

**Accessibility**

- The strip button has `aria-haspopup="dialog"`, `aria-expanded`, `aria-controls` and `aria-keyshortcuts="Alt+ArrowDown"`. Its glyphs are `aria-hidden`.
- A visible legend of the six glyphs sits on the same view as any strip (Workstation status line or the grid header).
- The Peek follows WCAG 1.4.13 (dismissable, hoverable, persistent) and never holds the only copy: the evidence rail's Facts section shows the same words.

**Removes switching:** opening the Evidence workspace, then the receipt list, then the Jobs dock to learn why one fact is in its state (J02, J35).
