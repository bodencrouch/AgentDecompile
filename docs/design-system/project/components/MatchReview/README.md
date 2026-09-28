# MatchReview

The cross-match review queue: token-bound decisions over pairs, with relation, divergence and the observed basis.

**Consumer provides** rows (source and destination build and address, names, score, status, relation, divergence class, components, producing channel, reason), the observed-basis token and the page.

- Paged by match ID. Select-all checks every decidable row on the page. Batches are all-or-nothing.
- Deciding opens ConfirmDialog ("Move 3 rows to verification? This cannot be undone here."). HTTP 202 means pending; the outcome shows only after the terminal result.
- A stale or missing basis refuses the decision and asks for a refresh and a new deliberate decision. Missing relation or components are "unavailable", never fabricated.
- Review is an override applied afterwards; it never gates progress.
