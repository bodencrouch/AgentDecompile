# ActionStrip

The typed command line for one catalog verb: what will run, on which target, with which fields, before anything is posted; it stays armed after Run so the next row is one key away.

**Consumer provides** the action title and id, the bound target (program, build, address or checked set), the optional fields from the catalog schema with their prefill origin, the checked-set count, and after Run the submitted job id and its lifecycle state.

- Sits under the session tabs when an action is armed. Palette picks, toolbar quick actions, StateNotice fixes and `d` in review share this one execute path (`GET /api/v1/actions` → strip → ConfirmDialog).
- Buttons: "Run with defaults" (`.primary`), "Run with last fields", "Fields…" to edit catalog parameters, and "Run N" when a checked set is bound, with an "N selected" count chip.
- **Prefill order**, each field labelled with its origin: the bound target from the primary selection ("from selection"), then the fields last used for this action on this program ("from last run 14:02"), then catalog defaults ("catalog default"). Refusals keep every entered field.
- **Stays armed after Run** with the same action and reads "Submitted a3f9 · pending" until the job's terminal result lands on the row (OutcomeCell). Nothing is shown optimistically; a 202 is pending.
- **Repeat**: with focus in a list or grid, j/k move to the next row and the strip rebinds to it; focus-scoped `.` repeats the armed action on the focused row. Mutating verbs still confirm once through ConfirmDialog, naming the exact target.
- **Batch summary chip** after a checked-set run: "4 runs: 1 running · 2 finished · 1 failed"; each word is a filter link over those rows, and the run becomes a worklist (F8 steps the failed rows).
- Closing: Esc disarms; a program change closes the strip and clears the checked set (with Undo).
- Field errors name the catalog field: "`kb` is required. Enter it in Fields…".

**Linking**

- **Publishes:** nothing. It binds the primary selection only, never a held pane or Kept card. The batch chip's words apply `f=outcome:…` to the rows, which their grid owns.
- **Follows:** the primary selection, after the settle; the bound target rebinds when the selection moves (j/k), and the strip never rebinds from a stale response. Not holdable.
- **Targets rendered:** the bound target → the Code Browser at that build and address · the submitted job → the dock Jobs record · each batch-chip word → the rows in that state. The action id is text.
- **Peek source:** Alt+↓ on the submitted job reads its stored job record.
- **Absent copy:** "No target bound. Select a function first." · "Submitted a3f9 · pending" · "`kb` is required. Enter it in Fields…" · "Unavailable for build-e: no bound program." (`aria-disabled` with the reason).
- **Target-size exception:** none; buttons are 28px, 44px below 700px.

**Keyboard**

- APG Toolbar: one tab stop, ←/→ between controls. Enter on a button runs it; Esc disarms. Focus-scoped `.` (in a list or grid, remappable) repeats the armed action on the focused row. Enter in a list always means Go, never "open the last action".

**Accessibility**

- `role="toolbar"` named "Armed action: ‹title›". Prefill origins are visible text beside each field. "Submitted a3f9 · pending" and the terminal result are announced once, politely; a batch is coalesced when its last job ends. Focus returns to the invoking row after Run or cancel.

**Removes switching:** reopening the palette and re-entering fields for the same verb on every row, and opening the dock to see whether it ran (J21, J22).
