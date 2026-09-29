# ProgramTreeView

One build's program trees (named organizations of folders and fragments over its code units) shown as an APG treegrid. Selecting a folder or fragment can restrict the Listing's view to it, and every tree edit or organization job names its build and passes through the catalog.

**Use it** as a navigator scope ("Program trees") beside Sections, Symbols and Bookmarks. Program trees are program-level objects: build-b's trees belong to build-b. Across builds they are compared, never merged, and never propagated. ContainerTree still covers file containers; this component covers organizations inside one loaded program.

**Consumer provides**
- For the inspected build:
  - the list of tree views with their names;
  - per tree, its folders and fragments, with each fragment's address ranges, byte size, code-unit count and every parent (a folder or fragment can have several parents);
  - the default tree's origin (one fragment per memory block).
- The block models the build's program offers (for the organization actions).
- The catalog's tree actions from `GET /api/v1/actions` (no action id is named here).
- The writer state for the build.
- For Compare: the same data for another build, read only when that build is open.

## Anatomy

1. **Header.** "Program trees · build-b". It has:
   - a **Build** menu button: switching the inspected build is an explicit action, and it states that the checked set will be cleared;
   - the writer line ("build-b · no writer" or "lock owned by another session");
   - **Compare with…**.
2. **Tree tabs.** One manual-activation tab per tree view in the program ("Program Tree", "Subroutines · Isolated entry"), plus **Open tree…** for trees not shown. **New default tree** is a catalog action that creates one fragment per memory block on this build. Each tab has a menu: **Close tree** (view only; the tree stays in the program), **Rename tree…** (inline, catalog) and **Delete tree…** (ConfirmDialog, catalog; the last tree cannot be deleted and says so).
3. **Treegrid columns:** Name (folder or fragment, with its kind word and "empty" when it holds no code units) · Ranges (the first range as an address link, then "+2 ranges") · Size · Code units · Also in (the other parent paths).
   - The Also in column matters because a shared fragment is one object. Renaming or moving code units in it changes every place it appears, and the rename editor says so ("also in /Modules/io").
4. **View restriction band.** It appears when the Listing is restricted: "Listing view: build-b · /Program Tree/.text, /Modules/io · 2 fragments · 0x41e00 bytes", with **Clear view**.
   - The restriction is per-viewer view state, read-only and never program data.
   - The OverviewBar and the SearchWorkbench's "View" scope use the same restriction. Searches say "within the view".
