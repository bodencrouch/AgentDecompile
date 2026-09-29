# ResultsTable

The one generic results table behind every Ghidra-style list: search hits, references, symbols, defined strings and data, comments, equates, relocations, function tags, types, address tables and selection ranges. Every instance has sortable, filterable and choosable columns, selection-to-listing, Make selection, Collect into worklist, CSV export, a checked set for the ActionStrip, and per-build hit columns when its scope is all builds.

**Use it** wherever a feature produces rows keyed to addresses or entities: under SearchWorkbench; as the navigator's Strings, Symbols and Imports scopes in table form; as the corpus "Show all" view for equates, relocations, tags, types and defined data; and as a temporary table made from a selection. It never replaces the one Functions grid or the XrefPanel. References that open "as a table" (All builds with many rows) render in this component with the XrefPanel's words.

**Consumer provides**
- The result set: kind, source (the query or read that produced it, with its fields), scope (one build, or all builds with the list), snapshot time, and the basis per build (generation or digest).
- For each build: the row count, whether the result was cut at a limit, and whether the build was searched, not loaded or unsupported.
- The column set for the kind (defaults plus discoverable extra columns), per-column settings where they exist, and the join rule for logical rows.
- The catalog actions that can act on a checked set of this kind, from `GET /api/v1/actions` (no action id is named here).
- The viewer's saved column set, sort and filter strategy per kind, from durable workspace state.

## Anatomy

1. **Header.** Kind and title ("Search memory · hex `8b 46 04 ?? 85 c0`"), the scope words ("All builds · build-a, build-b, build-c · build-d not loaded"), the snapshot ("as of 14:02"), per-build counts, and a **Refresh** that re-runs the same read. Refresh never widens the scope.
2. **Truncation line**, only when a limit was hit: "Stopped at 500 hits on build-a; more may exist. Raise the limit in the search's fields and run again." A count is never rounded or projected. An unsearched build reads "build-d not loaded · not searched", never "0".
3. **Toolbar** (APG Toolbar):
   - **Filter** field with strategy (contains, starts with, exact, glob, regular expression), multi-term (all or any), and "match on" (visible columns, or the chosen column);
   - **Column filters** as FilterChips carried as `f=` axes, for example "Build is build-c ×", "Kind is call ×", "Defined is not defined ×", "Refs ≥ 3 ×";
   - **Columns…** (choose, reorder, reset; Fit to content and Default width per column, so nothing needs dragging);
   - **Copy** (the focused cell, the row, or the checked rows; columns chosen);
   - **Export CSV…** (the chosen columns in displayed order, for the checked rows or for all loaded rows; the dialog states "exports the 500 loaded rows; the table was cut at the limit");
   - **Make selection** (below);
   - **Collect into worklist** (`w`);
   - **Remove from table** (view only);
   - the ActionStrip's arming menu for the kind's catalog actions.
