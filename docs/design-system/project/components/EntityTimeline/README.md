# EntityTimeline

Per-entity history in the evidence rail: receipts, jobs, facts changing state, name and type edits, propagation in and out, and basis changes, in time order, each event linked both ways along fact → receipt → job → stage node → changed entities.

**Use it** as a section of the evidence rail for the one primary selection, and as a kept evidence card when an operator wants one entity's history to stay while the selection moves. It answers "what happened to this, and what did it, since I last looked" without opening the dock, the Recovery workspace or a report.

**Consumer provides** the entity (logical id, concrete build and address) and an ordered event list from the event store. Per event: time, kind, the before and after values or fact states, the reason ("basis changed: build-b relinked"), provenance (fresh, reused, historical, legacy) with basis and read time, and the chain of references it belongs to: receipt, job, pipeline node, and the entities that event changed. Also: when this viewer last looked at this entity (per viewer, durable workspace state), the count of stored older events, and the read time.

- **Event kinds** are words in `type-kicker`: Fact, Receipt, Job, Name edit, Type edit, Propagation in (← from ‹build›), Propagation out (→ to ‹build›), Basis. Fact changes show both states with FactBadge glyphs and words ("Linked match ✓ passed → ◷ stale"); a blocked transfer shows ✕ "blocked" and the conflicting field. Nothing is summed, scored or merged: two facts changing at once are two events.
- **Fresh, reused and historical never look alike.** Each event that carries evidence has a ProvenanceStamp: fresh (2px `ink-strong` frame), reused (plain frame, "dependencies unchanged since it was made"), historical (dashed frame, "fenced; not current acceptance"). A basis change says how many receipts became historical and links to them. Reused evidence is never re-dated as a fresh run.
- **Changes since you looked** sits at the top: a count, when the viewer last looked, and one line per change in plain words, with **Go to first change** and **Mark as seen**. Events after that point carry a "new" word chip and a filled `ink-strong` node; a divider row reads "You looked at 13:02". "Looked" means this viewer had the entity as the primary selection; hover, peek and prefetch do not count. Marking as seen is per viewer and changes nothing else.
- **Linked both ways.** Each event ends with its chain as typed links separated by aria-hidden arrows: receipt → job → stage node → the job's Changed list ("14 entities"). The stage node comes from the job's verb in `catalog_verbs`; an unmapped verb shows "stage: unmapped" as words. The Changed link applies the FilterChip "Changed by a3f9" to the Functions list (`f=changed:a3f9`, a Go); a job that recorded no units offers no Changed link. The receipt card, job record and pipeline node each show "In history: ‹time› event for this entity", which opens this timeline scrolled to that event. A name transfer also links its work-view event (`t=`) so the WorkTimeline opens at that moment.
- The rail is a vertical rule in `line-control` with 9px square nodes: hollow for seen, filled `ink-strong` for new, dashed for historical. Node, word and stamp all carry the difference; color never does.
- Order is newest first. Filters: **This build | All builds** (all builds prefixes each event with its build), provenance (All, Fresh, Reused, Historical) and actor (**Human | Agent**) where events record the actor; otherwise the filter is replaced by the words "actor not recorded". Filters change only this list.
- **Older history is not loaded until asked.** The last row says "○ Not loaded. Open to read it. 22 older events are stored; reading them starts no work." **Read older** reads stored events only; it never analyzes, imports or recompiles.
- **Follows the selection** ("Follows selection"). On a selection change the previous history stays, dimmed, with "Loading history for ‹name›"; a late response for the old selection is dropped. **Keep** (`aria-pressed`, constant name) keeps it as an evidence card labelled **Kept** with its age and "not following"; when its basis changes it says "◷ Basis changed since kept · Refresh". It never refreshes by itself; Enter on a link inside the kept card goes.
- Empty is an answer: "No recorded changes for ‹entity› on ‹build›. Existing analysis only."
- **Moving between events writes nothing.** Arrows move focus only; no `t=` and no history. Only Enter on a link goes, and Enter on a work-view event link pushes one stop with `t=`. This stays an APG grid; only the WorkTimeline track is a slider.
- Fits the 260px rail default and grows to 480px; times are `type-code-small`, sentences `type-ui`, reasons 11px `ink-muted`. Below 700px it becomes part of NarrowFlow's Inspect pane with 44px targets.
- Both surfaces read the same event store. The static 8080 surface may omit the provenance filter; it never omits stamps, the "since you looked" block or the chain links.

