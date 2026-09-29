# StageCard

A pipeline stage card from the recovery overview: header band in the family fill, then Trying to · How · In → out · Gate.

**Consumer provides** the stage number and title, the family (`identity`, `recovery`, `unify`, `runtime`, `verify`, `intake`), try lines, how bullets, in and out lines, the gate text and an optional tag, all from `pipeline-model.json`. The live variant also takes the served model's revision, the stage's counts per fact axis, the oldest waiting item with its age, the running jobs (each with its verb's `catalog_verbs` mapping), and the read time.

- `pane` body, `node-stroke` at `stroke-card`, `radius-card`; 30px `dia-band-h` header with `ink-strong` title; section labels in the family ink (`.fi`).
- Every card answers what it is trying to do, how, what goes in and out, and what gates it. The gate line is `gate` amber.
- Card copy follows STRATEGY's stage names; there is no ninth stage.
- **Static variant** (diagram-only): the fixed-size print canvas and the docs. It reproduces the generator exactly with `dia-*` sizes and carries no live data.
- **Live variant** (in the app: PipelineMap peek, go-to `~stage-5` rows, evidence rail): the app type scale (≥11px labels, ≥12px body), never `dia-*` sizes. It shows the family as a word, counts per fact axis as separate filter links (never summed into one number), the gate wait as ◇ plus "Waiting at gate:" with its oldest age linked to that row or job, running jobs as job links, a read-time stamp, and an **Explain** disclosure. Nodes are links, never Run buttons.
- **Explain is design text, not evidence.** It renders the node's Trying to / How / In → out / Gate from the backend-served `pipeline-model.json`, never the outline markdown, so both surfaces show the same text at the same revision. It is headed "From the pipeline design · model rev ‹8 hex›" with "Design description ≠ this item's evidence", in the context-hint claim tier (dotted frame, ClaimTier). Any crosswalk line ends "(interpretation)". The live counts above it are the evidence.
- **Verbs and stages.** A running job's StageChip, and whether a job counts under this card at all, come only from `catalog_verbs`: stage 1 `corpus.extract-stabs` and `corpus.match-pair`, stage 2 `corpus.calibrate-global`, stage 3 `corpus.workspace`, stage 4 `corpus.ghidra-bulk`, stage 5 `corpus.cross-place`, stage 6 `corpus.genproject`, stage 7 `corpus.objdiff-check`; the proposed corpus jobs add `corpus.detect-transformations`, `corpus.extract-toolchain-facts` and `corpus.classify-variance` to stage 2, `corpus.propose-field-propagation` to stage 5 and `corpus.explain-match` to stage 7 (plan §2.1, "Verbs outside stages 1–7"). Stage 0 is open, add and resume, not a verb; stage 8 has no verb; no verb maps to a lane by name. Those cards list no jobs by verb, and a job with an unmapped verb says "stage: unmapped", with no lane guess.

**Linking**

- **Publishes:** nothing. A stage card never changes the selection, the inspected build or admission.
- **Follows:** static variant: nothing. Live variant: `project` and `f`, re-read from the stored projection after the settle; not holdable (a Peek of it can be kept as a card, `keep=node:stage-5`).
- **Targets rendered:** live variant only: title → its pipeline node (`?node=stage-5`, the PipelineMap node and its filtered live view) · gate line → `?node=gate-5` · each count → the Functions grid filtered by that axis (`f=`) · the oldest wait → that entity @ build (Code Browser) or job (dock Jobs record) · running jobs → their dock records. The static variant is print only; its node id is the docs outline anchor (`agentdecompile-recovery-pipeline.outline.md#stage-5`). Link names read "Pipeline node stage-5, Propagation (cross-place)"; "Job a3f9, corpus.cross-place, running".
- **Peek source:** Alt+↓ on the title reads the PipelineMap's cached counts, oldest waiting age and lock owner; Explain reads the served `pipeline-model.json` at its revision. Nothing is polled or started.
- **Absent copy:** "No work at this stage in corpus-alpha." · "Counts not loaded. Open the pipeline map to read them." · an axis with no receipts says "not run", never 0 · an unmapped catalog verb reads "stage: unmapped" · "Model not loaded. Explain needs pipeline-model.json from the backend."
- **Target-size exception:** inline: links inside the count and wait sentences use the WCAG 2.5.8 inline exception; Explain and the title link are 24px.

**Keyboard**

- Links follow the linked-views grammar: Enter goes, Shift+Enter opens beside, Alt+↓ peeks (counts, oldest wait and lock owner), Shift+F10 opens the one link menu.
- Explain is an APG disclosure button: Enter or Space toggles it; focus stays on the button.

**Accessibility**

- Static: in the SVG each card is a `<g id="stage-5">` in reading order under the diagram's `role="img"`; the generated text outline is the primary accessible form. The family is written as a word, never only a fill.
- Live: a `section` named by its title; the family word, the ◇ glyph (`aria-hidden`) beside "Waiting at gate:", and counts that are never live regions. Explain never moves focus (WCAG 3.2.1); its tier is the word "context hint", not only the dotted frame.

**Removes switching:** opening the diagram, the outline and then the Jobs dock to learn what a stage does and what is waiting at it now (helps J05, which the plan ledger credits to UX-08).
