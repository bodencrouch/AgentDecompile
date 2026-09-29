# Listing

The continuous instruction listing: flow, address, label, bytes, mnemonic, operands and xref hints, with one reflected cursor shared with the DecompileView, HexStrip and GraphPane.

**Use it** as the left half of CodeBrowser, and wherever instructions are read at one build and address: a held pane, SplitCompare panes, the Listing tab of the single-view layout below 700px. It is the landing view for every address link (35 typed links).

**Consumer provides** rows from existing analysis for the loaded section, with the current address; the decompile token ↔ instruction mapping when one exists; xref counts per label; the Edit items the catalog exposes for labels, operands and data (from `GET /api/v1/actions`); and any rows changed by a job since the last navigation.

- Sits in a `code-bg` well with `shadow-inset`, `type-code`. Addresses `address`, mnemonics `ink-strong`, bytes and xrefs `ink-muted`, symbol operands `lane-identity-ink`.
- **One header, not one per well.** Inside the Code Browser the composite header carries the function name with its NameProvenance tier word, the FactBadge strip as one Peek button and the inspected build; the well keeps only its view name and its follow or hold words ("Follows · as I move", "Follows · on Enter" or "Held · …"). Where the Listing is shown alone (a held pane, a SplitCompare pane), the pane header carries the same. The scroll well sets `scroll-padding` (`sticky-offset` plus the composite header) so the focused row is never hidden.
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
- **Absent copy:** "No decompiled line for 0041b21d" · "indirect · unresolved" for a computed target (a plain word, never a link) · "not indexed here" for xrefs · "Not loaded · Enter to load build-c"
- **Target-size exception:** operand, xref and job links sit in 18px code rows with one link per cell and use the code-well underline exception (underlined on the current, hovered or focused row only); rows are reached by row focus, Alt+↓ and the 44px row-menu button.

**Keyboard**

- A virtualized read-only APG Grid with one tab stop and roving focus on the row. ↑/↓ move by row, PageUp/PageDown by a page, Ctrl+Home/Ctrl+End to the first and last loaded row. → enters the row's cells and ←/→ move between them; inside Operands, ←/→ step token by token (the DecompileView rule); Home/End go to the first and last cell of the row.
- Enter on a row or operand with a target goes; Shift+Enter opens beside (a Held pane); Alt+↓ peeks inline; Shift+F10 or the Menu key opens the link menu.
- **F2** on a label row or label cell opens InlineRename under the row (`code.rename`). F2 on a function name or function header row opens InlineRename for the function, showing its identity and counterparts as in the Functions grid. F2 elsewhere says "F2 renames labels and function names here."
- Code-scope keys, focus-scoped and remappable (WCAG 2.1.4): `r` moves focus to the reflected row (Listing → Decompile; a hidden Decompile is shown in its slot and the switch is announced once); `h` toggles highlight-all on the focused register or constant; `x` focuses References; `]` / `[` step through References (35); Ctrl/Cmd+F finds in this well and announces "3 of 12 matches". Ctrl/Cmd+↓ and Ctrl/Cmd+↑ move to the next and previous function (`code.nextFunction`, `code.prevFunction`), stop at the end and say so. The `ida` profile adds `n`, `y` and `;`, which open the same editors under the row. The `ghidra` profile adds `l` (rename), `;` (comment editor), `t` (set data type), `d` (disassemble), `c` (clear code) and `f` (create function); each opens the same editors or arms the ActionStrip, and nothing posts from a key.
- Esc follows the one order in `keymap.json` `escapeOrder`.

**Accessibility**

