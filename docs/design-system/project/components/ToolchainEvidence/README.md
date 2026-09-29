# ToolchainEvidence

Which compiler, linker and flags produced each build, as a facts × builds grid where every value shows its evidence level. A byte witness or a record is solid. An inference from code-generation idioms is a dashed "hypothesis (heuristic)" that names its basis. No evidence is the word unknown. A rebuild-toolchain row warns when the rebuild toolchain (from the registry) differs from the evidence.

**Use it** as a corpus view in the Corpus workspace, `ws=evidence&panel=toolchain` (a registered `panel` value), reached from a build header's toolchain line, from ArtifactCard's provider line, and from VariantRelation's toolchain column. It answers "can these builds be the same source compiled differently, and can our rebuild toolchain byte-match each one?"

**Consumer provides** per build: the stored PE parse (Rich header entries decoded to product id, build number and count, including LTCG kinds; linker version; debug directory CodeView; imports); the PDB records when one is matched by GUID and age (S_COMPILE3, S_ENVBLOCK compiler and linker command lines, and source file checksums); the detector aggregates, each with its detector id, sample size and the example addresses (frame shape, jmp-thunk runs, hotpatch prologues, alias and fold map, duplicate literals, cookie and EH idioms, CRT Function ID matches); and the rebuild toolchain (from the registry): its compiler and linker, with their hashes. Each value comes with its source kind: witness, record or detector.

- **Columns are builds** (build-a … build-d). Each header links to the Navigator program row, and has a one-line summary composed only from solid values ("VC 7.1 · LTCG · /Oy (hypothesis)" names only what the cells show; a hypothesis in the summary keeps its word).
- **Rows** are facts, grouped:
  - **Compiler and linker identity**: Rich header (§7.1) · machine and pointer width (§4) · linker version (§7.2) · PDB / CodeView (§7.2) · CRT startup (§7.2).
  - **Code generation**: /GS cookie (T8) · EH model, FH3/FH4 and handler3/4 (T9, T10) · LTCG (T5) · /Oy frame pointers (T2; "not applicable" on x64, witnessed by the machine type).
  - **Link-time layout**: incremental-link thunks (T12) · hotpatch padding (T13) · ICF folding (T6) · string pooling (T7).
  - **Rebuild**: the rebuild toolchain (from the registry).

  Each row header carries a native link to its section of `docs/research/2026-09-29-msvc-optimization-for-decomp.md` ("research §7.1", "research T2").
- **Every cell is an evidence-level value** (`.ad-evd`). It shows the level word, the value, and a basis line:
  - **witness** (solid 1px `line-control` frame): bytes in this image. The basis names the entries or counts and links the witness address, typed and always with its build: "C++ 00600c05 ×212 · C 005f0c05 ×38 · LNK 005a0c05 · 00400080".
  - **record** (solid frame): a recorded toolchain, PDB or command-line record: "compiler command line (S_ENVBLOCK)".
  - **hypothesis (heuristic)** (dashed frame): inferred from code-generation idioms. The basis is always named with its sample, and says what was not checked: "basis: 212 of 226 sampled functions have no EBP frame · frame detector".
  - **unknown** (no frame, italic): no evidence. "no Rich header in the image; absence is not proof". Nothing guessed is drawn in.

  A cell may stack two values, for example a witnessed CRT import above a hypothesised entry-stub shape. A hypothesis never becomes a witness by repetition or by agreeing with its neighbours. A solid absence is written as what was checked ("the Rich header lists no LTCG entries"), never as a bare "no".
