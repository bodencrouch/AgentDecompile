# MemoryMapTable

The memory map of one build as a table: blocks with their range, length, permissions, volatile and artificial flags, overlay space, type, initialization, byte source, source and comment. An alignment view sets the builds' maps side by side, and block edits go through the catalog on one named build, never propagated.

**Use it** as the navigator's Sections scope and its "Show all" corpus view. Clicking a block goes to its start in the Listing. The alignment view is the Compare-workspace form for "how do these builds' layouts differ", beside ImageDeltaMap, which owns rebuild-versus-target deltas.

**Consumer provides**
- Per build:
  - the image base;
  - memory blocks from the existing memory read, including overlay address-space names, block type (default, bit mapped or byte mapped, with the mapping ratio), and the byte source per sub-block (file name and file offset, or the mapped start address);
  - source and comment;
  - the writer state;
  - whether the program is a versioned shared program, and whether this session holds its exclusive checkout.
- For the alignment view: the recorded provenance that classifies differences (source digest, toolchain, flags, link inputs) where it exists.
- The catalog's memory actions from `GET /api/v1/actions` (no action id is named here).
- For an image-base change, the anchors and pinned locators that use absolute addresses on this build.

## Anatomy

1. **Header.** "Memory map · build-b · image base `00400000`", a **View** control (**This build** or **Align builds**), the writer line, and, for a versioned program, the checkout state. An exclusive checkout is shown as the one-writer lock (VersionControlPanel owns the checkout itself).
2. **Per-build table** (row P03). Columns:
   - Name, Start and End as address links (an overlay start reads `OV1::00001000`);
   - Length, as hex with bytes in the accessible name;
   - Permissions as three letters, with a dash for an absent permission ("R-X"). The name is spoken in words: "read, not write, execute";
   - Volatile and Artificial as words;
   - Overlayed space, blank for non-overlay blocks;
   - Type (Default, Bit mapped, Byte mapped 2:4);
   - Initialized (initialized, uninitialized or file bytes);
   - Byte source ("build-b input · file offset 0x600", or "mapped from 00410000");
   - Source and Comment.

   Columns can be chosen and sorted with the ResultsTable header grammar.
3. **Inline editor** for a single block (the single-target fields): name, R/W/X, volatile, artificial and comment. It opens under the row and shows:
   - the build;
   - the catalog action by its label;
   - the old → new values;
   - the consequence in one sentence, for example "Removing execute from .text on build-b changes what analysis treats as code. Nothing re-analyzes on Save; re-disassembly needs admission."

   Enter or Save posts once.
4. **Block operations** (ActionStrip, each a catalog action when present): Add block… · Move… · Split… · Expand up or down… · Merge… (two or more checked adjacent blocks) · Delete… · Initialize… (with a fill byte) · Set uninitialized… · Rename overlay space… · Set image base…
5. **Align builds** (row P03 across builds).
   - Rows are blocks aligned by block name. The header says "aligned by name ≠ same role".
   - Columns are build-a…build-d; each cell holds start, length and permissions.
   - Cells that differ from the inspected build carry the ± marker and the word "differs". A block missing on a build reads "absent".
   - A **Class** column classifies each differing row with the variance-class glyph and word (≈ compile variance, ∼ entropy variance, ≠ source variance, ? unknown), with its evidence level:
     - solid only when source, toolchain and flag identity are recorded for both builds ("same source revision digest 71ad; flags differ");
     - dashed "hypothesis (heuristic)" otherwise, with its basis ("basis: length only");
     - "unknown" when no evidence exists.
   - Alignment is presentation only. Nothing is merged or copied between builds.

## Edits and doctrine

- **Program-local, never propagated.** Memory blocks, the image base and overlays belong to one build. No edit here offers "propose to counterparts". The alignment view is read-only.
- **Single target confirms in place:** rename, permission and flag toggles, and the comment on one block, through the inline editor.
- **ConfirmDialog** for everything that restructures memory or can destroy markup:
  - add, move, split, expand, merge and delete;
  - initialize and set uninitialized;
  - rename overlay space;
  - set image base.

  Each dialog names the build, the blocks and the consequence:
  - **Set uninitialized**: "Makes .bss on build-b uninitialized. Ghidra removes every function, instruction, data item and outgoing reference in that block: 0 functions, 214 data items, 12 references. This cannot be undone here unless the catalog offers undo for this transaction."
  - **Delete**: names what the block holds.
  - **Set image base**: names the anchors it affects. Anchors recorded as `module_rva` stay valid. Anchors and pinned locators recorded as absolute addresses on this build become degraded until re-resolved, and the dialog lists how many ("3 absolute anchors on build-b will read degraded"). Overlay blocks do not move with the image base, and the dialog says so.
  - **Rename overlay space**: states Ghidra's note that open comparisons may misbehave until the program is reopened.
