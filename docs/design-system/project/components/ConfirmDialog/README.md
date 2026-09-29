# ConfirmDialog

A confirm step for mutating or irreversible verbs: verb and object in the title, one sentence of consequence, the verb as the primary button.

**Consumer provides** the verb, the exact target (count, build, basis), the consequence sentence and the verb label.

- Title is verb + object. The body is one sentence stating what happens and what cannot be undone here. Cancel is always visible.
- Role `alertdialog`, `dialog-bg`, `shadow-popup`, square corners. Focus starts on Cancel; Esc cancels and returns focus to the invoker (the strip or the row).
- Never a naked "Are you sure?". After confirming, the outcome lands on the invoking row as an OutcomeCell only when the job's terminal result says so; a 202 means "pending".
- The target is frozen when the strip armed it. If the selection or basis changed since, the dialog does not post: it says so and returns to the strip.

**Linking**

- **Publishes:** nothing.
- **Follows:** nothing while open; it is modal and holds the target the ActionStrip armed. Not holdable.
- **Targets rendered:** none. The target is named in words (count, build, basis digest); a confirm never offers a link that would leave it. After confirming, the job link appears on the row, not here.
- **Peek source:** none.
- **Absent copy:** "Basis changed since this was armed. Nothing was submitted." · "Target no longer selected. Nothing was submitted."
- **Target-size exception:** none; buttons are 28px.

**Keyboard**

- Tab cycles inside the dialog; Enter on the focused button activates it; Esc cancels. Focus returns to the invoker.

**Accessibility**

- APG Alert dialog: `aria-modal`, `aria-labelledby` the title and `aria-describedby` the consequence sentence. Focus starts on Cancel.
