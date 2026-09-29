# ConfirmDialog

A confirm step for batch, destructive and cross-build verbs only: verb and object in the title, one sentence of consequence, the verb as the primary button.

**Consumer provides** the verb, the exact target (count, build, basis; for a type or callee, the known use or caller count), the consequence sentence and the verb label.

- **Tiering (35, Confirming edits).** The dialog opens only when Run in the ActionStrip would post a batch (a checked set), a destructive change, or a cross-build change. A struct-field retype, any structure-layout change that resizes, overwrites or clears components, and a callee-signature edit count as cross-build, because they change every use of that type or callee. Everything else confirms in place:
  - inline single-target edits (rename, retype, comment, storage) confirm in their own named editor with Enter or Save;
  - a single-target verb in the ActionStrip posts on Run;
  - saving a program bookmark posts on Run.
- Title is verb + object. The body is one sentence stating what happens and what cannot be undone here. For a type or callee it names the type or callee, the build and the known use or caller count, or "uses not indexed". Cancel is always visible. Never a naked "Are you sure?".
- Role `alertdialog`, `dialog-bg`, `shadow-popup`, square corners. Focus starts on Cancel; Esc cancels (keymap `escapeOrder`, step 1) and returns focus to the invoker (the strip or the row).
- **Frozen target.** The target is frozen when the strip armed it. If the selection or basis changed since, the dialog does not post: it says so and returns to the strip with every field kept.
- **History cancels it.** A history move (Back, Forward, a Recent pick) closes an open dialog as Cancel: nothing is sent, and the strip rebinds to the restored selection without arming. History never replays a confirmed or unconfirmed submission.
- **No dialog on navigation.** A program change, including one by Back or Forward, never raises this dialog to protect the checked set. The control's accessible description says so first ("Back · clears 12 checked rows on build-a"), the polite region confirms it afterwards, and there is no Undo for it. An explicit **Clear checked** keeps its own inline Undo.
- After confirming, the outcome lands on the invoking row as an OutcomeCell only when the job record names that row; a 202 means "pending". A refused batch (stale basis) needs a new dialog that names the new count.

**Linking**

- **Publishes:** nothing.
- **Follows:** nothing while open; it is modal and carries the target the ActionStrip armed. A history move closes it as Cancel. Not holdable.
- **Targets rendered:** none. The target is named in words (count, build, basis digest, use count); a confirm never offers a link that would leave it. After confirming, the job link appears on the row and in the strip, not here.
- **Peek source:** none.
- **Absent copy:** "Basis changed since this was armed. Nothing was submitted." · "Target no longer selected. Nothing was submitted." · "uses not indexed".
- **Target-size exception:** none; buttons are 28px, 44px below 700px.

**Keyboard**

- Tab cycles inside the dialog; Enter or Space on the focused button activates it; Esc cancels. Focus returns to the invoker.

**Accessibility**

- APG Alert dialog: `aria-modal`, `aria-labelledby` the title and `aria-describedby` the consequence sentence. Focus starts on Cancel. Everything under it is inert.
