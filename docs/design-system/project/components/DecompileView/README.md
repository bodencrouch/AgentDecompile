# DecompileView

Decompiled C in a code well that shares one cursor with the Listing: the selected statement and the listing rows that produced it are both marked, every token is a typed link, and a local opens an in-place editor instead of going anywhere.

**Use it** as the right half of CodeBrowser, beside the Listing, and on its own wherever only C is wanted: a held pane, a target opened beside (Open beside creates a Held pane), the single-view layout below 700px. There is one decompile surface; it never becomes a separate page.

**Consumer provides** the concrete build, function address and logical id; the decompiled lines from the decompile cache with their provenance (reused or fresh, generation, read time, and any later job that changed the function's or a callee's signature, storage or types); each line's address mapping (the instructions that produced it, or none); each token's kind and target (callee → function address, global and string literal → data address, field → type and offset, type → type, local and parameter → variable with type, storage and name tier); the Edit items the catalog exposes for each token kind, read from `GET /api/v1/actions`; the shared cursor (address, plus the token when the decompile drives); and the follow state (following, loading, not decompiled, held, not loaded).

- Well: `code-bg` with `shadow-inset`, `type-code`. The gutter holds the line number in `ink-muted`, then the first mapped address in `address` with the instruction count ("0041b217 ·3"). An unmapped line leaves the address gutter blank; when the cursor is on it the gutter says "○ none".
- **One cursor, reflected** (35 Reflection; this well keeps the existing shape). The focused pane shows the cursor with the selection shape: `selection` fill plus the 3px `accent` bar. The other views show the reflection: every corresponding row or line on `raised` with a 3px `ink-muted` bar (`reflect-bar`), the words "↔ line 7" on the first reflected listing row, and `▸` at the exact cursor address. When the Listing or HexStrip drives, the tokens produced by the cursor instruction carry a 2px `ink-strong` under-bar. Reflection is never color alone.
- **Highlight all** (`h`) boxes every occurrence of the focused register, variable or constant with a 1px `ink-strong` box (`highlight-box`) and its letter A–D (`highlight-badge`), never an underline; the legend chip in the gutter counts in words ("A local_8 · 3 in this function · variable") and removes it (35). **Pointer brushing**, when "Brush on hover" is on in View settings, is a 1px dotted `brush-outline` with no bar.
- **No mapping is an answer.** Declarations, braces and lines the decompiler synthesized can have no address. Selecting one shows `fact-unknown` ○ "No address mapping for line N" with the reason (for a declaration, its storage), leaves the Listing unmarked and keeps the Listing cursor where it was. A mapping is never inferred from line order or the nearest address.
- **Typed tokens.** callee → function (Code Browser at that address); global and string literal → data address; field → the type at that offset; type → the type; local and parameter → the variable. The kind is written in words in the status line, the token's accessible name, the menu header and the legend, never only in color. Only symbols take a hue: callees and globals use `lane-identity-ink`, as symbol operands do in the Listing. Keywords and type names are `ink-strong`, casts `ink-muted`, everything else `ink`.
- Navigable tokens are `.ad-link`. **Documented exception to the link rule (approved):** inside code wells the dotted underline shows only on the current, hovered and focused line, and the focused token is solid-underlined. Dense code stays readable, and the line under the cursor or pointer always shows which tokens act, so affordance still never depends on color.
- **A local is not an address.** A local or parameter is a `button` with `aria-haspopup="dialog"` and a solid underline on the current line (dashed is reserved for unproven values). Activating it opens InlineRename bound to (program, build, function address, local storage), under the line, pushing the following lines down. It never goes to, opens beside or copies an address.
- **The token menu is the one link menu** (35): a flat APG Menu with separated groups and no cascading submenu. Group 1 is Open · Open beside · Peek (Keep appears only inside a Peek or card). Group 2, **Edit**, lists only items the catalog exposes in `GET /api/v1/actions`, by token kind:
  - local: Rename…, Retype…, Comment…;
  - parameter: Rename…, Retype…, Edit signature…, Edit storage…;
  - field: Peek type, Retype field…;
  - callee: Edit callee signature…, which names the callee and the build.
  Every token also has Peek type, Highlight uses (`h`), Show reflected row (`r`), Find references and Trace data flow… (it arms the ActionStrip and never runs). Group 3, **Reveal in**, lists only the destinations the token's type resolves to (for a callee: Compare, Evidence, Navigator). Group 4 is Copy link · Copy ‹typed value› ("Copy address 0041d0a0", "Copy name local_8"). An item that does not apply stays listed, `aria-disabled`, with its reason: "A local is not a place to open."; "Locals have storage, not an address: stack [ebp − 0x4]." Nothing posts from the menu; an item opens its inline editor or arms the ActionStrip. Item labels come from the catalog; the design system hardcodes no action ids.
