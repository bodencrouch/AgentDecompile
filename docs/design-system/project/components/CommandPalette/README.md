# CommandPalette

Ctrl+K: the universal entry to actions, go-to surfaces and recent jobs.

**Consumer provides** the query, grouped results (Actions, Go to, Recent jobs) and the highlighted row.

- A `pane` sheet with `shadow-popup` over the `overlay` scrim; the query field is a `well`.
- Picking an action opens the action strip with the target prefilled; it never runs immediately.
- Toolbar search filters functions only. Jumping to a surface belongs here, not there.
- Arrow keys move, Enter picks, Esc closes and returns focus to where it was.