- `role="grid"`, `aria-readonly="true"`, named "Listing, build-a, ‹function›". Columns, with `aria-colindex`: Address (the row header, `th`-like `rowheader`), Label, Bytes (omitted while the HexStrip is shown), Instruction, Operands, Xrefs/Comment. Cells that host InlineRename (labels, commentable cells) set `aria-readonly="false"`.
- `aria-rowcount="-1"` unless the program's row total is known. `aria-rowindex` counts from the start of the loaded section, and the address row header is the stable locator; the focused row stays mounted while virtualized.
- **The row name is the template**, read under the one per-viewer **Screen-reader verbosity** value in View settings (address full, last 4 or off; bytes off by default but reachable with →). Operand text is spoken exactly as the Listing renders it; a plain-words form, where one exists, goes in `aria-description` with an `aria-describedby` fallback.
- Labels are their own rows ("label ResourceRef::Resolve, 12 xrefs"). Flow glyphs are `aria-hidden` and restated as words ("jump target from 0041b230"). Reflection is silent on cursor moves and announced only on `r` ("Decompiled C, line 7, from 3 instructions" or "No mapping; focus stays").
- **Accessible View** (Alt+F2, or the palette, the Help menu and the pane-header button, because GNOME and KDE take Alt+F2) opens the exact text of the function or range as read, following the verbosity value, with the caret on the focused row.
- The highlight is a box plus a letter and the reflection is a bar plus words, so neither relies on color. In forced colors the reflection is a solid 1px CanvasText outline and the highlight a CanvasText box.

**Removes switching** (counts from the plan ledger):

- J10 relate an instruction row to its decompiled statement: 6 → 0 at ≥700px, 2 below (U173).
- J09 follow a cross-reference from code and return: 4 → 0 (U177; one region move and one Alt+← back, not view switches).
- J15 diagnose a decompile artifact: 6 → 4 (U173).

**Parity extensions (2026-09-29)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): L04, L06–L09, L13, L15, L21, L22, N03, N04)

- Operand, EOL and XREF display options are owned by ListingFieldLayout (OptionsPanel only links to it).
- Function header rows show signature source, call-fixup, purge, tags, repeatable comment and register values at entry.
- Variable rows are collapsible. Composite data and arrays expand inline, with a Field name column.
- There is one row kind per comment type: EOL, pre, post, plate and repeatable.
- The flow-arrow margin offers "Go to source" and "Go to target" from an arrow's link menu. It can be turned off per viewer.
- An address selection has next and previous selected range, and Esc collapses it (Esc order step 5). It stays separate from the checked set.
- Select by flow (forward, reverse, subroutine, function, dead code) sets the extent on one build.
- Next and previous instruction, data, undefined, label, function, non-function and bookmark are keymap ids with no default keys. Next and previous function are Ctrl/Cmd+↓ and Ctrl/Cmd+↑ in code scope.
- All of this is read-only and per build. Nothing re-disassembles.

**Parity extensions, round 3 (2026-09-29)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): L20, L25, L26, N03, A09, F01, F02, F10, S11)

Each block below follows the house order: what it is, anatomy and states, linking, keyboard, accessibility. Every write names one build and goes through a catalog action from `GET /api/v1/actions`; no action id is named here. Nothing below analyzes, decompiles or opens a program as a side effect.

*Program colors (L20).* Ghidra stores background colors in the program (Colorizing: Set Color, Clear Color, Clear All Colors, Next and Previous Color Range). Here a stored color is a fact about one build, shown read-only; it is never a row fill, because fills mean selection, reflection and raised.

- **Anatomy.** A row inside a stored color range carries an area marker in the marker margin: a 2px bar plus the word "color", and in the row name "program color #c8d8ff, build-a, range 0041b213–0041b21b". The first row of a range shows a 10px swatch drawn with the stored value, beside the hex text; the swatch is decoration and the hex text and the word carry it. ListingFieldLayout's marker margin has a **Program colors** toggle (per viewer, on by default).
- **How it differs from marks.** MarksList marks are per-viewer, lettered, carry notes, live in durable workspace state and are never program data. Program colors are program data on one build, read through the catalog's program-object read (property maps), carry no meaning the design system can name, and are saved and checked in with that build. A mark never becomes a color and a color never becomes a mark.
- **Per build.** Colors on build-a are not drawn on build-b, and no range is carried to another build by address. In SplitCompare each pane shows its own build's colors; a range present on one side only says "color on build-a only".
- **Setting a color** is a catalog write to one build: **Set color…** (the current address or the address selection, one build), **Clear color** and **Clear all colors on build-a…**. Set and Clear confirm in place in the ActionStrip, naming the build and the range; Clear all uses ConfirmDialog ("Clear all colors on build-a · 14 ranges"). They are listed `aria-disabled` with "Not available on this server yet. Stored colors still read. · What this server offers" when the catalog has none. Colors are never proposed to counterparts.
- **Navigation.** `code.nextColorRange` and `code.prevColorRange` (keymap ids, no default keys) push one history stop to the start of the next or previous range.
- **States.** Not read: "program colors not read · Enter to read" in the marker-margin key, and nothing is fetched on follow. No read on this server: "Not available on this server yet. The Listing still reads. · What this server offers". None stored: "no program colors on build-a". Stale: "◷ colors changed by job a3f9 · Refresh".

