# AnalyzerPanel

The analyzers of every build in one grid: each build's enablement and per-analyzer options side by side, saved configurations, one-shot analyzers bound to a selection, each build's analysis state and the analysis log, where every configuration change and every run is an admitted catalog job and nothing runs on open.

**Use it** from the Analysis menu, the palette ("Analysis", "Analyzers", "One-shot") and a build's row menu in the navigator. It replaces Ghidra's Auto Analysis Options dialog, the Analysis section of Program Options, the One Shot submenu and the "Ask To Analyze" prompt. There is no Start button that fires on open, and nothing in this panel admits work except Run in the ActionStrip.

**Consumer provides** the project and its builds. Per build: its language and compiler spec, its analysis state (never analyzed, analyzed with a receipt, stale since a receipt, running, waiting on a writer, failed, or not read), the receipt id with its basis, provenance (fresh, reused, historical) and read time, the writer lock as reported (owner kind, job, PID and start time), and the stored analysis options, as the program holds them, read at a stated time. Per analyzer: name, description, "started by" trigger, whether it is a prototype, whether it supports one-shot use on this build's language, whether it applies to this build's language at all, its default enablement, and its options with defaults. Also the named configurations (Standard defaults, Current program options for a build, saved configurations), the catalog actions that set options, run analysis and run one analyzer (read from `GET /api/v1/actions`; no action id is named here), the viewer's drafts, and the log tail of the current analysis job.

**Anatomy**

- **Header.** "Analysis · ‹project› · N builds", a Scope segment (inspected build or All builds) and a Show segment (All analyzers, or "Differs or not default" with its count). With one build in scope the grid has one build column; All builds adds a column per build and an Across builds column. It never assumes one binary.
- **Analysis state per build.** One card per build, glyph plus word: "● analyzed · receipt valid for this basis" with the ProvenanceStamp; "◷ stale · program changed since receipt ‹id›" with the transaction count; "○ never analyzed · no receipt"; "● writer owned · analysis waits" with the owner exactly as reported; "running" with measured units or "Progress unknown · last event ‹time›"; "✕ failed" linking its FailureRecord; "? not read". A running job names the stale receipt that led to its admission. The inspected build's card has the `ink-strong` frame.
- **Analyzers grid.** Rows are analyzers, columns are builds. A cell says ✓ on, ○ off, ⊘ not applicable (with the reason, for example "build-d's language differs; this analyzer does not apply") or ? not read. A value that is not the standard default adds the words "not default" (Ghidra's highlighted row; ≠ stays reserved for source variance, divergence and claim boundaries). The Across builds cell compares stored values only, never drafts: "differs across builds" (±), "same in all builds" (≡) or "unknown for ‹build›" (?). Prototype analyzers carry a "prototype" chip (a plain chip; dashes are reserved for hypotheses) and the note that their results are analysis-tier candidates.
- **Function Start Search row.** Its options disclosure includes the pattern file the analyzer reads, and a **Patterns…** button opens FunctionStartPatterns for the inspected build. A pattern file drafted there by "Use in analysis…" arrives here as an ordinary per-build draft ("pattern file: pf-03 (was default)"), posted only through this panel's own confirm.
- **Options disclosure.** "Options · N" on a row expands a per-build table of that analyzer's options under the grid. Values are read, never inferred; a build that was not read says "not read".
- **Drafts.** Editing a cell or an option (Space on a focused cell, or a value in the options table) makes a per-build draft, drawn in the shared "draft" frame (solid `line-control` with the word "draft"; dashes are reserved for hypotheses) with the old value ("on (was off)"). Drafts are per viewer in durable workspace state and never in the URL. A draft never runs analysis and is never applied until posted.
- **Configuration row.** The Configuration select (Standard defaults, Current program options · ‹build›, saved configurations) fills drafts; it posts nothing. **Set analysis options on ‹build› (catalog)…** arms the ActionStrip for that one build with the drafts as fields. **Propose ‹build›'s options to ‹builds›…** is the separate cross-build step: a per-build preview (which values change, which analyzers are not applicable on that build's language and are skipped) and a ConfirmDialog naming each recipient. A recipient with a different language or compiler spec is excluded by name, never silently.
- **Run.** Two ActionStrip forms. **Analyze ‹build› (catalog)** names the build, the receipt it would reuse or why it is stale, and that the job reads that build's stored options. **One-shot · ‹analyzer› (catalog)** is bound to the Listing selection as an address set on one build, frozen when armed, and says "Analysis can change code outside the selection" (Ghidra: areas outside the selection may be changed). Only analyzers that support one-shot use on that build's language are listed.
- **Analysis log.** The current job's log tail in a `well`, read-only, lines prefixed by job id and time, addresses as typed links for that build. It links to the dock's Logs and Jobs records, which own the full record (ActivityRecord). "A finished analysis job is not recovery."

**States**

