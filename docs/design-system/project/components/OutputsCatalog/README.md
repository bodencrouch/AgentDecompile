# OutputsCatalog

Every export, output and result the project can produce, in one grid keyed by artifact with one cell per build: what each artifact is for, what produced it, its status on each build, its basis, and its claim tier with the sentence that says what it is not.

**Use it** as the corpus view `ws=evidence&panel=outputs` (a proposed `panel` value), reached from go to, from "Show all" on any rail section that names an output, and from the PipelineMap export band. It answers "what does this project produce, for which builds, and how much of it is real today?" It is a catalog, never a launcher: nothing runs from here.

**Consumer provides** the served outputs inventory (artifact id, group, name, one plain-words purpose line, format or schema, producing verb and pipeline node, claim tier and its "is not" sentence, corpus or per-build scope); for each artifact × build, the status from the stored receipts, with the receipt id, the producing job when recorded, the basis digest and its age; whether a stored file exists (path, size, hash, download route); the 8080 observation record (none today); and `catalog_verbs` from the served `pipeline-model.json` for the StageChip.

- **Groups.** The inventory's eight groups are the grid's row groups, in inventory order: A Export bundle · B Parity, contribution and whole-image results · C Corpus store tables and match objects · D Jobs, receipts, determinism and attestation · E Ghidra-side, analysis and agent outputs · F Runtime reuse outputs · G Distributed compute · H Reports and context packs. Each group header is a disclosure button with the group's count by status ("10 · 1 delivered · 3 partial · 6 future"). Expanded state lives in durable workspace state.
- **Header.** The title; one summary line with totals by status, ending "observed on 8080: 0"; the **not-observed notice** (StateNotice, `unknown`, ⊡), which stays until an artifact is actually observed through 8080: "Nothing here is observed on 8080. … Delivered means a receipt records bounded evidence for that scope; it does not mean the artifact is live, current or accepted." Then the filter toolbar and FilterChips.
- **Columns**, in order:
  1. **Artifact · what it is for**: the name as a typed link (Open), the format id in mono, one plain sentence of purpose, then the row actions.
  2. **Produced by**: the producing verb as the record names it (mono, never a hardcoded action id), then a StageChip rendered only from `catalog_verbs` (export verbs are unmapped today and read "stage: unmapped"), then the pipeline node as a link where the inventory names one.
  3. **One cell per build** (build-a … build-d): the artifact-status glyph, with the word in the cell's accessible name and in the legend (ReadinessMatrix rule). A corpus-scoped artifact (the bundle, pack v2) gets one cell spanning every build, with the words: "corpus scope · future · one bundle for every build".
  4. **Claim · what it is not**: the ClaimTier chip, then the ≠ sentence in `ink` ("An exported pack ≠ proof of a safe call or recovered source", "Compiling C ≠ verified recovery", "Local zero ≠ full-image or behavior proof"). An artifact that has never been produced shows "tier when produced: advisory" as plain muted text, never a tier chip, so no frame implies a claim that does not exist.
  5. **Basis · 8080**: the ProvenanceStamp (reused, fresh, historical, synthetic) with its receipt and basis age, or "no receipt"; then the 8080 line ("⊡ not observed"). A run whose provider differed from the requested one says so here ("⇄ build-c: provider differed").
- **Artifact status**: one closed set, each a glyph and a word, never a score:

  | Status | Glyph | Token | Meaning |
  |---|---|---|---|
  | delivered | ▣ | `ink-strong` | A receipt records bounded source/installed evidence, or a historical observed run, for this scope. Not live, not accepted. |
  | partial | ◐ | `fact-stale` | Some source or synthetic evidence exists; the ledger names what is missing. |
  | stale | ◷ | `fact-stale` | Delivered, but its basis changed since the receipt. |
  | future | ▷ | `fact-unknown` | Design, plan or contract only; no producer yet. |
  | never run | ○ | `fact-unknown` | A producer exists; nothing has run for this build. |
  | no report | ∅ | `fact-unknown` | A run is recorded, but its report is missing. Said plainly, never "no changes". |
  | reference | □ | `fact-unknown` | An implementation-CLI artifact; not an operating instruction. |

  The **8080 observation** is a separate axis: ⊡ "not observed on 8080" (today, every artifact) or "observed ‹time›" with its stamp. It never changes the status, and the status never implies it.
