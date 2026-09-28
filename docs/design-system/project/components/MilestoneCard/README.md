# MilestoneCard

A capability milestone with its delivery status kicker, body and acceptance predicate.

**Consumer provides** the milestone id and title, the delivery status, the body lines and the acceptance paragraph.

- `pane`, 1px stroke in the status color, `radius-milestone`; title in `ink-strong`; uppercase kicker in the stroke color.
- Status colors: implemented foundation `role-bytes`; future delivery `role-step` (engine capability) or `role-acceptance` (creative, playback); future qualification and feasibility `role-gate`.
- A milestone's status is a claim with evidence. Future milestones are ambitions, not completed features.
