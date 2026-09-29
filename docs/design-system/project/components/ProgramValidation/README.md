# ProgramValidation

Ghidra's post-analysis validators for every build in one panel: which validators ran on which build, their result per build, and every finding as a row linked to its address on that build. It is read-only. Running the validators is an admitted, non-mutating job per build, and findings can be collected into a worklist.

**Use it** from the Analysis menu ("Validate program…"), the palette ("Validate program", "Validators") and a build's row menu in the navigator, and from AnalyzerPanel's analysis-state card ("Validate ‹build›…"). It replaces Ghidra's Validate Program dialog. Opening it reads stored findings only. It never runs a validator, analyzes or decompiles, and an empty panel is not permission to analyze again.

**Consumer provides:**

- The project and its builds.
- Per build:
  - its analysis state and receipt, since validators are post-analysis;
  - the writer lock as reported (owner kind, job, PID and start time);
  - the last validation job: id, time, the basis it read, provenance (fresh, reused, historical);
  - the transactions committed since that basis, so staleness can be stated.
- Per validator: name and description as the server lists them, whether it applies to that build's language, and its result per build (no findings, warnings, errors, not run).
- Per finding:
  - build, validator and result;
  - the address or range on that build, or "program-wide";
  - the message as the validator wrote it, and the evidence it cites (a bookmark, a reference or a measured count).
- The locator of each finding's address to a logical entity, when one is recorded.
- The catalog action that runs validators, read from `GET /api/v1/actions`. No action id is named here.

**Anatomy**

1. **Header.**
   - "Validate program · ‹project› · N builds" and a Scope segment: the inspected build, or All builds.
   - A standing note (`role="note"`): "Validators read the program and change nothing. Running them is one admitted job per build. No findings is not proof the analysis is right."
2. **Run state per build.** One card per build, glyph plus word:
   - "✓ validated 13:40 · job ‹id› · current basis", with the ProvenanceStamp (fresh or reused).
   - "◷ stale · validated 11:02 · 3 transactions since", which leaves the old findings on screen, labelled stale.
   - "● writer owned · validation waits", with the owner exactly as reported.
   - "○ not run · no analysis receipt". Validation is post-analysis, so an unanalyzed build is not offered it. The card links AnalyzerPanel; it never offers to analyze from here.
   - The inspected build's card has the `ink-strong` frame.
3. **Results grid.**
   - Rows are validators and columns are builds.
   - Each cell holds one result word: "✓ no findings", "△ 1 warning", "✕ 2 errors", "○ not run", "◷ stale" (the counts from the stale run follow) or "⊘ not applicable" with its reason.
   - Enter on a cell filters the Findings table to that validator and build.
   - There is no Across builds column. Validator results are program-level facts of each build, so they are compared side by side and never merged or summed into a score.
4. **Findings table** (the ResultsTable pattern):
   - Columns: Build, Validator, Result, Location, Entity and Message.
   - **Location** is a typed address link on that build. A program-wide finding says "program-wide · no address".
   - **Entity** names the logical entity whose body holds the address, when a locator is recorded ("ResourceRef::Resolve · 88"). Otherwise it reads "no entity at this address". A finding on one build is never inferred for another build.
   - A **Same entity on other builds** disclosure lists what the other builds' own findings say for that entity ("none on build-b · build-c stale · build-d unresolved"). It is a comparison, never a copy.
   - Row actions:
     - **Collect into worklist…** (`w`), which hands the checked or filtered rows, in order, to the MarksList dialog;
     - **Step findings**, which makes the snapshot the active worklist so F8 steps it.
5. **Run.**
   - **Validate ‹build› (catalog)…** opens a ConfirmDialog. It is a ConfirmDialog, not in place, because it can queue behind a writer and replaces the build's current findings.
   - The dialog lists the validators, all checked by default as in Ghidra, and each can be unchecked.
   - Its consequence sentence reads: "One read-only job on build-c. It changes nothing in the program. Its findings replace the stale findings of job ‹id›, which stay in the job history."
   - A per-build preview gives the writer state and the analysis receipt read.
   - **Validate other builds…** chooses builds explicitly. There is no all-builds default, and each build is its own job with its own outcome.
6. **Relation to ProblemsList.**
   - Findings are advisory. They are not unmet predicates and do not block an objective by themselves.
   - They reach the dock's Problems tab only if an objective names "validation errors on ‹build›" as a predicate. None does today; that is a proposal for the objective model.
   - To work through findings, collect them into a worklist. The footer says this in one sentence and links `dock=problems`.

**States**

