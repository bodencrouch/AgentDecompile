# ListingFieldLayout

The per-viewer field formatter for the Listing: which fields each row kind shows, in what order and width, how operands, xref hints and comments are displayed, and what the flow-arrow and marker margins draw. It changes presentation only; no program data, and nothing is propagated.

**Use it** from the Listing pane header's **Fields** toggle (`aria-pressed`, constant name) or the palette ("Listing fields…"). It opens as a band above the Listing well and pushes the rows down; it never covers the cursor row. The same layout applies to every build and to both SplitCompare panes, so build-a beside build-c always line up column for column (spec pattern *viewer*). The static 8080 surface may open it as an anchored panel with the same words and controls.

**Consumer provides** the default format for each row kind; the viewer's diff against it from durable workspace state (never the URL or browser storage); the catalog's read actions for optional columns, taken from `GET /api/v1/actions` (no action id is named here); for each optional column whether that read exists on this server; and the rows of the loaded range with whatever each enabled optional read has already returned.

## Anatomy

1. **Header.** "Listing fields · per viewer · applies to every build", a count of changes from the default ("4 changes from default"), **Reset this row kind**, **Reset all** and **Close**.
2. **Row-kind tabs** (manual activation): Address break · Plate · Function · Variable · Instruction/Data · Open data · Custom (one tab per custom structure format). With **Follow cursor row kind** on, the tab follows the kind of the Listing's cursor row and the field under the cursor is marked with the reflection shape (`raised` fill, `reflect-bar`, the word "under cursor"). Following never moves the cursor.
3. **Format rows.** Each row kind has one or more format rows. Each row is a labelled sequence of **field controls**, in the order the Listing draws them, each sized by its width in characters. A field control is a button that carries its name and its state word:
   - **on**: drawn in the Listing;
   - **off**: keeps its space, draws nothing (Ghidra's Disable Field); the name is struck and the word "off" is visible. Off is never dashed, because dashed means hypothesis;
   - **added**: added in this viewer's diff (2px `ink-strong` frame and the word "added");
   - **needs a read**: an optional column whose catalog read has not run for the loaded range ("not read").
4. **Available fields.** Every field not in the current row kind, each with **Add**. Spacer fields take optional static text ("Set text…").
5. **Field settings.** The focused field's options, grouped as in Ghidra's options:
   - **Address**: pad to full width; prefix the block name.
   - **Bytes**: group size; reverse order; maximum bytes shown, then "+3 more" (the full bytes are in the row name and the HexStrip).
   - **Operands** (row L04): show block names; always show the primary reference (`=>` suffix); non-local and local namespace prefixes, with a local override prefix; markup of register and stack variable references, including inferred ones; follow read or indirect pointer references; offcut detail (`s_bar+4`); scalar-reference adjustment; word wrap and maximum lines; wrap on semicolons; abbreviated default string labels and their maximum length. **Reference underline** is *current row only* (the code-well default), *all rows* or *none*. It changes only the resting underline; every reference stays a typed link with the same accessible name.
   - **XREF field** (row L09): delimiter; local block prefix; non-local, local and library namespace prefixes; the ref-type letter (R W * c j T); group by function; maximum shown, then "N more" as a link to References; sort by address or by type. Every letter has its word in the row name: "c" is read "call".
   - **EOL comments**: which comment kinds show (EOL, repeatable, referenced repeatable, automatic); maximum lines; semicolon prefix.
   - **P-code**: raw varnodes; maximum lines.
   - **Source map**: file name only; show at every address; maximum entries; show the file identifier (digest).
   - **Offsets**: show the name prefix; hexadecimal or decimal.
6. **Margins** (rows L15, L16): the flow-arrow margin width (0 hides it), and which marker kinds the marker margin draws: program bookmarks by category, the viewer's marks, selection, highlights A–D, "changed by job", search hits of the active result set, and differences from an open comparison.
7. **Preview key.** One line under the band restates the margin glyphs in words.

**Optional columns** (rows L10, L11). Each names its source and never guesses:

| Column | Shows | Source | When it has nothing |
|---|---|---|---|
| Function offset | `ResourceRef::Resolve+0x6` | client, from the loaded function's entry | blank outside a function |
| Block offset | `.text+0x1a216` | client, from the build's memory blocks | — |
| Image-base offset | `imagebase+0x1b216` | client, from the build's image base | "other space" when the address is not in the image-base space |
| File offset | `build-a:0x1a616` | catalog read (address → file offset) | "not mapped" when the importer recorded no file bytes; "catalog action needed" when the server has no such read |
| P-code | one sub-row per p-code op | catalog read | "not read · Enter to read" |
| Stack depth | `-0x10` | catalog read | "unknown" (Ghidra's bogus value is never printed as a number) |
| Register transition | `eax := 0x0` | catalog read | blank where no value changes |
| Parallel | `‖` with the word "parallel" | the build's language | — |
| Source map | `resource.c:41` | recorded source map | "no source map for build-c" |

Reading an optional column is read-only and never analyzes. A following Listing never issues these reads on a cache miss. The column shows "not read · Enter to read" until the viewer asks, and then reads only the loaded range.

**Flow-arrow margin** (row L15). It is drawn from the build's recorded flow references.
- An unconditional jump uses heavy line glyphs (┏ ┃ ┗) and a conditional jump uses light ones (┌ │ └). Both are solid, because they are recorded flow.
- Only a computed target inferred by analysis (a switch-table guess) is drawn dashed (┆), and its row says "hypothesis · basis: jump-table inference".
- The arrow at the cursor is bold. A selected arrow (Enter on the margin cell) stays drawn while its ends scroll away, and its row says so.
- **Go to source** and **Go to target** are link-menu items and keys on the margin cell. Arrows are `aria-hidden`; every row restates them in words ("jump target from 0041b234, conditional").

**Marker margin** (row L16). It sits left of the flow margin.
- **Point markers** use one glyph each: ▪ program bookmark, a–z mark, • search hit, ✎ changed by job.
- **Area markers** are a 2px bar with a word: selection, highlight A–D, differs.
- Each marker is restated in the row's accessible name ("bookmark Analysis; search hit 3 of 40").
- The navigation margin for the whole view is the OverviewBar.

**Open and close functions** (row L31). With the Function row kind's **Collapsible body** option on, the function header row carries a 24px **Collapse** or **Expand** button and states the count ("48 rows collapsed"). Collapsing is view state only. Find, Highlight all and F8 still reach collapsed rows and expand them on arrival.

**Custom formats.** Ghidra can save a custom structure format into the program. Here a custom format is per-viewer only. "Save to program" is not offered, because it would be program data. The Custom tab says "Per viewer; not saved to the program".

## States

| State | Shown as |
|---|---|
| Default layout | "Default layout" in the header; Reset is disabled with "Already the default" |
| Changed | "4 changes from default"; each changed field carries its word (added, off, moved) |
| Optional column without a catalog read | the field control reads "catalog action needed", `aria-disabled` with that reason; it can stay in the layout and shows "unavailable" in rows |
| Optional column not read for this range | "not read · Enter to read" in the column; nothing is fetched on follow |
| Read failed | "✕ read failed · 14:02 · Retry" in the column header only; rows keep what was read |
| Stale | "◷ build-b changed since read by job a3f9 · Refresh" on the column header |
| Held pane | the band is read-only there and says "Layout is per viewer; change it in the primary Listing" |
| Reset | Reset this row kind or Reset all confirms in place ("Reset Instruction/Data to default? Your 4 changes are replaced.") and offers **Restore previous layout** once in the status line. This is per-viewer state, not a program transaction |

## Linking

- **Publishes:** nothing. The layout is per-viewer view state (PV) in durable workspace state, beside the keymap and View settings diffs. It is never in the URL and never propagated.
- **Follows:** the Listing's cursor row kind, only while **Follow cursor row kind** is on, to choose the tab and mark the field under the cursor. It never moves the cursor, fetches or analyzes. Not holdable; a held Listing shows the same layout read-only.
- **Targets rendered:** in the preview key and optional columns, the file offset is a copyable value, not a link. A source-map cell is a compiler-diagnostic-style link (`src.line`) to the SourceRepairDiff line, present only when a recorded source map names it. Arrow ends are address links carrying their build.
- **Peek source:** none in the band. In the Listing, Alt+↓ on an optional cell peeks the cached value's basis ("read 14:02 · catalog read · build-a").
- **Absent copy:** "catalog action needed" · "not read · Enter to read" · "not mapped" · "unknown" (stack depth) · "no source map for build-c" · "other space".
- **Target-size exception:** field controls, Add, Reset and Collapse are 24px or more (44px below 700px and with a coarse pointer). Marker and arrow glyphs in the margins are `aria-hidden` and are not targets. They are reached through row focus, the margin cell's link menu and the OverviewBar key (the 2.5.8 Equivalent exception).

## Keyboard

- The band is a region. Row-kind tabs are APG Tabs with manual activation. Each format row is an APG Toolbar with one tab stop; ←/→ move between field controls; Home/End go to the ends.
- Keymap ids (composite scope, the ListingFieldLayout format rows only; registered in `keymap.json`):
  - `fields.move`: Ctrl/Cmd+Shift+←/→ moves the focused field within its row, and Ctrl/Cmd+Shift+↑/↓ to the previous or next format row. It never uses Alt+←/→, which stay Back and Forward.
  - `fields.toggle`: Space switches the focused field between on and off.
  - `fields.remove`: Delete removes the focused field to Available fields, with "Removed Stack depth · Add to restore" in the status line.
  - `fields.settings`: Enter opens the focused field's settings.
  - `listing.fields`: toggles the band. It has no default key; use the pane-header button or the palette.
- Code-scope ids for the Listing (extensions this component configures; registered in `keymap.json`, checked against precedence, the leader, `browserReserved` and the ida profile):
  - `code.fold`: `z` collapses or expands the function at the cursor.
  - `code.arrowSource` and `code.arrowTarget`: `{` and `}` move the cursor to the source or target of the arrow at the cursor, pushing one history stop.
  - Both match the typed character.
- Dragging a field control is an optional pointer path. Every move is available through the keys above and each control's menu (Move left, Move right, Move to row…), so nothing requires dragging (WCAG 2.5.7).
- Esc follows the one order in `keymap.json` `escapeOrder`. Closing the band returns focus to the Fields toggle.

## Accessibility

- The band is `role="region"` named "Listing fields, per viewer". Each format row is `role="toolbar"` named "Instruction/Data row 1, 7 fields". Each field control's name carries its state: "Stack depth, off, keeps its space". Moves are announced once ("Operands moved before Mnemonic").
- The field under the cursor is `aria-current="true"` with the visible word "under cursor". The focused field for settings is `aria-selected="true"`.
- In the Listing, optional columns join the grid with their own `aria-colindex` and header names. The verbosity View setting decides whether they are read in the row name (default: off for offsets and p-code, reachable with →).
- Margin glyphs are `aria-hidden`; their words are in the row name. Conditional versus unconditional is a word and a line weight, never color. A hypothesis target is dashed and says "hypothesis".
- In forced colors, field controls use CanvasText borders, and the selected field and cursor row use Highlight and HighlightText.

## Parity rows covered

- **L10** (offset fields) and **L11** (p-code, stack depth, register transition, parallel and source map fields), as optional columns with named sources.
- **L12** (Browser Field Formatter: add, remove, move, enable, disable, insert and remove rows, spacer text, custom formats, reset and reset all). Custom formats are per viewer; "save to program" is deliberately not offered.
- **L31** (open and close functions), as the collapsible body option and `code.fold`.
- The display-option parts of **L02** (address), **L03** (bytes), **L04** (operand display options), **L08** (EOL options) and **L09** (XREF field options). The row kinds themselves remain Listing extensions.
- The margin parts of **L15** (flow-arrow margin: select an arrow, go to source and target, width 0 to disable) and **L16** (marker margin). The navigation margin is the OverviewBar.

**Ownership (decided):** ListingFieldLayout owns the Listing operand (L04), EOL (L08) and XREF field (L09) display options. OptionsPanel's Listing display and Cross-reference hints rows are links to this component's Field settings group and hold no values, so there is one store and one set of words (guideline 30, Listing, navigation and search tools).

## Prior art

- Ghidra help: `CodeBrowserPlugin/Browser_Field_Formatter.htm` (formats per row kind, field controllers, disable versus remove, spacer text, custom formats, the PCode quick toggle), `CodeBrowserPlugin/CodeBrowserOptions.htm` (operand, XREF, EOL, p-code, source map and offset field options) and `CodeBrowserPlugin/CodeBrowser.htm` (margin markers, flow arrows). Ghidra's green selected arrow and dashed conditional arrows are replaced, because color is semantics here and dashed means hypothesis.
- Research note C3 (`docs/research/2026-09-29-reference-re-ui-patterns.md`): objdiff's "(inferred)" suffix is the model for how optional derived columns name their basis.
- Existing components: Listing (the grid these fields feed), KeymapSettings (a per-viewer diff against a shared default, with reset), HexStrip (the bytes column's other home).
