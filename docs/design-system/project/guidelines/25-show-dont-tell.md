# Show, don't tell

The layout is a picture; words explain it on demand. A reverse engineer reads a view the way they read a listing: by shape, position, glyph and number. Text in the layout is almost never a sentence. A tip explains what the user is looking at.

**The text-off test is the gate.** Hide every visible word that is not evidence, an identifier or a numeral. A reviewer must still be able to point to:

- the build that differs;
- every hypothesis;
- every build that cannot be compared;
- what a pending write touches, and whether it can be undone;
- the dominant class;
- every empty or unavailable state.

A view that fails is telling, not showing.

## Visible text

Nothing else is visible at rest.

| Kind | Limit | Example |
|---|---|---|
| Evidence: bytes, mnemonics, operands, addresses, code, logs, diffs, recorded comments | none; it is content | `83 EC ??` · `sub esp, imm8` |
| Identifiers: entities, builds, patterns, jobs, receipts, language ids | none; `translate="no"` | `build-d`, `P1`, `x86:LE:64` |
| Numerals | see Numbers | `71%`, `n 1,144`, `≥500` |
| View title | 3 words plus `· scope` | Function start patterns · corpus-alpha |
| Pane and section headers | 3 nouns plus `· scope`; no function words | Clipboard · build-a |
| Column headers | 1 word, or a drawn header | Sequence |
| Controls and menu items | a verb, or verb + object: 2 words plus an identifier | Create functions…, Gather build-c… |
| Tabs | 1 word plus a count | Clipboard 3 |
| State words | 2 words, only after a vocabulary glyph or frame | ◷ stale, ○ not gathered |
| Key-value chips | key 1 word, value 1 token | len ≥ 3 |
| Value legends | swatch, 2 words, count | undefined 311 |
| Form labels | 3 words | Destination |
| Axis ends | none | 0 · 15 |

- **A run fails** if it has four or more consecutive words that are not identifiers, a finite verb, a final period, or a colon followed by prose. The only exceptions are under Words that stay visible.
- **Budgets at rest**, with the Key collapsed:
  - at most 45 label words per view;
  - at most 10 label words per dialog;
  - at least as many drawn semantic marks as label words.

  Tabs, headers, controls, chips and legends count toward the budget. Evidence, identifiers and numerals do not.
- **Ghidra labels.** A command that mirrors a Ghidra command keeps Ghidra's full label in menus and the palette. The layout uses the short form.

## Words that stay visible

These never depend on hover, and none is a sentence.

- **Honesty words.** `unknown` is always a word. `reused`, `fresh` and `stale` are stamps. `absent` marks a missing counterpart in entity-mapping cells.
- **Confirm.**
  - The title is verb + count + object, at most 4 words ("Create 311 functions").
  - The consequence is drawn: the target map and the class stack.
  - The primary button repeats the count ("Create · 311").
  - The undo slot shows `↶ undoable` or `⊘ no undo`. It is visible, focusable, and placed before Cancel.
- **Error or refusal.** ✕, at most 6 words ("Refused: basis changed") and one recovery button. It stays visible until resolved. Its detail is its tip or Peek.
- **Writer held elsewhere.** ● and the owner id ("● job 4471"), at most 4 tokens.
- **Form validation.** At most 6 words beside the field.
- **Empty or unavailable.** See Empty and unavailable.
- **Text by design.** Help, Accessible View, the shortcut sheet and the Key. Live announcements are spoken, not shown.
- **Preview kickers** name the specimen state in at most 3 words and never make a statement ("Save", not "Save · posts once").

## What a tip is

A tip answers one question: **what am I looking at?** It names the mark, gives this instance's exact values, and adds one reading when the mark carries an evidence tier or a boundary.

A tip never describes:

- how the product behaves;
- which keys do what, except the next one;
- what happens elsewhere;
- what the product does not do.

That text belongs in Help (Accessibility help for this view, Alt+F1) or in the component README. The one exception is a ≠ chip: its tip is its claim boundary.

A sentence recast as a glyph plus words ("≠ arrows bind", "≠ wrap") is still telling. ≠ marks a claim boundary or a divergence class, and nothing else.

