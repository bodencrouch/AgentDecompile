# Button

A square catalog-action control; the only clickable box in the chrome. Buttons act; links go.

**Use it** for verbs from the action catalog (Decompile, Match siblings, Save), for arming the ActionStrip, and for toolbar toggles. Anything that navigates to an address, symbol, counterpart, job, receipt, logical id or pipeline node is an `.ad-link`, never a Button. The result is reported on the invoking row and in the activity dock, never in the button.

**Consumer provides** the exact verb as label, an optional keyboard hint (`.ad-kbd`) mirrored in `aria-keyshortcuts`, and one variant: default, `.primary` (at most one per region: the verb the strip or dialog will run), `.quiet` (toolbar icons, always with an accessible name), `aria-pressed` for toggles, or unavailable with the reason written nearby.

- `radius-none`, `line-control` border, `pane` fill, `row-hover-bg` on hover; `control-h-comfortable` (28px) or `.compact` (24px); `touch-h` below 700px.
- `.primary` is a 2px `ink-strong` frame and bold label; the accent is not a status. A pressed toggle uses `selection` plus `ink-strong`.
- No colored fills for "go"; destructive verbs are not red, they open ConfirmDialog.
- **Unavailable** actions are `aria-disabled="true"` with the reason in `aria-describedby`, so they stay focusable and explain themselves; `disabled` is only for controls that must leave the tab order.
- Never a per-stage Run button: pipeline stages are observable, not a checklist. Keys and buttons only arm; mutations confirm once.

**Linking**

- **Publishes:** nothing. A button never changes the location; arming writes the ActionStrip, and view toggles write only their own view state (`views`, `dock`) through their host.
- **Follows:** its host; an unavailable verb's reason updates with the primary selection after the settle. Not holdable.
- **Targets rendered:** none; a button is never a link.
- **Peek source:** none.
- **Absent copy:** the unavailable reason, for example "Select a function first." · "Needs a bound program for build-e."
- **Target-size exception:** none; 24px minimum (`.compact`), 44px below 700px.

**Keyboard**

- Enter and Space activate; toggles flip `aria-pressed`. Inside a toolbar (ActionStrip, WorkflowControl, Views) arrows move between buttons and the toolbar has one tab stop.

**Accessibility**

- Icon-only buttons carry a name naming the destination or verb ("Back to Actor::LoadFromTemplate"). Keyboard hints are exposed with `aria-keyshortcuts`.