- **Separate claims stay separate.** Whole-image acceptance shows three claims per build, byte exact · behaviour · toolchain origin, each a FactBadge word. An accuracy or parity report (objdiff, reccmp) is a different row, and its numbers never appear as acceptance: "Accuracy ≠ acceptance."
- **Across builds**, a report whose numbers differ by build shows "◐ varies across builds · not averaged". The catalog never averages builds, and never merges reports from different source revisions.
- **Row actions** (nothing runs from here):
  - **Open** is the name link, going to the ArtifactCard.
  - **Peek** (Alt+↓, or the Peek button) shows the card's header and first two sections.
  - **Copy path** copies the stored path and announces it ("Copied path out/hookpack-v1.json"). With no stored file it stays `aria-disabled` and gives the reason ("No stored path: the bundle has never been produced").
  - **Download** appears only when the record names a stored file with its hash. It is a native link (never intercepted). Its accessible name gives the file name, size and "not observed on 8080". The preview's route is a placeholder for the one the record names.

  A historical-only archive offers no Download, only the reason.
- **Filters use FilterChip**: an **Add filter** menu button offers status, build, group, tier, has a stored file, and observed on 8080. Each filter applied becomes one chip and one `f=` entry. Links apply chips too ("Show outputs at this tier" on a ClaimTier legend; "Outputs for build-c" from a build header). Proposed axes: `artifact.status`, `artifact.group`, `artifact.build`, `tier`, `artifact.file`, `observed`.
- **Relationships strip**, under the grid, for the selected row: **bundle → members** (each member with its status glyph and link; the optional source-projects member dotted, "when absent, a not_in_scope receipt"), and **receipt → job → stage** as an ordered chain drawn only from what the records name ("receipt 5c1e → job not recorded → stage: unmapped"). Nothing is correlated by timing.
- **Narrow form.** Below a 480px container, one list item per artifact: name, purpose, each build in words, tier and ≠ sentence, and the 8080 word. Otherwise the grid is a labelled horizontal scroll region.
- Read-only by construction: it reads the served inventory, receipts, job records and file metadata. It never exports, verifies, rebuilds or opens a program.

**Linking**

- **Publishes:** `f` for its chips (pushState when a link applied one, replaceState when typed or removed). Expanded groups go to durable workspace state, never the URL. Open is a Go to the ArtifactCard (`artifact=` plus `ws=evidence&panel=outputs`; `artifact` is a proposed parameter).
- **Follows:** `project` and `f`; commit-on-Enter (an expensive corpus view). Not holdable; a single artifact is kept as an ArtifactCard (`keep=artifact:‹id›`, a proposed kind).
- **Targets rendered:** artifact name → the ArtifactCard · build header → the Navigator program row · build cell with a receipt → that receipt card · receipt id → receipt card · job id → the dock Jobs record · StageChip → PipelineMap node · pipeline node id → PipelineMap node · member → its ArtifactCard. Link names read "Open artifact Portable pack v1, delivered bounded" and "Receipt 5c1e, export-hookpack, reused".
- **Peek source:** the stored inventory row, the receipt header and the file metadata. Nothing is fetched and no file is read.
- **Absent copy:** "no receipt" · "job not recorded" · "stage: unmapped" · "no report" · "never run" · "corpus scope" · "No stored path: ‹reason›" · "not observed on 8080". A future artifact never shows a tier chip.
- **Target-size exception:** none. Name links, the Peek, Copy path and Download controls, and the group buttons are all at least 24px, and 44px below 700px or with a coarse pointer. Build cells are 24px glyph targets inside rows at least 28px tall.

**Keyboard**

- A row-focus APG Grid with one tab stop. ↑/↓ move between rows (group headers included); ←/→ move across cells and their links. Home/End and Ctrl+Home/End work as in the Semantics table (90).
- On a group header, Enter or Space toggles the group. On a row, Enter opens the artifact, and Shift+Enter opens it beside as a Held pane (a new window on 8080).
- Alt+↓ peeks the row or the focused build cell. Shift+F10 opens the link menu: Open · Open beside · Peek · Keep, Reveal in Evidence and Pipeline map, then Copy link · Copy path.
- `c` copies the focused row's path, and `w` collects the filtered rows as a worklist. Both are focus-scoped and remappable in `keymap.json`, and typeahead starts with `/`.
- Chips form the FilterChip toolbar before the grid in Tab order.

**Accessibility**

- `role="grid"` named "Outputs of corpus-alpha by artifact and build", with `aria-rowcount` and `aria-describedby` pointing to the legend. Each group header is a `th scope="rowgroup"` holding a disclosure button with `aria-expanded`. Artifact names are row headers.
- A build cell's accessible name carries the status word and the 8080 word ("build-a: delivered, bounded, receipt 5c1e; not observed on 8080"). The glyphs are `aria-hidden`.
- The not-observed notice is a `role="note"`, not a live region. A filter result is announced once, debounced (FilterChip).
- Never color alone: every status is a glyph and a word, the tier is a word inside its frame, and the ≠ sentence is text.
- Forced colors: chip and member frames map to `CanvasText`. The dotted optional member keeps its dots and the word "optional".

**Removes switching:** from "is this output real?" to the receipt, the job and the stage in one grid. There is no separate trip to the dock, the diagram and the docs to find out which outputs exist and which are only designed.
