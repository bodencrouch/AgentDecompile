# TaskLifecycle

A task's position in its lifecycle rail, with terminal and side states; its compact form is the **OutcomeCell** a row carries after its verb ran.

**Consumer provides** the current state, prior states and, for terminals and side states, the reason; for the compact form, the job id, the measured unit position and, once finished, the facts whose receipts that job wrote.

- Rail: proposed → waiting → ready → admitted → running → awaiting_acceptance → accepted, as an `<ol>` with `aria-current="step"`. Done steps on `pane`; the current step is a 2px `ink-strong` frame plus bold words, never the accent.
- Terminals: ✕ negative, ⊘ unsupported, ⊗ cancelled. Side states (dashed): ↻ retry_wait, ∅ budget_exhausted.
- **Crosswalk**: admitted, running and awaiting_acceptance link to the execution contract steps they instantiate (`exec-step-2` admit one eligible attempt, `exec-step-3` compute outside commit, `accept-4` independent acceptance), so Explain can render that step in place.
- **Compact form (OutcomeCell)** on EntityRow, MatchReview, token rows and checked sets: "a3f9 · running · unit 3 of 6", then the terminal word; under "finished" the facts whose receipts that job wrote, as words ("Compilation: passed, new receipt"). A 202 reads "pending · job c4e1" until the terminal result. If the job record names no bound target, the cell reads "outcome in dock · job a3f9". It shows only the latest job this viewer submitted for that exact target, or a job whose own record names it; never a timing guess, never optimistic.
- Resource occupancy is not a negative result. Terminal task counts never define objective completion. Lifecycle is never merged into the seven facts: a finished job is not a match.

**Linking**

- **Publishes:** nothing.
- **Follows:** its host row or record. The OutcomeCell updates only when its job's transition arrives; the dock's Freeze updates also freezes the cell. Not holdable.
- **Targets rendered:** the job id → the dock Jobs record, focused · a crosswalked state → its contract node (`?node=exec-step-2`, `exec-step-3`, `accept-4`) · a fact named under "finished" → its new receipt card. Link names read "Job a3f9, match siblings, running, unit 3 of 6".
- **Peek source:** Alt+↓ on the job id reads the stored job record (its three readouts); nothing is polled.
- **Absent copy:** "Progress unknown" in place of units · "pending · job c4e1" after a 202 · "outcome in dock · job a3f9" · no cell at all before a verb ran on the row.
- **Target-size exception:** spacing: the job id is the one link in the cell.

**Accessibility**

- The rail is an ordered list; state words are visible. The OutcomeCell is text ("Rename: running, job a3f9" → "Rename: accepted"), referenced from its row by `aria-describedby`; glyphs are `aria-hidden`. One polite message per job transition; a batch is coalesced when its last job ends ("Run on 4 rows: 3 finished, 1 failed"). In-cell progress is not live.

**Removes switching:** opening the Jobs dock after every run to learn whether it finished and what it wrote (J21, J22).
