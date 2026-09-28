# WorkTimeline

Freeze, step and history for any animated work view, over the accepted-event stream.

**Consumer provides** the event list (accepted, rejected, observed) with cursor, and the current position.

- Pause freezes the picture; step moves one event; the track shows accepted (`fact-passed`) and rejected (`fact-failed`) events, the cursor in `accent`.
- Never auto-pan away from the operator. Reduced motion shows the same step as a static before/after.