*Highlight from an address selection (L25).* A highlight is a lasting copy of an address selection: it survives clicks and cursor moves, where the address selection does not.

- **Actions** (Select menu, the link menu's Address selection group and the palette): **Highlight selection** (set), **Add selection to highlight**, **Subtract selection from highlight**, **Clear highlight**, **Select highlight** (turns the highlight back into an address selection) and **Next** and **Previous highlighted range**.
- **One pool of four letters.** A range highlight takes the next free letter A–D, shared with Highlight all (`h`), and draws as an area marker (2px bar plus its letter) in the marker margin and the OverviewBar hits lane. Its legend chip counts in words: "B · 3 ranges · 32 bytes · from address selection · build-a". Subtracting 0041b240–0041b245 leaves "2 ranges · 26 bytes".
- **Per build and per viewer.** A highlight belongs to one build, like an address selection. On another build its chip says "B is on build-a · not drawn here"; nothing is carried by address. It is client view state, never in the URL, never program data, and nothing is written. Esc never clears it (Esc collapses the address selection, step 5). Changing the program keeps it with its build.
- **Keyboard.** Keymap ids with no default keys: `highlight.fromSelection`, `highlight.add`, `highlight.subtract`, `highlight.clear`, `highlight.toSelection`, `code.nextHighlightRange` and `code.prevHighlightRange`. Each announces once: "Highlight B: 3 ranges, 32 bytes on build-a".

*Paste (L26).* Copy and Copy special are specified elsewhere (AccessibleView, ResultsTable Copy, the link menu's Copy group). Paste always targets one explicit build, previews first and never posts on a key alone.

- **What can be pasted**, by what the clipboard holds:
  - **A label, comment or address string** (a default copy of one field): into the focused label or comment only. It opens InlineRename or the comment editor prefilled on that build; it confirms in place.
  - **Labels and comments** (Copy special "Labels and comments" over a range): placed by offset from the paste point, on the same build only. The preview lists each item: offset, target address, item, what is there now and the result word (added · replaces a default label · skipped: a default label cannot be pasted · blocked: inside an instruction). More than one item uses ConfirmDialog. Across builds it is refused: "Labels and comments copied from build-a place by offset, and offsets do not carry across builds. Use Propose to build-b to carry names along identity edges."
  - **Bytes** (a byte string, spaces ignored): opens PatchEditor's Bytes mode prefilled at the paste point on the inspected build, with its original, current and after preview. Bytes paste only over undefined bytes; a range with code or data says "Clear first; 0045f204 is data" and offers PatchEditor Clear. Every byte write uses ConfirmDialog ("Write 12 bytes at 0045f200 on build-b"), and reads back after the terminal result. "Patched bytes are not recovery evidence." Bytes are never proposed to counterparts.
  - **Anything else** (formatted code, text the Listing did not produce): "The clipboard holds text that is not a Listing format. Paste it into a field instead." Nothing is armed.
- **Target.** The Paste preview's header names it: "Paste to build-a at 0041c880 · from build-a 0041b210" or "Paste 12 bytes to build-b at 0045f200 · copied on build-a". A clipboard from another project says so and pastes only strings.
- **Keyboard.** `code.paste` (Ctrl/Cmd+V, code scope, registered) arms Paste and opens its preview; it never posts. Reading the system clipboard may prompt the browser for permission; if refused, the preview says "Clipboard not readable · paste into the field with Ctrl/Cmd+V".

*Step by kind, matching bytes and Invert (N03).* The step commands of the first extension gain two things.

- **Next and Previous matching bytes** (`code.nextMatchingBytes`, `code.prevMatchingBytes`, no default keys): go to the next code unit whose bytes equal the cursor unit's bytes ("8b 45 08"), on this build.
- **Invert** (`code.stepInvert`, a toggle, `aria-pressed`, no default key) negates every step kind, as Ghidra does: instruction steps to the next data or undefined; data to the next instruction or undefined; undefined to the next instruction or data; label to the next unit without a label; function to the next instruction run outside any function; bookmark to the next address without the chosen bookmark category; matching bytes to the first unit whose first byte differs from the cursor unit's first byte ("First unit after 0041b300 whose first byte is not 00: 0041b320 · skipped 32 bytes of 00").
- **Anatomy.** The Listing header's **Step** control: a kind menu button (Instruction, Data, Undefined, Label, Function, Non-function, Matching bytes, Bookmark with a category), Previous and Next (24px), and the Invert toggle, whose state is also a word in the header ("Step · Matching bytes · inverted"). Shift on Previous or Next reverses the direction for one step, as a pointer shortcut only.
- **Linking and states.** A step is a Go on one build: one history stop, focus on the landing row. It never crosses builds and never analyzes. At the end: "No later code unit with bytes 8b 45 08 on build-a" (a step result, not absence: the same code on another build may encode differently). While the read runs past the loaded section: "Searching build-a · Esc cancels".

*Comment annotations (A09).* Comments may embed annotations. They render as typed links on the comment's own build, and are edited as raw text.

- **Syntax** (quotes recommended; the tag is required):

  | Annotation | Aliases | Parameters | Renders as |
  |---|---|---|---|
  | `{@symbol "Archive::OpenMember"}` | `@sym` | an address or a fully qualified symbol | a symbol link on this build (the symbol's current name) |
  | `{@address "0041b210" "entry"}` | `@addr` | an address, optional display text | an address link on this build |
  | `{@url "https://example.org/notes" "format notes"}` | `@hyperlink`, `@href`, `@link` | a URL, optional display text | an external link that says "opens outside" |
  | `{@program "build-c@00082f40"}` | none | a program path with an optional `@address` or `@symbol`, optional display text | a build link in this project, or the cross-project notice |
  | `{@variable "local_8" "ResourceRef::Resolve"}` | `@var` | a variable name, optional function | a variable link into DecompileView on this build |

- **Rendering.** Resolution reads cached symbols of the comment's build only. A symbol given by name resolves to its address on that build; the saved text keeps what the author wrote, and nothing is rewritten on display. A program link to a build that is not open lands on "Not loaded · Enter to load build-c". A link into another project shows the StateNotice with **Switch to corpus-beta** and **Stay**; it never switches silently. A `ghidra://` server URL is shown as text with "server link · opens nothing here". Any executing annotation is shown as text with "not run here".
- **Unresolved.** An annotation that names nothing on this build keeps its raw text and adds the word "unresolved" ("Archive::Close · unresolved"). A parse error shows the raw text and "annotation error: missing closing brace". Neither is linked to a guess.
- **Across builds.** An annotation resolves on its own build only. When a comment is proposed to a counterpart (PropagationTransfer, Comments), `@symbol` travels by name and `@address` is re-resolved through anchors; with no anchor it arrives as "unresolved".
- **Editing** happens in the comment editor (InlineRename comment mode). **Add annotation** (a menu button: Symbol, Address, URL, Program, Variable) wraps the selected text in the template. A rendered preview line under the field shows each annotation as it will read, "not checked yet" while the cached read is pending. The field itself stays raw text. Alt+↓ on a rendered comment peeks its raw text.
- **Accessibility.** A rendered annotation's name is "Symbol Archive::OpenMember, build-a, in comment"; an external link adds "opens outside AgentDecompile". The raw text is the `aria-description`.

*Function group (F01, F02, F10) and entry point (S11).* The link menu on an instruction row, a function header or an address selection gets a **Function** group, after Edit. Items are present only when the catalog exposes them, each naming its build.

- **Create function…** (F01): at the cursor, or at the minimum address of the address selection. The body is the address selection, or "follows flow from 0041c880 · computed by the action". A leading unconditional jump makes a thunk, and the preview says so. The name is the existing label or `FUN_0041c880`, editable with the repository's naming hint. It confirms in place in the ActionStrip. Parameters and locals the action creates are listed after the terminal result, never predicted.
- **Re-create function…** (F01): at an existing entry point. It rebuilds the body from flow, or from the address selection, and keeps parameters and stack references. The preview shows the old and new body ranges. Ghidra starts analysis afterwards; here nothing runs, and the confirm says "No analysis runs. New code stays unanalyzed until you admit analysis as a job."
- **Create multiple functions…** (F01): over an address selection on one build. Addresses already inside functions are skipped. It is a batch, so ConfirmDialog: "Create functions in 0041c880–0041c9ff on build-a · addresses already in functions are skipped · the count is known after the run." A predicted count is never shown.
- **Delete function…** (F02) always uses ConfirmDialog, listing its consequences from stored reads:
  - stack variables removed (6), and the references to them from instructions (9) become `Stack[offset]`;
  - register references from instructions in the body are removed;
  - the function-level facts (signature, tags, purge) go, and the plate comment stays if it was edited;
  - the label stays. The name tier changes: `FUN_0041c880` becomes the placeholder `SUB_0041c880` while call references remain; a user or debug name stays as a label with its tier;
  - references to the entry (4) remain, as references to a label;
  - identity edges, receipts and cached decompiles that name this function on build-a are listed and become stale (◷). They are not deleted, and the build-a endpoint reads "no function" until the function is re-created.

  The primary button is **Delete function**. The dialog ends "Undo applies to build-a only" or "cannot be undone here", as the catalog reports. Delete is never proposed to counterparts.
- **Set stack depth change…** (F10) on an instruction: one field, decimal or hex (`-0x1a`), prefilled with the current change, or with the instruction's default and the word "default". On a call it asks where the value goes: **Local** (a stack depth change at 0041b216, confirm in place) or **Global** (the purge of `String::CStr`, which opens SignatureEditor's purge field; a callee-signature edit, so ConfirmDialog there). **Remove stack depth change** appears on the "StackDepth = StackDepth + …" row, a row kind this extension adds. Purge itself is SignatureEditor's (F10).
- **Set as external entry point** and **Remove external entry point** (S11) on a label row. An entry point needs a symbol at the address; otherwise the item is `aria-disabled` with "Add a label first; entry points need a symbol". Set confirms in place and names the build; removing one the importer recorded uses ConfirmDialog ("Recorded by the importer from the export table on build-a"). SymbolTree has the same items.
- **Multi-build.** Every item acts on one build. Create function may afterwards be proposed to counterparts only at accepted anchors (PropagationTransfer, Functions). Delete, stack depth changes and entry points are program-local and never proposed: stack depth is code generation, which differs between builds.
- **Keyboard.** Keymap ids with no default keys: `code.createFunction`, `code.recreateFunction`, `code.createFunctions`, `code.deleteFunction`, `code.stackDepth` and `code.entryPoint`. They open or arm; the ActionStrip's Run or the dialog's primary button posts.
- **One writer.** With build-a's lock owned elsewhere, the items stay listed with "build-a has a writer: another session (agent) · your edit waits for it".

## Behavior

- "Nothing is inferred from line order or the nearest address." (formerly the `≠ nearest` chip on the no-line note)
- "Shift reverses one step · stays on build-a · never analyzes" (formerly the Shift reverse tip)
- "Global opens SignatureEditor's purge and confirms there, because it changes every caller." (formerly the all-callers tip)
- "Local is program-local and never proposed." (formerly the `≠ proposed` chip)
