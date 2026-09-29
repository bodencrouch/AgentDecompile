# SearchWorkbench

One search surface for memory bytes, program text, decompiled text, instruction patterns (masked or wildcard), scalars, strings, direct references, address tables and search-and-replace. Every search takes a scope (its search bounds) of this build, all builds, a selection or the view, shows exactly what it will search for per build, and sends its results to a ResultsTable with per-build hit columns.

**Use it** from the palette ("Search…"), the Code Browser's Search menu, the Listing link menu ("Search for matching instructions", "Search for direct references"), or a ResultsTable's "Edit search". It opens as a secondary area under the Code Browser center (`panel=search`, registered), with its ResultsTable below the form. Below 700px it is its own pane in NarrowFlow's Analyze group. The static 8080 surface may render the same form and table on one page with identical words.

**Consumer provides**
- The builds of the project with their load state, language, endianness and pointer size.
- The Listing's current selection (one build) and the ProgramTreeView view restriction.
- For instruction mode: the selected code units with their bytes and the operand masks per code unit. These come from the build's language, through a catalog read.
- The catalog's search reads and the mutating actions (Make string, Make table, Disassemble, batch replace) from `GET /api/v1/actions` (no action id is named here). A mode with no backing read is listed with "catalog action needed".
- The viewer's recent searches for this project, in durable workspace state.

## Anatomy

1. **Mode tabs** (manual activation): Memory · Text · Decompiled text · Instructions · Scalars · Strings · Direct references · Address tables · Replace. A mode whose catalog read is missing stays listed, `aria-disabled`, with "catalog action needed".
2. **Scope chips** (a radio group, carried as the registered `f=search.scope:` axis):
   - **This build · build-a**;
   - **All builds**, listing each build and its state: loaded, "not loaded · will be skipped · Open build-d to include it", or "unsupported for this mode";
   - **Selection · build-a 0041b210–0041b37f** (enabled only with a Listing selection; disabled in All builds, with "A selection belongs to one build");
   - **View** (the ProgramTreeView restriction).

   The chosen scope is repeated in the Search button ("Search all builds") and the results header. Nothing is searched outside it.
3. **Query line**, per mode:
   - **Memory** (Q01): format (hex, binary, string, regular expression, decimal, float, double) and input, with validation per format (`aria-invalid` and the reason inline). Options: endianness, alignment, decimal size, signed or unsigned, string encoding (ASCII, UTF-8, UTF-16), case sensitivity, escape sequences, and code-type filters (instructions, defined data, undefined bytes).
   - **Text** (Q02): the text, whole word, case, regular expression; the fields (functions, labels, comments by kind, mnemonics, operands, data fields); and the search type:
     - **Program database** (fast; stored fields only);
     - **Listing display** (what the Listing renders; slow).
   - **Decompiled text** (Q12): the text or regular expression, over **stored decompilations only**. The line states coverage per build ("build-c: 212 of 1,480 functions decompiled in the stored cache; the rest are not searched and not decompiled"). It never decompiles to search. Decompiling more is a separate admitted action.
   - **Instructions** (Q03, Q04, Q11): the pattern builder (below), or a wildcard assembler line (`mov `Q1`, dword ptr [`Q2` + 0x4]`) where the catalog offers it.
   - **Scalars** (Q05): a specific value, or a range (minimum and maximum), signed or unsigned, and the operand kinds to include.
   - **Strings** (Q06): minimum length, alignment, require null termination, Pascal strings, charset, the word model (Is word column), and loaded blocks only or all blocks. **Encoded strings** adds a charset choice, the scripts to allow, and "show only valid strings". Validity is a score from the build's own bytes and is drawn as a dashed "hypothesis (heuristic)" with its basis ("charset guess; not checked against the program's locale"), never as a defined string.
   - **Direct references** (Q07): to the cursor address or to the addresses in the Listing selection, with an alignment filter. With **All builds**, each build is searched for **its own counterpart address**, which is taken from its locator and its accepted identity edge ("build-c: 00082f40 · accepted"). A build without a resolved counterpart is skipped and says why ("build-d: unresolved; not searched"). An address value is never carried across builds.
   - **Address tables** (Q08): minimum length, alignment, skip length.
   - **Replace** (Q10): find, replace, regular expression with capture groups (`$1`), case, whole word, and element kinds (classes, functions, labels, namespaces, parameters, locals, data types, data-type categories, data-type fields, data-type comments, enum values, comments, memory blocks, program trees), with Select all and Deselect all. Memory blocks and program trees are program-local; their rows are never proposed to other builds.
4. **What will be searched** (always shown before Search). A per-build `dl`:
   - the byte sequence, with masked bits drawn as `.` in binary and `[001..011]` in hex, following Ghidra's preview;
   - the endianness it was converted with;
   - the alignment;
   - the scope actually covered.

   Builds whose endianness or pointer size differs get their own converted line. A pattern that cannot be converted for a build says so, and that build is skipped.