- **Never analyzed:** StateNotice "‹build› has no analysis. Opening it did not start analysis." with Analyze ‹build› (catalog)… armed-not-run. An empty Listing or Functions list is not permission to analyze again.
- **Valid receipt:** "Receipt ‹id› is valid for ‹build›." The stored analysis is reused and labelled reused. Reanalysis needs the catalog's force field and a ConfirmDialog that names the build and what it rewrites.
- **Stale:** the receipt names its basis and the transactions since; nothing re-runs by itself.
- **Writer owned:** "Waiting: ‹build› has a writer", with the owner as reported. Run is disabled with that reason. Nothing is killed or restarted to make room; an external owner is never offered either.
- **Running, checking, finished, failed, cancelled:** the Job outcome words on the invoking row and in the dock; "Checking whether the operation completed" disables Run on that build until reconciled.
- **Options not read:** "Not loaded. Open to read it." in that build's cells. Reading options is a read; it never analyzes.
- **Option not stored:** a program that was never analyzed may hold no value for an analyzer; the cell says "unknown · not stored in ‹build›'s options", never the default as if it were read.
- **No catalog action:** "Options are read-only here" names the missing action class. The grid still reads; set and propose buttons are `aria-disabled` with that reason.
- **Analyze All Open:** not a button here. Corpus-wide analysis is WorkflowControl admission (Z03); this panel links to it.

**Multi-variant rules**

- Keyed by project and analyzer, with build as a column. Each mutation names one build.
- Analyzer options are program-level: across builds they are compared, never merged. Different options on builds that are later compared are flagged in the ProvenanceStamp basis of the comparison.
- A difference between builds' configurations is labelled by cause only when a record states it (for example "set by job ‹id›"); otherwise it is "differs across builds" and the cause is unknown.
- Multi-user merge does not merge analysis options (Ghidra's own note), so VersionControlPanel warns before a check-in that can replace them.

**Linking**

- **Publishes:** `panel=analysis` (registered) with `build` for the inspected build. The Show filter is `f=analyzer:differs` (registered in `location-schema.json`). Scope and the options disclosure are durable workspace state, not location. Arming or running never changes the selection.
- **Follows:** the inspected build, settle; the one-shot strip is bound to the Listing selection and does not follow once armed ("Bound to 0041c880–0041c97f · selection is now …· Rebind"). Not holdable.
- **Targets rendered:** receipts → the receipt card · jobs → the dock Jobs and Logs records · owners → OwnershipPanel for that lock · the Function Start Search row's Patterns… → FunctionStartPatterns · addresses in the log → the Code Browser at that build · a failed run → its FailureRecord.
- **Peek source:** Alt+↓ on a receipt or job reads the stored record; on an analyzer name, its stored description and options. Nothing is fetched.
- **Absent copy:** "not read" · "Not loaded. Open to read it." · "not applicable · ‹reason›" · "no receipt" · "unknown for ‹build›" · "Options are read-only here".
- **Target-size exception:** addresses in the log are inline code tokens (the inline exception); everything else is 24px, 44px below 700px and with a coarse pointer.

**Keyboard**

- The analyzers grid is an APG Grid, one tab stop: arrows between cells, Home/End, Ctrl+Home/End. Space on a build cell toggles that build's draft (a draft, never a post); Enter on "Options · N" expands the options table. Typeahead needs `/` because Space and `x` act in the grid.
- Keymap id `analysis.open` (registered; "Analysis", `g then a` in composite and code scopes; palette). No key runs analysis: Run in the ActionStrip posts, ConfirmDialog for cross-build and forced runs.

**Accessibility**

- APG Grid with row headers; each cell reads "Demangler Microsoft, build-c: off, not default"; glyphs are `aria-hidden`. The state cards are a list; the current build's card carries `aria-current="true"`.
- The options table is a plain table with a caption; the disclosure button has `aria-expanded` and `aria-controls`.
- The log is a `pre` with an accessible name; it is not a live region. Job transitions are announced once by the dock, not here.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "New components needed".

- **Z02** analyzer list and options: enable, disable, per-analyzer options, saved configurations (Select All, Deselect All, Reset and Save map to drafts plus the Configuration select; Delete configuration is a catalog action).
- **Z04** one-shot analysis on a selection, as an ActionStrip bound to the frozen address set.
- **Z08** Demangler, Aggressive Instruction Finder and other prototype analyzers: the prototype chip, per-build enablement, and results labelled as candidates.
- Supporting, owned elsewhere: Z01 (no auto-analysis; ImportAdmission and WorkflowControl), Z03 (Analyze All Open is workflow scope), Z05 (the analysis log's full record is ActivityRecord in the dock).

**Prior art**

Ghidra Auto Analysis, Program Options › Analysis, One Shot analyzers, Ask To Analyze and saved options configurations (`AutoAnalysisPlugin/AutoAnalysis.htm`); the Show Log and task monitor topics. The per-build columns follow the project's multi-variant rule; the draft frame is the shared solid draft frame; it is not a hypothesis and is never dashed.
