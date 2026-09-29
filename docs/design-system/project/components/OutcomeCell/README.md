# OutcomeCell

The outcome of a verb, landed on the row that invoked it: a compact TaskLifecycle ("a3f9 · running · unit 3 of 6", then "finished", "failed" or "cancelled") with its job id as a typed link, never merged into the row's facts.

**Use it** in an Outcome column or line on EntityRow, MatchReview, token rows and every checked-set row after the ActionStrip submits, and as the per-row result of a batch. A batch adds one summary chip above the grid: "4 runs: 1 running · 2 finished · 1 failed", whose words are filter links. It replaces reading the Jobs dock to learn what happened to the row in front of you.

**Consumer provides** for each row: the latest job this viewer submitted for the row's exact bound target (from the submitting client), or any job whose own record names that target; the job id, catalog verb and lifecycle state (pending after HTTP 202, admitted, waiting with its blocking owner, running, finished, failed, cancelled, or "checking" for an ambiguous submit); measured units when instrumented, else the last event time; for a finished job, the facts whose receipts that job wrote, each with the new receipt id; for failed and cancelled, the job record's reason and kept outputs. For a batch: its worklist id and the per-state counts.

- Order in the cell: the job id (`type-code-small` mono link), the state word, then detail in `ink-muted`. Words carry every state; glyphs appear only on terminals, from TaskLifecycle: ✕ failed in `fact-failed`, ⊗ cancelled in `fact-unknown`.
- The state word sits in a small `radius-chip` frame, drawn in the TaskLifecycle rail's shapes: **running** has the 2px `ink-strong` "now" frame; **finished**, **failed** and **cancelled** a solid 1px `line-control`; **pending**, **admitted**, **waiting** and **checking** a dashed 1px `line-control`. Never a spinner, a pulse, a percentage or an ETA.
- **pending · job a3f9** after HTTP 202: the job exists, nothing is shown optimistically. **waiting** names the owner and resource ("lock 1 owned by 77c0, external"); resource occupancy is not a negative result. **running** shows "unit 3 of 6" only from measured durable units; otherwise "Progress unknown · last event 13:52".
- **finished** lists, as FactBadge words on a second line, only the facts whose receipts that job wrote: "Compilation: passed, new receipt", or "Compilation: failed, new receipt · C2065 archive.c(88)". A finished job can carry a failed fact. With no fact receipt it says "no fact receipts written". The cell never repaints the row's FactStrip and never says matched, verified or done. The host carries "A finished job is not a match." once. For a resolution job, the row's OutcomeTag ("unresolved", "ambiguous") sits beside the cell and says what the ladder concluded; the two are never merged.
- **failed** is the job's own failure from its record ("worker exited 1"), distinct from a failed fact. **cancelled** names who cancelled and what was kept ("outputs of 2 units kept"); it never claims a rollback.
- **checking**: an ambiguous submit reads "Checking whether the operation completed", and mutation of that operation on that row is disabled with that reason until reconciled. Read-only views stay available.
- **outcome in dock · job a3f9** when the job record does not name the row's bound target. The cell never attaches an outcome by timing or by a job that merely ran nearby.
- **Batch summary** (`.ad-ocsum`): "4 runs:" in `ink-strong`, then one link per non-zero state ("1 running", "2 finished", "1 failed"). Each link applies a FilterChip on the host grid (`f=outcome:failed`, replaceState) within the run's worklist (`wl=run-b7e2`), so F8 steps exactly those rows. The checked-set count chip stays separate.
- Stale responses update only their own row, never another row and never the ActionStrip binding. A row whose target changed since submission keeps its cell, labelled with the job's target, until the next navigation.
- Both surfaces render the cell from the same job records and client submissions; there is no new job store or scheduler. The static 8080 surface renders the same words server-side.

**Linking**

- **Publishes:** nothing; the cell never moves the primary location. Its batch words apply `f=outcome:…` to the host grid, which owns that filter (replaceState).
- **Follows:** its row's bound target and the job records that name it; it changes only when a job transition arrives. The dock's Freeze updates freezes it too. Not holdable.
- **Targets rendered:** job id → the dock Jobs record, focused (it does not move the primary location) · receipt id ("new receipt") → its receipt card · compiler diagnostic → the SourceRepairDiff line · lock and owner → the PipelineMap lock node and the owner's job record · batch words → the rows in that state (FilterChip). Link names read "Job a3f9, compile candidate, running".
- **Peek source:** Alt+↓ on a job id reads the stored job record as a read-only ActivityRecord (three readouts, StageChip, target named by the record); Shift+K inside the Peek keeps it. On a receipt it reads the stored receipt.
- **Absent copy:** no cell before any verb ran on the row · "pending · job a3f9" · "outcome in dock · job a3f9" (the record names no bound target) · "Progress unknown · last event 13:52" · "no fact receipts written".
- **Target-size exception:** inline: "new receipt" and diagnostic links inside the fact sentence rely on the inline exception. Job ids and batch words are 24px; 44px below 700px.

**Keyboard**

- The cell's links are items of its grid cell (`tabindex="-1"`); the host grid reaches them with its cell navigation. The one link grammar applies: Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 opens the link menu, Ctrl/Cmd+Enter opens a browser tab.
- After Run or Cancel, focus returns to the invoking row (WCAG 2.4.3). j/k move to the next row; focus-scoped `.` repeats the armed ActionStrip action on the focused row (ActionStrip owns it; remappable, WCAG 2.1.4).
- The batch summary words are ordinary links in the host header's Tab order.

**Accessibility**

- The row references its cell with `aria-describedby`, so moving to a row reads "ResourceRef::Resolve … a3f9 running unit 3 of 6". Job links are named "Job a3f9, compile candidate, running". Glyphs are `aria-hidden` beside their words.
- One polite message per job transition (started, finished, failed, cancelled). A batch is coalesced when its last job ends: "Run on 4 rows: 3 finished, 1 failed." Never per poll; unit progress in the cell is not live. The dock's Freeze updates also freezes the cells and reports "N events since frozen".
- Assertive only for "checking" when it blocks the action in hand.
- Job links and batch words are at least 24px tall; 44px below 700px. Text survives WCAG 1.4.12 spacing; the cell wraps, never truncates.
- Forced colors map state frames to `CanvasText`; the running frame keeps its 2px weight.

**Removes switching:** J21, run a verb on the selected function and read its outcome, goes from 5 switches to 2 (the outcome is read on the row; the dock is needed only on failure). J22, one verb on a checked set, goes from 7 to 2 independent of batch size: one cell per row, the summary's "1 failed" filters to it and F8 steps it. J12's Jobs-dock verification trip is removed, J30's imported rows show acceptance in place, and J19 reaches the job from the row in 1.
