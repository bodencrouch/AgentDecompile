# FunctionStartPatterns

Byte and instruction patterns around function starts and returns, per build, with an evaluation of any pattern against one build's recorded starts. It is Ghidra's Function Bit Patterns Explorer, made multi-build: the builds of a project are variants of one application, so the same pattern is read on each build and the difference is explained, not averaged. A pattern is always a hypothesis about how a compiler lays out function entries. It is never evidence that a function exists.

**Use it** from Tools › Function start patterns…, the palette ("Function start patterns", "Bit patterns", "Pattern clipboard") and AnalyzerPanel's Function Start Search row ("Patterns…"). It replaces Ghidra's Function Bit Patterns Explorer window, its Data Gathering Parameters dialog, its Analyze Sequences table and its Pattern Clipboard. Opening it reads stored gathers and stored mining results only. It never gathers, mines, searches or analyzes by itself.

**Consumer provides:**

- Per build: the stored **gather** receipts (the windows around recorded function starts and returns), each with its parameters, its basis (program generation and digest), the job that wrote it and the count of starts it read, split by the origin of each start (debug info, authentic symbols, analysis).
- Per build: the language id and compiler spec (ProgramSettings), because windows compare only within one language.
- From a gather, per build: byte sequences (first bytes, pre-bytes, return bytes) with counts; instruction sequences (first, pre and return instructions) as a tree with instruction lengths; the function-start address histogram for an alignment modulus; the values recorded for the requested context registers.
- Stored mining results (closed sequential patterns with support and fixed-bit counts) and evaluation results (matches per build, each classified).
- The viewer's pattern clipboard (durable workspace state, per viewer).
- The build's toolchain evidence (ToolchainEvidence), to name a variance basis.
- The catalog actions that gather, mine, evaluate, export and import patterns, and the function-creation mode of `manage-function` (read from `GET /api/v1/actions`; no action id is named here).

**Anatomy**

1. **Header.**
   - "Function start patterns · ‹project›", then the build scope: a checkbox group of builds, each with its language ("build-d · x86:LE:64 · compared separately").
   - The note (`role="note"`): "A pattern is a hypothesis about code generation. It is not evidence that a function exists. Agreement with recorded starts is not accuracy: recorded starts are themselves analysis results."
   - An APG tablist: **Byte sequences** · **Instruction trees** · **Alignment** · **Context registers** · **Clipboard** (with its count).
2. **Gather** (a job, ConfirmDialog). **Gather windows…** opens the parameters as a form, with Ghidra's names and its recommended values beside them:
   - Number of first bytes (20), pre-bytes (8), return bytes (8); number of first instructions, pre-instructions and return instructions (3, 4 or 5); context registers (comma-separated; "none" is valid).
   - **Programs**: the builds, each checkable. A build without an analysis receipt reads "excluded: no recorded function starts · nothing is analyzed here".
   - **Reuse first**: a stored gather with the same parameters and an unchanged basis is shown and reused ("reused · gather g41c, basis unchanged"); **Gather again** is a separate, explicit choice.
   - **Consequence**: "Reads build-a and build-c. Writes one gather receipt per build. The programs are not changed." The primary button counts the jobs ("Gather · 2 jobs").
   - **Directory of pattern-info files**: Ghidra's other data source, gathers written elsewhere by the pattern-info script. Importing one is a read-only parse into a gather labelled "external · file ‹name› · sha ‹8 hex›"; it is never mixed into a build's own gather.
3. **Byte sequences.** Sub-tabs **First bytes** · **Pre-bytes** · **Return bytes**; filters are per sub-tab, as in Ghidra.
   - **Length filter** (required): minimum length and a prefix length, or a suffix length written as a negative number. **Context register filter** (optional).
   - The grid: rows are sequences, columns are builds (one column per build in scope) plus **Across builds**. A cell reads "812 of 1,144 starts · 71%". A sequence that does not occur reads "0 of 1,152 · absent". A build with another language reads "not comparable · x86:LE:64".
   - Bytes are mono hex in groups; a ditted position is a `.` and the row names it ("3 fixed bytes, 2 ditted").
   - The disassembly of a sequence is shown as a second line when it decodes the same on every build in scope ("push ebp · mov ebp, esp"), and "decodes differently per build" otherwise.
   - **Across builds** uses the cross-build words: "same in all builds (x86-32)", "differs: consistent pattern", "absent in build-b". A difference carries its variance class with its evidence level, for example "≈ compile variance · hypothesis (heuristic): /Oy on build-b (ToolchainEvidence hypothesis); frame-pointer prologue in 4% of starts". A variance class is never solid unless source, toolchain and flag identity are recorded for both builds.
