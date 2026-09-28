# CommandPalette

Ctrl/Cmd+K: the universal entry to catalog actions, go-to surfaces and recent jobs.

**Consumer provides** the query and grouped results (Actions, Go to, Recent jobs) with the highlighted row.

- A `dialog-bg` sheet with `shadow-popup` over the `overlay` scrim; the query field is a `well`.
- Picking an action opens the ActionStrip with the target prefilled; it never posts immediately.
- Toolbar search filters functions only; jumping to a surface belongs here.
- ↑↓ move, Enter picks, Esc closes and returns focus. Recent actions are remembered per viewer.
