# ResultsTable

The one generic results table behind every Ghidra-style list: search hits, references, symbols, defined strings and data, comments, equates, relocations, function tags, types, address tables and selection ranges. Every instance has sortable, filterable and choosable columns, selection-to-listing, Make address selection, Collect into worklist, CSV export, a checked set for the ActionStrip, and per-build hit columns when its scope is all builds.

**Use it** wherever a feature produces rows keyed to addresses or entities: under SearchWorkbench; as the navigator's Strings, Symbols and Imports scopes in table form; as the corpus "Show all" view for equates, relocations, tags, types and defined data; and as a temporary table made from a selection. It never replaces the one Functions grid or the XrefPanel. References that open "as a table" (All builds with many rows) render in this component with the XrefPanel's words.

**Consumer provides**
- The result set: kind, source (the query or read that produced it, with its fields), scope (one build, or all builds with the list), snapshot time, and the basis per build (generation or digest).
- For each build: the row count, whether the result was cut at a limit, and whether the build was searched, not loaded or unsupported.
- The column set for the kind (defaults plus discoverable extra columns), per-column settings where they exist, and the join rule for logical rows.
- The catalog actions that can act on a checked set of this kind, from `GET /api/v1/actions` (no action id is named here).
- The viewer's saved column set, sort and filter strategy per kind, from durable workspace state.

## Anatomy

1. **Header.** Kind and title ("Search memory · hex `8b 46 04 ?? 85 c0`"), the scope words ("All builds · build-a, build-b, build-c · build-d not loaded"), the snapshot ("as of 14:02"), per-build counts, a **Refresh** that re-runs the same read (Refresh never widens the scope), and **Rename table…**, which sets this table's title for the viewer (Ghidra's Renaming Windows; per viewer, never program data).
2. **Truncation line**, only when a limit was hit: "Stopped at 500 hits on build-a; more may exist. Raise the limit in the search's fields and run again." A count is never rounded or projected. An unsearched build reads "build-d not loaded · not searched", never "0".
3. **Toolbar** (APG Toolbar):
   - **Filter** field with strategy (contains, starts with, exact, glob, regular expression), multi-term (all or any), case sensitive, invert, and "match on" (visible columns, or the chosen column);
   - **Navigate on focus** (`aria-pressed`, on by default): Ghidra's Selection Navigation and single-click navigation. Off, row focus moves nothing and only Enter goes;
   - **Column filters** as FilterChips carried as the registered `f=` axes `results.build`, `results.kind`, `results.defined`, `results.refs` and `results.source`, for example "Build is build-c ×" (`f=results.build:build-c`), "Kind is call ×" (`f=results.kind:call`), "Defined is not defined ×" (`f=results.defined:not-defined`), "Refs ≥ 3 ×" (`f=results.refs:≥3`), "Source is user ×" (`f=results.source:user`);
   - **Columns…** (choose, reorder, reset; Fit to content and Default width per column, so nothing needs dragging);
   - **Copy** (the focused cell, the row, or the checked rows; columns chosen);
   - **Export CSV…** (the chosen columns in displayed order, for the checked rows or for all loaded rows; the dialog states "exports the 500 loaded rows; the table was cut at the limit");
   - **Make address selection** (below);
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
| Search hits (memory, text, instruction, scalar, decompiled text) | Location, Match bytes or text, Match value, Label, Code unit, Function | Make address selection, Collect, Make string or data where offered |
| Symbols (S05) | Name, Location, Type, Namespace, Source, Refs, Offcut refs | Rename…, Delete…, Set primary…, Stay at this address on rebase… (Ghidra "pin symbol"), Delete references… |
| Defined strings (A01) | Location, String, Type, Length, Charset, Referencing functions | Translate… (A03), Settings… (charset and rendering of the string data; catalog, ConfirmDialog for more than one row), Make address selection |
| Found strings (Q06) | Defined state, Location, Label, Preview, String, Type, Length, Is word | Make string…, Make char array… (offset, auto label) |
| Defined data (A02) | Location, Data type, Value, Label, Size | Make address selection; a type filter chip |
| Comments (A08) | Location, Kind (EOL, pre, post, plate, repeatable), Text, Function | Comment… (InlineRename comment mode, one target) |
| Equates (P06) | Name, Value, Refs, Enum-backed, Display | Rename…, Remove…, Apply enum…, Show enum (TypeManager at that enum), Edit enum… (TypeEditor enum mode), Convert display… (signed or unsigned decimal, hex, octal, char, binary, float, double) |
| Relocations (P05) | Address, Type, Values, Original bytes, Symbol | none; read-only, feeds ObjectDiff's relocation-aware equality |
| Function tags (F14) | Tag, Comment, Use count per build | Create…, Edit…, Delete…, Add to checked functions…, Remove from checked functions…, Load tags… |
| Types (T17) | Name, Category, Size, Kind, Uses per build | open in TypeManager (Go); program types only filter |
| Address tables (Q08, E11) | Location, Label, Length, Data (hex and ASCII) | Make table… (offset, auto label), Disassemble targets… |
| Ranges (L24) | Start, End, Length, Block | Make address selection; ranges come from an address selection |
| Direct references (Q07) | From, Label, From preview, To, To preview | Make address selection; Create reference… through ReferenceEditor |

