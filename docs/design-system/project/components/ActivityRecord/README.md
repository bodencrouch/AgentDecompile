# ActivityRecord

One job in the activity dock with its three separate readouts (liveness, execution progress and goal progress) and walkable provenance: its stage, the builds and entities it changed, the receipts it produced, and log lines that link to what they name.

**Consumer provides** job id and catalog action, owner (managed or external, with process identity as reported), the stage and lane of its catalog verb, source and target builds, measured units with the current one, accepted outcomes, blocking prerequisites, the recorded changed units (entity @ build), the receipts it produced, last event time and the log tail.

- Liveness, execution progress and goal progress are three labelled readouts; never one bar. PID churn increments nothing.
- Units are measured durable units: done `progress-unit-done`, current outlined `progress-unit-now`. Uninstrumented work says "Progress unknown" and the last event.
- A live job is on `pane`; history on `chassis`. An external job stays visible and non-cancellable, and blocks duplicate admission.
- **StageChip** line: "5 Propagation · lane A", from the catalog verb's stage mapping; an unmapped verb says "stage: unmapped".
- **Changed** line, built only from recorded units: "3 recipients on build-b: ResourceRef::Resolve, Actor::LoadFromTemplate, +1 more". Activating it applies a removable FilterChip "Changed by a3f9 ×" to the Functions grid (a button named "Remove filter: changed by a3f9"). A job that did not record its units says "Changed entities: not recorded"; nothing is inferred from timing.
- Source and target builds are links. **Produced** lists the receipts the job wrote.
- Log tails show the latest lines. Addresses, source locations and compiler diagnostics in a line are links stamped with the run (`job=`), so they resolve against that run's basis.
- Derive/backfill rows show row → derived column → receipt. Finished copy: "Finished. Recipient verification: not run." A finished job is not a match.

**Linking**

- **Publishes:** `dock=jobs` and `job` for the focused record (replaceState). The Changed line applies `f=changed:a3f9` to the Functions grid, which owns that filter.
- **Follows:** the dock tab and, with **Selection only** pressed, the primary `entity` and `build` (records that name them). It updates from the existing job stream; **Freeze updates** stops re-rendering and announcements. Not holdable.
- **Targets rendered:** job id → this record, focused · StageChip → the PipelineMap node · source and target builds → the Code Browser for that build (same entity when the record names one) · Changed → the Functions grid filtered to the rows the job changed · produced receipt → its receipt card · log address → the Code Browser at that build and address · log source location or diagnostic → the SourceRepairDiff line · blocking prerequisite → its job record or lock node. Link names read "Job a3f9, corpus.cross-place, running".
- **Peek source:** the stored job record, its units and its receipts' headers; nothing is polled beyond the dock's stream.
- **Absent copy:** "Changed entities: not recorded" · "stage: unmapped" · "Progress unknown" · "process identity: not reported" · "Finished. Recipient verification: not run."
- **Target-size exception:** spacing: links inside the log tail line and the Changed sentence; chips and the FilterChip are 24px.

**Keyboard**

- The job list is an APG Feed: PageDown/PageUp move between records; Tab moves through a record's links. Links follow the linked-views grammar.
- Ctrl/Cmd+J toggles the dock. Freeze updates and Selection only are toggle buttons (`aria-pressed`).

**Accessibility**

- `role="feed"` with `aria-busy` while loading; each record is an `article` named by its title and described by its three readouts in a `<dl>`.
- The log tail is `role="log"` with `aria-live="off"`; a per-job "Announce new lines" toggle is off by default. Job transitions are announced once, politely; polls and log lines never are.
- The FilterChip and StageChip are words plus a number, never color alone.

**Removes switching:** opening the Functions list, the receipt list and the logs to learn which entities and builds a job changed and what it produced (J03, J19, J22, J30, J38).
