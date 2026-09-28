# ImportAdmission

Nonblocking import: validate, durably accept, close the dialog, and show the admitted work in the workspace.

**Consumer provides** the dropped or chosen inputs, SHA-256 identity, duplicate aliases, and the admitted work.

- The dialog closes as soon as the import is durably accepted. No application-wide "Working…".
- Duplicates alias an existing identity (shown as "alias of"); aliases and provenance are kept, nothing unrelated is deleted.
- Grouping into variant families comes from match evidence, not filenames. Insufficient evidence means unresolved grouping.