**Temporary tables.** Tables made from a query or a selection are snapshots. They say "as of 14:02", keep their source link, and never merge in new rows silently. Refresh re-reads. If the basis moved, rows are marked "changed since you looked", "new since you looked" or "left this page since you looked", as in the Copy rules.

## Make address selection, worklists and removal

- **Make address selection** sets the Listing's address selection on one build from the checked rows, or from all rows. With all builds in scope, it asks "Make address selection on build-a (inspected)" or "on build-c" and names the rows that will not be included ("9 rows on other builds are not included; an address selection belongs to one build"). It is client state and never in the URL. Changing the program clears it (F11).
- **Collect into worklist** (`w`) snapshots the rows in their current order, across builds if they span builds, through the MarksList dialog: "It changes nothing in the project and starts no work." F8 then steps them.
- **Remove from table** removes rows from this view only. The row is struck until the next refresh, and the status line says "Removed 3 rows from this table; nothing in the program changed".

## Mutations

- A checked set arms one catalog action in the ActionStrip, bound to that set on one build. Rows from other builds are unchecked first, and the strip says so.
- A single row with an inline editor (Rename…, Comment…) confirms in place.
- Batch, destructive or cross-build actions use ConfirmDialog. This covers delete, a batch rename, Make table, Disassemble targets, Make string on several rows, Apply enum, and a batch display conversion. The dialog names the build, the count and the known references ("Delete 12 symbols on build-b · 31 references become unnamed").
- **Disassemble targets** (E11) is an admitted analysis job on one build (NA). It never runs from a row activation, and the dialog says it starts disassembly.
- Tags and names can be proposed to counterparts afterwards through PropagationTransfer, only along accepted identity edges. Equate names are offered only at anchor-aligned operands. Relocations, memory hits and address tables are program-local.
- One writer: with the build's lock owned elsewhere, actions stay listed with the reason, and Run is refused.
- Each affected row gets its OutcomeCell after the terminal result. Nothing is optimistic.

## Translate strings and charsets (A03)

Ghidra decorates a string with a translated value from a translation service, shown in »chevrons« in place of the original, and lets the charset of string data be chosen. Here a translation is a hypothesis about a string's meaning, with its service named as the basis. It never replaces bytes, the decoded string or a name, and it is never evidence for identity or recovery.