### Content

Four lines, in this order. Lines 3 and 4 are optional.

1. **Term.** An echo swatch of the mark (the real class, `aria-hidden`), the Key's exact term in bold, then the scope identifier: "Share of starts · build-a".
2. **Values.** Exact, mono and tabular:
   - numerator / denominator and a one-decimal percent ("812 / 1,144 · 71.0%"); or
   - a key-value table of at most 4 rows × 3 columns, in build column order.
3. **Reading.** The tier word first, then its basis or boundary, in at most 12 words and one sentence ("hypothesis · heuristic, ToolchainEvidence; no source identity").
4. **Next.** At most two keycaps (`.ad-kbd`), each followed by a one-word command ("Alt+↓ Peek").

**Limits:** at most 30 words outside the table and keycaps, 5 lines and 280px wide. A tip never scrolls and never has a fixed height (WCAG 1.4.12).

**Never inside a tip:** a link, button, input or anything focusable; an image of text; a chart; another mark's legend. Anything that needs a link, more than 4 rows, a sample, a receipt to follow or an action is a Peek. Its tip keeps lines 1 and 2 and "Alt+↓ Peek".

**Accessible text.**

- The tip text is the element's accessible description.
- The accessible name is the term and the primary value with its denominator ("Share of starts, build-a, 812 of 1,144, 71 percent"), so grid travel stays short.
- Glyphs in a description are `aria-hidden`, and their words are in `.sr-only`.

## Two surfaces

### Readout (`adv-readout`) for dense cells

Dense cells are grid cells, small multiples, histogram bins, tree rows, stack segments and target-map tiles. They never open a floating tip.

- **On hover or focus**, a dense cell writes lines 1–3 into a one-line strip within one frame.
- **Position:** directly under its graphic, sticky at the bottom of the graphic's own scroll region. At 200% zoom or more, or below 700px, it renders inline under the focused row.
- **At rest** it shows line 2 of the selected item.
- **Speech:** the readout is `aria-hidden`. Each cell's own description is the source, so nothing is spoken twice.

### Floating tip (`adv-tip`) for explicit triggers only

Explicit triggers are header chips, evidence chips, stamps, `?`, a lone glyph, an `aria-disabled` control and an empty-state glyph.

- Each trigger is a `<button>` or a natively focusable control.
- A trigger is never `aria-hidden` and never a focusable `role="img"`.

## Triggering

- **Pointer.**
  - A tip opens after `peek-pointer-rest` (400ms).
  - It opens at 0ms within `tip-warm` (600ms) of another tip closing, so a row of chips scans without waiting.
  - The `peek-gap` (4px) is bridged.
  - The tip closes `peek-grace` (300ms) after the pointer leaves both trigger and tip. There is no timeout.
- **Keyboard.**
  - A trigger's tip opens at 0ms on `:focus-visible`, but not on focus from a mouse click.
  - Cells in a `role="grid"` hold no Tab stops of their own. They feed the readout, and Alt+↓ opens the Peek.
- **Pin.**
  - Activation toggles the tip pinned, with `aria-expanded`. Enter, Space, click, tap, voice and switch all activate the same way.
  - A pinned tip wears the held frame (2px `ink-strong`).
  - It closes on Esc, a second activation or an outside click.
  - Alt+↓ (`link.peek`) or the row ⋯ opens the Peek.
- **One at a time.**
  - At most one floating tip is visible app-wide.
  - While a tip is pinned, hover opens no other floating tip; the readout still works.
  - Opening a Peek closes the tip.
- **Esc** closes the open tip before anything else, including a modal: it is layer 0 of `escapeOrder`. Focus does not move and the key stops there. A second Esc reaches the dialog.
- **Coarse pointer.**
  - Triggers are 44×44px, and a tap toggles the tip.
  - A tap on a dense cell selects it and fills the readout.
  - The row's 44px ⋯ offers Explain, which opens the same text as a Peek sheet.
  - Nothing needs hover or long-press, and no tip has a close button at any size.
