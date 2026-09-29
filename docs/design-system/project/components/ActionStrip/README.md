# ActionStrip

The typed command line for one catalog verb: what will run, on which target, with which fields, before anything is posted. Keys only arm it; only Run posts. It stays armed after Run, so the next row is one key and one activation away.

**Consumer provides** the action title and id from `GET /api/v1/actions`, the catalog field schema (which fields are typed as targets), the bound target (program, build, address or checked set), the last-used non-target fields for this action on this program from durable workspace state (F23) with their time, the checked-set count, any job record for the same verb and target that is not yet terminal, and after Run the submitted job id and its Job outcome word (State vocabularies).

- **One execute path.** The strip sits under the session tabs while an action is armed. Palette picks, toolbar quick actions, the link menu's Edit group, a StateNotice's armed fix and `d` in review all arm this one path: `GET /api/v1/actions` → strip → Run, with ConfirmDialog only where 35 (Confirming edits) requires it. Arming never posts.
- **Controls.** One **Run** button (`.primary`; "Run on 3 checked" when a checked set is bound, beside the "3 checked" count chip), **Fields…** to edit catalog parameters, **Reset to catalog defaults**, and Disarm. There is no second run button with a different, hidden field set.
- **Prefill order** (90, No retyping), each field labelled with its origin:
  1. fields the catalog types as targets (address, recipient, donor, build) bind from the primary selection ("from selection"), always. They never carry over from the last run;
  2. other fields last used for this action on this program ("from last run 14:02"), kept in durable workspace state, never localStorage or the URL;
  3. catalog defaults ("catalog default").

  Reset to catalog defaults replaces the non-target fields; target fields stay bound to the selection. Refusals keep every entered field.
- **Run posts once.** For a single-target verb, Run is the commit point. ConfirmDialog opens only for batch (a checked set), destructive or cross-build verbs; a struct-field retype, a structure-layout change or a callee-signature edit counts as cross-build. Inline single-target edits (InlineRename, the inline retype and comment editors, StorageEditor) confirm in place in their own named editor and never pass through the strip or ConfirmDialog. Saving a program bookmark arms the catalog's bookmark action for one build and address; Run posts once, with no dialog.
- **Duplicate guard.** Run is `aria-disabled`, with its reason as visible text in `aria-describedby`, while a job record for the same verb and target is not terminal ("Already submitted a3f9 for this target · running") and while an ambiguous submit is being reconciled ("Checking whether the operation completed"). The guard reads job records, not client memory, so a second tab, a double activation or a reconnect is refused the same way (50, Operator actions). Read-only views stay available.
- **Stays armed after Run** and names its own target: "Submitted a3f9 for 0041b210 · pending" until the terminal result lands on the row as an OutcomeCell. After j/k it still names 0041b210, so it never reads as the new row's status. When the job record names no bound target, no row gets a cell and this line reads "outcome in dock · job 77c0". Nothing is shown optimistically; a 202 is pending.
- **`.` arms or repeats; it never posts.** With focus in a list or grid, j/k move; focus-scoped `.` (keymap `list.repeat`) rebinds the armed action to the focused row, or arms a disarmed draft for it, and moves focus to Run. With nothing armed or drafted, `.` does nothing and the status line says "No armed action".
- **Rebind, never a silent retarget.** When the selection moves other than by a history step, an armed strip keeps its bound target and says "Bound to ResourceRef::Resolve · selection is now Actor::LoadFromTemplate · Rebind". **Rebind** binds it to the current selection and leaves it disarmed ("Draft · Match siblings on Actor::LoadFromTemplate · Prepare"); Run is offered again only after Prepare (its accessible name adds "nothing runs until Run") or `.`. The entered fields stay as a draft either way.
- **Esc** disarms only while focus is inside the strip, keeping the fields as a draft (keymap `escapeOrder`, step 4). Esc elsewhere never touches the strip.
- **History.** A history move (Back, Forward, a Recent pick) cancels an open ConfirmDialog, so nothing is sent, and rebinds the strip to the restored selection without arming it. It never replays an action or a submission. An armed fix comes from the resolved state, never from URL parameters.
- **Program change** closes the strip; its draft stays in durable workspace state for that program. The checked set clears as any program change does, stated first in the control's description and confirmed politely after (35, History); the strip adds no dialog of its own.
- **Edit guard.** While the strip has unsent edited fields, F8 and Shift+F8 do nothing and the status line says "Finish or cancel the edit first (Esc)".
- **Batch runs.** After a checked-set run, a run-summary chip (OutcomeCell), separate from the checked-set count chip, reads "4 runs: 1 running · 2 finished · 1 failed". Each word applies a FilterChip on the host grid. A run never becomes a worklist by itself; "Collect failed as worklist (w)" opens the MarksList dialog.
- Field errors name the catalog field: "`kb` is required. Enter it in Fields…".

**Linking**

- **Publishes:** nothing. It binds the primary selection only, never a held pane or Kept card. The batch chip's words apply `f=outcome:…` on the host grid, which owns that filter; applying a filter from a link is a Go and pushes one stop.
- **Follows:** the primary selection at arming time only. While armed it keeps its bound target and offers Rebind; `.` rebinds to the focused row; a history move rebinds without arming; a program change closes it. It never rebinds from a stale response. Not holdable.
- **Targets rendered:** the bound target → the Code Browser at that build and address (the address link always carries `build`) · the submitted job → the dock Jobs record · each batch-chip word → the host rows in that state. The action id, the Rebind line and the field values are text.
- **Peek source:** Alt+↓ on the submitted job reads its stored job record as a read-only ActivityRecord; on the bound target, the cached listing at that address.
- **Absent copy:** "No target bound. Select a function first." · "No armed action" · "Submitted a3f9 for 0041b210 · pending" · "Already submitted a3f9 for this target · running" · "Checking whether the operation completed" · "outcome in dock · job 77c0" · "`kb` is required. Enter it in Fields…" · "Unavailable for build-e: no bound program." · "Finish or cancel the edit first (Esc)".
- **Target-size exception:** none; buttons are 28px (24px compact), 44px below 700px.

**Keyboard**

- APG Toolbar: one tab stop, ←/→ between controls. Enter or Space activates the focused button. Esc, with focus inside the strip, disarms and keeps the fields as a draft.
- Focus-scoped `.` in a list or grid arms or rebinds and moves focus to Run; it never posts. It is remappable and can be turned off (WCAG 2.1.4). Enter in a list always means Go, never "open the last action".

**Accessibility**

- `role="toolbar"` named "Armed action: ‹title›" ("Draft action: ‹title›" when disarmed). Prefill origins are visible text beside each field. An unavailable Run stays focusable (`aria-disabled`) with its reason in `aria-describedby`.
- Nothing is announced on pending. The terminal result is announced once, politely; a batch is coalesced when its last job ends. The Rebind line is visible status text, not a live region.
- Focus returns to the invoking row after Run or Cancel (WCAG 2.4.3); `.` moves focus to Run visibly. The armed strip counts in `sticky-offset`, so it never hides the focused row.

**Removes switching:** reopening the palette and re-entering fields for the same verb on every row, and opening the dock to see whether it ran (J21, J22; counts in the plan ledger).
