# ImportAdmission

Nonblocking import: validate, durably accept, close the dialog, and show the admitted work in the workspace, with the admitted batch row focused.

**Consumer provides** the dropped or chosen inputs, SHA-256 identity, duplicate aliases, the admitted work (job ids per input), and per input whether its function inventory has been observed yet.

- The dialog closes as soon as the import is durably accepted. No application-wide "Working…". After acceptance, focus moves to the admitted batch row in the dock, and acceptance is announced once, politely.
- Duplicates alias an existing identity (shown as "alias of"); aliases and provenance are kept, nothing unrelated is deleted.
- Grouping into variant families comes from match evidence, not filenames. Insufficient evidence means unresolved grouping.
- **"Go to build-e"** appears only once that build's inventory has been observed; until then the row says "inventory not observed yet". The selection changes only when the operator activates the link. Importing never navigates by itself.
- "Choose files…" is always offered beside drop; nothing requires dragging.

**Linking**

- **Publishes:** nothing on acceptance. Activating "Go to build-e" publishes `build` (one history stop).
- **Follows:** `project`; rows update from the admitted jobs' transitions. Not holdable.
- **Targets rendered:** admitted work → each input's job in the dock Jobs record · "alias of" → the existing build that identity already names · "Go to build-e" → the Code Browser for that build, once its inventory is observed · the identity digest → the identity receipt card.
- **Peek source:** Alt+↓ on a job reads its stored job record; on an alias, the existing build's identity row.
- **Absent copy:** "inventory not observed yet" · "variant group unresolved" · "alias of build-a" · "rejected: not a supported format" (with the field named).
- **Target-size exception:** none; rows are 28px.

**Keyboard**

- The batch is a grid row group: ↑/↓ rows, Enter follows the focused link, Alt+↓ peeks. Choose files… is a button; drop is never the only path.

**Accessibility**

- One polite message when the batch is accepted ("3 inputs accepted; analysis admitted for 2"). The table names each input as its row header.

**Removes switching:** watching a blocking dialog, then hunting the dock for the admitted jobs, then the project tree for the new build (J30).