4. **Header cells** are sort buttons. Click or Enter sorts ascending, and again descending. With a modifier, a column is added as the next sort key, and each sorted header shows its order number ("▲1", "▼2"). A third activation on a secondary key removes it, and **Unsort** removes all sorts (useful for very large tables). Sort, column set and widths are per-viewer and per kind.
5. **Rows** (28px). A 24px check cell, then the kind's columns. Address and symbol cells are typed links carrying their build. Evidence columns say where each value came from ("defined", "not defined", "partially defined", "conflicts with an instruction").
6. **Per-build hit columns** (scope all builds). One column per build with its LocatorGlyph word and address link, or:
   - "absent" (searched, no hit);
   - "not searched" (not loaded or excluded);
   - "not indexed" (no index for this kind);
   - "no anchor" (the row's join needs an anchor and none is recorded).

   Rows are joined into one logical row only by the kind's stated rule, shown in the header:
   - **symbols, functions, tags, comments on entities**: by identity edge ("joined by accepted identity edge"; candidates show their edge word);
   - **strings, equates by name, types by name**: by content or name ("joined by content ≠ same entity");
   - **memory, instruction, scalar, direct-reference and address-table hits**: never joined across builds. Rows are grouped per build, because one pattern at different addresses is expected. A hit inside an anchored function says "in ResourceRef::Resolve on build-a, build-c · via anchor". Nothing is aligned by offset or order.
7. **Footer.** Source and read time per build. The keyboard summary.

**Kinds** (default columns; every kind can add columns through Columns…):

| Kind | Default columns | Row actions through the ActionStrip (catalog) |
|---|---|---|
| Search hits (memory, text, instruction, scalar, decompiled text) | Location, Match bytes or text, Match value, Label, Code unit, Function | Make selection, Collect, Make string or data where offered |
| Symbols (S05) | Name, Location, Type, Namespace, Source, Refs, Offcut refs | Rename…, Delete…, Set primary…, Keep at address on rebase… (Ghidra "pin symbol"), Delete references… |
| Defined strings (A01) | Location, String, Type, Length, Charset, Referencing functions | Translate… (A03), Make selection |
| Found strings (Q06) | Defined state, Location, Label, Preview, String, Type, Length, Is word | Make string…, Make char array… (offset, auto label) |
| Defined data (A02) | Location, Data type, Value, Label, Size | Make selection; a type filter chip |
| Comments (A08) | Location, Kind (EOL, pre, post, plate, repeatable), Text, Function | Comment… (InlineRename comment mode, one target) |
| Equates (P06) | Name, Value, Refs, Enum-backed, Display | Rename…, Remove…, Apply enum…, Convert display… (signed or unsigned decimal, hex, octal, char, binary, float, double) |
| Relocations (P05) | Address, Type, Values, Original bytes, Symbol | none; read-only, feeds ObjectDiff's relocation-aware equality |
| Function tags (F14) | Tag, Comment, Use count per build | Create…, Edit…, Delete…, Add to checked functions…, Remove from checked functions…, Load tags… |
| Types (T17) | Name, Category, Size, Kind, Uses per build | open in TypeManager (Go); program types only filter |
| Address tables (Q08, E11) | Location, Label, Length, Data (hex and ASCII) | Make table… (offset, auto label), Disassemble targets… |
| Ranges (L24) | Start, End, Length, Block | Make selection; ranges come from a Listing selection |
| Direct references (Q07) | From, Label, From preview, To, To preview | Make selection; Create reference… through ReferenceEditor |

**Temporary tables.** Tables made from a query or a selection are snapshots. They say "as of 14:02", keep their source link, and never merge in new rows silently. Refresh re-reads. If the basis moved, rows are marked "changed since you looked", "new since you looked" or "left this page since you looked", as in the Copy rules.

## Make selection, worklists and removal

- **Make selection** sets the Listing's address-set selection on one build from the checked rows, or from all rows. With all builds in scope, it asks "Make selection on build-a (inspected)" or "on build-c" and names the rows that will not be included ("9 rows on other builds are not included; a selection belongs to one build"). It is client state and never in the URL. Changing the program clears it (F11).
- **Collect into worklist** (`w`) snapshots the rows in their current order, across builds if they span builds, through the MarksList dialog: "It changes nothing in the project and starts no work." F8 then steps them.
- **Remove from table** removes rows from this view only. The row is struck until the next refresh, and the status line says "Removed 3 rows from this table; nothing in the program changed".

## Mutations

- A checked set arms one catalog action in the ActionStrip, bound to that set on one build. Rows from other builds are unchecked first, and the strip says so.
- A single row with an inline editor (Rename…, Comment…) confirms in place.
- Batch, destructive or cross-build actions use ConfirmDialog. This covers delete, a batch rename, Make table, Disassemble targets, Make string on several rows, Apply enum, and a batch display conversion. The dialog names the build, the count and the known references ("Delete 12 symbols on build-b · 31 references become unnamed").
- **Disassemble targets** (E11) is an admitted analysis job on one build (NA). It never runs from a row activation, and the dialog says it starts disassembly.
- Tags and names can be proposed to counterparts afterwards through PropagationTransfer, only along accepted identity edges. Equate names are offered only at anchor-aligned operands. Relocations, memory hits and address tables are program-local.
- One writer: with the build's lock held, actions stay listed with the reason, and Run is refused.
- Each affected row gets its OutcomeCell after the terminal result. Nothing is optimistic.

## States

| State | Shown as |
|---|---|
| Loading | earlier rows dimmed with "Loading results · build-b"; per-build progress in measured units ("3 of 7 blocks") or "Progress unknown · last event 14:02" |
| Empty | "No hits on build-a, build-b · build-d not searched", with the query and scope; never "not found anywhere" |
| Cut at limit | the truncation line; counts show "≥500" |
| Not loaded build | its column reads "not searched · Open build-d to include it"; nothing opens |
| Stale | "◷ build-b changed since read by job a3f9 · Refresh"; rows keep their values, marked stale |
| Changed since you looked | row words as in 70-copy |
| Filtered | "38 of 500 rows · 2 filters" with FilterChips |
| Read failed on one build | that column reads "✕ read failed 14:02 · Retry"; other builds stay |

## Linking

- **Publishes:**
  - Enter or click on a location goes to that build and address and pushes one stop.
  - Row focus with ↑/↓ moves the Listing cursor only for rows on the inspected build, with replaceState after the settle ("selection-to-listing"; this matches Ghidra's click-to-navigate without pushing history).
  - Rows on another build never change the build on focus; they need Enter, which is announced.
  - Filters are `f=` axes (replace while typing; push when applied from a link).
  - `wl=` when a worklist is collected and made active.
- **Follows:** nothing. A result set is a snapshot of its source. It marks the row containing the primary location ("contains cursor"). It can be kept as a card (`keep=results:‹id›@‹build›`, a proposed kind) and held with its pane.
- **Targets rendered:** address, symbol → the Code Browser at that build · logical id → Compare · counterpart with its edge word · type → TypeManager at that type (`type=`) · job → the dock Jobs record · receipt → its card · source query → the SearchWorkbench with the same fields (a Go).
- **Peek source:** Alt+↓ on a row peeks the cached Listing lines at its location, or the cached decompile line for decompiled-text hits. For a string, it peeks the full text and charset; for a relocation, the original and current bytes. Nothing is fetched.
- **Absent copy:** "absent" · "not searched" · "not indexed" · "no anchor" · "Stopped at 500 hits on build-a; more may exist" · "no longer resolves on build-b" (a row whose target vanished).
- **Target-size exception:** location and name links sit in 28px rows with one link per cell (44px below 700px and with a coarse pointer). Check cells and sort buttons are 24px or more.

## Keyboard

- An APG Grid with row focus and a checked set (Linked views, grid modifier precedence): ↑/↓ and j/k move; ←/→ move between cells; Home/End; Ctrl+Home/End; PageUp/PageDown. Space or `x` checks; Shift+↑/↓ and Shift+j/k extend; Ctrl/Cmd-click toggles; Shift-click extends. Enter goes; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the link menu; `.` rebinds the armed action to the focused row (`list.repeat`).
- In the header row, ←/→ move between sort buttons and Enter sorts. Proposed id `results.sortAdd`: Shift+Enter on a header adds the column as the next sort key. Header cells are not links, so the link meaning of Shift+Enter does not apply there.
- `w` collects into a worklist (`list.worklist`). `/` focuses the filter (`list.typeahead`), and ↓ from the filter returns to the grid.
- Proposed composite-scope ids (where "Results table"; not yet in `keymap.json`):
  - `results.makeSelection` (`s`);
  - `results.copy` (Ctrl/Cmd+C, the focused cell or the checked rows);
  - `results.columns` (no default key; palette and toolbar);
  - `results.export` (no default key);
  - `results.remove` (Delete; removes from this table only, never from the program).

## Accessibility

- `role="grid"` named by kind, source and scope ("Search memory hits, all builds, as of 14:02"). `aria-rowcount` is the total when it is known, and −1 when the table was cut at a limit.
- Sorted headers carry `aria-sort`. The sort order is in the header's name ("Location, sorted ascending, first key").
- Per-build cells use LocatorGlyph words. An unsearched build is the words "not searched", never an empty cell or a zero.
- Result counts are announced politely, debounced 300ms ("38 of 500 rows"). Truncation is announced once per run.
- Check cells are `role="checkbox"` named "Check ‹row›". The checked count is a visible chip ("3 checked").

## Parity rows covered

- **L24**: selection tables (ranges mode).
- **S05** and **S06**: the Symbol Table, with its columns, filters, rename, delete symbols or references, set primary, pin (as "keep at address on rebase"), make selection and temporary tables.
- **T17**: data types as a flat table with a program-types filter.
- **P05**: the relocation table. **P06**: the equates table with rename, remove, apply enum and convert display.
- **A01**: defined strings. **A02**: defined data. **A03**: translate as a row action. **A08**: the comment window.
- **F14**: the function tag window.
- **E11**: make address tables and disassemble their targets.
- **Q09**: the search results window: navigation, rename, make selection, remove items, and selection navigation through worklists.
- **I10**: sort (including multi-column), choose columns, column settings and filters, copy, CSV export, and filter strategies.
- The result side of **Q01–Q08**, **Q10** and **Q12**.

## Prior art

- Ghidra help:
  - `Framework/Docking/.../Tables/GhidraTableHeaders.html`: multi-column sort with order numbers, choose columns and discoverable columns, column settings, copy, and CSV export of selected rows;
  - `.../Trees/GhidraTreeFilter.html`: filter strategies and column filters;
  - `Search/Query_Results_Dialog.htm`: the navigation, marker margins, Make selection and Remove items, and the result limit;
  - `SymbolTablePlugin/symbol_table.htm` and `symbol_table_transient.htm`;
  - `Search/Search_for_Strings.htm`: defined-state column, Make string;
  - `Search/Search_for_AddressTables.htm`: Make table, Disassemble;
  - `EquatePlugin`, `RelocationTablePlugin`, `DataWindowPlugin`, `CommentWindowPlugin` and `FunctionTagPlugin`.
- Research: C3 (relocations by entity), D5 (honest client-side filters, no rounding up) and C9 (correlation tables) in `docs/research/2026-09-29-reference-re-ui-patterns.md`.
- Existing components: XrefPanel (per-build row groups), FilterChip, MarksList (worklists), ActionStrip, OutcomeCell, ConfirmDialog.
