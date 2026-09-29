# MatchReview

The cross-match review queue: token-bound decisions over pairs, with the U17 match record and the observed basis, reviewed master-detail from the keyboard with outcomes landing on the rows. Its master-detail is **ReviewDetail**, and its refusal recovery is ReviewDetail's named part **BasisDelta**.

**Use it** as the Review panel of the Compare workspace (`ws=compare&panel=review`), one page at a time by match id, with the Review layout preset (`g then 3`).

**Consumer provides** rows in U17 order: match id, source and destination build and address, then relation, divergence_class, components, thresholds_version, producing_channel and reason, each "unavailable" where missing; status; the observed-basis token and the page; for each decided row, its job and OutcomeCell; after a refusal, the refreshed rows to compare with the rows shown.

- Paged by match id. **Check all** checks every decidable row on the page. Batches are all-or-nothing.
- **Columns:** the checkbox, Match (the row header), Source, Destination (with the edge word, never "counterpart"), the six U17 fields in U17 order, and an **OutcomeCell** column. Missing relation, components or reason read "unavailable" and are never fabricated.
- **Master-detail** is ReviewDetail: Enter on a row expands its detail in place, or fills the detail pane beside the queue, and the detail follows the focused row after the 200ms settle. There is no "Detail in rail" option.
- **Buttons** above the grid, 24px (44px below 700px): **Open both beside** (`o`) re-points the Review held pair to the focused match and never adds holds; **Decide…** (`d`) arms Decide in the ActionStrip bound to the checked set, then Run opens ConfirmDialog ("Move 3 rows to verification? This cannot be undone here."). HTTP 202 means pending: each decided row's OutcomeCell reads "pending · job c4e1" and changes only when that job's terminal result arrives. Nothing is announced on pending, and the row stays in place.
- **Batch refusal recovery** (BasisDelta, see ReviewDetail). A stale or missing basis refuses the batch, and the assertive line reads "Decision refused: basis changed. 2 rows changed and were unchecked; nothing was applied. F8 steps them after Step changed rows." The checked set, the match-id page and the scroll position (anchored on the focused match id) are kept, and focus returns to the invoker. Unchanged rows keep their check; changed rows are unchecked and marked "± changed since you looked" with field old → new; new rows are marked "+ new since you looked". Rows that left the page go into a separate collapsed group, "Left this page since you looked (N) · basis 9f3c… read 13:58"; they are historical, cannot be checked or decided, and show match-id links only. **Changed only** is a session-local filter button (after a reload: "Changes since the previous basis are not available; all rows need re-reading."). **Step changed rows** makes them the active worklist explicitly, with an announcement, and F8 then steps them. Deciding again needs a new ConfirmDialog that names the new count; nothing is resubmitted automatically.
- The StarvationMeter age of the oldest unreviewed row sits in the queue header and links to that row.
- Review is an override applied afterwards; it never gates progress.
- **Parity.** The static 8080 `wb-review` surface uses ReviewDetail's in-place form with the same U17 object, the BasisDelta summary and OutcomeCell, and opens the held pair as a new window.

**Linking**

- **Publishes:** `page` (the match-id cursor, replaceState). `o` re-points the held pair (two `hold` entries, replaced, never added). Outcome filters use `f=outcome:…`; applying one from a link is a Go (pushState) and typing or removing a chip uses replaceState. "Changed only" is session-local and never in the URL. The primary entity and build do not change while reviewing unless Enter goes to an endpoint.
- **Follows:** `project`, `page` and `f`; the detail follows the focused row after the settle. The queue is not holdable; the held pair is.
- **Targets rendered:** source and destination addresses → the Code Browser for that build, with the edge word · match id → this row, focused (`page=`) · OutcomeCell job → the dock Jobs record · basis → the ProvenanceStamp detail · alternatives → their instances · the queue header's age → the oldest unreviewed row.
- **Peek source:** Alt+↓ on an endpoint reads its cached listing lines; on a job, the stored job record. The detail reads stored review rows and cached listings only.
- **Absent copy:** "unavailable" for missing U17 fields · destination "absent" (plain) · "left this page since you looked" · "+ new since you looked" · "± changed since you looked" · "pending · job c4e1".
- **Target-size exception:** none; rows are 28px, checkbox cells 24px, and the two buttons 24px (44px below 700px). With a coarse pointer each row adds one 44px row-menu button carrying the same link menu.

**Keyboard**

- A row-selection APG Grid with one tab stop: ↑/↓ or **j/k** move between rows, ←/→ move between cells in the row, Home/End go to the first and last cell of the row, Ctrl+Home/Ctrl+End to the first and last row.
- **Enter** on a row expands or collapses its detail (ReviewDetail). There are no →/← open and close keys and no `n`/`p` keys.
- **x** or **Space** checks a row; **Shift+↑/↓** and **Shift+j/k** extend the checked range. **Ctrl/Cmd-click** toggles a row and **Shift-click** extends the range, including on the match-id and address links (35 grid modifier precedence); Open beside there is Shift+Enter or the link menu, and a new tab is Ctrl/Cmd+Enter or middle-click. Typeahead starts with `/`.
- Focus-scoped and remappable: **o** opens both endpoints beside (re-points the held pair), **d** arms Decide, **.** arms or repeats the armed action on the focused row and never posts.
- **F7 / Shift+F7** step the detail's alignment differences. **F8 / Shift+F8** step the active worklist; after Step changed rows, the changed rows.
- Esc follows the one order in `keymap.json` `escapeOrder`; it never clears the checked set.

**Accessibility**

- `role="grid"` named for the page, with `aria-rowcount`; row headers are the match ids. The detail is a labelled region ("Detail: match 18421, build-a 0041b210 to build-c 00082f40") referenced by `aria-controls` from the row while open. Checkboxes are named "Check match 18421, ResourceRef::Resolve, build-a to build-c".
- Terminal outcomes are announced politely, once per job; nothing is announced on pending. A refusal is assertive because it blocks the action in hand.
- Change words are text ("changed since you looked", "new since you looked"); glyphs are `aria-hidden` beside them.

**Removes switching** (counts from the plan ledger): J07 review a candidate match and check both endpoints, 8 → 0 plus one modal confirm per decision (U186); J08 recover from a refused decision, 4 → 1 (U186).

## Behavior

- After a refused decision, the page cursor, the scroll on the focused match and your other checks are kept. Deciding again opens a new ConfirmDialog that names the new count.
