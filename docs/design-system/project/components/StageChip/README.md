# StageChip

Where a job, receipt, problem or go-to row sits in the recovery pipeline, as one short link: the stage number and name, the lane when there is one, and the family in words, pointing at that node of the PipelineMap.

**Use it** on every ActivityRecord header, receipt card and ProvenanceStamp group, ProblemsList row and go-to job or receipt row, right after the verb or receipt it describes. It answers "which stage or lane produced this?" on the row itself, without opening the diagram.

**Consumer provides** the catalog verb of the job (for a receipt, the verb of the job that wrote it) and that verb's mapping from `catalog_verbs` in the served `pipeline-model.json`: zero or more stage node ids and zero or more lane node ids, each with its model title and family, plus the model revision the surface loaded ("model rev ‹8 hex›"). The chip renders only that mapping. It never infers a stage from timing, log text, the verb's spelling or the receipt kind. A receipt never stores a stage; the mapping is read at render time.

**What is mapped today.** `catalog_verbs` is filled only from the consolidated plan §2.1, which maps stages 1–7: stage 1 `corpus.extract-stabs` and `corpus.match-pair`; stage 2 `corpus.calibrate-global`; stage 3 `corpus.workspace`; stage 4 `corpus.ghidra-bulk`; stage 5 `corpus.cross-place`; stage 6 `corpus.genproject`; stage 7 `corpus.objdiff-check`. Stage 0, stage 8 and every lane have no mapped verb until a decision is recorded, so no chip names them.

- **Compact form** (rows, dock, problems): the stage number in mono `type-code-small` `ink-strong` and the stage's short model title in `type-ui` 12 ("5 Propagation", "4 C/C++ candidates"). A lane part would follow only when the verb also maps to a lane; none does today. One line; it never wraps inside a part.
- **Full form** (receipt cards, rail sections, peek headers): the full model title ("Propagation (cross-place)") and the family word under it in `type-kicker` `ink-muted` ("source recovery"), with "model rev ‹8 hex›" beside it.
- **Family color is decorative.** Each part carries a 3px inline-start rule in its family `-fill` through the shared `fam-*` classes (`lane-recovery-fill`, `lane-unify-fill`, and so on), exactly like PipelineBreadcrumb's top rule. The number, the title and the lane letter carry the meaning; family is also in every accessible name. The chip has no state glyph, count, pass/fail color or score: it says where, never how well.
- Frame: 1px `badge-frame`, `radius-chip`, parts at least 24px tall, transparent ground so it sits on `chassis`, `pane`, `raised` and `selection`; text `ink`, promoted to `ink-strong` inside a selected row. Parts are separated by the next part's rule plus a 1px `line`.
- **More than one node**: a verb mapped to two nodes would render two chips in pipeline order, never a range ("7–8") and never the nearest stage. No verb maps to two nodes today.
- **Unmapped**: "stage: unmapped" in italic `ink-muted` inside a solid `line-control` frame, with no lane guess. It is text, not a link, and its description names the verb and the model revision ("The verb of job 5e10 is not in catalog_verbs, model rev ‹8 hex›. No stage is guessed."). This is also what every verb missing from `catalog_verbs`, and every verb that a future `GET /api/v1/actions` comparison finds on only one side, renders.
- **Freshness is not the chip's job.** The ProvenanceStamp beside it keeps "reused", "historical" and "legacy". The mapping is versioned design data read from the served model; a change to `catalog_verbs` changes every chip at once, and the Peek names the revision.
- Inside a listbox option (go-to, palette) the chip renders as text with the same look (`.as-text`): an option is one target. The node is reached from the option's Reveal in menu.
- Both surfaces render the chip from the same model file; the static 8080 surface may drop the family rule, never the words.

**Linking**

- **Publishes:** nothing. A pipeline node does not move the primary location; Enter goes to the PipelineMap node (`node=` pushes one history stop) and focus lands on that map node.
- **Follows:** the row it sits in. Not holdable.
- **Targets rendered:** pipeline node → the PipelineMap node and its filtered live view (`?project=…&node=stage-5`). In the link menu, Reveal in lists Pipeline map only; Copy offers "Copy link" and "Copy node stage-5". Link names read "5 Propagation (cross-place), pipeline stage, source recovery".
- **Peek source:** Alt+↓ reads the served `pipeline-model.json`, headed "From the pipeline design · model rev ‹8 hex›" (title, Trying to, the gate text, the lanes beside it), and the node's cached counts (how many wait at the gate, the oldest age). Nothing is fetched. The Keep button, or Shift+K inside the Peek, keeps it (`keep=node:stage-5`).
- **Absent copy:** "stage: unmapped" (plain words, never a link to a guess).
- **Target-size exception:** none; each part is at least 24px tall and the whole part is the target; 44px below 700px and with a coarse pointer.

**Keyboard**

- Each part is a link in the Tab order of its host. Inside a grid cell the parts are the cell's items with `tabindex="-1"`; the grid's cell navigation reaches the cell, and →/← or Tab move between the parts the way the host grid moves between links in a cell.
- The one link grammar applies: Enter goes, Shift+Enter opens beside (a Held pane), Alt+↓ peeks, Shift+F10 opens the link menu, Ctrl/Cmd+Enter opens a browser tab. Focus alone never goes, filters or changes history.

**Accessibility**

- Each link's name starts with its visible text (WCAG 2.5.3) and adds the kind and family: "5 Propagation (cross-place), pipeline stage, source recovery". `aria-keyshortcuts="Alt+ArrowDown"` is set once on the host grid, not on every chip.
- Unmapped carries `aria-describedby` with the verb and the words "No stage is guessed."
- Never color alone: the family rule is decorative, and the number, title, lane letter and family words are all text.
- Targets: each part is at least 24px tall and the whole part is the target (WCAG 2.5.8); 44px below 700px and with a coarse pointer.
- Forced colors: frames and rules map to `CanvasText`.
- Node ids and verbs carry `translate="no"`; stage titles are ordinary words and may be translated.

**Removes switching:** J03, finding which stage produced a receipt or job, goes from 4 switches to 0 where §2.1 maps the verb; otherwise the row says "stage: unmapped". J02, fact → receipt → job, goes from 5 to 1: the Peek reads the receipt and its stage at 0, and the 1 is the dock-tab change to open the job (+1 below 700px). Both are credited to U180. From a row to the diagram node and its live view is one activation.