- **Placement.** A tip opens below its trigger, otherwise above. It flips at viewport edges and never covers its trigger or the focused element (WCAG 2.4.11).
- **Motion.** Tips and the readout never animate, in any mode. The rest and the grace are steps, not fades.
- **Forced colors.** A `Canvas` fill with a 1px `CanvasText` border (2px when pinned). Echo swatches keep their patterns with `forced-color-adjust: none`.
- **Setting.** "Tips on hover" joins "Peek on hover" in View settings. With it off, tips still open on focus and activation, and the readout, Key and Peek still work.
- **State.** JavaScript owns the open, pinned and dismissed states; CSS alone cannot meet WCAG 1.4.13. The CSS rules are the fallback for static previews.

## Who explains what

| Question | Owner |
|---|---|
| What does this shape mean? (the same for every instance) | The Key |
| What is this one, exactly? (per instance, at most 30 words) | The tip or readout |
| The evidence: sample, members tried, receipts, lists over 4, links, actions | The Peek |
| The complete text for assistive tech | Name (term + value) and description (the tip text) |
| How to do something; what keys do; what the product never does | Help, Accessible View, the component README |

No layer repeats another layer's content. A tip repeats only the Key's term, never its gloss.

## The Key

- **Button.** `?` in every view header is a disclosure button (`aria-expanded`), never a tooltip.
- **Panel.** An `adv-key` list:
  - each `dt` is the real rendered mark;
  - each `dd` is at most 3 words, and is the exact term that tips use;
  - the list ends with 3–5 keycaps.
- **Generated.** The Key is generated from the view: the set of encodings drawn equals the set of Key rows.
- **Brushing.** Resting on or focusing a Key row brushes every live instance of that mark (`adv-brush`, the dotted brush outline). There are no badges, callouts or tours.
- **Docking.** The Key docks open as a one-line strip under the header on a viewer's first visit to a view, and again whenever the view gains an encoding that viewer has not seen. Dismissed, it collapses to `?`. This state is stored per viewer in durable workspace state, never in browser storage.

## Numbers

Numerals are data, not sentences. Values that are compared are visible at the same time.

**Visible:**

- the integer percent beside every fraction bar, in every row;
- the denominator, once per column header ("n 1,144");
- the count an action acts on, in the title and the primary button;
- class counts in value legends;
- tab and filter counts and values;
- cuts ("≥500");
- axis ends;
- the one histogram bin that a hypothesis rests on;
- sizes and addresses in evidence.

**Readout, tip and name only:**

- numerator / denominator per cell;
- one-decimal values;
- small-multiple and bin values;
- sample size;
- fixed-bit counts;
- instruction lengths.

**Format:**

- Thousands separators always.
- Round to the nearest integer, but never to 0 or 100 unless exact: a non-zero value that rounds to 0 reads "<1%", and a non-exact value that rounds to 100 reads ">99%".
- A tip shows one decimal.
- A cut count reads "≥N".

## Measure states

Each state has one drawn form. A bare "0" means a measured zero and nothing else; a blank means nothing.

| State | Drawn as | Class |
|---|---|---|
| measured | solid fill (at least 2px when non-zero) and the numeral | `adv-frac` |
| measured zero | empty track and a dim "0" | `adv-frac.zero` |
| thin sample (n < 30) | a 2px-high fill in the track; the numeral stays; n goes in the readout | `adv-frac.low` |
| cut at a limit | notched bar end and "≥N" | `adv-frac.cut` |
| not measured | the word "unknown", with no track and no frame | `adv-unk` |
| not comparable | a hatched track in each cell; ⊘ and the language id once in the column header | `adv-nc` |
| missing counterpart | the word "absent" | — |

## One meaning per mark

The drawn vocabulary follows State vocabularies. A mark with two meanings is a defect.

