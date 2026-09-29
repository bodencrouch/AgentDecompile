# StackFrameEditor

The stack frame editor for one function on one explicit build. It is the editing counterpart of [FrameLayout](../FrameLayout/README.md): it uses the same logical-slot rows, slot-kind tags, top-down order (higher addresses first) and normalised offsets, but here you edit local size, parameter offset and size, and the stack variables (create, delete, clear, retype, array). The other builds' frames stay beside it as read-only columns.

**Relationship to FrameLayout.** FrameLayout is read-only. It is a rail section, a secondary pane or a MatchExplain drill-down, and it can be held. StackFrameEditor does not duplicate it. It opens from FrameLayout's link menu (Edit frame on ‹build›… in the Edit group, which appears when the catalog exposes a frame action) or from Edit stack frame… on the function name in DecompileView or the Listing. It opens with the same slot order, the same frame-base words ("offsets from EBP after the prologue", "ESP frame normalised to entry ESP") and the same absence words. The two share these parts of FrameLayout's anatomy:

- rows keyed by logical slot, never by offset;
- slot tags `arg`, `return`, `saved`, `EH node`, `cookie`, `buffer`, `local`, `spill` and `align`;
- a 2px `line-control` rule under the saved frame pointer;
- raw ESP offsets shown beside normalised ones;
- dashed hypothesis cells with a named basis;
- register-resident locals as the words "register ‹reg›".

The editor adds these on top: the explicit target, editable cells on the target column, the frame fields, the review block, the Save tier and the Propose step. Its `.ade-slot` tag mirrors FrameLayout's slot tag; the two should become one class at integration. After Save reaches its terminal result, FrameLayout re-reads the frame and the edited rows carry "✎ job ‹id›".

**Consumer provides**

- **Target:** the function, its target build, address and basis generation; the writer state.
- **Target frame:** the stored frame for the target (frame base, frame size, local size, parameter offset, parameter size, return address offset, and stack variables with offset, size, datatype, name and comment).
- **Other builds:** the same function's frame as FrameLayout reads it (normalised offsets, raw offsets for ESP frames, register-resident locals, "not loaded").
- **Slot mapping:** the logical-slot mapping between builds, with its pairing quality (bijective, non-bijective, or insufficient alignment).
- **Evidence:** the recorded variance witnesses, and the stack-reference count on the target build, or "references not indexed".
- **Actions:** the catalog actions from `GET /api/v1/actions` that edit the frame and its variables. The inventory notes that function variable operations cover part of this, and the rest is "catalog action needed". No action id is named here.

**Anatomy**

1. **Header.** "Edit stack frame ‹function›", the catalog action label marked "(catalog)", and a Hex toggle (a per-viewer display setting).
2. **Target bar.** The framed target build chip, the function address link, the frame base in words, and the writer line.
3. **Frame fields.** Frame size (read-only, computed, old → new); Local size; Parameter offset, with the return address offset in words; Parameter size, which is cross-checked against the signature's purge ("matches purge 8 in the signature", or a caution when it does not).
4. **Slot grid.** One row per logical slot, higher addresses first. Columns: slot (tag and name), type (the draft), then one column per build, with the target column framed and editable. Other build cells read as FrameLayout does ("entry ESP −0x8", with the raw offset under it, "none (FPO)", "register EAX", "absent", "not loaded").
   - A draft row carries a 3px `ink-strong` bar and the words "new in draft". A retype shows old → new.
   - Differences carry a variance class (compile variance, entropy variance, source variance or unknown) with its evidence level. Slot order and reuse are compile variance by default, and each such claim is a dashed hypothesis with its basis. A local that exists only on one build, with no inlining explanation, is source variance by hypothesis.
5. **Variable actions.** Create a stack variable at an offset; delete; clear; retype (it opens the type chooser); create array (with an element count); rename and comment (in place); show component path; go to offset.
6. **Review block.** It lists each draft operation, the target build, the stale-decompile note ("nothing is re-decompiled") and "Other builds are unchanged".
7. **Footer.** Save frame on ‹build› (Ctrl/Cmd+S), Cancel, and the tier note.
8. **Propose names and types.** This runs by slot mapping, never by offset, and only after Save reaches its terminal result.
   - Only the name and type of a paired slot are proposed.
   - Offsets, local size and parameter size are never proposed, because each build keeps its own frame.
   - A bijective mapping is eligible.
   - A non-bijective mapping or insufficient alignment blocks the recipient and says why ("insufficient alignment to pair slots"). It never guesses a mapping.
   - Propose… opens ConfirmDialog. Each recipient gets its own outcome.