- **No analysis on Save.** Memory edits never trigger analysis or re-disassembly. The OutcomeCell's terminal words and the "◷ predates job ‹id›" marks on cached Listing and decompile views say what may now be stale.
- **One writer.** With the build's lock owned elsewhere, or a versioned program without this session's exclusive checkout, the operations stay listed with the reason, and Run is refused ("build-b is checked out exclusively by another session").
- **Undo is per transaction**, only when the catalog exposes it. A memory restructure that Ghidra cannot undo cleanly says so in its dialog.

## States

| State | Shown as |
|---|---|
| Not loaded | "Not loaded · Enter to load build-c" (per build column in Align builds; nothing opens until Enter) |
| Overlay | the start carries the overlay space prefix; the row says "overlay · does not move with the image base" |
| Uninitialized | the word "uninitialized", and "no bytes" in the byte-source cell |
| Editing | the inline editor under the row; the row keeps its current values until the terminal result |
| Edit pending | the row's OutcomeCell; nothing optimistic |
| Stale | "◷ build-b changed since read by job a3f9 · Refresh" |
| Checked out elsewhere | the writer line names it; every operation is `aria-disabled` with the reason |

## Linking

- **Publishes:** Go on a block name or start pushes one stop to the Code Browser at the block start on that build. In Align builds, a cell link goes to that build explicitly (announced).
- **Follows:** the inspected build, and the cursor, to mark the block that contains it ("contains cursor"). It is cached and never fetches another build on follow. Not holdable.
- **Targets rendered:** address (start, end, mapped-from address) → the Code Browser at that build · build → its Navigator row · job → the dock Jobs record · receipt that classified a difference → its receipt card.
- **Peek source:** Alt+↓ on a block peeks its cached Listing lines at the start and its byte-source detail. Nothing is fetched.
- **Absent copy:** "absent on build-d" · "no bytes" · "Not loaded · Enter to load build-c" · "unknown · no source identity for build-d".
- **Target-size exception:** address links sit in 28px rows with one link per cell (44px below 700px and with a coarse pointer). Toggle and checkbox cells are 24px.

## Keyboard

- An APG Grid with row focus, and a checkable grid for the multi-block operations: Space or `x` checks, and Shift extends. Enter goes; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the link menu; F2 opens the inline editor on the name.
- Composite-scope ids (the MemoryMapTable grid only; registered in `keymap.json`):
  - `mmap.edit` (`e`) opens the inline editor for the focused block.
  - `mmap.align` (`a`) switches between This build and Align builds.
- Keys only open editors or arm the ActionStrip; Save and Run post. Esc follows `keymap.json` `escapeOrder`.

## Accessibility

- `role="grid"` named "Memory map, build-b, image base 00400000, 7 blocks". Permission cells read in words. Differences in Align builds carry "differs" and the class words, never color alone.
- The inline editor is a non-modal `role="dialog"` named "Edit block .text, build-b". Its review sentence is linked with `aria-describedby` from Save.
- ConfirmDialog is an APG alert dialog; focus starts on Cancel.

## Parity rows covered

- **P03**: the memory map table with every Ghidra column (name, start, end, length, R, W, X, volatile, artificial, overlayed space, type, initialized, byte source, source, comment), plus the image base. Side by side per build in Align builds.
- **P04**: block edits: rename, permissions, volatile, artificial, initialize and set uninitialized, and comment; add, move, split, expand, merge and delete; set image base; rename overlay space. All are program-local, catalog-backed and confirm-gated as above.

## Prior art

- Ghidra help `MemoryMapPlugin/Memory_Map.htm`: block types, overlays and their image-base exception, the editable columns, the uninitialize side effect, the add-block dialog, and the exclusive-checkout requirement for versioned programs.
- Research: relocation- and layout-aware comparison (C3), placement maps (`docs/research/2026-09-29-msvc-optimization-for-decomp.md` §9, view 8), and the variance classes with evidence (Premise, `docs/research/2026-09-29-reference-re-ui-patterns.md`).
- Existing components: ImageDeltaMap (rebuild deltas), ObjectDiff, LocatorGlyph (degraded and pinned anchors), ConfirmDialog, ActionStrip.
