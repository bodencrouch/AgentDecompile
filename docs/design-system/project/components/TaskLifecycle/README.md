# TaskLifecycle

A task's position in its lifecycle rail, with terminal and side states. Its compact variant is the **OutcomeCell** a row carries after a verb ran on it.

**Consumer provides** the current backend state, the prior states and, for terminals and side states, the reason; for the Explain disclosure, the served `pipeline-model.json` revision and its `crosswalks` entry for the current state, if any; for the compact variant, what OutcomeCell lists (job id, Job outcome word, measured units, submitter, and the facts whose receipts that job wrote).

- **Rail: backend states only.** proposed → waiting → ready → admitted → running → awaiting_acceptance → accepted, as an `<ol>` with `aria-current="step"`. Done steps on `pane`. The current step is the 2px `ink-strong` now-frame plus bold words, never the accent (90: the accent is not a status). Rail steps are words, not links.
- Terminals: ✕ negative, ⊘ unsupported, ⊗ cancelled. Side states (drawn off the main path, with their words): ↻ retry_wait, ∅ budget_exhausted.
- **Explain (design text, not evidence).** An APG disclosure beside the rail. It reads the crosswalked node from the backend-served `pipeline-model.json`, never the outline markdown. It is headed "From the pipeline design · model rev ‹8 hex›" with the sentence "Design description ≠ this item's evidence", in the context-hint claim tier (dotted frame, ClaimTier). Its crosswalk line ends "(interpretation)", for example "running → exec-step-3 Compute outside commit (interpretation)". The model's crosswalks are interpretations, never recorded facts:
  - ready and admitted → `exec-step-2` Admit one eligible attempt;
  - running → `exec-step-3` Compute outside commit;
  - awaiting_acceptance and accepted → `accept-4` Independent acceptance, short commit;
  - proposed, waiting, negative, unsupported, cancelled, retry_wait and budget_exhausted are unmapped. Explain says "No crosswalk for this state" and links nothing.
- **Compact variant (OutcomeCell)** on EntityRow, MatchReview, token rows and checked sets: "a3f9 · running · unit 3 of 6 · by you", then a terminal word. It uses the Job outcome words (State vocabularies): pending, admitted, waiting, running, checking, then finished, failed or cancelled. It binds only a job whose own record names the row's target; never client memory, never a timing guess, never optimistic. OutcomeCell owns the details.
- Resource occupancy is not a negative result. Terminal task counts never define objective completion. Lifecycle is never merged into the seven facts: a finished job is not a match.

**Linking**

- **Publishes:** nothing.
- **Follows:** its host row or record; it changes only when a transition arrives, unless its own region is frozen. Not holdable.
- **Targets rendered:** the job id → the dock Jobs record, focused · inside Explain only, the crosswalked node → the PipelineMap node (`?node=exec-step-2`, `exec-step-3` or `accept-4`), labelled "(interpretation)". Rail steps are not links. Link names read "Job a3f9, match siblings, running, unit 3 of 6"; "exec-step-3 Compute outside commit, interpretation".
- **Peek source:** Alt+↓ on the job id reads the stored job record (its three readouts); Explain reads the served `pipeline-model.json` at the stated revision. Nothing is polled.
- **Absent copy:** "Progress unknown · last event 13:52" in place of units · "No crosswalk for this state" · "Model not loaded. Explain needs pipeline-model.json from the backend."
- **Target-size exception:** none; the Explain button is 24px. The compact variant's inline job link is OutcomeCell's exception.

**Accessibility**

- The rail is an ordered list; state words are visible; the now-frame is a second cue. Explain is an APG disclosure that never moves focus (WCAG 3.2.1); its tier is a word ("context hint"), not only the dotted frame.
- The compact variant is text ("Rename: running, job a3f9" → "Rename: finished"), referenced from its row by `aria-describedby`; glyphs are `aria-hidden`. Nothing is announced on pending; one polite message per job transition; a batch is coalesced when its last job ends ("Run on 4 rows ended: 3 finished, 1 failed."). In-cell progress is not live.

**Removes switching:** opening the Jobs dock after every run to learn whether it finished and what it wrote (J21, J22; counts in the plan ledger).

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- Key (moved text): "Rail: backend states only; the now-frame is in ink-strong."
- 202 ∅: "after HTTP 202 · nothing announced" (nothing is announced on pending).