4. **Instruction trees.** Sub-tabs **First** · **Pre** · **Return**. An APG Tree per build, side by side at 960px and stacked below it. Instruction length is part of the path ("push ebp (1 byte)" and "push (2 bytes)" are different branches).
   - Each node shows its share of paths as a number and a word ("41% of 1,144 paths"); Ghidra's hover percentage is always visible here.
   - **Percentage filter** removes nodes below the threshold and says how many it hid ("12 nodes under 5% hidden"). The context register filter is the same as for bytes.
   - **Analyze sequences** on a node opens the byte sequences under it (step 6).
5. **Alignment.** A modulus field (default 16) and, per build, a table of residue → count, with the largest residue in bold. A reading is a hypothesis with its basis: "build-d: 1,391 of 1,402 starts at residue 0 · hypothesis (heuristic): 16-byte aligned". An unaligned build reads "no dominant residue". Ghidra's use of this, skipping unaligned offsets when searching, is offered only as the clipboard's Alignment column.
6. **Analyze sequences.** A table of the selected sequences with counts and disassembly. Actions on a checked set:
   - **Send to clipboard**; **Merge selected** (a position all rows agree on keeps its bits, others become dits; the merged row says "merged from 3 sequences · 14 fixed bits"); **Send merged to clipboard**;
   - **Mine patterns…** (a job, only for byte sequences): minimum support percentage (10), minimum fixed bits (16), and **Bits** or **Characters** (nibbles; "fewer patterns, much faster", as Ghidra says). Results are closed sequential patterns: a pattern is listed only when no longer pattern occurs as often. Each result reads its support and fixed bits and is a hypothesis with basis "support 38% of 1,152 first-byte windows on build-b".
7. **Clipboard.** The viewer's patterns, each with Kind (**PRE**: before a start, from pre-bytes, pre-instructions and returns; **POST**: from first bytes and first instructions), bits with dits, fixed-bit count, Alignment (editable, as in Ghidra), context register values and its source ("mined on build-b · job m7a2").
   - **Evaluate on…** (a read on one named build). If both PRE and POST patterns are checked, they are combined, as in Ghidra. The result is a table of matches in four classes, with counts first: **at a recorded start** · **inside a recorded function** · **in undefined bytes** · **in defined data**. The summary names its reference: "1,204 matches on build-a: 802 at recorded starts (67% agreement with recorded starts, not accuracy) · 311 in undefined bytes · 58 inside functions · 33 in data". Each match links its address with its build.
   - **Create functions…** on checked matches of one build (normally "in undefined bytes"). One match confirms in place; more than one uses ConfirmDialog, which names the build, the count, the patterns that found them and that each new start is recorded as "created from pattern P1+P2 · hypothesis". Each creation is its own transaction and undoable in EditHistory. Nothing is created on another build.
   - **Export pattern file…** (a job): Total bits and Post bits, with Ghidra's rule written out ("each PRE pattern joined with each POST pattern that together fix at least 32 bits, at least 16 of them after the PRE bits"). The file is an artifact listed by its job record in OutputsCatalog.
   - **Use in analysis…** opens AnalyzerPanel on one build with the Function Start Search analyzer's pattern-file option drafted to the exported file. Nothing runs until that panel's own confirm, and a one-shot run analyzes that one build only.
   - **Import pattern file…** is a read-only parse. Attributes the clipboard does not support are refused by name ("unsupported attribute: postrules"), never dropped silently.

**States**

- **Never gathered:** "No gather on build-a · Gather windows… reads its recorded function starts; nothing is analyzed". The tabs show the same line, not empty grids.
- **Reused:** a gather or mining result whose basis is unchanged reads "reused · ‹job› · basis unchanged".
- **Stale:** a gather whose basis predates a program change reads "◷ stale · 3 transactions since gather g41c"; its numbers stay visible and are labelled stale.
- **No recorded starts:** "build-x has no analysis receipt · no recorded function starts to gather".
- **Not comparable:** another language's column reads "not comparable · ‹language id›" in every cell; it never shows 0.
- **Running, checking, finished, failed, cancelled:** the Job outcome words, for gather, mine and export.
- **Truncated:** an evaluation over its limit reads "first 5,000 matches of 12,340 · counts are complete", and the counts are exact.
- **Not loaded:** "Not loaded. Open to read it."
- **No catalog action:** "Pattern gathering is read-only here · catalog action needed · not offered yet". Stored gathers and results still read.
- **Narrow (below 700px):** builds stack under each sequence as rows ("build-a · 812 of 1,144 · 71%"); trees stack per build; the clipboard becomes a list with one row menu per pattern.

**Multi-variant rules**