- **Rebuild toolchain (from the registry)** is the last row, set off by a 2px `line-control` rule. Each cell is the registry record, with version and hash, and whether it matches the evidence. When it does not match, the cell adds a mismatch box, and a notice (StateNotice `conflict`: `.fault`, ⇄) repeats it under the grid: "⇄ Mismatch: the evidence says VC 8.0 build 50727. A modern cl.exe cannot byte-match this build; its compiles are compile checks only." The notice links research §0 and §7.3. It arms at most one catalog action from `GET /api/v1/actions` for that build, and says so when there is none ("Not available on this server yet. The evidence still reads. · What this server offers"). Nothing runs from here. A build with no registry record reads "unknown · not in the registry". ("Pinned" is reserved for the ◎ locator status.)
- **What the evidence suggests · by pair.** Under the grid, a short list per pair of builds, built only from the cells above:
  - "build-a ↔ build-b: same toolchain (witness) · differ in LTCG (witness) and /Oy (hypothesis) → compile variance (same source, compiled differently) is plausible · hypothesis (heuristic): no recorded source identity on either build".
  - A pair whose source, toolchain and flag identity are recorded for both builds says so; only then can a variance class be solid In corpus-alpha no pair qualifies yet: only build-d has recorded source identity, and the list ends by saying so.

  Each pair links to VariantRelation with `cmp`.
- Alt+↓ on a hypothesis cell peeks the stored detector run: basis, what was not checked, what would make it solid, and one example address.
- Read-only by construction. It reads stored parses, PDB records, detector results and the toolchain registry. It never runs a detector, compiles, registers or downloads a toolchain.

**Linking**

- **Publishes:** nothing but Go. A witness address is a Go to the Code Browser at that build. A pair link is a Go to VariantRelation (`ws=compare&panel=variants&cmp=build-a..build-b`). Keep on a peek publishes `keep=peek:…`.
- **Follows:** `project`; commit-on-Enter (a corpus view). With a `build` in the location, that column carries the selection shape. Not holdable.
- **Targets rendered:** witness address → the Code Browser at that build and address (the Rich header, optional header, debug directory, import table, FuncInfo, a cookie check, the ILT start, a padding run) · build header → the Navigator program row · research link → the research section (a native `/docs` link, never intercepted) · pair → VariantRelation · detector receipt → its receipt card. Link names read "Address 00400080, build-a, Rich header".
- **Peek source:** the stored detector run and its receipt; stored PDB record excerpts. Nothing is parsed or fetched on peek.
- **Absent copy:** "unknown" · "no Rich header in the image; absence is not proof" · "PDB not available" · "not in the registry" · "none found" (always as a hypothesis, with the detector named) · "Not available on this server yet. The evidence still reads. · What this server offers".
- **Target-size exception:** inline. Witness addresses sit inside the basis line of a value and are 24px tall. Research links are 24px rows under the fact name.

**Keyboard**

- A cell-focus APG Grid with one tab stop. Arrows move focus across facts and builds, and Home/End and Ctrl+Home/End work as in ReadinessMatrix. Group header rows are skipped by ←/→ and read by ↑/↓.
- Enter on a cell goes to its first witness link. Tab and Shift+Tab move between links inside a cell, the way the host grid moves between links in a cell. Alt+↓ peeks a hypothesis or record. Shift+F10 opens the link menu.

**Accessibility**

- `role="grid"` named "Toolchain evidence by fact and build", `aria-describedby` the level key. Facts are row headers, builds are column headers, and group rows are `th scope="rowgroup"`.
- The level word is visible text in every cell, so the frame style is only the second cue. Dashed and solid frames stay 1px `line-control` (3.2:1). They become 2px under Increase contrast and `CanvasText` in forced colors.
- The mismatch box is `role="note"` with ⇄ plus words, and is never color alone.
- Below a 480px container the grid follows NarrowFlow's build-column grid rule: one list item per fact, each build a labelled line ("build-c: cl 19.51 · record"), with nothing scrolling sideways.
- Identifiers (product ids, addresses, symbols, command-line switches) carry `translate="no"`.

**Removes switching:** comparing builds' toolchains no longer means opening each program's headers, PDB and detector output one at a time; the same facts line up in one grid, each with its evidence level.