| Mark | Means | Never |
|---|---|---|
| solid frame | recorded, witnessed, or a plain frame | |
| dashed frame | hypothesis, only | a reference line; pending; an inner ▮ or H |
| dotted | context: link underline, unresolved, estimate, disabled, brushing | unknown; "has a tip" |
| 2px `ink-strong` frame | current; held (including a pinned tip); acted on now (the primary button, the tile it writes, the class it writes) | an outlier; selection |
| double | Byte-authoritative claim tier | irreversible |
| `selection` fill + 3px inline-start bar | selection | |
| 135° hatch | no data here by design: not comparable, excluded, no line | a stack class |
| stack patterns: solid, vertical rules, dots, outline | the classes named in that bar's value legend | |
| ± | the build that differs | |
| ⊘ | does not apply, or cannot be done here | alone in a cell |
| ○ | not run, never run, not loaded, free; always with its word | zero |
| ● | owned; the writer lock, with its owner id | a build |
| ◇ ◆ | gates | a reference build |
| ≈ | compile variance, as the subject in a dashed chip | hypothesis in general |
| ≠ | a claim boundary or a divergence class | a behavior note |

Builds are identified by column position and build id. The small multiples draw the build axis once, in their column header, in header order, and follow the Builds filter. There are no build sigils and no letters under individual multiples. The reference build, where a view names one, is the first build column.

## Density

Per view:

- at most 6 semantic glyphs, all from State vocabularies (not counting ? × ⋯ ▸ ▾ and checkboxes);
- at most 4 fill patterns besides solid, and only the frames above;
- at most 3 status chips in the view header, and at most 3 ≠ chips in the view;
- at most 1 evidence chip per row, in a fixed column;
- at most 3 visible actions per group, with the rest behind ⋯ (a menu button);
- at most 5 filter chips before "+N".

**One fact, one encoding.** Never a glyph, a word and a numeral for the same fact. A fact true of a whole column is stated once, in its header.

**Mystery meat.**

- A control that acts or navigates shows a verb or is a universal glyph (? × ⋯ ▸ ▾), and has a control border.
- An explain-only chip shows a glyph or frame plus a noun, never a verb. It shows `cursor: help` and is never underlined; the dotted underline stays reserved for links.
- Every drawn mark explains itself the same way, so the user never has to discover which marks explain.

## Sentence to shape

| A sentence that says… | Is drawn as | Class |
|---|---|---|
| a share of one build's total ("812 of 1,144 starts, 71%") | a fraction bar and the integer percent; the denominator once in the column header | `adv-frac` |
| the same measure across builds, and which build differs | small multiples on one scale, the build axis once in the header, ± under the build that differs | `adv-sm`, `adv-sm-ax` |
| a difference from a named reference build | a 1px baseline at the reference value, and a signed tick per build | `adv-sm b.ref`, `adv-delta` |
| a build that cannot be compared (another language) | a hatched track in each cell; ⊘ and the language id once in the header | `adv-nc` |
| a distribution (residues, sizes, depths) | a histogram with its axis ends and a 1px solid rule at the uniform share; a scrub cursor feeds the readout | `adv-hist`, `b.ref` |
| how one count splits into disjoint classes | a stacked bar with one pattern per class, and a value legend | `adv-stack`, `adv-skey` |
| a tree node's share of paths | a share line under the node | `adv-share` |
| an instruction's length | one tick per byte | `adv-len` |
| where a pattern sits relative to the start (pre, post, return) | a 7-cell ruler: the start edge heavy, the pattern's cells filled | `adv-win` |
| a mask finer than a nibble | one cell per bit under the bytes: full height when fixed, a baseline when wildcard | `adv-mask` |
| which of several builds a chip covers | one 8px square per build in column order, covered squares filled | `adv-scope` |
| "this is a hypothesis; basis: …" | the dashed chip with its subject; the basis is its tip | `adv-h` |
| "backed by a witness or record" | the solid chip; the witness is its tip | `adv-w` |
| a claim boundary ("not evidence", "not accuracy", "not a recovery claim") | ≠ plus one word; the boundary is its tip | `adv-bnd` |
| what a change will touch and what it leaves alone | a target map: the written tile in the 2px frame with ✎ and its count; untouched tiles dim and struck | `adv-tmap` |
| "cannot be undone here" | ⊘ no undo, in the undo slot | `adv-w` |
| "undoable", "reused", "fresh", "stale" | the stamp or chip word | `ad-stamp`, `adv-w` |
| filters and parameters | key-value chips | `adv-chips` |
| "nothing here yet; do X" | the skeleton, the glyph with its word, and the one action | `adv-ghost`, `adv-empty` |
| "not available on this server yet" | the disabled control with ⊘; the reason is its tip, the offer list a Peek | `adv-na` |
| "another writer holds this" | ● and the owner id | — |
| "follows as you move" or "held" | the pane frame and one state chip | HeldPane |
| history across runs | a per-build sparkline on one scale; a missing report is a gap, never zero | `adv-spark` |

