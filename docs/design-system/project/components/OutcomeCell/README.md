# OutcomeCell

The outcome of a verb, landed on the row it acted on: the compact TaskLifecycle ("a3f9 · running · unit 3 of 6 · by you", then finished, failed or cancelled) with its job id as a typed link, never merged into the row's facts.

**Use it** in an Outcome column or a wrapped second line on EntityRow, MatchReview, token rows and checked-set rows after the ActionStrip submits, and as the per-row result of a batch. It replaces reading the Jobs dock to learn what happened to the row in front of you.

**Consumer provides** for each row: the latest job whose own record names the row's exact bound target (the catalog submission records its binding); the job id, catalog verb, submitter (you, an agent, or external) and Job outcome word; measured units when instrumented, else the last event time; for a terminal job, the facts whose receipts that job wrote, each with its receipt id and time, and whether the receipt was reused; for failed and cancelled, the record's reason and kept outputs; whether the record reports per-target units; and whether the host region is frozen. For a batch: the per-word counts.

- **Binding from the job record only.** The cell shows a job only when that job's record names the row's target. Client memory, the submitting tab and timing are never the source, so both surfaces draw the same cell on the same row. A record with no binding draws no cell on either surface; only the ActionStrip's own line reports it ("outcome in dock · job 77c0").
- **Words from the Job outcome vocabulary** (State vocabularies): pending, admitted, waiting, running, checking, finished, failed, cancelled. Terminal words are finished, failed and cancelled. Glyphs appear only on terminals: ✕ failed in `fact-failed`, ⊗ cancelled in `fact-unknown`.
- Order in the cell: the job id (`type-code-small` mono link), the state word in a small `radius-chip` frame, then detail in `ink-muted` ending with the submitter ("by you", "by agent", "external"). **running** has the 2px `ink-strong` now-frame; finished, failed and cancelled a solid 1px `line-control`; pending, admitted, waiting and checking a dashed 1px `line-control`. The accent is never a status. Never a spinner, a pulse, a percentage or an ETA.
- **pending · job a3f9** after HTTP 202: the job record exists; nothing is shown optimistically. **waiting** names the owner and resource ("lock 1 owned by 77c0, external"); resource occupancy is not a negative result. **running** shows "unit 3 of 6" only from measured durable units, otherwise "Progress unknown · last event 13:52".
- **Facts as of the job.** Under a terminal word, as FactBadge words on a second line, only the facts whose receipts that job wrote: "Compilation: passed · receipt 7c21 14:03", or "Compilation: passed · reused receipt 7c21". When the row's FactStrip later changes, the line turns historical ("historical · facts changed since this job"). A finished job can carry a failed fact. With no fact receipt: "no fact receipts written". The cell never repaints the FactStrip and never says matched, verified or done; the host carries "A finished job is not a match." once. For a resolution job, the row's OutcomeTag sits beside the cell and says what the ladder concluded; the two are never merged.
- **failed** is the job's own failure from its record ("worker exited 1"), not a failed fact. **cancelled** names who cancelled and what was kept ("outputs of 2 units kept"); it never claims a rollback.
- **checking**: an ambiguous submit reads "Checking whether the operation completed", and the ActionStrip's Run for that verb and target is `aria-disabled` with that reason until reconciled. Read-only views stay available.
- **Batches.** A checked row gets its own cell only when the batch job's record reports per-target units; otherwise it reads "in batch job ‹id› · per-row outcome not reported". A **run-summary chip** (`.ad-ocsum`), separate from the checked-set count chip, reads "4 runs: 1 running · 2 finished · 1 failed". Each non-zero word is a link that applies a FilterChip on the host grid (`f=outcome:failed`); a filter applied from a link is a Go and pushes one stop. A run never becomes a worklist by itself: **Collect failed as worklist (w)** opens the MarksList dialog, and only then does F8 step those rows.
- **Freeze is per region.** The host region's own Freeze updates freezes its cells, which then read "Frozen at 14:02 · 2 events since" where they are. The dock's Freeze never freezes cells in another region.
- **Width.** At navigator widths (240px) the cell is a wrapped second line under the name, never truncated.
- Stale responses update only their own row, never another row and never the ActionStrip binding. A row whose target changed since submission keeps its cell, labelled with the job's target, until the next navigation.
- Both surfaces render the cell from the same job records; there is no new job store or scheduler. The static 8080 surface renders the same words server-side.

**Linking**

- **Publishes:** nothing; the cell never moves the primary location. Its batch words apply `f=outcome:…` to the host grid, which owns that filter (push, as a filter applied from a link).
- **Follows:** its row's bound target and the job records that name it; it changes only when a job transition arrives, unless its own region is frozen. Not holdable.
- **Targets rendered:** job id → the dock Jobs record, focused (the primary location does not move) · receipt id → its receipt card · compiler diagnostic → the SourceRepairDiff line · lock → the PipelineMap lock node; its owner → the owner's job record · batch words → the rows in that state (FilterChip). Link names read "Job a3f9, compile candidate, running, by you".
- **Peek source:** stored job records. Alt+↓ on a job id reads the record as a read-only ActivityRecord (three readouts, StageChip, the target named by the record, the submitter); Shift+K inside the Peek keeps it. On a receipt it reads the stored receipt header.
- **Absent copy:** no cell before any job named the row · no cell when the record names no target · "pending · job a3f9" · "in batch job 77c0 · per-row outcome not reported" · "Progress unknown · last event 13:52" · "no fact receipts written" · "Frozen at 14:02 · 2 events since".
- **Target-size exception:** inline: the job link (a four-character id at least 22px wide in a 24px row) and the receipt and diagnostic links inside the fact sentence rely on the WCAG 2.5.8 inline and spacing exceptions. Batch words and "Collect failed as worklist" are 24px; everything is 44px below 700px. With a coarse pointer the host row's one 44px row-menu button carries the job link's menu; there is no long-press.

**Keyboard**

- The cell's links are items of its grid cell (`tabindex="-1"`); the host grid reaches them with its cell navigation. The one link grammar applies: Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 opens the link menu, Ctrl/Cmd+Enter opens a browser tab.
- After Run or Cancel, focus returns to the invoking row (WCAG 2.4.3). j/k move to the next row; focus-scoped `.` rebinds the armed ActionStrip action to the focused row and focuses Run; it never posts (ActionStrip owns it).
- The batch summary words and Collect are ordinary links and a button in the host header's Tab order.

**Accessibility**

- The row references its cell with `aria-describedby`, so moving to a row reads "ResourceRef::Resolve … a3f9 running unit 3 of 6 by you". Glyphs are `aria-hidden` beside their words.
- Nothing is announced on pending. One polite message per job transition; a batch is coalesced when its last job ends ("Run on 4 rows ended: 3 finished, 1 failed."). Never per poll; unit progress in the cell is not live. A frozen region queues its messages and later reports "N events since frozen".
- Assertive only for "checking" when it blocks the action in hand.
- Text survives WCAG 1.4.12 spacing; the cell wraps, never truncates. Forced colors map state frames to `CanvasText`; the running frame keeps its 2px weight.

**Removes switching:** reading each row's outcome without opening the Jobs dock (J21 and J22, credited to U184; counts in the plan ledger). It also helps J12, J19 and J30, which the ledger credits to other units.
