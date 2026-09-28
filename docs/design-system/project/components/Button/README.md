# Button

A square, 24px catalog-action control; the only clickable box in the chrome.

**Use it** for verbs from the action catalog (Decompile, Match siblings, Save) and for toolbar toggles. Label with the exact verb; the result is reported in the activity dock, never in the button.

**Consumer provides** the label, an optional keyboard hint (`.ad-kbd`), and one of: default, `.primary` (at most one per region: the verb the strip or dialog will run), `.quiet` (toolbar icons), `aria-pressed` for toggles, `disabled` with a reason nearby.

- Square corners (`radius-none`), `line-control` border, `pane` fill, `raised` on hover.
- A pressed toggle uses `selection`; never a colored fill for "go".
- `.roomy` uses `control-h-roomy` (28px) in the navigation bar and roomy density; below 700px every button is `touch-h`.
- Don't make destructive buttons red. Destructive verbs open a confirm step that names the target and says what cannot be undone.
