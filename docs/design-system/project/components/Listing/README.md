# Listing

The continuous instruction listing: flow, address, label, bytes, mnemonic, operands and xref hints, with one reflected cursor shared with the DecompileView, HexStrip and GraphPane.

**Use it** as the left half of CodeBrowser, and wherever instructions are read at one build and address: a held pane, SplitCompare panes, the Listing tab of the single-view layout below 700px. It is the landing view for every address link (35 typed links).

**Consumer provides** rows from existing analysis for the loaded section, with the current address; the decompile token ↔ instruction mapping when one exists; xref counts per label; the Edit items the catalog exposes for labels, operands and data (from `GET /api/v1/actions`); and any rows changed by a job since the last navigation.

- Sits in a `code-bg` well with `shadow-inset`, `type-code`. Addresses `address`, mnemonics `ink-strong`, bytes and xrefs `ink-muted`, symbol operands `lane-identity-ink`.
- **One header, not one per well.** Inside the Code Browser the composite header carries the function name with its NameProvenance tier word, the FactBadge strip as one Peek button and the inspected build; the well keeps only its view name and its Following or Held word ("Listing · Follows · as I move"). Where the Listing is shown alone (a held pane, a SplitCompare pane), the pane header carries the same. The scroll well sets `scroll-padding` (`sticky-offset` plus the composite header) so the focused row is never hidden.
- **Cursor and reflection** follow 35 Reflection and keep the existing shape. The cursor row in the focused Listing uses the selection shape (`selection` fill plus the 3px `accent` bar). When another view drives, the Listing marks the mapped set of rows with the `raised` fill, a 3px `ink-muted` bar (`reflect-bar`), the words "↔ line 7" on the first reflected row and `▸` at the exact cursor address. Focus, cursor and reflection each look different (outline; fill plus accent bar; raised plus muted bar and words), never color alone.
- **Missing mappings are answers.** A row with no decompiled line says "No decompiled line for 0041b21d"; a statement with no rows says "No address mapping for line 9" in the DecompileView. The other view keeps its cursor and draws no mark. Nothing jumps to the function start and nothing is inferred from line order or the nearest address.
- **Highlight all** (`h`) on a register, variable or constant boxes every occurrence in each visible view of the same build with a 1px `ink-strong` box (`highlight-box`) and its letter A–D (`highlight-badge`), never an underline; the legend chip in the gutter bar counts in words ("A eax · 3 in this function · text match") and removes it (35).
- **XREF[n] hints are links** to References at that build and address, Line scope, incoming (35 typed links: it does not move the primary location; if the row is not the cursor, the cursor moves with replaceState; focus lands on the References grid). Call and jump targets and symbol operands are address links. Rows changed by a job carry a "changed by job a3f9" gutter mark (a job link) until the next navigation, drawn only from stored or cached reads.
- **Link menu** (35): one flat APG Menu with separated groups. Open · Open beside · Peek (plus Show reflected row, Highlight all and Find references); **Edit**, only on labels, operands and data and only for items the catalog exposes, such as Rename label…, Set data type… and Comment… (an item that does not apply stays listed, `aria-disabled`, with its reason, for example "0041b210 is code; data types apply to data."); **Reveal in**, only the destinations an address resolves to (Compare, Evidence, Navigator); Copy link · Copy address. Nothing posts from the menu. Rename label… and Comment… open InlineRename under the row; they confirm in place.
- **Coarse pointer.** Each row exposes one 44px row-menu button carrying the same menu (24px with a fine pointer where it is shown, 44px below 700px); inline links fall back to Go. There is no long-press.
- Bytes and processor context stay visible: the listing is interpreted evidence, not ground truth. While the HexStrip is shown, the Bytes column is omitted and the bytes live in the strip.
- **Restore reads now.** On a history restore or landing, the Listing renders from stored evidence as a cached pane. Opening a listing never reanalyzes; an empty listing is a StateNotice with at most one catalog action armed (reuse first), never permission to analyze again.
- Both surfaces render the same rows, marks and menu groups from the same reads and catalog. The static 8080 surface may render a table with the same row names and open the editors as anchored dialogs with identical words.

**Linking**

