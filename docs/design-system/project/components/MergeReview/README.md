# MergeReview

A file-manager-like review of a project merge, then its outcome per binary, name, type, comment and relationship: added, reused, skipped, conflicting. Conflicts are reviewed master-detail beside the summary, in the active project.

**Consumer provides** both projects, the matched artifact identities, per category the counts and items in each outcome, and for each conflicting item the entity, build and both values with their tiers and sources.

- Both projects are named. Richer compatible fields are kept; human edits and conflicts are preserved.
- Outcome columns are added · reused · skipped · conflicting. "Contested" is reserved for locators; merges say "conflicting".
- Each non-zero count is a link that lists those items; "0" is plain text.
- **Conflicts, master-detail** (the ReviewDetail pattern): the focused conflicting row drives a detail, inline below 860px or beside at 860px and wider. The detail is NameProvenance for that name or type in its build **in the active project**: both values, their tiers and sources. Nothing is auto-picked, and following a link never applies a value; a choice is an edit through InlineRename or the ActionStrip.
- **Another project is never opened from here.** Links resolve only inside the active project. An item that exists only in the other project is words ("in local-analysis · not open"). Any link that names the other project lands on 35's cross-project StateNotice, which names both projects, with Switch armed and confirm-gated and Stay; it never opens that project.
- Never summarize as "Project data combined."

**Linking**

- **Publishes:** `f=merge:…` filters for the item lists; applying one from a count link is a Go and pushes one stop. The primary selection moves only when Enter goes to an affected entity in the active project.
- **Follows:** `project` and the merge record it reviews; the detail follows the focused conflict row after the settle and reads cache only. Not holdable.
- **Targets rendered:** each count → the list of those items (`f=merge:names.conflicting`) · a conflicting name or type → NameProvenance for that entity and build in the active project (a cache-only Peek, or the rail's "Why this name") · an affected entity → the Code Browser at that build and address · the merge job → the dock Jobs record · a link naming the other project → the cross-project StateNotice, never the project.
- **Peek source:** Alt+↓ on a conflict reads the stored NameProvenance rows for that entity and build; nothing is merged again or fetched from the other project.
- **Absent copy:** "0" counts are plain text, not links · "skipped · project locked" · "conflicting · not applied" · "in local-analysis · not open".
- **Target-size exception:** none; count cells are 24px targets, 44px below 700px. With a coarse pointer each row carries one 44px row-menu button with the same link menu; there is no long-press.

**Keyboard**

- An APG Grid: arrows move cells; Enter on a count lists its items; Enter on a conflict goes to its entity; Alt+↓ peeks its NameProvenance.

**Accessibility**

- The category is the row header; each count link's name reads "Names conflicting, 4". Conflict is a word, not only `fact-failed` color. A link naming the other project says in its name that it lands on the project notice.

**Removes switching:** opening each affected build and its names view after a merge to find what conflicted (J31, credited to UX-01; counts in the plan ledger).

## Behavior

- Each count links to its rows; counts are separate, never summed.
- Nothing is auto-picked (formerly the "≠ auto-pick" chip: "nothing auto-picked · not applied"); a conflict stays not applied until chosen.
- cache-only: a choice is an edit through InlineRename or the action strip.
- ↗ local-analysis lands on the project notice with Switch armed; it never opens the project.
