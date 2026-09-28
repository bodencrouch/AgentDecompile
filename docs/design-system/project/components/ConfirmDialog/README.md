# ConfirmDialog

A confirm step for mutating or irreversible verbs: verb and object in the title, one sentence of consequence, the verb as the primary button.

**Consumer provides** the verb, the exact target, the consequence sentence and the verb label.

- Title is verb + object. The body is one sentence stating what happens and what cannot be undone here. Cancel is always visible.
- Role `alertdialog`, `dialog-bg`, `shadow-popup`, square corners. Focus starts on Cancel; Esc cancels and returns focus.
- Never a naked "Are you sure?". After confirming, the outcome appears only when the job's terminal result says so (a 202 means pending).