- **Publishes:** `addr` as the cursor moves inside one function (replaceState after the settle); Go on an operand, flow target or symbol pushes one history stop with `build` and `addr`; Open beside publishes `hold=addr:0041c460@build-a` for a new Held pane.
- **Follows:** `entity`, `build`, `addr` and `views`, after the settle, as a cached pane (follows as you move; commit on Enter under Update panes: On Enter); reflection follows the other code views' cursor. Holdable with Hold this pane: it freezes to entity × build × address with its own Back and Forward.
- **Targets rendered:** call or jump target and symbol operand → the Code Browser at that build and address (focus on the Listing row) · XREF[n] → References at that build and address, Line scope, incoming (`f=xref.dir:in`) · "changed by job a3f9" → the dock Jobs record · a data operand → the Listing at that data address. Link names read "Address 0041c460, build-a, String::CStr" and "12 references to ResourceRef::Resolve, build-a, incoming".
- **Peek source:** Alt+↓ on an operand opens the inline peek under the row from the cached listing of the target; nothing is decompiled.
- **Absent copy:** "No decompiled line for 0041b21d" · "indirect · unresolved" for a computed target (a plain word, never a link) · "not indexed here" for xrefs · "Not loaded. Open build-c to read it."
- **Target-size exception:** operand, xref and job links sit in 18px code rows with one link per cell and use the code-well underline exception (underlined on the current, hovered or focused row only); rows are reached by row focus, Alt+↓ and the 44px row-menu button.

**Keyboard**

- A virtualized read-only APG Grid with one tab stop and roving focus on the row. ↑/↓ move by row, PageUp/PageDown by a page, Ctrl+Home/Ctrl+End to the first and last loaded row. → enters the row's cells and ←/→ move between them; inside Operands, ←/→ step token by token (the DecompileView rule); Home/End go to the first and last cell of the row.
- Enter on a row or operand with a target goes; Shift+Enter opens beside (a Held pane); Alt+↓ peeks inline; Shift+F10 or the Menu key opens the link menu.
- **F2** on a label row or label cell opens InlineRename under the row (`code.rename`); F2 elsewhere says "F2 renames labels here. Use Rename… in the menu for functions."
- Code-scope keys, focus-scoped and remappable (WCAG 2.1.4): `r` moves focus to the reflected row (Listing → Decompile; a hidden Decompile is shown in its slot and the switch is announced once); `h` toggles highlight-all on the focused register or constant; `x` focuses References; `]` / `[` step through References (35); Ctrl/Cmd+F finds in this well and announces "3 of 12 matches". The `ida` profile adds `n`, `y` and `;`, which open the same editors under the row.
- Esc follows the one order in `keymap.json` `escapeOrder`.

**Accessibility**

- `role="grid"`, `aria-readonly="true"`, named "Listing, build-a, ‹function›". Columns, with `aria-colindex`: Address (the row header, `th`-like `rowheader`), Label, Bytes (omitted while the HexStrip is shown), Instruction, Operands, Xrefs/Comment. Cells that host InlineRename (labels, commentable cells) set `aria-readonly="false"`.
- `aria-rowcount="-1"` unless the program's row total is known. `aria-rowindex` counts from the start of the loaded section, and the address row header is the stable locator; the focused row stays mounted while virtualized.
- **The row name is the template**, read under the one per-viewer **Screen-reader verbosity** value in View settings (address full, last 4 or off; bytes off by default but reachable with →). Operand text is spoken exactly as the Listing renders it; a plain-words form, where one exists, goes in `aria-description` with an `aria-describedby` fallback.
- Labels are their own rows ("label ResourceRef::Resolve, 12 xrefs"). Flow glyphs are `aria-hidden` and restated as words ("jump target from 0041b230"). Reflection is silent on cursor moves and announced only on `r` ("Decompiled C, line 7, from 3 instructions" or "No mapping; focus stays").
- **Accessible View** (Alt+F2, or the palette, the Help menu and the pane-header button, because GNOME and KDE take Alt+F2) opens the exact text of the function or range as read, following the verbosity value, with the caret on the focused row.
- The highlight is a box plus a letter and the reflection is a bar plus words, so neither relies on color. In forced colors the reflection is a dashed CanvasText outline and the highlight a CanvasText box.

**Removes switching** (counts from the plan ledger):

- J10 relate an instruction row to its decompiled statement: 6 → 0 at ≥700px, 2 below (U173).
- J09 follow a cross-reference from code and return: 4 → 0 (U177; one region move and one Alt+← back, not view switches).
- J15 diagnose a decompile artifact: 6 → 4 (U173).

**Parity extensions (2026-09-29)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): L04, L06–L09, L13, L15, L21, L22, N03, N04)

- Operand and EOL display options are read from OptionsPanel's Listing display section.
- Function header rows show signature source, call-fixup, purge, tags, repeatable comment and register values at entry.
- Variable rows are collapsible. Composite data and arrays expand inline, with a Field name column.
- There is one row kind per comment type: EOL, pre, post, plate and repeatable.
- The flow-arrow margin offers "Go to source" and "Go to target" from an arrow's link menu. It can be turned off per viewer.
- Address-set selection has next and previous selected range, and Esc collapses it (Esc order step 5). It stays separate from the checked set.
- Select by flow (forward, reverse, subroutine, function, dead code) sets the extent on one build.
- Next and previous instruction, data, undefined, label, function, non-function and bookmark are keymap ids with no default keys. Next and previous function keep their keys.
- All of this is read-only and per build. Nothing re-disassembles.
