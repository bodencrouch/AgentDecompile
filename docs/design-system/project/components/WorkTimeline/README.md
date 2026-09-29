# WorkTimeline

Freeze, step and history for any animated work view, over the accepted-event stream.

**Consumer provides** the event list (accepted, rejected, observed) with each event's sentence and the diff or transfer it drew, the cursor, and the current position.

- Pause freezes the picture; step moves one event; the track shows accepted (`fact-passed`) and rejected (`fact-failed`) events and the cursor.
- **Non-color cue**: accepted events are tall bars, rejected events are small diamonds, observed events are short bars, and the cursor is a 2px bar plus the event sentence ("Event 41 of 58 · accepted identity edge · build-b · 13:57:52"). Color is never the only carrier.
- **Events are links.** The current event's sentence links to the diff or transfer it drew, at that moment (`t=41`); the listed recent events do the same. Stepping writes `t=` with replaceState.
- Never auto-pan away from the operator. "Follow active work" can be turned on only for a held or secondary pane, never the primary. Reduced motion shows the same step as a static before/after.

**Linking**

- **Publishes:** `t` (replaceState while stepping; Go on an event pushes one history stop).
- **Follows:** the work view it controls; not holdable itself, but the pane it steps may be held.
- **Targets rendered:** event → the work-view evidence it drew at that moment: PropagationTransfer, SourceRepairDiff, ObjectDiff, CandidateAlignment or IdentityEdge (`t=`), opened beside when Shift+Enter · the event's job → the dock Jobs record · its build → the counterpart in the Code Browser. Link names read "Event 41 of 58, accepted identity edge, build-b, 13:57:52".
- **Peek source:** the stored accepted-event receipts; nothing is replayed live.
- **Absent copy:** "No events recorded for this view." · "event evidence not recorded" (plain, no link) · "Frozen at 13:57:52 · 3 events since".
- **Target-size exception:** none; step buttons are 24px and the track is one slider at least 24px tall.

**Keyboard**

- The track is a slider: ←/→ step one event, Home/End first and last, PageUp/PageDown ten events. Enter on the cursor sentence goes to that event's evidence.

**Accessibility**

- The cursor is `role="slider"` with `aria-valuetext` in words; the event list is a list of links. Stepping announces nothing; the sentence is visible text.

**Removes switching:** opening the evidence list and scrolling history to inspect what one work-view event drew (J20).