- **Confirm tiers** (35 Confirming edits). Rename, retype and comment of a local, parameter or label confirm in place in InlineRename; Enter or Save posts the catalog action once. A struct-field retype, any structure-layout change that resizes, overwrites or clears components, and a callee-signature edit go through ConfirmDialog, because they change every use on the build: the dialog names the type or callee, the build and the known use or caller count, or "uses not indexed". Edit storage… opens StorageEditor under the signature line.
- The status line under the well names the token under the caret, its kind and target, and the mapping of the cursor line: "Callee Archive::OpenMember → function 0041d0a0 · line 7 ← 4 instructions 0041b222–0041b22e".
- **Following.** A following pane tracks the primary selection after the 200ms settle and reads the decompile cache only. While a cached entry is read, the previous function stays, dimmed to `ink-muted` (still 4.5:1), under an inline "… Loading ‹name› ‹address› from the decompile cache" notice; a response for a superseded selection is dropped and never lands.
- **Cache miss.** A following pane never decompiles. It shows the not-loaded StateNotice, `fact-unknown` ○ "Not decompiled in this session · Enter to decompile", with a Decompile button. Only an explicit Go or Enter on the function decompiles it, as a read of existing analysis with no reanalysis. Peek, hover and prefetch never decompile.
- **Predates a job.** After a job changes a function's signature, storage or types, that function's cached decompile and its callers' carry "◷ predates job c4d2" in the pane header, in held panes and in Peeks. They are never re-decompiled automatically; Enter decompiles.
- **Program not open.** `fact-unknown` ○ "Not loaded · Enter to load" with an explicit **Load ‹build›** button. Nothing opens a program, decompiles on another build or starts analysis as a side effect of following.
- **Outcome.** After a Save, the token gets a compact lifecycle cell (admitted → running → terminal word, with its job link) once the terminal result arrives; nothing is shown optimistically and nothing is announced on pending. The terminal message is InlineRename's ("Rename saved: local_8 is now itemCount on build-a, job c4d2."). The changed statements then carry "✎ job c4d2" in the gutter until the next navigation, and BeforeAfterBand may open under them.
- Panes narrower than 640px soft-wrap long lines with a 4ch hanging indent. Below 460px the address gutter hides and the status line carries the mapping.
- Both surfaces render the same lines, mapping, token kinds and menu groups from the same decompile projection and catalog. The static 8080 surface may draw the well as a table and open the editors as anchored dialogs with identical words, fields and states.

**Linking**

- **Publishes:** the shared cursor to `addr`: replaceState while the caret moves inside one function, pushState on Go. Open beside publishes `hold=fn:…@build[:addr]` for the new Held pane; Keep inside a Peek publishes `keep=`.
- **Follows:** the primary location (`project`, `entity`, `build`, `addr`) after the settle, as a cached pane; under Update panes: On Enter it commits on Enter. Holdable with Hold this pane.
- **Targets rendered:** callee, global and string literal → the Code Browser at that build and address; type and field → the type (`type=CacheEntry` or `type=CacheEntry.name_len`); the "predates job" and "✎ job" marks → the dock Jobs record. Locals and parameters are editor buttons, not links.
- **Peek source:** Alt+↓ reads the peek cache: for a callee its cached decompile or listing and facts, for a type its stored layout, for a local its type, storage, tier and uses from this function. Nothing is decompiled for a Peek.
- **Absent copy:** "No address mapping for line N"; "Not decompiled in this session · Enter to decompile"; "Not loaded · Enter to load"; "unresolved import" for a call target with no symbol. None is linked to a guess.
- **Target-size exception:** tokens are inline text inside the grid (the WCAG 2.5.8 inline exception, underlined on the current, hovered or focused line). Menu items and editor controls are at least 24px, 44px below 700px; with a coarse pointer each line has one 44px row-menu button carrying the same menu.

**Keyboard**

