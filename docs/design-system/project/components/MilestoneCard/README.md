# MilestoneCard

A capability milestone with its delivery status kicker, body and acceptance predicate.

**Consumer provides** the milestone id and title, the delivery status, the body lines and the acceptance paragraph.

- `pane`, 1px stroke in the status color, `radius-milestone`; title in `ink-strong`; uppercase kicker in the stroke color.
- Status colors: implemented foundation `role-bytes`; future delivery `role-step` (engine capability) or `role-acceptance` (creative, playback); future qualification and feasibility `role-gate`.
- A milestone's status is a claim with evidence. Future milestones are ambitions, not completed features. The kicker's words carry the status; the stroke color never does alone.

**Linking:** none (print diagram). Its nodes keep their pipeline-model ids (`milestone-M0`…`milestone-M7`): where the app renders the same node (a capability status view or go to `~milestone-M2`), that rendering links it to `?node=` with that id, and in docs the name links to the outline anchor (`autonomous-capabilities.outline.md#…`). The print canvas itself carries no links and no live data.

**Accessibility**

- Each card is a list item with a heading; the kicker is text. In the SVG each card is a `<g id="milestone-M0">`.
