# MatchReview

The cross-match review queue: token-bound decisions over pairs, with relation, divergence and the observed basis, reviewed master-detail from the keyboard with outcomes landing on the rows.

**Consumer provides** rows (source and destination build and address, names, score, status, relation, divergence class, components, thresholds version, producing channel, reason), the observed-basis token and the page; for each decided row, its job and lifecycle; after a refusal, the refreshed rows to compare with the rows shown.

- Paged by match ID. Select-all checks every decidable row on the page. Batches are all-or-nothing.
- **Master-detail**: the focused row drives a detail region, the **ReviewDetail** component, inline under the row (→ opens, ← closes, and it stays open while j/k move) or in the evidence rail ("Detail in rail", per viewer). It follows after the settle and shows CandidateAlignment of source ↔ destination with shared anchors in words, the IdentityEdge, relation, divergence class, components, thresholds version, producing channel and reason ("unavailable" where missing), and alternatives with their margin.
- Deciding arms Decide in the ActionStrip bound to the checked set (`d`), then opens ConfirmDialog ("Move 3 rows to verification? This cannot be undone here."). HTTP 202 means pending: each decided row gets an **OutcomeCell** "pending · job c4e1", which changes only when that job's terminal result arrives; the row stays in place.
- **Refusal recovery**: a stale or missing basis refuses the decision. The checked set, the match-ID page and the scroll position (anchored on the focused match ID) are kept. A BasisDelta compares the rows shown with the refreshed rows: unchanged rows keep their check; changed rows are unchecked and flagged "◷ changed since you looked" with field-level before → after; rows that left say "no longer on this page"; new rows say "new". A "Changed only" filter and F8 step the changed rows. Deciding again needs a new, deliberate confirm; nothing is resubmitted automatically.
- The StarvationMeter age of the oldest unreviewed row sits in the queue header and links to that row.
- Missing relation or components are "unavailable", never fabricated. Review is an override applied afterwards; it never gates progress.

**Linking**

- **Publishes:** `page` (the match-ID cursor, replaceState) and `f` for "Changed only" and outcome filters. `o` opens both endpoints beside as a held pair (`cmp`, `hold`) without leaving the queue. The primary entity and build do not change while reviewing unless Enter goes to an endpoint.
- **Follows:** `project`, `page` and `f`; the detail follows the focused row after the settle. The queue is not holdable; the `o` pair is.
- **Targets rendered:** source and destination addresses → the Code Browser for that build, with the edge word · match id → this row, focused (`page=`) · OutcomeCell job → the dock Jobs record · basis → the ProvenanceStamp detail · alternatives → their instances · the queue header's age → the oldest unreviewed row.
- **Peek source:** Alt+↓ on an endpoint reads its cached listing lines; on a job, the stored job record. The detail reads stored review rows and cached listings only.
- **Absent copy:** "unavailable" for missing relation or components · destination "absent" (plain) · "no longer on this page" · "new" · "◷ changed since you looked" · "pending · job c4e1".
- **Target-size exception:** none; rows are 28px, checkbox cells 24px. With a coarse pointer each row adds one 44px row-menu button.

**Keyboard**

- APG Grid with row focus: ↑/↓ or j/k rows, → opens the inline detail, ← closes it. x or Space checks; Shift extends. Focus-scoped and remappable: `o` opens both endpoints beside, `n` / `p` step evidence highlights in the detail, `d` arms Decide, `.` repeats the armed action on the focused row. F8 steps changed rows after a refusal.

**Accessibility**

- The detail is a labelled region ("Detail: match 18421, build-a 0041b210 ↔ build-c 00082f40") referenced by `aria-controls` from the row's disclosure button while open. Checkboxes are named "Select match 18421, ResourceRef::Resolve, build-a to build-c". Pending and terminal outcomes are announced politely, once per job; a refusal is assertive because it blocks the action in hand, and focus moves to the first changed row.

**Removes switching:** opening both builds' listings to check each pair, and re-finding rows after a refused decision (J07, J08).