**New in this revision:** `adv-readout`, `adv-sm-ax`, `adv-sm b.ref`, `adv-hist b.ref`, `adv-len`, `adv-win`, `adv-mask`, `adv-scope`, `adv-unk`, `adv-ghost`, `adv-brush`, `adv-frac.low`, `adv-frac.cut`.

**Specified but not yet styled:** `adv-delta`, `adv-spark`.

## Empty and unavailable

These four states look different without hover.

- **Never gathered or never run:**
  - the view's real skeleton (`adv-ghost`: headers and empty tracks, never invented values);
  - "○ not gathered";
  - one action naming its object ("Gather build-c…").
- **Filtered to zero:** "0 / 1,144" and Clear filter.
- **Failed:** the error line under Words that stay visible.
- **Not on this server:** the disabled control with ⊘ ("⊘ Gather…"). Its tip names the reason, and "What this server offers" is a Peek.

## Rules

- **One scale per comparison.** Bars and small multiples for builds share one scale in one view. A bar is one measure of one build: never a sum of separate facts, never an average across builds, never a score.
- **Never color alone.** Every shape is also a pattern, frame or glyph, and survives forced colors as `CanvasText` shapes.
- **A quoted sentence in a component README** is the text of its tip, Key entry or accessible description. The visible layout follows this guideline.
- **Specimens.** The default render has no open tip. A pinned tip appears only in a specimen captioned "Tip pinned".

## Acceptance

A reviewer checks every preview and its render.

1. **Text-off test.** The test above passes.
2. **Runs.** The regex `/\b[A-Za-z]+(\s+[A-Za-z]+){3,}/`, run over visible text outside evidence, `[role="tooltip"]`, `.sr-only` and the listed exceptions, finds nothing. No visible label ends in ".".
3. **Budgets.** At rest: at most 45 label words per view and 10 per dialog, and at least as many semantic marks as label words.
4. **Coverage.**
   - Every drawn mark has an accessible name. Where the mark is numeric, the name carries the exact numerator and denominator.
   - Every drawn mark also has either `aria-describedby` pointing to exactly one `role="tooltip"`, or membership in a row that feeds a readout.
   - Every number in a name appears in its tip or readout.
5. **Tip shape.**
   - No `role="tooltip"` contains `a`, `button`, `input` or `[tabindex]`.
   - Tips hold at most 30 words and one sentence.
   - The first term of a tip equals a Key `dd`.
6. **Tips describe the mark.** No tip gives key instructions outside line 4, or describes behavior ("never", "opens", "press", "until"), except a ≠ chip's boundary.
7. **Key.** The encodings drawn equal the Key rows. The Key has `aria-expanded` and is not a tooltip.
8. **Registry.** No mark, glyph or class has two meanings (see One meaning per mark). `adv-bnd` holds only ≠.
9. **Density.** The density budgets hold.
10. **Numbers.** No non-zero value renders as "0" or "0%". "100%" appears only when exact. Every fraction bar shows its percent.
11. **Behavior.**
    - A cold tip opens at 400±50ms; a warm one within one frame.
    - The pointer can cross the gap without the tip closing.
    - Esc closes the tip with `document.activeElement` unchanged, even over a ConfirmDialog.
    - At most one tip is visible.
    - A grid hover opens no floating tip and updates the readout within one frame.
    - Cells inside `role="grid"` add no Tab stops.
    - `transition-duration` is 0s.
12. **Renders.** Forced-colors, grayscale and 400% zoom renders keep every class distinct and keep the readout inside the viewport.
13. **Coarse pointer.** Under `pointer: coarse`, every trigger and row ⋯ is at least 44×44px, and nothing needs hover.
14. **Tips off.** With tips turned off, every action is still found by its visible verb.
15. **Default render.** No tip is open, except in a specimen captioned "Tip pinned".