- APG Grid with one tab stop. ↑/↓ move by line, ←/→ move token to token and wrap to the next line, Home/End go to the first and last token of the line, Ctrl+Home/Ctrl+End to the first and last line, PageUp/PageDown by a page.
- **Enter** on a navigable token goes there and pushes one history stop; on a function the pane has not decompiled, Enter decompiles it. **Shift+Enter** opens it beside as a read-only Held pane; the selection does not change. Ctrl/Cmd+Enter keeps the browser's new-tab meaning.
- **Enter** or **F2** on a local, parameter or label opens InlineRename with the name field focused (`code.rename`). **F2** on a function name opens InlineRename for the function, showing its identity and counterparts as in the Functions grid. F2 anywhere else does nothing and says why in the status line: "F2 renames locals, parameters, labels and function names."
- **Alt+↓** peeks the focused token inline under the line (Peek inline form). Inside an open Peek, the Keep button (or Shift+K while focus is inside it) keeps it as a card.
- **Shift+F10** or the Menu key opens the token menu above.
- In the open editor, **Enter** saves in place (the one key path that mutates, and only there). **Esc** follows the one order in `keymap.json` `escapeOrder`; it never clears held panes.
- Code-scope single keys from `keymap.json`, active only while focus is in the well, remappable and off under the `off` profile (WCAG 2.1.4): `r` focuses the reflected row in the Listing, `h` highlights every occurrence of the focused token, `x` focuses References, `]` and `[` step to the next and previous reference, `g o` opens the CodeBrowser Outline (`code.outline`). Ctrl/Cmd+F finds in this well and announces "3 of 12 matches". The `ida` profile adds `n` (rename), `y` (set type) and `;` (comment), which open the same editors under the line. The `ghidra` profile adds `l` (rename), `;` (comment editor), `t` (set data type), `d` (disassemble), `c` (clear code) and `f` (create function); each opens the same editors or arms the ActionStrip, and nothing posts from a key.

**Accessibility**

- `role="grid"` named "Decompiled C, ‹function›, ‹build›", with columns line, code and mapping, `aria-rowcount` for the whole function and `aria-readonly="true"` (cells that host InlineRename set `aria-readonly="false"`). Each row reads its line and its mapping under the one per-viewer **Screen-reader verbosity** value in View settings: "Line 7: pCVar1 = Archive::OpenMember(resourceArchive,local_8); from 4 instructions, 0041b222 to 0041b22e", or "…no address mapping". Line numbers and gutter glyphs are `aria-hidden`; the row name carries them.
- **Accessible View** (Alt+F2, or the palette, the Help menu and the pane-header button, because GNOME and KDE take Alt+F2) opens the exact text of the function as read, following the verbosity value, with the caret on the focused line.
- A token's name carries kind, target and state: "Function Archive::OpenMember, 0041d0a0, build-a"; "Local local_8, char pointer, stack minus 0x4, placeholder name. Enter to rename or retype". Local buttons expose `aria-expanded` and `aria-controls` while their editor is open.
- Caret moves announce only the focused token's name; there is no live-region chatter. A chord-opened peek is announced once, as in Peek, and a dropped late response announces nothing (WCAG 4.1.3).
- WCAG 3.2.1 and 3.2.2: moving the caret never navigates or switches the build. Only Enter, Shift+Enter or a menu pick act; opening the menu or editor never changes the selection.
- WCAG 2.4.11: `scroll-padding-block` keeps the focused line clear of the composite header, and the inline editor never covers the line it edits.
- Identifiers carry `translate="no"` and the well isolates direction. Under `forced-colors` the selection maps to Highlight, the reflection to a solid 1px CanvasText outline, a highlight to a CanvasText box with its letter, and the token under-bar to an underline.

**Removes switching** (counts from the plan ledger):

- J10 relate an instruction row to its decompiled statement: 6 → 0 at ≥700px, 2 below (U173).
- J11 rename or retype a local seen in the decompiler: 6 → 0 (F2, type, Enter; U185).
- J13 inspect a variable's or field's type and retype it: 5 → 2 (Peek type and Retype in place; changing the structure still opens the type view).
- J15 diagnose a decompile artifact: 6 → 4 (callers and bytes are co-visible in CodeBrowser; data flow and the prototype edit stay their own verbs).

**Parity extensions (2026-09-29)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): D05, D15, D16, D19–D21, D24–D27, D32)

