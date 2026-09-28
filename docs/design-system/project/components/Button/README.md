# Button

A square catalog-action control; the only clickable box in the chrome.

**Use it** for verbs from the action catalog (Decompile, Match siblings, Save) and toolbar toggles. The result is reported in the activity dock, never in the button.

**Consumer provides** the exact verb as label, an optional keyboard hint (`.ad-kbd`), and one variant: default, `.primary` (at most one per region: the verb the strip or dialog will run), `.quiet` (toolbar icons), `aria-pressed` for toggles, `disabled` with the reason written nearby.

- `radius-none`, `line-control` border, `pane` fill, `row-hover-bg` on hover; `control-h-comfortable` (28px) or `.compact` (24px); `touch-h` below 700px.
- A pressed toggle uses `selection`. No colored fills for "go"; destructive verbs are not red, they open ConfirmDialog.
- Never a per-stage Run button: pipeline stages are observable, not a checklist.
