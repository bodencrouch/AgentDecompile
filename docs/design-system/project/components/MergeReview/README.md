# MergeReview

A file-manager-like review of a project merge, then its outcome per binary, name, type, comment and relationship: added, reused, skipped, conflicting; conflicts reviewed master-detail beside the summary.

**Consumer provides** both projects, the matched artifact identities, per category the counts and items in each outcome, and for each conflicting item the entity, build and both values.

- Both projects are named. Richer compatible fields are kept; human edits and conflicts are preserved.
- Outcome columns are added · reused · skipped · conflicting. "Contested" is reserved for locators; merges say "conflicting".
- Each count is a link that lists those items. **Conflicts** open master-detail: the conflicting row drives a NameProvenance detail (both values, tiers, sources) inline or in the rail; nothing is auto-picked.
- Never summarize as "Project data combined."

**Linking**

- **Publishes:** `f=merge:…` filters (replaceState) for the item lists. The primary selection moves only when Enter goes to an affected entity.
- **Follows:** `project` and the merge record it reviews; not holdable.
- **Targets rendered:** each count → the list of those items (`f=merge:names.conflicting`) · a conflicting name or type → NameProvenance for that entity and build (Peek, or the rail's "Why this name") · an affected entity → the Code Browser at that build and address · the merge job → the dock Jobs record.
- **Peek source:** Alt+↓ on a conflict reads the stored NameProvenance rows for both projects; nothing is merged again.
- **Absent copy:** "0" counts are plain text, not links · "skipped · project locked" · "conflicting · not applied".
- **Target-size exception:** none; count cells are 24px targets.

**Keyboard**

- A grid: arrows move cells; Enter on a count lists its items; Enter on a conflict goes to its entity; Alt+↓ peeks it.

**Accessibility**

- The category is the row header; each count link's name reads "Names conflicting, 4". Conflict is a word, not only `fact-failed` color.

**Removes switching:** opening each affected build and its names view after a merge to find what conflicted (J31).
