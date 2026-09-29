# MilestoneCard

A capability milestone with its delivery status kicker, body and acceptance predicate.

**Consumer provides** the milestone id and title, the delivery status, the body lines and the acceptance paragraph.

- `pane`, 1px stroke in the status color, `radius-milestone`; title in `ink-strong`; uppercase kicker in the stroke color.
- Status colors: implemented foundation `role-bytes`; future delivery `role-step` (engine capability) or `role-acceptance` (creative, playback); future qualification and feasibility `role-gate`.
- A milestone's status is a claim with evidence. Future milestones are ambitions, not completed features. The kicker's words carry the status; the stroke color never does alone.

**Linking**

- **Publishes:** nothing. Diagram-only.
- **Follows:** nothing; the content is `pipeline-model.json`.
- **Targets rendered:** in app renderings the title links to its pipeline node (`?node=milestone-M0`…`milestone-M7`); in docs to the outline anchor (`autonomous-capabilities.outline.md#milestone-M2`). An "Evidence:" line names receipts only where one exists; each is a receipt link to its receipt card.
- **Absent copy:** "Live delivery is unverified." and "not run" where no evidence exists; a future milestone never links to a receipt.

**Accessibility**

- Each card is a list item with a heading; the kicker is text. In the SVG each card is a `<g id="milestone-M0">`.
