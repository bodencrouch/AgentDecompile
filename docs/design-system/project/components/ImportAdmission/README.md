# ImportAdmission

Nonblocking import: validate, durably accept, close the dialog, and show the admitted work where the task continues.

**Consumer provides** the dropped or chosen inputs, SHA-256 identity, duplicate aliases, the batch id, the admitted work (job ids per input), per input whether its function inventory has been observed yet, whether the dock is open, and the current checked-set count and build (for the switch words).

- **The dialog closes as soon as the import is durably accepted.** No application-wide "Working…".
- **Focus after acceptance** (the one documented APG dialog exception, in 90):
  - at 700px and wider with the dock open, focus moves to the admitted batch row in the dock, because the task continues there, and the acceptance is announced once, politely;
  - otherwise focus returns to the invoker, and the polite message says "Import accepted: 3 inputs, batch b7. Go to last announcement (g then j, or the palette) shows it."
  Nothing else moves focus by itself.
- Duplicates alias an existing identity (shown as "alias of"); aliases and provenance are kept, nothing unrelated is deleted.
- Grouping into variant families comes from match evidence, not filenames. Insufficient evidence means "variant group unresolved".
- **"Go to build-e"** appears only once that build's inventory has been observed; until then the row says "inventory not observed yet". It is an explicit build switch: its description states the switch and any checked-set clearing first ("switches the inspected build to build-e · clears 4 checked rows on build-a"), and the polite region confirms it after. Importing never navigates by itself.
- "Choose files…" is always offered beside drop; nothing requires dragging.
- An import adds inputs to the active project only; it never opens or switches projects.

**Linking**

- **Publishes:** nothing on acceptance. Activating "Go to build-e" publishes `build` (one history stop).
- **Follows:** `project`; rows update from the admitted jobs' transitions. Not holdable.
- **Targets rendered:** admitted work → each input's job in the dock Jobs record · "alias of build-e" → the Navigator program row for that build (the inspected build does not change) · "Go to build-e" → the Code Browser for that build, once its inventory is observed · the identity digest → the identity receipt card.
- **Peek source:** Alt+↓ on a job reads its stored job record; on an alias, the existing build's identity row.
- **Absent copy:** "inventory not observed yet" · "variant group unresolved" · "alias of build-e" · "rejected: not a supported format" (with the field named).
- **Target-size exception:** none; rows are 28px and links at least 24px, 44px below 700px. With a coarse pointer each row carries one 44px row-menu button with the same link menu; there is no long-press.

**Keyboard**

- The batch is a grid row group: ↑/↓ rows, Enter follows the focused link, Alt+↓ peeks. Choose files… is a button; drop is never the only path.

**Accessibility**

- One polite message when the batch is accepted ("Import accepted: 3 inputs, batch b7. Go to last announcement (g then j, or the palette) shows it."). The table names each input as its row header. The focus move to the batch row is announced once and happens only while that row is visible.

**Removes switching:** watching a blocking dialog, then hunting the dock for the admitted jobs, then the project tree for the new build (J30; counts in the plan ledger).