**Confirm tier**

- **Confirmed in place** with Enter or Save: rename one stack variable, or edit its comment (the InlineRename rules, with the camelCase hint).
- **ConfirmDialog:**
  - create, delete, clear, retype or create array;
  - a change to local size, parameter offset or parameter size.

  These rewrite the frame and every stack reference to those slots. The dialog names the function, the build and the known reference count, or "references not indexed".
- **Validation before anything posts:** overlapping variables, an array that would overwrite slots, non-integer offsets, a parameter size that is not a multiple of the stack alignment. Each is reported inline with ✕ and the fix, and says "Nothing was posted".
- **Modification conflict (MC):** both frames are shown side by side, with "Save mine over gen ‹n›", "Keep the arrived frame" and Cancel. None is pre-picked.
- **Register parameters** have no frame slot. The editor says so and points to StorageEditor on that build ("size lives in EDX on build-c").

**States**

- editing;
- invalid;
- no change to submit;
- awaiting ConfirmDialog;
- pending, admitted, running, then finished or failed, shown as an OutcomeCell on the header with its job link;
- ambiguous outcome ("Checking whether the operation completed");
- conflict (⇄);
- waiting at gate;
- "Not decompiled in this session · Enter to decompile", for a comparison build without stack references. The editor never decompiles on its own;
- not loaded.

**Linking**

- **Publishes:** nothing. The draft is durable workspace state, never in the URL.
- **Follows:** nothing while open. It is bound to its function and build. It cannot be held, although FrameLayout can.
- **Targets rendered:**
  - the function address → the Code Browser at that build;
  - a slot name → its decompiler variable on that build (Go leaves the editor open with its draft kept);
  - a slot's type → TypeEditor;
  - the job → the dock Jobs record;
  - FrameLayout → the read-only frame of the same function (Reveal in).
- **Peek source:** the stored stack-reference analysis for that slot and build (FrameLayout's Peek source).
- **Absent copy:** "absent" · "none (FPO)" · "register ‹reg›" · "not loaded" · "Not decompiled in this session · Enter to decompile" · "insufficient alignment to pair slots" · "references not indexed" · "No frame change to submit".
- **Target-size exception:** none. Rows are 28px, controls 24px or more, and 44px below 700px.

**Keyboard**

- APG Grid with cell focus, the same keys as FrameLayout: ↑/↓ move between slots, ←/→ between build columns, plus Home/End and Ctrl+Home/End. Enter or F2 edits a target cell. Esc leaves edit mode. Ctrl/Cmd+S saves.
- Proposed keymap ids (grid scope): `frame.newVariable` (Insert); `frame.clear` (`c`); `frame.array` (`[`); `frame.delete` (Delete); `frame.hex` (Shift+H, shared with `typeEditor.hex`); `frame.gotoOffset` (`o`).

**Accessibility**

- A `form` named by its heading. The grid is `role="grid"`, named "Stack frame of ‹function› by logical slot, draft on ‹build›, offset per build, higher addresses first", and described by the key. Slot tags and names are row headers.
- Cells read "build-c, entry ESP minus 0x8, raw esp plus 4 after push esi". A draft row reads "new in draft". Invalid cells carry `aria-invalid` and `aria-describedby`.
- The frame fields are labelled inputs. The review block is visible before Save. ConfirmDialog follows the APG Alert dialog pattern.

**Parity rows covered**

- F13, the stack frame editor: local size, parameter offset and size, and stack variables (create, delete, clear, retype, array), plus hex display.
- Also F11, deleting a variable. The spec lists delete as missing; here it is a frame verb behind ConfirmDialog.

**Prior art**

- Ghidra's Stack Frame Editor: local size, parameter offset and size, create array and clear.
- IDA's stack frame view: a pseudo-structure with the special members `r` and `s`.
- Binary Ninja's Stack panel.
- reccmp `stackcmp`: bijective and non-bijective slot pairing.
- The research note [reference RE UI patterns](../../../../research/2026-09-29-reference-re-ui-patterns.md) A5 and B5, and [MSVC optimization for decomp](../../../../research/2026-09-29-msvc-optimization-for-decomp.md) T2 on frame-pointer omission.