- **Not run:** "No validation recorded for build-a. Opening this panel did not run it." **Validate build-a (catalog)…** is armed, not run.
- **No analysis:** on a build with no analysis receipt the Validate button is `aria-disabled`, with "Validators check analysis results; build-d has no analysis receipt." It links AnalyzerPanel.
- **Stale:** the findings stay, labelled "stale · 3 transactions since job ‹id›". Nothing re-runs by itself.
- **Writer owned:** the run waits in admission with the owner as reported. Nothing is killed or restarted, and an external owner is never offered either.
- **Running, checking, finished, failed, cancelled:** the Job outcome words appear on the build's card and in the dock. A running validator shows measured units, or "Progress unknown · last event ‹time›". A cancelled run names the validators that already finished; their results stay.
- **Not loaded:** "Not loaded. Open to read it." in that build's column. Reading stored findings is a read.
- **No catalog action:** "Validation is read-only here · catalog action needed · not offered yet". Stored findings still read, and the Validate buttons are `aria-disabled` with that reason.

**Multi-variant rules**

- The panel is keyed by project and validator, with build as the column. Each run names one build. A run on several builds is one confirmed batch of per-build jobs ("3 runs: 1 waiting · 2 finished").
- Findings stay on their build. The Entity column maps an address to a logical entity only through a recorded locator. Addresses never move between builds by offset, so a finding at 0041b213 on build-a says nothing about 0041b2c3 on build-b.
- Results are never promoted. A validator result is not a fact of the seven, not a claim tier and not recovery evidence.

**Linking**

- **Publishes:**
  - proposed `panel=validation` with `build`, not yet registered in `location-schema.json` (see the proposals);
  - the Result filter as proposed `f=finding:warning|error`; until registered, it is durable workspace state;
  - Enter on a Location, which goes to that address on that build (one history stop).
  - Arming or running never changes the selection.
- **Follows:** the inspected build, after the settle. Not holdable. A kept findings set is a ResultsTable snapshot (`keep=results:‹id›@‹build›`).
- **Targets rendered:**
  - an address → the Code Browser at that build;
  - an entity → Compare with the CounterpartStrip;
  - a job → the dock Jobs and Logs records;
  - a receipt → the receipt card;
  - an owner → OwnershipPanel;
  - an error bookmark cited as evidence → MarksList, Bookmarks scope.
- **Peek source:** Alt+↓ on a Location reads the cached Listing lines. On a job, it reads the stored job record. Nothing is decompiled or fetched.
- **Absent copy:** "not run" · "no findings" · "program-wide · no address" · "no entity at this address" · "unresolved on build-d" · "Not loaded. Open to read it." · "catalog action needed · not offered yet".
- **Target-size exception:** none. Rows are 28px, and links in cells are 24px tall (44px below 700px and with a coarse pointer).

**Keyboard**

- The results grid and the Findings table are APG Grids, one tab stop each. Arrows move between cells, and Home/End and Ctrl+Home/End also work. Enter on a result cell filters the findings. Enter on a Location goes to it, and Shift+Enter opens it beside.
- `w` collects the findings into a worklist (`list.worklist`), `x` and Space check rows, and F8 steps the active worklist.
- Proposed keymap id `validation.open` has no keys; it is reached from the menu and palette only. No key runs a validator.

**Accessibility**

- The note is `role="note"`. The run-state cards are a list, and the inspected build's card carries `aria-current="true"`.
- The grid is named "Validator results per build". A cell reads "Offcut references, build-a: 1 warning". Glyphs are `aria-hidden`, and each result is its word.
- The Findings grid is named with its scope and time ("Validation findings, build-a and build-c, as of 14:02"). When a new run finishes, the dock announces it politely once ("Validation on build-c finished: 2 errors, 1 warning"); this panel is not a live region.
- Forced colours: result glyphs keep their words, and the card frames use `CanvasText`.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "Rows not yet designed".

- **P11** Validate Program covers:
  - the list of validators, each turned on or off before a run;
  - Run Validators as an admitted job per build, with each validator's progress, and cancellation of the job, after which the finished validators' results stay;
  - the OK, warnings or errors result per validator;
  - the text of each finding, as linked rows instead of a text area.
- **Related, not planned: X08 Function Bit Patterns Explorer.** It mines function-start byte patterns to author new pattern files for Ghidra's analyzers. Those patterns are a tool-level change to how every build is disassembled, so using them would mean re-analysing, not reusing valid receipts. Mined patterns would also be heuristic evidence that no recovery fact consumes. Function discovery here relies on the stored analysis, identity evidence and Function ID (FunctionIdManager). The row stays "needed (not planned)".

**Prior art**

Ghidra Validate Program (`ValidateProgram/ValidateProgram.html`): post-analysis problem detection, the validator list and the per-validator result icon. Unlike Ghidra, results are per build with the build named, and findings are linked rows, not a text area.
