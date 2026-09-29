# StageChip

Where a job, receipt, problem or go-to row sits in the recovery pipeline, as one short link: the stage number and name, the lane when there is one, and the family in words, pointing at that node of the PipelineMap.

**Use it** on every ActivityRecord header, receipt card and ProvenanceStamp group, ProblemsList row and go-to job or receipt row, right after the verb or receipt it describes. It answers "which stage or lane produced this?" on the row itself, without opening the diagram.

**Consumer provides** the catalog verb of the job (for a receipt, the verb of the job that wrote it) and that verb's mapping from `catalog_verbs` in `pipeline-model.json`: zero or more stage node ids and zero or more lane node ids, each with its model title and family, plus the model version the surface loaded. The chip renders only that mapping. It never infers a stage from timing, log text, the verb's spelling or the receipt kind.

- **Compact form** (rows, dock, problems): the stage number in mono `type-code-small` `ink-strong`, the stage's short model title in `type-ui` 12 ("Propagation", "C/C++ candidates", "Open · add · resume"), then a second part "lane A" when the verb also maps to a lane. One line; it never wraps inside a part.
- **Full form** (receipt cards, rail sections, peek headers): the full model title ("Propagation (cross-place)", "lane A Knowledge fusion") and the family word under each part in `type-kicker` `ink-muted` ("source recovery", "unification & export").
- **Family color is decorative.** Each part carries a 3px inline-start rule in its family `-fill` through the shared `fam-*` classes (`lane-recovery-fill`, `lane-unify-fill`, and so on), exactly like PipelineBreadcrumb's top rule. The number, the title and the lane letter carry the meaning; family is also in every accessible name. The chip has no state glyph, count, pass/fail color or score: it says where, never how well.
- Frame: 1px `badge-frame`, `radius-chip`, parts at least 24px tall, transparent ground so it sits on `chassis`, `pane`, `raised` and `selection`; text `ink`, promoted to `ink-strong` inside a selected row. Parts are separated by the next part's rule plus a 1px `line`.
- **More than one node**: a verb mapped to two stages (for example stages 7 and 8) renders two chips in pipeline order. Never a range ("7–8") and never the nearest stage.
- **Lane-only verbs** (runtime reuse, distributed compute) render one part, "lane C Runtime reuse", with "separately owned" in `ink-muted` when the model says so. Stage 0 renders "0 Open · add · resume": it gates writes only.
- **Unmapped**: "stage: unmapped" in italic `ink-muted` inside a dashed `line-control` frame. It is text, not a link, and its description names the verb ("corpus.relabel-notes has no stage or lane in pipeline-model.json"). It never falls back to a guess.
- **Freshness is not the chip's job.** The ProvenanceStamp beside it keeps "reused", "historical" and "legacy". The mapping is static, versioned design data; a change to `catalog_verbs` changes every chip at once.
- Inside a listbox option (go-to, palette) the chip renders as text with the same look (`.as-text`): an option is one target. The node is reached from the option's Reveal in menu.
- Both surfaces render the chip from the same model file; the static 8080 surface may drop the family rule, never the words.

**Linking**

- **Publishes:** nothing. A pipeline node does not move the primary location; Enter goes to the PipelineMap node (`node=` pushes one history stop) and focus lands on that map node.
- **Follows:** the row it sits in. Not holdable.
- **Targets rendered:** pipeline node → the PipelineMap node and its filtered live view (`?project=…&node=stage-5`, `?project=…&node=lane-A`). In the link menu, Reveal in lists Pipeline map only; Copy offers "Copy link" and "Copy node stage-5". Link names read "5 Propagation (cross-place), pipeline stage, source recovery".
- **Peek source:** Alt+↓ reads `pipeline-model.json` (title, Trying to, the gate text, the lanes beside it) and the node's cached counts (how many wait at the gate, the oldest age). Nothing is fetched. Shift+K inside the Peek keeps it (`keep=`).
- **Absent copy:** "stage: unmapped" (plain words, never a link to a guess).
- **Target-size exception:** none; each part is at least 24px tall and the whole part is the target; 44px below 700px.

**Keyboard**

- Each part is a link in the Tab order of its host. Inside a grid cell the parts are the cell's items with `tabindex="-1"`; the grid's cell navigation reaches the cell, and →/← or Tab move between the parts the way the host grid moves between links in a cell.
- The one link grammar applies: Enter goes, Shift+Enter opens beside (a Held pane), Alt+↓ peeks, Shift+F10 opens the link menu, Ctrl/Cmd+Enter opens a browser tab. Focus alone never goes, filters or changes history.

**Accessibility**

- Each link's name starts with its visible text (WCAG 2.5.3) and adds the kind and family: "5 Propagation (cross-place), pipeline stage, source recovery"; "lane A, Knowledge fusion, unification & export". Links expose `aria-keyshortcuts="Alt+ArrowDown"`.
- Unmapped carries `aria-describedby` with the verb and the words "No stage is guessed."
- Never color alone: the family rule is decorative, and the number, title, lane letter and family words are all text.
- Targets: each part is at least 24px tall and the whole part is the target (WCAG 2.5.8); 44px below 700px.
- Forced colors: frames and rules map to `CanvasText`.
- Node ids and verbs carry `translate="no"`; stage titles are ordinary words and may be translated.

**Removes switching:** J03, finding which stage or lane produced a receipt or job, goes from 4 switches (dock, plan table, diagram, back) to 0: the stage is on the row. J02, fact → receipt → job, drops from 5 to 0 with Peek because the receipt card names its stage. J05 in reverse, row to the diagram node and its live view, is 1 activation instead of opening the overview image and filtering the dock by hand.
