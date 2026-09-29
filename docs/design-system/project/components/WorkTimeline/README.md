# WorkTimeline

Freeze, step and history for the work view, over the accepted-event stream. Code panes never follow active work; the work view keeps its own freeze, step and history, and a header chip says where the work is.

**Consumer provides** the event list (accepted, rejected, observed) with each event's id, sentence, time and the diff or transfer it drew; the work view's cursor and frozen state; and, for the header chip, the running job's record: its current build and entity.

- **Event marks** (State vocabularies, Work-view events). Each mark is a shape plus a glyph plus a word; color is never the only carrier:
  - accepted: a tall tick with ✓ and the word "accepted";
  - rejected: a short tick with ✕ and the word "rejected", never a diamond (◇ and ◆ are reserved for gates);
  - observed: a plain tick and the word "observed".
- **The cursor** is a 2px `ink-strong` frame around the current event on the track and in the list, plus its sentence ("Event 41 of 58 · accepted identity edge · build-b · 13:57:52"). It is never the accent.
- **The event list is the accessible form**: an ordered list of every retained event, newest first, each with its glyph, word, sentence and time. The track is a second cue.
- **Freeze** stops the picture and queues new events without dropping them ("Frozen at 13:57:52 · 3 events since"). It freezes this view only. Step moves one event. Never auto-pan away from the operator. Reduced motion shows the same step as a static before/after.
- **Header chip**: "Job a3f9 is at build-b · ResourceRef::Resolve · Go". It updates silently. **Go** is an explicit move that pushes one history stop; its description states any build switch and checked-set clearing first ("switches the inspected build to build-b · clears 4 checked rows on build-a"). Nothing else in the work view moves the primary selection.
- **Events are links.** Enter on an event link (or on the cursor sentence) is Go to the evidence it drew at that moment: PropagationTransfer, SourceRepairDiff, ObjectDiff, CandidateAlignment or IdentityEdge. It writes `t=` and pushes one stop; the primary location does not move. Shift+Enter opens that evidence beside as a Held pane (on 8080 without split panes, in a new window: "Open beside (new window)"). Stepping the track moves only the work view's own cursor and writes nothing to the URL or browser history.

**Linking**

- **Publishes:** `t` on Go from an event link (push). The chip's Go publishes `entity`, `build` and `addr` (push). Stepping publishes nothing.
- **Follows:** the work view it controls, never the primary selection; the chip follows the job record. Not holdable itself; evidence opened beside from an event is a Held pane.
- **Targets rendered:** event → the work-view evidence it drew at that moment (`t=`); focus lands on the timeline event · the chip's job → the dock Jobs record · the chip's Go → the Code Browser at the job's build and entity. Link names read "Event 41 of 58, accepted identity edge, build-b, 13:57:52".
- **Peek source:** Alt+↓ on an event reads its stored accepted-event receipt; nothing is replayed live.
- **Absent copy:** "No events recorded for this view." · "event evidence not recorded" (plain, no link) · "Event ‹id› is no longer retained" · "Frozen at 13:57:52 · 3 events since".
- **Target-size exception:** none; step buttons and Freeze are 24px, the track is one slider at least 24px tall, and list rows are 24px. With a coarse pointer each event row carries one 44px row-menu button with the same link menu; there is no long-press.

**Keyboard**

- The track is `role="slider"` (the only slider; EntityTimeline stays an APG grid): ←/→ step one event, Home/End first and last, PageUp/PageDown ten events. Enter on the cursor sentence or an event link is Go. The step buttons and Freeze sit beside it in Tab order.

**Accessibility**

- The slider carries `aria-valuetext` in words. The event list is an `<ol>` of links; the current event has `aria-current="true"`. Glyphs are `aria-hidden` beside their words.
- Stepping announces nothing; the sentence is visible text. The chip updates silently. A frozen view later reports "N events since frozen".

**Removes switching:** opening the evidence list and scrolling history to inspect what one work-view event drew (J20; counts in the plan ledger).
