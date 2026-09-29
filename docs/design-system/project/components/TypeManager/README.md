# TypeManager

The Types navigator scope: one tree of archives, categories and data types, keyed by logical type, with a column per build for presence, size, layout and sync state, plus find, favourites, and the archive, apply, capture, replace, merge and header-import verbs, each routed through the catalog.

**Use it** from the Navigator's scope list (Types, beside Strings, Imports, Exports, Sections, Symbols and Bookmarks), from a `type=` link, or from the palette ("Types"). It replaces Ghidra's Data Type Manager window. It is a navigator scope, not a center surface. Editing a type opens TypeEditor, and it never adds a second types sidebar.

**Consumer provides** the related-build scope and the inspected build. For each build: whether its program is open, its type manager's categories and types, each type's kind, size, alignment, a layout digest and its source-archive association and sync state. It also provides the open archives (built-in, file `.gdt`, project) with their writable state, architecture, unsaved-change count and archive undo depth; the program writer and each archive writer as the resource record reports them; use counts per build, or "uses not indexed"; any recorded variance witness per type and build (for example a compiler-flag receipt that records packing); the viewer's favourites and recently used types from durable workspace state; and the catalog actions from `GET /api/v1/actions` for archive lifecycle, sync, category and type edits, replace, merge, apply and capture function data types, create labels from enums, export and header parsing. The design system names no action ids.

**Anatomy**

1. **Header.** The scope switch is an APG radio group: "This build · build-a" or "All builds · 4". Next to it are the writer lines in ResourceState words: "● writer: this session · 4 programs" and "○ corpus-alpha.gdt free", or "● corpus-alpha.gdt writer owned elsewhere" with the external owner as reported.
2. **Find.** One field with a find-by radio group: Name, Size, Enum value, Struct size and Struct offset. The hint under the field states the scope and how many builds hit ("Size 0x18 matches on build-a and build-b"). All builds shows one hit column per build. Hits are never merged, and the same logical type may match on one build only.
3. **Tree.** The top-level groups are Favourites (per viewer), Recently used (per viewer), Program types (one type manager per build), File archives, Project archives and Built-in (read-only). Categories nest under each group. Each type row carries:
   - the logical type name (a link that opens TypeEditor) and a ★ favourite mark, which is also said in the row's name;
   - its kind (structure, union, enum, typedef, pointer, array or function definition);
   - one cell per build: ● and the size when present, the word "absent" when missing, "not loaded" for a closed program, and ± with the difference when the layout differs from the inspected build. A second line gives the layout word (↔ same, ± next at +0x18) and the sync state;
   - a variance cell: compile variance, entropy variance, source variance or unknown. A solid frame means a recorded witness and the frame names it. A dashed frame means "hypothesis" and names its basis. Unknown is the plain word.
4. **Sync state** (per build, per associated type): in sync · changes to commit · archive newer (update available) · conflicting (both changed) · archive not open (sync state unknown) · not associated. Refresh sync indicators is a read.
5. **Archive rows.** Each archive row shows its kind, path, writable or read-only, architecture, "2 unsaved changes" and "archive undo 2". Archive undo and redo act on the archive's own transactions. They never touch a program.
6. **Status line.** The focused type's use counts per build ("build-a 14 · build-b 14 · build-c 11 · build-d uses not indexed"), and the keys.
7. **Link menu** (one menu, per Linked views). The Open group has Open in type editor, Peek layout per build and Keep. The Edit group lists only catalog actions, by their catalog labels with no "(catalog)" mark: New structure, union, enum, typedef, pointer or function definition; New category; New enum from selected enums; Rename; Move; Copy; Cut and Paste (a move); Delete (types and categories); Replace; Merge; Associate with archive; Update from archive; Commit to archive; Revert; Disassociate; Create labels from enum; Apply function data types; Capture function data types; Import C header; and, for archives, Open, Create (file or project archive), Open for editing, Close for editing, Close, Save, Save as…, Set architecture, Clear architecture, Archive undo, Archive redo, Delete archive and Remove invalid archive. **Archive paths…** (where file archives are looked up) is a per-viewer setting (PV), not a program write. Expand all and Collapse all are view state. An item that does not apply stays listed, `aria-disabled`, with its reason. Reveal in has uses on ‹build› (ResultsTable or XrefPanel), Show in tree, Show base type, Compare with… (two types side by side, read-only, each with its build or archive) and Display as graph (GraphPane, read-only). Copy has Copy link and Copy type name.