- Decompiler options are set in OptionsPanel (D05). A view decompiled under other options says "decompiled with ‹option› ‹value› · Enter to decompile".
- Slice highlights (def-use, forward, backward, and forward and backward operator slices) are drawn as highlight sets A–D (D25, D26). Each is labelled with its basis and has next and previous highlight.
- Next and previous brace are keymap ids (D27).
- The token-kind word says "committed" or "decompiler-only" (D32).
- Edit group items, all catalog actions with ConfirmDialog where cross-build:
  - Commit Params/Return and Commit Local Names (D15, D16);
  - Split Out As New Variable (D19);
  - Force Field and Adjust Pointer Offset (D20);
  - Auto Create/Fill Structure, whose result opens TypeEditor (D21);
  - Convert/Set Equate (D24).

**Parity extension, round 3 (2026-09-29): Debug Function Decompilation (D06)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): D06)

Ghidra's Debug Function Decompilation performs a full decompile of the current function and saves everything that decompile used (instruction bytes, symbols, data types and the settings that affect decompilation) as an XML file, for decompiler bug reports. Here it is a job that captures that XML as an artifact for one function on one build.

- **Where.** The function-name token's link menu and the pane header's **More** menu: **Capture decompiler debug XML…**, in a **Diagnostics** group after Edit. It is listed only when the catalog exposes the capture job; otherwise it is `aria-disabled` with "Not available on this server yet. Decompiling still works. · What this server offers".
- **What it binds.** It arms the ActionStrip with the catalog job, bound to one function and one build: "Capture debug XML · ResourceRef::Resolve · build-a 0041b210". The fields state the decompiler options the capture will use, from the build's program options and the viewer's request options, with each value's origin. Run posts once. No ConfirmDialog is needed: the job is read-only for the program (not mutating; it writes only to the output tree).
- **Reuse first.** Before Run, the strip checks OutputsCatalog for a capture of the same function, build and basis (program generation and options). If one exists it says "A capture with this basis exists · artifact d07a · 13:40 · Open" and Run becomes **Capture again**, which says why it would be needed.
- **What it is not.**
  - It does not update this view. The job decompiles inside its own run; the pane's cached decompile, its "predates job" marks and its cursor are unchanged. A capture made under other options than the pane's says so on the artifact.
  - It is not recovery evidence. It carries no claim tier and no fact, and nothing counts it toward a match.
  - It never runs from following, hover, Peek or prefetch, never analyzes, and never runs for another build. Each build is its own capture.
- **Output.** After the terminal result, the job's receipt lists the artifact, and the pane's status line says once: "Debug XML captured for ResourceRef::Resolve on build-a · artifact d07a · job e5a0". The artifact appears in OutputsCatalog (`ws=evidence&panel=outputs&artifact=d07a`) and opens as an ArtifactCard:
  - status ▣ delivered only when the receipt records the file and its hash; "delivered" means only that a bounded receipt exists;
  - the basis: build, function address, program generation, decompiler options and the capture time; ◷ stale when any of these changes;
  - its contents in words: instruction bytes, symbols, data types, options;
  - "not observed on 8080" as a separate axis;
  - **Copy path** (`outputs.copyPath`, `c`). The file lives in the output tree; the design has no file chooser.
- **Sensitivity.** The capture contains the function's bytes and types. The ArtifactCard says so ("contains program bytes and types from build-a"), and the artifact belongs to this project only.
- **States.** Armed · pending (202) · running · finished with artifact · failed with its FailureRecord ("decompiler exited with an error · log line 211", linking `f=log.line:211`) · cancelled · already captured with this basis.
- **Keyboard.** `code.debugDecompile` (code scope, no default key) arms the strip; Run posts. The palette has "Capture decompiler debug XML".
- **Accessibility.** The menu item's description says "Runs a job that decompiles this function on build-a and saves the debug XML as an artifact. This view does not change." The terminal message is announced once in the polite region.

## Behavior

- Follows: the pane follows as the cursor moves ("Follows · as I move"); a following pane reads the decompile cache only.
- Trace data flow… arms the ActionStrip bound to the target on its build; nothing runs (formerly the "≠ runs" menu note).
- Rename… on a callee opens the editor bound to that function; F2 is for locals, parameters and labels (formerly "editor · F2 ≠ function").
- Not decompiled (formerly the "≠ reanalyze" chip): "Following reads the decompile cache only. Enter here, or Go on Log::Warn, decompiles it from existing analysis without reanalyzing. Peek and hover never decompile."
- Debug XML capture: "The decompile in this pane is unchanged."
