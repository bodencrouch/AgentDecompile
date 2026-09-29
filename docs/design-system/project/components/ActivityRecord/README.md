# ActivityRecord

One job in the activity dock with its three separate readouts (liveness, execution progress and goal progress) and walkable provenance: its stage, what it was asked to act on, what its receipts recorded as changed, the receipts it produced, and log lines that link to what their record names.

**Consumer provides** job id and catalog action, owner (managed or external, with process identity as reported), submitter (you, an agent or external), the verb's mapping from `catalog_verbs` in the served `pipeline-model.json`, source and target builds, the job request's targets, measured units with the current one, accepted outcomes, blocking prerequisites, the recorded changed units (entity @ build), the receipts it produced, last event time, the Job outcome word, and the log tail with any structured fields the record carries (address, file:line, build).

- Liveness, execution progress and goal progress are three labelled readouts; never one bar. PID churn increments nothing. State words are the Job outcome words (State vocabularies): pending, admitted, waiting, running, checking, finished, failed, cancelled.
- Units are measured durable units: done `progress-unit-done`, the current one in a 2px `ink-strong` frame (never the accent). Uninstrumented work says "Progress unknown" and the last event.
- A live job is on `pane`; history on `chassis`. An external job stays visible and non-cancellable, and blocks duplicate admission.
- **StageChip** line, rendered only from the verb's `catalog_verbs` mapping: "5 Propagation" for `corpus.cross-place`, with a lane part only when the model maps one. A verb missing from `catalog_verbs` says "stage: unmapped", with no lane guess.
- **Targets and Changed are separate lines.**
  - **Targets** (from the job request): "Targets: 31 recipients on build-b". What the job was asked to act on, not what happened.
  - **Changed** (from the units its receipts recorded): "Changed: 3 (recorded units) · Show in Functions". Show in Functions applies the removable FilterChip "Changed by a3f9 ×" (`f=changed:a3f9`) to the Functions grid. A filter applied from a link is a Go and pushes one stop; removing the chip replaces.
  - A job that recorded no units says "Changed entities: not recorded", with no filter. Nothing is inferred from timing.
- Source and target builds are build links: they reveal that build's Navigator program row and never switch the inspected build. **Produced** lists the receipts the job wrote.
- **Log lines** link only what the record names:
  - structured fields the job record carries (address, file:line, build) are links stamped with the run (`job=`), so they resolve against that run's basis;
  - a free-text address links only when the job names exactly one target build. It is labelled "from log text", opens at that build, and shows "◷ basis changed since this run" when the basis has moved;
  - anything else stays plain text with a Copy button.
- Derive/backfill rows show row → derived column → receipt. Finished copy: "Finished. Recipient verification: not run." A finished job is not a match.
- **Selection only** (one dock toggle for Jobs, Problems and Logs, `aria-pressed`) shows the FilterChip "Selection only: ResourceRef::Resolve · build-b ×" (`f=scope:selection`). Logs are filtered by job records that name the target, never by searching log text.
- **Freeze updates** freezes this region only: the records say "Frozen at 14:02 · 7 events since" and queue events without dropping them. It never freezes OutcomeCells or any other region.

**Linking**

- **Publishes:** `dock=jobs` (replaceState) and `job` for the focused record: moving focus in the feed replaces; a job link activated elsewhere pushes. Show in Functions applies `f=changed:a3f9` to the Functions grid, which owns that filter (push).
- **Follows:** the dock tab and, with **Selection only** pressed, the primary `entity` and `build` (records that name them), after the settle. It updates from the existing job stream unless frozen. Not holdable; a record can be kept from its Peek as a card (`keep=job:a3f9@build-b`, the build its record targets).
- **Targets rendered:** job id → this record, focused · StageChip → the PipelineMap node · source and target builds → the Navigator program row for that build (the primary location does not move) · Show in Functions → the Functions grid filtered to the rows the job's receipts recorded as changed · produced receipt → its receipt card · structured log address → the Code Browser at that build and address · structured file:line or diagnostic → the SourceRepairDiff line · a free-text address in a single-build job → that build and address, "from log text" · blocking prerequisite → its job record or lock node. Link names read "Job a3f9, corpus.cross-place, running"; "Address 0041b2c0, build-b, from log text".
- **Peek source:** the stored job record, its units and its receipts' headers; nothing is polled beyond the dock's stream.
- **Absent copy:** "Changed entities: not recorded" · "stage: unmapped" · "Progress unknown" · "process identity: not reported" · "Finished. Recipient verification: not run." · "◷ basis changed since this run" · "Frozen at 14:02 · 7 events since".
- **Target-size exception:** inline: links inside a log tail line and inside the Targets and Changed sentences use the WCAG 2.5.8 inline exception; chips, FilterChips, Copy and the toggles are 24px, 44px below 700px. With a coarse pointer each record carries one 44px row-menu button with the same link menu; there is no long-press.

**Keyboard**

- The job list is an APG Feed: PageDown/PageUp move between records; Tab moves through a record's links. Links follow the linked-views grammar.
- Ctrl/Cmd+J toggles the dock. Freeze updates and Selection only are toggle buttons (`aria-pressed`) with stable names.

**Accessibility**

- `role="feed"` with `aria-busy` while loading; each record is an `article` named by its title and described by its three readouts in a `<dl>`.
- The log tail is `role="log"` with `aria-live="off"`; a per-job "Announce new lines" toggle is off by default. A link made from log text keeps "from log text" in its name. Job transitions are announced once, politely; polls and log lines never are.
- The FilterChip and StageChip are words plus a number, never color alone.

**Removes switching:** opening the Functions list, the receipt list and the logs to learn which entities and builds a job changed and what it produced (J03, J19, J30 and J38; J22 is credited to U184; counts in the plan ledger).