**Verbs and their confirm tier** (Doctrine; 35 Confirming edits)

- **Reads** confirm nothing and start nothing: find, filter, expand, favourites, recently used, show base type, display as graph, refresh sync indicators, export preview and Peek. Favourites and recents are per-viewer state (PV), never program data, and never propagated.
- **Confirmed in place:**
  - renaming a category or a type through InlineRename. The type name follows `PascalCase` and the hint says so; a category rename is a single target;
  - creating a category;
  - saving an archive;
  - setting an archive's architecture when the archive is empty.
- **ConfirmDialog**, which names the build or archive, the type and the use count per build:
  - replace, merge, move or delete a type;
  - delete a category or an archive;
  - commit, update, revert or disassociate sync;
  - apply function data types (a batch on one build) and capture function data types (a batch into one archive);
  - creating labels from an enum, which is a batch on one build;
  - importing a C header into a target.
  Replace and merge carry the conflict mode as a field in the dialog: Rename the new type, Use the existing type, Replace the existing type, or Replace only empty placeholders. There is no hidden, sticky conflict mode.
- **Header import (C-parser).** The destination is one archive or one build's program types, never all builds. Parsed types appear as dashed "hypothesis · parsed" rows with a size check for each build. A parse is not layout proof (NP). Applying a parsed type to a build whose size check fails is blocked, and the block says why ("0x18 vs 0x1c").
- **Every mutation names its exact target.** The target is a build's program types or one archive, and "all builds" is never a write target. A shared archive is how a type reaches several builds. It gets there through an explicit, per-build commit or update, each layout-gated and each with its own outcome.
- **Propagation** is TypeEditor's "Propose to build-b, build-c" step. TypeManager's per-build columns show where a type is absent or differs, and Update from archive on each build is the confirm-gated path.
- **One writer.** Program writes need the build's program writer. Archive writes need that archive's writer. While another owner holds it, the verb waits and names the owner as reported. It never starts a second writer, and it never offers kill or restart. Ownership is never inferred from job labels.
- **Undo** is per program or per archive, and per transaction (EditHistory). A replace or merge that rewrote uses on build-c is undone on build-c only. The dialog says "cannot be undone here" when the catalog reports that the verb has no inverse.
- **Outcomes land on the row.** After the terminal result the type row gets an OutcomeCell with its job link (for example `a3f9`). Nothing is shown optimistically.

**States**

- loading (… "Loading types for build-c"), shown only while a read that was asked for is in flight;
- not loaded (○ "Not loaded. Open to read it."), for a build whose program is not open. The Open action reuses the existing analysis and never analyzes;
- empty (∅), for a find that hits nothing, naming the scope it searched;
- partial (◐), when some builds were read and others were not, with the missing builds named;
- stale (◷ "Type manager changed since read · Refresh");
- conflict (⇄), for a sync conflict, with both definitions side by side and neither pre-picked;
- writer owned elsewhere (●, ResourceState words), when an archive or program writer is owned by another session or process; writes wait and name the owner as reported;
- ambiguous outcome ("Checking whether the operation completed"), during which that verb on that type is disabled;
- read-only, for built-in and read-only archives, whose Edit items are `aria-disabled` with the reason.

**Linking**

- **Publishes:** the `type` parameter. Enter on a type row is Go: it pushes one stop and opens TypeEditor for that type at the inspected build. Arrow moves only replace the URL after the settle. The scope and find text are `f=` filters (registered axes `type.scope` and `type.find`) and replace the URL.
- **Follows:** the project. "This build" follows the inspected build after the settle; "All builds" does not follow the build. It is a navigator scope and cannot be held. A type row can be kept as a card through Peek → Keep (registered kind `type`).
- **Targets rendered:**
  - type → TypeEditor for that type and build (`type=CacheEntry&build=build-a`);
  - a use count → the uses of the type on that build (ResultsTable, `f=type.use:CacheEntry`);
  - a build column header → that build's Navigator program row;
  - the writer line → the resource record (OwnershipPanel);
  - an outcome → the dock Jobs record.
