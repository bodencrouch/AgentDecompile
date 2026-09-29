# EntityTimeline

Per-entity history in the evidence rail: receipts, jobs, facts changing state, name and type edits, propagation in and out, and basis changes, in time order, each event linked both ways along fact → receipt → job → stage node → changed entities.

**Use it** as a section of the evidence rail for the one primary selection, and as a kept evidence card when an operator wants one entity's history to stay while the selection moves. It answers "what happened to this, and what did it, since I last looked" without opening the dock, the Recovery workspace or a report.

**Consumer provides** the entity (logical id, concrete build and address) and an ordered event list from the event store. Per event: time, kind, the before and after values or fact states, the reason ("basis changed: build-b relinked"), provenance (fresh, reused, historical, legacy) with basis and read time, and the chain of references it belongs to: receipt, job, pipeline node, and the entities that event changed. Also: when this viewer last looked at this entity (per viewer, durable workspace state), the count of stored older events, and the read time.

- **Event kinds** are words in `type-kicker`: Fact, Receipt, Job, Name edit, Type edit, Propagation in (← from ‹build›), Propagation out (→ to ‹build›), Basis. Fact changes show both states with FactBadge glyphs and words ("Linked match ✓ passed → ◷ stale"); a blocked transfer shows ✕ "blocked" and the conflicting field. Nothing is summed, scored or merged: two facts changing at once are two events.
- **Fresh, reused and historical never look alike.** Each event that carries evidence has a ProvenanceStamp: fresh (2px `ink-strong` frame), reused (plain frame, "dependencies unchanged since it was made"), historical (dashed frame, "fenced; not current acceptance"). A basis change says how many receipts became historical and links to them. Reused evidence is never re-dated as a fresh run.
- **Changes since you looked** sits at the top: a count, when the viewer last looked, and one line per change in plain words, with **Go to first change** and **Mark as seen**. Events after that point carry a "new" word chip and a filled `ink-strong` node; a divider row reads "You looked at 13:02". "Looked" means this viewer had the entity as the primary selection; hover, peek and prefetch do not count. Marking as seen is per viewer and changes nothing else.
- **Linked both ways.** Each event ends with its chain as typed links separated by aria-hidden arrows: receipt → job → stage node → changed entities ("14 entities"). The receipt card, job record and pipeline node each show "In history: ‹time› event for this entity", which opens this timeline scrolled to that event. A name transfer also links its work-view event (`t=`) so the WorkTimeline opens at that moment.
- The rail is a vertical rule in `line-control` with 9px square nodes: hollow for seen, filled `ink-strong` for new, dashed for historical. Node, word and stamp all carry the difference; color never does.
- Order is newest first. Filters: **This build | All builds** (all builds prefixes each event with its build) and provenance (All, Fresh, Reused, Historical). Filters change only this list.
- **Older history is not loaded until asked.** The last row says "○ Not loaded. Open to read it. 22 older events are stored; reading them starts no work." **Read older** reads stored events only; it never analyzes, imports or recompiles.
- **Follows the selection** (sync icon plus "Follows selection"). On a selection change the previous history stays, dimmed, with "Loading history for ‹name›"; a late response for the old selection is dropped. **K** keeps it as an evidence card labelled **Kept** in a 2px `ink-strong` frame with its age and "not following"; when its basis changes it says "◷ Basis changed since kept" and offers **Refresh** and **Make primary**. It never refreshes by itself.
- Empty is an answer: "No recorded changes for ‹entity› on ‹build›. Existing analysis only."
- Fits the 260px rail default and grows to 480px; times are `type-code-small`, sentences `type-ui`, reasons 11px `ink-muted`. Below 700px it becomes part of the Inspect pane with 44px targets.
- Both surfaces read the same event store. The static 8080 surface may omit the provenance filter; it never omits stamps, the "since you looked" block or the chain links.

**Linking**

- Publishes: nothing on focus. Enter on an event goes to the thing that changed (the fact's receipt card, the edited name or type in the Code Browser, the job record), pushing one history stop; `receipt=` or `job=` with `e`, `b` carry it.
- Follows: the primary selection (entity and inspected build), unless kept.
- Renders: fact (receipt card), receipt id, job id, pipeline node id, basis digest, counterpart (entity @ build), work-view event, and a changed-entities set (the job's Targets list).
- Absent: "no job" for direct saves, "unresolved on build-d" for a missing counterpart, and "Not loaded" for older events; never a guessed link.

**Keyboard**

- APG Grid (layout grid) with one tab stop: ↑/↓ move between events, ←/→ between the event and its chain links, Home/End to the first and last event. Enter goes; Shift+Enter opens beside; Alt+↓ peeks the focused link; Shift+F10 opens **Reveal in**.
- **K** keeps the timeline as a card when focus is on the timeline card itself (its header or the "since you looked" block); on an event row, j/k keep their row-movement meaning. Both are remappable in KeymapSettings.
- **Go to first change** moves focus to the oldest new event. The toolbar precedes the grid in Tab order.

**Accessibility**

- `role="grid"` named "History of ‹entity› on ‹build›, newest first" with `aria-rowcount` for all stored events; the time is the row header. An event reads as a sentence: "13:58, fact, new: Linked match passed to stale, because its basis changed. Fresh objdiff. Receipt d41a, job a3f9, stage 7, 14 entities."
- Arrows and state glyphs are `aria-hidden`, with "to", "from" and state words present. Identifiers carry `translate="no"`.
- "N changes since you looked" is one polite announcement when the entity becomes the selection, never per event or poll (WCAG 4.1.3).
- Filtering or reading older events never moves focus or the selection (WCAG 3.2.2). `scroll-padding-block` keeps the focused event clear of the header (2.4.11). Chain links are 24px tall, 44px below 700px (2.5.8).

**Removes switching:** J02 "fact → receipt → job" goes from 5 switches (fact strip, Evidence rail, Recovery or Report, Jobs dock, log tail) to 1. J19 "which entities did this job change" goes from 4 to 1 through the "14 entities" link. J35 "why is this fact stale" goes from 3 to 0: the reason is on the event. J03 "which stage produced this receipt" goes from 4 to 0: the stage node is in the chain. Counts before come from the journeys table; after counts are design targets.
