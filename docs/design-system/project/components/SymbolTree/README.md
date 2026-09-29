# SymbolTree

The symbol hierarchy of the project as an APG treegrid: Imports, Exports, Functions, Labels, Classes and Namespaces, with parameters under functions. Each logical node has one presence column per build, and every edit names its exact build and is proposed to counterparts only as a separate, confirm-gated step.

**Use it** as the navigator's Symbols, Imports and Exports scopes (Workstation layout). The Functions grid stays the one Functions surface. This tree is the namespace view of the same entities, and its Functions category links into that grid rather than duplicating it. The static 8080 surface may render the same treegrid as nested lists with identical words and columns.

**Consumer provides**
- The logical symbol hierarchy of the project: the namespace path per logical entity, with its kind.
- Per build: the symbol's namespace path, address, LocatorGlyph status and identity-edge word; the ICF alias set where one address carries several symbols; and the inlined-only state where a function has no out-of-line body.
- Imports per build: libraries (including `<EXTERNAL>` for unassociated locations), each library's external program if set, and external locations and functions.
- Exports per build.
- The catalog's symbol, namespace, class, external-location and rename actions from `GET /api/v1/actions` (no action id is named here).
- The writer state per build: free, or owned by a named job or session with its PID and start time as the ownership record reports them.

## Anatomy

1. **Header.** "Symbols · corpus-alpha" and a **Scope** segmented control: **Logical · all builds** or **build-a only** (one concrete build).
   - The logical scope is keyed by entity, with one presence column per build.
   - The build scope is exactly that program's own symbol tree (Ghidra parity), with one address column.
   - Beside the control sits the writer line per build: "build-b · lock owned by another session (agent) · edits wait". It is never a kill or restart control.