- Windows, trees, alignment and evaluations are per build. A sequence is compared across builds only within one language id; build-d (x86:LE:64) is compared with nothing here.
- Counts are exact fractions per build and are never pooled or averaged across builds. There is no project-wide percentage.
- A pattern mined on one build is evaluated on one named build at a time. Evaluating it on another build is a separate read that names that build. Nothing propagates, and Create functions writes one build.
- Recorded starts differ in origin. The gather states how many came from debug info (a record, build-d), authentic symbols or analysis, and a pattern's basis inherits that mix.
- Differences between builds carry a variance class and its evidence level. A frame-pointer prologue present on build-a and rare on build-b is "differs: consistent pattern" with "≈ compile variance · hypothesis (heuristic)", naming the toolchain hypothesis it leans on.

**Linking**

- **Publishes:**
  - `panel=patterns` with `build`, registered in `location-schema.json`.
  - Tab, sub-tab, filters, the modulus and the clipboard are durable workspace state, never the URL.
  - Enter on a match goes to that address on its build (Listing).
  - **Show all occurrences** on a sequence opens SearchWorkbench's memory search on that build with the bytes filled in (`panel=search&build=build-a&q=55 8B EC`); nothing searches until its Enter.
- **Follows:** the inspected build for the build scope's default, after the settle. Not holdable.
- **Targets rendered:**
  - a match address → the Code Browser at that build;
  - a gather or mining job → the dock records;
  - a variance basis → ToolchainEvidence;
  - a language exclusion → ProgramSettings;
  - Use in analysis → AnalyzerPanel;
  - an exported file → OutputsCatalog and ArtifactCard;
  - a created function → EditHistory's transaction.
- **Peek source:** Alt+↓ on a sequence reads its first 20 stored occurrences on that build with their addresses. On a tree node, it reads the node's sequences. Nothing is searched beyond stored results.
- **Absent copy:** "No gather on ‹build›" · "absent" · "not comparable · ‹language›" · "no dominant residue" · "no recorded function starts" · "Not loaded. Open to read it." · "catalog action needed · not offered yet".
- **Target-size exception:** none; rows are 28px and every control is 24px, or 44px below 700px and with a coarse pointer.

**Keyboard**

- The tablist and sub-tabs use APG Tabs with manual activation. Sequence grids, the clipboard and the match table are APG Grids with one tab stop each; trees are APG Trees.
- Space checks a row. Ctrl/Cmd-click toggles and Shift-click extends, as in every checkable grid. Enter on a sequence opens Analyze sequences; Enter on a match goes to its address.
- Keymap id `patterns.open` has no keys; it is reached from the menu and palette only. No key gathers, mines, evaluates, exports or creates.

**Accessibility**

- A byte cell reads "55 8B EC, build-a: 812 of 1,144 starts, 71 percent. Across builds: differs, consistent pattern; compile variance, hypothesis." Bytes carry `translate="no"`; a dit is read as "any".
- Tree nodes carry `aria-level`, `aria-setsize` and `aria-posinset`, and their share is in the name.
- The evidence level and the variance class are words; the dashed frame is the second cue.
- A finished gather, mining run or export is announced once by the dock. Evaluation counts are a polite status once they settle.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "12. Patching, Program Diff, Version Tracking".

- **X08** Function Bit Patterns Explorer covers:
  - both data sources (the current program, as selected builds, and a directory of pattern-info files, as a read-only import);
  - every data-gathering parameter (first, pre and return bytes; first, pre and return instructions; context registers);
  - the byte sequence tabs with length and context register filters; the instruction sequence trees with percentage and context register filters; the function start alignment tab; the context register information tab;
  - Analyze Sequences: send to clipboard, merge selected, send merged, mine closed sequential patterns (minimum support, minimum fixed bits, bits or characters);
  - the pattern clipboard: PRE and POST, the editable alignment, evaluate selected patterns, create functions, export a pattern file (total bits, post bits) and import one.
  - Supporting, owned elsewhere: running the Function Start Search analyzer with the file (AnalyzerPanel, Z02), and memory search (SearchWorkbench, Q01).
  - Backend: contract entries J19–J21 and R37–R39 in the [catalog contracts](../../../../dashboard-design/2026-09-29-catalog-contracts-for-parity.md).

**Prior art**

Ghidra's Function Bit Patterns Explorer (`FunctionBitPatternsExplorerPlugin.htm`) and the pattern-info script it reads. Unlike Ghidra, every build in scope is read side by side, a build of another language is never compared, a pattern is always a hypothesis, evaluation reports agreement with recorded starts rather than accuracy, and creating functions or using a pattern file in analysis is an explicit, confirmed change to one build.