- **Where.** The Defined strings kind: **Translate…**, **Clear translations…** and **Show translations** (a per-viewer toggle, `aria-pressed`) in the ActionStrip arming menu and the row menu; the Listing link menu on string data offers the same items. The checked set must be on one build; rows on other builds are unchecked first, and the strip says so.
- **Service choice.** The Translate… form lists the services the catalog's translate job accepts, each by its generic kind and host ("Manual", "self-hosted translation server · translate.lab.internal:5000"); none is hardcoded. **Manual** is always offered: one string, a value typed by you, confirmed in place.
- **Settings**, per service, stored per viewer in durable workspace state beside the other request options:
  - server URL; API key (a credential: entered once, stored by the server's secret store, shown as "set" or "not set", never in the URL, the page or an export);
  - source language: **auto-detect** or **ask each time**; target language (default `en`);
  - batch size (strings per request); timeout, plus extra time per string.
- **Network approval.** A service outside this machine is a network dependency. Run opens ConfirmDialog every time: "Send 12 strings from build-b to translate.lab.internal? Their text leaves this machine." The primary button is **Send 12 strings**. Nothing is sent from a preview.
- **One build, one job.** Translate runs the catalog job for the checked strings on one build and writes each translation as a string setting on that build (mutating; one writer; it never touches bytes). It is not offered while the build's lock is owned elsewhere. Clear translations on more than one row uses ConfirmDialog.
- **How a translation shows.**
  - In the String column, the original decoded text always stays visible. The translation sits under it: »resource not found« with a 1px dashed frame and the words "translation · hypothesis · basis: self-hosted server, auto → en, 14:02".
  - A manual translation says "basis: manual, by you".
  - **Show translations** off hides the line for this viewer only; stored translations are unchanged.
  - Alt+↓ peeks the bytes, the charset, the decoded text and the translation with its basis, side by side.
- **Stale.** When a string's bytes or charset change after it was translated, the translation reads "◷ string changed since translated · Translate again". It is never re-sent on its own.
- **Across builds.** A translation belongs to the string on one build. Rows joined by content ("joined by content ≠ same entity") show each build's own translation state; translating build-b's row does not translate build-c's. A new column, **Translation**, reads "none", "hypothesis" or "stale" per build, and filters by `f=results.translation:` (registered).
- **Charsets.** **Settings…** on string rows opens the charset picker:
  - a table of the charsets the build's server offers: Name (non-registry names start `x-`), Description, Fixed length, Min and max bytes per character, and Scripts; the details show the aligned size (UTF-16 and UTF-32 only) and sample characters;
  - a **preview** column for the checked rows, decoded client-side from bytes already read: "decodes as ‹text› · 2 bytes not decodable (shown as the Unicode replacement character, U+FFFD)". Previewing writes nothing and fetches nothing new;
  - **Apply charset on build-b** is the catalog's data-settings write: in place for one row, ConfirmDialog for more ("Set charset UTF-16LE on 4 strings on build-b · their translations become stale").
  Charset changes and translations are never proposed to counterparts.
- **States.** No service in the catalog: "Not available on this server yet. Manual translations still work. · What this server offers" (the last part links to Help › What this server offers). Service unreachable: "✕ translate.lab.internal did not respond in 30 s · nothing was changed · Retry". Partial batch: "9 of 12 translated · 3 failed, listed". Pending and terminal OutcomeCell words per row.
- **Keyboard.** `results.translate` (no default key) opens Translate… for the checked rows. In the form, Tab order is service, settings, strings preview, Cancel, Run.
- **Accessibility.** The translation line's name is "Translation, hypothesis, basis self-hosted server, auto to English: resource not found"; the dashed frame is the second cue after the word. Chevrons are `aria-hidden`.

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
- **Follows:** nothing. A result set is a snapshot of its source. It marks the row containing the primary location ("contains cursor"). It can be kept as a card (`keep=results:‹id›@‹build›`, the registered kind `results`) and held with its pane.
- **Targets rendered:** address, symbol → the Code Browser at that build · logical id → Compare · counterpart with its edge word · type → TypeManager at that type (`type=`) · job → the dock Jobs record · receipt → its card · source query → the SearchWorkbench with the same fields (a Go).
- **Peek source:** Alt+↓ on a row peeks the cached Listing lines at its location, or the cached decompile line for decompiled-text hits. For a string, it peeks the full text and charset; for a relocation, the original and current bytes. Nothing is fetched.
- **Absent copy:** "absent" · "not searched" · "not indexed" · "no anchor" · "Stopped at 500 hits on build-a; more may exist" · "no longer resolves on build-b" (a row whose target vanished).
- **Target-size exception:** location and name links sit in 28px rows with one link per cell (44px below 700px and with a coarse pointer). Check cells and sort buttons are 24px or more.

## Keyboard

- An APG Grid with row focus and a checked set (Linked views, grid modifier precedence): ↑/↓ and j/k move; ←/→ move between cells; Home/End; Ctrl+Home/End; PageUp/PageDown. Space or `x` checks; Shift+↑/↓ and Shift+j/k extend; Ctrl/Cmd-click toggles; Shift-click extends. Enter goes; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the link menu; `.` rebinds the armed action to the focused row (`list.repeat`).
- In the header row, ←/→ move between sort buttons and Enter sorts. Registered id `results.sortAdd`: Shift+Enter on a header adds the column as the next sort key. Header cells are not links, so the link meaning of Shift+Enter does not apply there.
- `w` collects into a worklist (`list.worklist`). `/` focuses the filter (`list.typeahead`), and ↓ from the filter returns to the grid.
- Composite-scope ids (the ResultsTable grid only; registered in `keymap.json`):
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
- **S05** and **S06**: the Symbol Table, with its columns, filters, rename, delete symbols or references, set primary, pin (as "Stay at this address on rebase"), make selection (as "Make address selection") and temporary tables.
- **T17**: data types as a flat table with a program-types filter.
- **P05**: the relocation table. **P06**: the equates table with rename, remove, apply enum and convert display.
- **A01**: defined strings, with refresh and settings. **A02**: defined data. **A03**: translate strings with service choice, service settings, network approval, manual translation, clear and show, and charset handling, with every translation a hypothesis naming its service. **A08**: the comment window.
- **F14**: the function tag window.
- **E11**: make address tables and disassemble their targets.
- **Q09**: the search results window: navigation (Navigate on focus), renaming the window (Rename table…), make selection, remove items, and stepping through worklists. Its marker-margin part is the OverviewBar hits lane and the Listing marker margin.
- **I10**: sort (including multi-column), choose columns, column settings and filters, copy, CSV export, select all (the check-all cell), and filter strategies with case sensitivity and invert.
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