5. **Row menu** (Edit items listed only when the catalog exposes them, otherwise `aria-disabled` with the reason):
   - Go · Restrict view to this · Add to view · Remove from view · Make address selection (makes the Listing's address selection on this build; read-only);
   - Expand all · Collapse all;
   - Create folder… · Create fragment… · Rename… (inline, confirms in place);
   - Delete…, allowed only when the node is empty or has another parent, otherwise disabled with "Not empty and has no other parent";
   - Merge with parent… · Sort by name or address… · Move address selection here… (moves the code units of the Listing's address selection on this build into this fragment);
   - Move to… (a folder picker; cut and paste arm the same move) · Copy to… (adds another parent, so the node becomes shared and says "also in …") · Move up and Move down (reorder within the folder);
   - Organize ▸ By subroutine (block model…) · Dominance · Complexity depth.
6. **Compare** (optional): the same tree name on two builds side by side, aligned by folder or fragment name. The header says "aligned by name ≠ same contents". Rows present on one side only read "absent" on the other. Ranges and sizes are that build's own. Nothing is merged or copied.

## Edits, jobs and honesty

- **Exact target.** Every edit names the build and the tree ("Create folder in build-b · Program Tree").
- **Single target confirms in place:** create one folder or fragment, rename one node.
- **ConfirmDialog** for:
  - delete (names the node and whether it is shared);
  - merge with parent (names the children that move);
  - sort (reorders the folder for everyone who opens this program);
  - moving code units (names the range, byte count, source fragment and destination);
  - moving or copying a folder or fragment to another folder, or reordering it (names the node, the old and new parent, and whether it becomes shared);
  - any organization.
- **Organizations are admitted jobs.** By subroutine, Dominance and Complexity depth run as jobs on this build with an OutcomeCell on the invoking node. They never run on open and never run automatically after an analysis.
  - The dialog states that cancelling keeps the folders already created, as Ghidra does.
  - The dialog states that undo is one transaction on this build, and only if the catalog exposes undo for it.
- **Never propagated.** A tree edit or organization on build-b is not offered to other builds. To organize build-c the same way, run the organization on build-c; the Compare view then shows both.
- **One writer.** With the lock owned elsewhere, edits stay listed with the reason, and Run is refused.

## States

| State | Shown as |
|---|---|
| Not loaded | "Not loaded. Open build-c to read it." (for Compare); nothing opens on follow |
| Default only | "1 tree · default (one fragment per memory block)" |
| Empty fragment | the word "empty" beside the name; Delete enabled |
| Shared node | "Also in /Modules/io" and "shared · edits apply everywhere it appears" |
| Restricted view | the view band, with 2px `ink-strong` top rule and Clear view |
| Organization running | the node's OutcomeCell: admitted → running "Progress unknown · last event 14:02" or measured units → finished, failed or cancelled ("cancelled · 41 folders kept") |
| Stale | "◷ build-b changed since read by job a3f9 · Refresh" |

## Linking

- **Publishes:**
  - Go on a node pushes one stop to the Code Browser at the fragment's first address on this build.
  - Restrict view changes the Listing's view. It is carried as the registered `f=ptree.view:‹tree›/‹path›` axis (replaceState) and is not a history stop.
  - Make address selection sets the Listing's address selection (client state, never in the URL).
- **Follows:** the inspected build, and the cursor, to mark the fragment containing it ("contains cursor"). A **Select fragment at cursor** toggle mirrors Ghidra's option; it marks and scrolls, and never moves the cursor. Not holdable.
- **Targets rendered:** address (range starts) → the Code Browser at that build · build → its Navigator row · job → the dock Jobs record.
- **Peek source:** Alt+↓ on a fragment peeks its cached Listing lines at the first address and its full range list. Nothing is fetched.
- **Absent copy:** "absent on build-c" (Compare) · "empty" · "Not loaded. Open build-c to read it." · "No trees beyond the default".
- **Target-size exception:** address links sit in 28px rows with one link per cell (44px below 700px and with a coarse pointer). Disclosure buttons are 24px.

## Keyboard

- APG Treegrid: ↑/↓, →/← open, close and move to the parent, Home/End, `*` expands siblings, and typeahead starts with `/` into a visible filter field (plain letters are commands). Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 opens the menu, F2 renames inline.
- Composite-scope ids (the ProgramTreeView treegrid only; registered in `keymap.json`):
  - `ptree.restrict` (`v`) restricts the Listing view to the focused node; `ptree.addToView` (Shift+V) adds it.
  - `ptree.clearView` has no default key; it is on the view band and in the palette.
  - `ptree.select` (`s`, "Make address selection") makes an address selection of the node's addresses in the Listing.
- Tree tabs are APG Tabs with manual activation. Moves use the menu or arm the ActionStrip; drag and drop is an optional path to the same armed Move.

## Accessibility

- `role="treegrid"` named "Program Tree, build-b". Rows carry `aria-level`, `aria-expanded`, `aria-setsize` and `aria-posinset`. Shared nodes carry "also in …" in the row name. Empty fragments carry "empty".
- The view band is a `region` named "Listing view restriction". Clearing it is announced once ("Listing view cleared; whole image").
- The node containing the cursor has the visible words "contains cursor", not only a mark.

## Parity rows covered

- **P01**: folders and fragments. Create, delete (with Ghidra's empty-or-shared rule), rename, move code units, move, copy (another parent) and reorder nodes, merge with parent, sort, select, expand and collapse all, and restrict, add to and remove from the view.
- **P02**: tree views and organizations. Create the default tree, open, close, rename and delete trees, and organize by subroutine (with a block model), dominance and complexity depth. Each organization is an admitted, per-build job.

## Prior art

- Ghidra help `ProgramTreePlugin/program_tree.htm` (multiple parents, the delete rule, merge with parent, move code units), `view_manager.htm` (tree views, restricting the Listing view, select fragments at the location) and `Program_Organizations.htm` (subroutine, dominance and complexity-depth modularization; partial results on cancel).
- Existing components: ContainerTree (APG tree house style), OverviewBar and SearchWorkbench (consumers of the view restriction), MemoryMapTable (the blocks behind the default tree).