5. **Search controls.**
   - **Search** (all hits, into a new or the same ResultsTable).
   - **Next** and **Previous** from the Listing cursor (incremental; memory, text and instruction modes; this build only).
   - **Combine with current results**: Replace · Add (union) · Intersect · Remove (subtract) · Either but not both. Combining works per build and says so ("Intersect on build-a; build-c had no current results").
   - **Result limit** (the catalog's field, default shown).
   - **Re-check hits** (Ghidra's scan controls, memory mode): re-reads the bytes at the current hits on the same build and keeps the hits whose value changed, did not change, increased or decreased since the search. It is a read. On another build it re-checks only hits carried through a recorded anchor ("build-c: via anchor"), never by offset.
   - **Highlight matches** (per viewer): marks the active result set's matches in the Listing on the inspected build.
   - **Recent** menu of earlier searches, restoring their fields and scope.
6. **Progress** per build in measured units ("build-a: 5 of 7 blocks · build-c: waiting · build-d: skipped, not loaded"), or "Progress unknown · last event 14:02". **Cancel** keeps the hits already found and says "cancelled · 212 hits kept on build-a". There is never a percentage without units.
7. **Results** go to a ResultsTable of the mode's kind. Memory, instruction, scalar, direct-reference and address-table hits are grouped per build and never joined. Text and string hits join only by the kind's stated rule. The OverviewBar's hits lane and the Listing's marker margin show the active result set on the inspected build.

## The pattern builder (instruction mode)

- It is filled from the Listing selection on one build, as **Load selection** or **Add selection**, or by **Enter bytes manually**.
- Each code unit is a row: address, bytes, mnemonic and its operands. Each operand is a **mask toggle** (`aria-pressed`, the word "masked" when on).
- The quick masks mirror Ghidra: Mask all operands · Mask scalars · Mask addresses · Mask data (non-instructions) · Clear masks. The three presets from Search for Matching Instructions are available: include operands, exclude operands, include operands except constants.
- The **masked-bits view** shows the resulting value and mask in binary (masked bits as `.`) and hex (a partly masked byte shows its bits in brackets), with **Copy pattern**.
- **Evidence level.** The pattern's bytes are solid (they came from build-a). A masked pattern that finds a hit on another build is a candidate identity channel only (NP). The results header says "hits are candidates; a pattern match is not identity". Zero hits on build-c is not absence of the function, because compile variance changes register encodings, and the empty state says so.

## Replace mode and mutations

- Replace first runs a **preview** per build: element, old text, new text, and a naming-convention check. A result that breaks the convention for its kind (for example a local that is not camelCase) is flagged "does not follow the naming convention", and is never auto-fixed.
- **Apply** arms the catalog's batch replace in the ActionStrip for the checked preview rows on one build, then opens ConfirmDialog ("Rename 14 elements on build-a"). With All builds in scope, Apply opens a cross-build ConfirmDialog. It shows counts per build and a per-recipient outcome after the terminal results. Each build is its own transaction, with MC conflicts resolved explicitly.
- **Make string** (Q06), **Make table** and **Disassemble targets** (Q08) are ResultsTable row actions. They are catalog-gated per build with ConfirmDialog for more than one row. Disassemble is an admitted analysis job (NA).
- Every mutation names its exact build. Propagation to counterparts is only the separate PropagationTransfer proposal.
- One writer: with the build's lock owned elsewhere, Apply and the row actions stay listed with the reason, and Run is refused.

## States

| State | Shown as |
|---|---|
| Invalid input | the field has `aria-invalid` and "Hex digits only; ‘g’ at position 7"; Search stays enabled and reports the reason again on activation |
| Mode unavailable | the tab is `aria-disabled` with "catalog action needed" |
| Build skipped | "build-d: not loaded · skipped · Open build-d to include it"; nothing opens |
| Searching | per-build measured units; Cancel |
| Cut at limit | passed to the ResultsTable truncation line |
| No hits | "No hits on build-a, build-c · build-d not searched · pattern ‹…›" and, for instruction mode, "zero hits is not absence" |
| Stored-only coverage | decompiled text: coverage per build, as above |
| Stale results | "◷ build-b changed since this search (job a3f9) · Search again" |

## Linking

- **Publishes:** Search pushes one stop carrying `panel=search`, the mode and scope as the registered `f=search.mode:` and `f=search.scope:` axes, and the text as `q`. The byte pattern and masks are in the result set's source and not in the URL. Next and Previous move the Listing cursor (replaceState, like Find). A result row Go pushes from the ResultsTable.
- **Follows:** the inspected build and the Listing selection, to keep the Selection chip and "Load selection" current. It never re-runs a search on follow. Not holdable; its ResultsTable can be kept.
- **Targets rendered:** address (cursor, selection bounds, counterpart addresses in direct-reference mode) → the Code Browser at that build · counterpart with its edge word · build → its Navigator row · job → the dock Jobs record · the result set → its ResultsTable.
- **Peek source:** Alt+↓ on a code-unit row in the pattern builder peeks the cached Listing lines there. On a counterpart address, it peeks the locator evidence. Nothing is fetched.
- **Absent copy:** "not loaded · skipped" · "unresolved on build-d; not searched" · "catalog action needed" · "A selection belongs to one build" · "zero hits is not absence" · "not decompiled in the stored cache; not searched".
- **Target-size exception:** none. Tabs, chips, toggles and mask buttons are 24px or more (44px below 700px and with a coarse pointer).

## Keyboard

- Mode tabs: APG Tabs, manual activation. Scope: an APG radio group. The pattern builder: an APG Grid in which Space toggles the mask on the focused operand cell.
- In the query field, Enter runs Search. Keymap ids (registered in `keymap.json`; `search.next` and `search.prev` in region scope, SearchWorkbench):
  - `search.next` and `search.prev`: Ctrl/Cmd+↓ and Ctrl/Cmd+↑, incremental from the Listing cursor on this build;
  - `search.open`: Ctrl/Cmd+Shift+F, global, with a platform caution. It opens the workbench in the last mode and focuses the query. The palette's "Search…" does the same. There is no leader key, because `g then f` belongs to FrameLayout;
  - `search.loadSelection`: no default key; the Load selection button and the palette.
- Axis values: `f=search.mode:` is `memory`, `text`, `decompiled`, `instructions`, `scalars`, `strings`, `directrefs`, `addrtables` or `replace`; `f=search.scope:` is `build`, `all`, `selection` or `view`.
- F8 steps the active worklist collected from its results. `w` in the ResultsTable collects.
- Keys never post a mutation. Replace's Apply and every row action pass through the ActionStrip, and ConfirmDialog where required.

## Accessibility

- The workbench is a `region` named "Search, memory mode, all builds". The "what will be searched" block is a `dl` named "Search pattern per build". Its masked bits are spoken as "masked" through the row name ("byte 4, masked; byte 5, 0x85").
- Validation messages are `aria-describedby` on the field. Progress is `role="status"` with units in words, and only when the operator started the search. The result count is announced once, debounced 300ms.
- Mask toggles carry `aria-pressed` and the visible word "masked". A masked value is struck, never shown by color alone.
- Skipped and unsupported builds are words in the scope group and in the results.

## Parity rows covered

- **Q01**: Search Memory in hex, binary, string, regular-expression, decimal, float and double formats, with incremental forward and backward, combined searches (set operations) and the byte options. The scan controls become **Re-check hits** (changed, not changed, increased, decreased) on the same build, and on another build only through anchors, never by offset. Highlight matches is a per-viewer toggle.
- **Q02**: Search Program Text, with fields, database versus Listing-display search, incremental and all, and regular expressions.
- **Q03** and **Q04**: Search for Matching Instructions, with the three presets, and the Instruction Pattern Search dialog, with the instruction table, mask toolbar, binary and hex preview, bounds and manual entry.
- **Q05**: Search for Scalars, with a specific value or range, the selection scope, and filters in the ResultsTable.
- **Q06**: Search for Strings, with its options, encoded strings (validity as a labelled hypothesis) and Make string as a row action.
- **Q07**: Search for Direct References, per build, using each build's own counterpart address.
- **Q08**: Search for Address Tables, with Make table and Disassemble as row actions.
- **Q10**: Search and Replace, as a per-build preview, a batch ConfirmDialog, and a cross-build dialog.
- **Q11**: wildcard assembler patterns, where the catalog offers them.
- **Q12**: Search Decompiled Text across functions, over stored decompilations only and with the coverage stated.
- **Q09**: results go to ResultsTable.

## Prior art

- Ghidra help `Search/`:
  - `Search_Memory.htm`: formats, byte-sequence preview with masks, set-operation combining, the scan controls (changed, not changed, increased, decreased), and the results columns;
  - `Search_Formats.htm`;
  - `Search_Program_Text.htm`: database versus Listing-display search;
  - `Instruction_Mnemonic_Search.htm`: include, exclude and except-constants masks;
  - `Search_Instruction_Patterns.htm`: instruction table, mask toolbar, `.` and `[001..011]` preview;
  - `Search_for_Strings.htm`, `Search_for_DirectReferences.htm`, `Search_for_AddressTables.htm` and `SearchAndReplace.htm`: element kinds and capture groups.
- Research: register-rename awareness (C2) and why pattern hits are candidates, not identity (C9 and the variance classes), in `docs/research/2026-09-29-reference-re-ui-patterns.md`; the reccmp HTML report's search modes (§C11 notes).
- Existing components: ResultsTable, OverviewBar, MarksList, ActionStrip, ConfirmDialog, PropagationTransfer, CommandPalette (entry point).