- **Peek source:** Alt+↓ on a type reads the stored layout of each build (size, alignment, fields with offsets) as last read, labelled "as read ‹time›". It never opens a program.
- **Absent copy:** "absent" (plain word) · "not loaded" · "Not loaded. Open to read it." · "uses not indexed" · "archive not open · sync state unknown" · "No structure has a field at +0x40 on build-a".
- **Target-size exception:** none. Rows are 28px (24px compact) and 44px below 700px. Row links carry the name, never a glyph alone.

**Keyboard**

- APG Treegrid: ↑/↓ rows; → expands, then moves into the cells; ← moves out of the cells, then collapses, then goes to the parent; Home/End; Ctrl+Home/End; `*` expands siblings (`tree.expandSiblings`). Typeahead starts with `/` because single letters are commands here.
- Enter is Go (it opens TypeEditor). Shift+Enter opens it beside. Alt+↓ peeks. Shift+F10 opens the link menu. F2 renames in place.
- Keymap ids (registered), all in the composite scope:
  - `types.favourite` (`f`): toggles a favourite; it is per-viewer state, not a mutation;
  - `types.scope` (`a`): switches between This build and All builds;
  - `types.uses` (`u`): reveals uses on the inspected build;
  - `types.find` (`/`): focuses Find, aliased to `list.typeahead`.

**Accessibility**

- `role="treegrid"`, named "Types, ‹scope›, ‹find›", with `aria-level` and `aria-expanded` on rows and the type name as the row header. Per-build cells are gridcells whose words carry the state ("present, 0x1c, differs: next at +0x18, changes to commit"). The ● and ± glyphs are backed by words, and the ★ is said as "favourite".
- The key below the grid is tied to the grid with `aria-describedby`. The horizontal scroll container is a focusable, labelled region.
- The scope and find-by controls are APG radio groups. Find result counts go to the polite region, debounced to 300ms.
- A dialog opened from the tree returns focus to the row that opened it.

**Parity rows covered**

- T01 the tree, archives and categories; T02 the archive lifecycle; T03 source-archive sync; T04 categories.
- T05 the type create, rename, move, copy and delete verbs (the edits open TypeEditor).
- T06 replace and merge with the conflict mode; T07 find by name, size, enum value and struct size or offset.
- T08 apply and capture function data types; T09 export (it hands off to ExportDialog), labels from enums, show base type and graph.
- T15 C-header import.
- Also T18 favourites and recently used (PV). T17's flat table is a ResultsTable mode that TypeManager opens with "Show as table".

**Prior art**

- Ghidra Data Type Manager: archives, categories, sync indicators, conflict resolution mode, and find by size or offset.
- IDA Local Types: a flat list synchronized with the database.
- Binary Ninja: the Types sidebar with platform type libraries.
- The research note [reference RE UI patterns](../../../../research/2026-09-29-reference-re-ui-patterns.md), A2 and A10: one row set keyed by identity with a column per build, and one model with provenance and sync state.
- What changes here: the per-build columns, the variance words with their evidence level, the writer lines and the explicit write target.

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- Key (moved text): "\"absent\" is a word, never a guess · \"not loaded\" is never fetched from here. Target map: the one build or archive a write touches. Enter opens the type editor · Shift+F10 link menu · f favourite."
- ⊘ not loaded (build-d cell): "not loaded. Open build-d to read it."
- Replace confirm: the ⊘ undo chip becomes the focusable undo slot ⊘ no undo before Cancel; "this cannot be undone here".
- 1 destination: "destination is one archive or one build's program types, never all builds"
- ≠ layout proof (full original tip): "A parse is not layout proof; applying it to build-c is blocked until its size check passes."
- ≠ applied (chip removed): "Nothing is applied to any build by this step."
- ≠ kill (chip removed): "The owner is never offered kill or restart."
- ○ not loaded: "Not loaded. Open to read it. build-d's program is not open, so its type presence, size and sync state are not shown. Opening reuses its existing analysis; it never analyzes."
- ∅ +0x40: "No structure has a field at +0x40 on build-a. Find by struct offset searched build-a only. Switch the scope to all builds for one hit column per build."
- ⇄ capture (chip removed): "Capture function data types is the reverse: from one build into one archive."
- Keycap Key rows (removed; keycaps are not drawn encodings): "Enter · type editor"; "f · favourite".
