# MergeReview

A file-manager-like review of a project merge, then its outcome per binary, name, type, comment and relationship: added, reused, skipped, conflicting.

**Consumer provides** both projects, the matched artifact identities, and per category the counts and items in each outcome.

- Both projects are named. Richer compatible fields are kept; human edits and conflicts are preserved.
- Outcome columns are added · reused · skipped · conflicting. "Contested" is reserved for locators.
- Never summarize as "Project data combined."
