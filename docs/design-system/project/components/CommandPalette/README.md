# CommandPalette

Ctrl/Cmd+K: the universal entry to catalog actions, go-to surfaces and recent jobs.

**Consumer provides** the query and grouped results (Actions, Go to, Recent jobs) with the highlighted row.

- A `dialog-bg` sheet with `shadow-popup` over the `overlay` scrim; the query field is a `well`.
- Picking an action opens the ActionStrip with the target prefilled; it never posts immediately.
- Ctrl/Cmd+K is for verbs and surfaces; Ctrl/Cmd+P (NavigationBar go-to) is for places: addresses, symbols, logical ids, jobs, receipts and pipeline nodes. A `>` typed in go-to switches to the palette and back.
- ↑↓ move, Enter picks, Esc closes and returns focus. Recent actions are remembered per viewer.