2. **Filter.** `/` opens the tree filter: strategy (contains, starts with, exact, glob, regular expression), multi-term (all terms or any term), case sensitive, invert (show what does not match), and "match on name only" or "name and namespace" (Ghidra's Use path). Filtered-out ancestors stay shown dimmed, so the path is never lost. The count reads "38 of 4,112 symbols".
3. **Categories** (fixed, not editable): Imports · Exports · Functions · Labels · Classes · Namespaces. **Hide category** and **Show category** (Ghidra's Disable and Enable Category) are per-viewer view state; a hidden category is listed in the header ("Labels hidden · Show").
   - Large categories show **group nodes** by common prefix ("FUN_0041… · 312"), as Ghidra does, with their counts.
   - Group nodes are organizational only and cannot be renamed or dropped onto.
4. **Nodes.** A disclosure button (24px), the kind word (namespace, class, function, label, parameter, library, external location, external function), and the name as a typed link.
   - A symbol link carries its build, in build scope and in each presence cell.
   - A logical id link goes to Compare.
   - The name shows the NameProvenance tier word when it has one.
5. **Presence columns** (logical scope), one per build, using the LocatorGlyph words:
   - ● resolved, with the address link;
   - ◎ pinned (`module_rva` or `section_offset`, non-portable);
   - ◑ degraded;
   - ⋯ ambiguous and ⇉ contested, each linking to its ladder evidence;
   - ◌ unresolved;
   - **absent**, a plain word.

   Two additional words come from the compiler research (not new glyphs):
   - **folded**: identical-code folding, where one address carries several symbols. It lists the other symbols at that address.
   - **inlined only**: the OutcomeTag, where the function has no out-of-line body on that build.

   A namespace path that differs between builds reads "namespace differs" in that cell. Its Peek shows each build's path. It is never merged into one path.
6. **Row menu and ActionStrip** (Edit group; each item is present only when the catalog exposes it, and otherwise listed `aria-disabled` with its reason):
   - Rename… (InlineRename, F2);
   - Create namespace… and Create class… under the focused node;
   - Convert namespace to class;
   - Move to… (a namespace picker), and Cut and Paste for the same move;
   - Delete…;
   - Imports only: Create library…, Set external program…, Clear external program…, Move library up and Move library down (the library search order), Create external location… and Edit external location… (with Restore original label when the importer recorded one), and Create external function.
   - Reads, in the Open and Reveal groups: Show references to (XrefPanel), Make selection (the node's addresses on one build, client state) and Create table from selection (a ResultsTable of the checked nodes, symbols kind, on one build).

## Edits and the multi-build rules

- **Exact target.** Every edit acts on one concrete build. In logical scope, the Edit items name it ("Rename on build-a (catalog)"). When the node is present on several builds, a build chooser inside the editor defaults to the inspected build and never to "all".
- **Single target confirms in place.** Rename, create one namespace or class, convert one namespace, and edit one external location confirm in their own inline editor (Enter or Save). The editor shows:
  - the naming-convention hint for the kind (classes and namespaces PascalCase, functions and labels as the repository convention);
  - the build;
  - the catalog action by its label, with "(catalog)".
- **Batch, destructive and cross-build use ConfirmDialog.** This covers moving several symbols, deleting any symbol, and pasting a cut set. The dialog names the build, the count and the known reference count ("Delete 3 labels on build-b · 17 references become unnamed").
- **Propagation is separate.** After a terminal result on build-a, the row offers **Propose to build-b, build-c**. That opens PropagationTransfer with:
  - one preview row per recipient (old → new namespace path per field);
  - the identity-edge gate (accepted edges only; candidates are listed and blocked);
  - a name-collision check on each recipient's namespace;
  - its own ConfirmDialog.

  Each recipient gets its own outcome. Nothing is applied automatically.
- **External locations are program-local.** A library's external program and an external location belong to one build and are never proposed to counterparts. Set external program lists only programs already in this project, and choosing one opens nothing.
- **One writer.** When the build's lock is owned elsewhere, Edit items stay listed with "build-b has a writer: another session (agent) · your edit waits for it". Run is refused with that reason. Admission never offers to stop the other owner.
- **Undo is honest.** After a terminal result, the status line offers Undo only when the catalog exposes undo for that program's transaction. It states the scope ("Undo on build-a only; build-c's proposed copy has its own outcome"). A deleted symbol's references stay unnamed if undo is not available, and the dialog says so before Delete.

## Set external entry point (S11)

Ghidra marks an address as an external entry point: an address where execution can start from outside the program (the program entry, a DLL's exports). The property belongs to the address, so every label there shares it; it needs at least one symbol at the address; and a default label there reads `EXT_` with an "EXTERNAL" plate.

- **Where.** The row menu's Edit group on a function or label, and the Listing link menu's Function group: **Set as external entry point on build-a** and **Remove external entry point on build-a**. Each is present only when the catalog exposes it; on a node with no address (a class or namespace) it is not listed; on an address with no symbol it is `aria-disabled` with "Add a label first; entry points need a symbol".
- **One build, confirmed.** Set confirms in place in the ActionStrip, naming the build, the address and the catalog action ("Set external entry point (catalog) · build-a · 0041b210"). Remove uses ConfirmDialog when the importer recorded the entry point: "Remove external entry point at 0041b210 on build-a? The importer recorded it from the export table." A batch over checked nodes uses ConfirmDialog with the count.
- **Evidence, per build.** The Exports category lists entry points per build with their basis in words: "entry point · importer record (export table)" (solid, a record) or "entry point · set by you · job 6e21". A set entry point is an operator statement, not a witness: it never makes the export table say anything.
- **Program-local.** Entry points are never proposed to counterparts, because each build's export set is its own fact: build-b may export a function build-a does not. A logical row shows each build's own state ("entry point on build-a · not an entry point on build-c"), never merged.
- **What it does not do.** Setting an entry point starts no analysis and creates no function. If a function should start there, Create function… is a separate Listing action.
- **States.** Pending and terminal OutcomeCell words on the row; "⇄ conflict on build-b" when another session changed the symbol meanwhile; the writer line when the lock is owned elsewhere.
- **Keyboard.** `code.entryPoint` (no default key) opens the item from the Listing; in the tree it is in the row menu (Shift+F10). Keys arm; Run or the dialog posts.

## States

| State | Shown as |
|---|---|
| Loading | "Loading symbols · build-b" beside the stale rows; `aria-busy` on the tree only when it does not hold focus |
| Not loaded | a build column reads "Not loaded. Open build-c to read it." and fetches nothing |
| Category closed after a bulk change | "Functions reorganized after job a3f9 · Expand to reload"; nothing reloads on its own |
| Empty category | "No exports on build-d", in words |
| Filtered | "38 of 4,112 symbols · filter: starts with Cache" with a FilterChip |
| Cut pending | cut rows are dimmed and say "cut · paste to move"; Esc clears the cut, which is client state only |
| Edit pending | the row's OutcomeCell: pending → running → finished or failed, with the job link; nothing is shown optimistically |
| Modification conflict | "⇄ conflict on build-b: renamed by another session since you opened the editor · Resolve" opens the catalog's conflict resolution; the draft is kept |

## Linking

- **Publishes:** Go on a symbol pushes one stop with `entity`, `build` and `addr`. In logical scope, Go on the name goes to the inspected build's counterpart, and a presence cell goes to that build explicitly (announced). A class or namespace node has no address; Go filters the Functions grid to it (`f=name:ResourceRef::`), which is a push.
- **Follows:** the primary selection, to reveal and mark the current symbol ("Reveal current" on by default). Focus moves only on arrows. Following never expands a closed category that needs a reload. Not holdable; it is a navigator scope.
- **Targets rendered:** symbol and address → the Code Browser at that build · logical id → Compare · counterpart (entity @ build, with its edge word) · library's external program → that program's Navigator row (never opened) · job → the dock Jobs record · ladder evidence for ambiguous and contested cells.
- **Peek source:** Alt+↓ on a node peeks its cached Listing lines at the entry, the per-build namespace paths, and the ICF alias set. Nothing is fetched.
- **Absent copy:** "absent" · "unresolved on build-d; members tried: 7" · "ambiguous · 2 candidates" · "contested · no winner" · "inlined only on build-b" · "folded with Actor::Release at 0041d2a0" · "namespace differs" · "Not loaded. Open build-c to read it."
- **Target-size exception:** name and address links sit in 28px rows with one link per cell (44px below 700px and with a coarse pointer). Disclosure buttons are 24px.

## Keyboard

- APG Treegrid: ↑/↓ move rows; → opens a node or moves into its cells; ← closes a node, moves to its parent, or moves back out of cells; Home/End; `*` expands siblings (`tree.expandSiblings`). Typeahead starts with `/` because the tree binds letter commands.
- Enter goes; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the link menu; F2 renames in place (`tabs.rename` / `code.rename` semantics: InlineRename).
- Composite-scope ids (the SymbolTree treegrid only; registered in `keymap.json`):
  - `symbols.cut` (Ctrl/Cmd+X) marks the focused or checked nodes as cut. It is client state only.
  - `symbols.paste` (Ctrl/Cmd+V) on a destination arms the Move action in the ActionStrip bound to that build. It never posts.
  - `symbols.delete` (Delete) arms Delete in the ActionStrip.
  - `symbols.newNamespace` has no default key; use the menu or the palette.
  - `symbols.scope` (`s`) toggles Logical and one-build scope and announces it.
- Keys only navigate or arm. Every post goes through the inline editor's Enter or the ActionStrip's Run, and ConfirmDialog where required. Drag and drop is an optional pointer path that arms the same Move action; Move to… and Cut/Paste reach every move without dragging.

## Accessibility

- `role="treegrid"` named "Symbols, corpus-alpha, logical, 4 builds", with `aria-level`, `aria-expanded`, `aria-setsize` and `aria-posinset` on rows. The name cell is the row header. Presence cells are grid cells named in words ("build-c: resolved, 00082f40, accepted").
- LocatorGlyph glyphs are `aria-hidden`; the word is always visible. "absent" is never an empty cell.
- Rows with a pending or finished edit carry their OutcomeCell words. Transitions are announced once in the polite region ("Rename on build-a finished, job a3f9").
- The writer line is text, not color: "lock owned by another session".

## Parity rows covered

- **S01**: the hierarchy of Imports, Exports, Functions, Labels, Classes and Namespaces, with group nodes and parameters under functions, and per-build presence.
- **S02**: create namespace or class, convert namespace to class, move by cut and paste, Move to… or drag, delete, and rename. Each is per-build, then proposed to counterparts.
- **S03**: external locations and libraries: create library, set and clear the external program, library order, create and edit external location, restore the original label, create external function. All are program-local.
- **S12**: namespaces and classes for functions and labels, through Move to… and the class and namespace nodes. SignatureEditor's namespace field uses the same picker.
- **F05**: external functions under Imports, with a logical row per import across builds.
- **S04** (navigation mode and snapshot) stays with Following and HeldPane. This tree adds "Reveal current".
- **S11**: set and remove an external entry point, per build and never proposed, with its basis (importer record or set by you) under Exports.
- **I10**: the tree-filter part: strategies, multi-term, globbing, case sensitivity, invert and use path.
- Also from `SymbolTree.htm`: show references to, make selection, create table from selection, and disable or enable a category (as per-viewer hide and show).

## Prior art

- Ghidra help `SymbolTreePlugin/SymbolTree.htm`: categories, `<EXTERNAL>` and library namespaces, group nodes and their auto-close after bulk changes, the valid move rules per symbol kind, and the create, convert, delete and external-location dialogs. Also `Framework/Docking/.../Trees/GhidraTreeFilter.html` for the filter strategies.
- Research: ICF folding ("one address, many symbols", T6) and inlining (T3) in `docs/research/2026-09-29-msvc-optimization-for-decomp.md`; entities, not addresses, as the key (Premise and D9 in `docs/research/2026-09-29-reference-re-ui-patterns.md`).
- Existing components: ContainerTree (APG tree house style), LocatorGlyph, NameProvenance, InlineRename, PropagationTransfer, OwnershipPanel.
