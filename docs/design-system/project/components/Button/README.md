# Button

A square catalog-action control; the only clickable box in the chrome. Buttons act; links go.

**Use it** for verbs from the action catalog (Decompile, Match siblings, Save), for arming the ActionStrip, and for toolbar toggles. Anything that navigates to an address, symbol, counterpart, job, receipt, logical id or pipeline node is an `.ad-link`, never a Button. The result is reported on the invoking row and in the activity dock, never in the button.

**Consumer provides** the exact verb as label, an optional keyboard hint (`.ad-kbd`) mirrored in `aria-keyshortcuts`, and one variant: default, `.primary` (at most one per region: the verb the strip or dialog will run), `.quiet` (toolbar icons, always with an accessible name), `aria-pressed` for toggles, or unavailable with the reason written nearby.

- `radius-none`, `line-control` border, `pane` fill, `row-hover-bg` on hover; `control-h-comfortable` (28px) or `.compact` (24px); `touch-h` (44px) below 700px and with a coarse pointer.
- `.primary` is a 2px `ink-strong` frame and bold label; the accent is not a status. A pressed toggle uses `selection` plus `ink-strong`.
- **Toggles keep a constant name.** An `aria-pressed` toggle never renames itself; its state is words beside it ("Hold this pane" with "Follows · as I move" or "Held · ResourceRef::Resolve @ build-c · 4 min"; "Keep" with the "Kept" tag; "Selection only" with "On · ResourceRef::Resolve · build-a").
- No colored fills for "go"; destructive verbs are not red. Batch, destructive and cross-build verbs open ConfirmDialog; single-target inline edits confirm in place.
- **Unavailable** actions are `aria-disabled="true"` with the reason in `aria-describedby`, so they stay focusable and explain themselves; `disabled` is only for controls that must leave the tab order.
- Never a per-stage Run button: pipeline stages are observable, not a checklist. Keys and buttons only arm; only the ActionStrip's Run, or Enter or Save in an inline editor, posts, and it posts once. Labels of catalog verbs come from `GET /api/v1/actions`; the design system names no action ids.

**Linking**

- **Publishes:** nothing. A button never changes the location; arming writes the ActionStrip, and view toggles write only their own view state (`views`, `dock`) through their host.
- **Follows:** its host; an unavailable verb's reason updates with the primary selection after the settle. Not holdable.
- **Targets rendered:** none; a button is never a link.
- **Peek source:** none.
- **Absent copy:** the unavailable reason, for example "Select a function first." · "Needs a bound program for build-e."
- **Target-size exception:** none; 24px minimum (`.compact`), 44px below 700px and with a coarse pointer.

**Keyboard**

- Enter and Space activate; toggles flip `aria-pressed`. Inside a toolbar (ActionStrip, WorkflowControl, Views) arrows move between buttons and the toolbar has one tab stop.

**Accessibility**

- Icon-only buttons carry a name naming the destination or verb ("Back to Actor::LoadFromTemplate"). Keyboard hints are exposed with `aria-keyshortcuts`.