**Linking**

- **Publishes:** nothing on focus or on moving between events. Enter on an event link goes to the thing that changed (the fact's receipt card, the edited name or type in the Code Browser, the job record), pushing one history stop; `receipt` or `job` with `entity` and `build` carry it, and a work-view event link carries `t=`. Keep publishes `keep=history:‹entity›@‹build›` (replaceState).
- **Follows:** the primary selection (entity and inspected build) after the settle, unless kept. It is a rail section, so it is kept as a card, never held.
- **Targets rendered:** fact → its receipt card · receipt id · job id → the dock Jobs record · pipeline node → the PipelineMap node · basis digest → the ProvenanceStamp detail · counterpart (entity @ build, with its edge word) · work-view event → the WorkTimeline at `t=` · the job's Changed list → the Functions list filtered by `f=changed:‹job›`.
- **Peek source:** Alt+↓ on a chain link reads the stored receipt, the stored job record as of the dock's last read, the node's model text or the counterpart Peek. "Read older" reads stored events only.
- **Absent copy:** "no job" for direct saves · "unresolved on build-d" for a missing counterpart · "stage: unmapped" · "Changed entities: not recorded" · "actor not recorded" · "Not loaded. Open to read it." for older events; never a guessed link.
- **Target-size exception:** chain links are inline links in a 24px row and rely on the WCAG 2.5.8 inline exception; buttons are 24px; 44px below 700px and with a coarse pointer.

**Keyboard**

- APG Grid (layout grid) with one tab stop: ↑/↓ move between events, ←/→ between the event and its chain links, Home/End to the first and last event. Moving writes no `t=` and no history. Enter goes; Shift+Enter opens beside; Alt+↓ peeks the focused link; Shift+F10 opens the one link menu.
- **Keep** is the header's `aria-pressed` button. Shift+K (`link.keep`) keeps only while focus is inside the section's header or the "since you looked" block, never on an event row, where k moves (`list.move`). Both are remappable in KeymapSettings. Esc follows the one Esc order in the Keymap section.
- **Go to first change** moves focus to the oldest new event. The toolbar precedes the grid in Tab order.

**Accessibility**

- `role="grid"` named "History of ‹entity› on ‹build›, newest first" with `aria-rowcount` for all stored events; the time is the row header. An event reads as a sentence: "13:58, fact, new: Linked match passed to stale, because its basis changed. Fresh objdiff. Receipt d41a, job a3f9, stage 7, 14 entities."
- Arrows and state glyphs are `aria-hidden`, with "to", "from" and state words present. Identifiers carry `translate="no"`.
- "N changes since you looked" is one polite announcement when the entity becomes the selection, never per event or poll (WCAG 4.1.3).
- Filtering or reading older events never moves focus or the selection (WCAG 3.2.2). `scroll-padding-block` keeps the focused event clear of the header (2.4.11). Chain links are 24px tall, 44px below 700px (2.5.8).

**Removes switching:** the ledger's counts, with their credits: J02 "fact → receipt → job" 5 → 1, J19 "which entities did this job change" 4 → 1 through the Changed link, and J03 "which stage produced this receipt" 4 → 0 where the verb is mapped, all credited to U180. J35 "why is this fact stale" 3 → 0 (1 when the basis evidence is not cached) is credited to U174; the event's reason supports it. Add 1 below 700px wherever the dock is involved.

**Parity extensions (2026-09-29)**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): A07, S10.

- **Comment history (A07).** Comment edits become events of kind "comment": the comment type (EOL, pre, post, plate, repeatable), the address, before and after text, who made it (you, agent, external) and the job or inline edit. Read from the program's comment history through a catalog read action; until one exists, older comment edits read "comment history not recorded before ‹time›" and only edits made through this workbench appear.
- **Label history (S10).** Label adds, renames and removals become events of kind "label", with before and after names, the symbol source (user, analysis, imported, default) and the job. NameProvenance keeps the tier; the timeline keeps the order.
- Both kinds are per build: an entity's timeline shows the build on each event, and a propagated rename shows one event per recipient. The existing filter gains "Comments" and "Labels". The preview is unchanged.
