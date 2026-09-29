# Show, don't tell

The layout shows; words explain on demand. A reverse engineer should read a view the way they read a listing: by shape, position and glyph, not by sentences.

## What may be visible text

- Names and identifiers: entities, builds, addresses, bytes, mnemonics, job and receipt ids, file names.
- Numbers: counts, percentages, sizes, offsets, times.
- Headers: view, pane, section and column titles.
- Labels of **at most three words** on controls, tabs, chips, menu items and state marks ("Create functions…", "reused", "≈ compile", "Not loaded").
- Evidence itself: code, logs, diffs, transcripts and source. It is content, not a label.

Nothing else is visible. An instruction, disclaimer, claim boundary, consequence, reason, basis, provenance note, empty-state explanation or scope statement is drawn, never written out in the layout.

## Where the words go

Every sentence still exists, word for word, in all of these:

1. **The accessible name or description** of the drawn element. It is always the full sentence; Screen-reader verbosity decides how much is spoken.
2. **A tip** on hover and on keyboard focus (`adv-tip`, `role="tooltip"`, referenced by `aria-describedby`). WCAG 1.4.13: it can be hovered, stays until dismissed and closes on Esc. A tip holds one or two sentences and may hold one link.
3. **The view's Key**: a `?` button in every view header (`adv-q`), listing every glyph, pattern and frame the view uses with its word.
4. **A Peek** for longer detail: a basis with its sample, members tried, a receipt.

On a coarse pointer, the row's 44px menu button opens the same text as a Peek; nothing depends on hover.

## Sentence to shape

| A sentence that says… | Is drawn as | Class |
|---|---|---|
| a share of one build's total ("812 of 1,144 starts, 71%") | a fraction bar and the percent | `adv-frac` |
| the same measure across builds, and which build differs | small multiples, one column per build on one scale; the differing build framed | `adv-sm` (`.out`) |
| a build that cannot be compared (another language) | a hatched empty track and ⊘ | `adv-nc` |
| a distribution (residues, sizes, depths) | a histogram with its axis ends | `adv-hist` |
| how one count splits into disjoint classes | a stacked bar with one pattern per class and a key with counts | `adv-stack`, `adv-skey` |
| a tree node's share of paths | a share line under the node | `adv-share` |
| "this is a hypothesis; basis: …" | the dashed chip with one or two words; the basis is its tip | `adv-h` |
| "backed by a witness or record" | the solid chip; the witness is its tip | `adv-w` |
| a claim boundary ("not evidence", "not accuracy", "not a recovery claim") | ≠ plus one word; the full boundary is its tip | `adv-bnd` |
| what a change will touch and what it leaves alone | a target map: one tile per build, written builds framed with the glyph and count, untouched builds dim and struck | `adv-tmap` |
| "undoable", "reused", "fresh", "stale" | the existing stamp or chip word; its detail is the tip | `ad-stamp`, `adv-w` |
| filters and parameters ("length at least 3, prefix 3") | key-value chips | `adv-chips` |
| "nothing here yet; do X" | one glyph with a tip, and the one next action as a button | `adv-empty` |
| "not available on this server yet" | the disabled control with ⊘; the reason and "What this server offers" are its tip | `adv-na` |
| "follows as you move" or "held" | the pane frame and the one state chip ("Follows", "Held · build-c") | HeldPane |

Glyphs keep their State vocabularies meanings; this guideline adds shapes, not new glyphs.

## Kept as words

- A ConfirmDialog title is verb + object ("Create 311 functions"). Its consequence is a target map plus chips, and the full consequence is the dialog's description.
- An error or refusal the operator must act on shows one line of at most six words ("Refused: basis changed") with its detail in a tip or Peek.
- Help, Accessible View, the shortcut sheet and the Key are text by design.
- Live announcements are spoken, not shown.

## Rules

- **One scale per comparison.** Bars and small multiples for builds share one scale in one view. A bar is one measure of one build: never a sum of separate facts, never an average across builds, never a score.
- **Never color alone.** Every shape is also a pattern, frame or glyph, and survives forced colors as `CanvasText` shapes.
- **Numbers stay exact.** The bar shows the share; the exact fraction is in the accessible name and tip, and a cut count still reads "≥500".
- **A quoted sentence in a component README** is the text of its tip, Key entry or accessible name. The visible layout follows this guideline.
- **Specimen captions** in previews (kickers) name the state in at most three words.
