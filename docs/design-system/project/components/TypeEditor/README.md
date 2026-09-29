# TypeEditor

The editor for one data type on one explicit build target: structure, union, enum, typedef/pointer and function-definition modes. Rows are keyed by logical field or value, with one offset or value column per build and a layout check per build before Save. Any propagation to counterparts is a separate "Propose to build-b, build-c" step, gated by confirmation.

**Use it** from a type link: a `type=` link, the TypeManager row (Enter), or the DecompileView type token's link menu (Edit data type…, D22). Retype Field on a field token opens it focused on that field row (D14). Adjust Pointer Offset and Force Field open pointer-typedef mode (D20). Auto Create Structure and Auto Fill in Structure open it with their inferred rows (D21). The Listing's Create structure from selection and the quick Edit Field open it too (E06), as does TypeManager's New… verbs (T05). It replaces Ghidra's Structure, Union and Enum editors and the pointer-typedef settings dialog.

**Consumer provides**

- **Target and writer:** the type and its target, one build's program type manager or one archive, with the basis generation, and the writer state for that target.
- **Draft source:** the stored components of the target (offset, size, datatype, name, comment, bitfield position), plus packing, alignment and size.
- **Per-build comparison:** for every other build in the related-build scope, the same type's stored layout (or "absent" or "not loaded") with its read time, and the identity edge for the type on each build.
- **Language facts:** each build's language facts from its own spec (pointer width, endianness, default alignment).
- **Evidence:** any recorded variance witness, the use count per build (or "uses not indexed"), and for inferred layouts the usage basis (the addresses and access widths).
- **Actions:** the catalog actions from `GET /api/v1/actions` that edit structures, enums, typedefs and function definitions, and the one that resolves a modification conflict. No action id is named here.
- **After Save:** the job, its receipt and the re-read layout.

**Anatomy**

1. **Header.** The mode and type name ("Edit structure CacheEntry") and the catalog action label, marked "(catalog)". The draft's own undo and redo depth appears here ("draft · undo 1 · redo 0").
2. **Target bar**, bound when the editor opens. It names the target build (a framed "target" chip, such as `build-a`) or the archive, the category, the basis generation and the writer line in ResourceState words. A standing sentence says other builds are read for comparison only. The target never changes while the editor is open. A different build is a new editor.
3. **Properties.**
   - Name, with the hint "Types use PascalCase."
   - Description.
   - Packing: None, Default or Explicit ‹n›.
   - Alignment: Default, Machine or Explicit ‹n›, with the computed alignment for the target build.
   - Size. A size change resizes every use, so Save routes it to ConfirmDialog.
4. **Component grid** (composite modes). There is one row per logical field, keyed by field identity rather than by offset or order. Filler rows are shown, never hidden. Each row has these columns:
   - Field, with the snake_case hint;
   - Type (draft), showing old → new when edited;
   - one column per build with `+offset : size`, the target column framed;
   - Across builds, a correspondence word: same, shifted, resized, retyped, added, removed or reordered;
   - Comment.

   Size and alignment form the last row. A difference carries its variance class, classified as compile variance, entropy variance, source variance or unknown. A solid frame names its witness ("build-d language is x86-64, pointer width 8"). A dashed frame reads "hypothesis" and names its basis ("same fields in the same order"). Unknown is a word.
5. **Composite edit actions**, each a draft operation until Save:
   - insert undefined byte;
   - move up or down;
   - duplicate, and duplicate multiple;
   - delete;
   - clear;
   - create array (with an element count);
   - create flexible (zero-element) array, the last component only;
   - unpackage;
   - create structure from selected components;
   - add and edit bitfields, in non-packed structures only;
   - go to offset;
   - search in the editor;
   - hex display, a per-viewer toggle.
6. **Bit view** for bitfields: one cell per bit of the storage unit. Field bits carry their bit numbers, dotted cells are padding, and a conflict gets a 2px `fact-failed` frame plus the word "conflict". It is a named image whose text key states the bit ranges. Bit order follows each build's endianness and says so.
7. **Layout check per build**, read before Save. Each build gets one row: size before and after, the fields that move, and the result: "fits", "layout identical to build-a", "layout differs … (why)", "absent" or "not loaded". The check never opens a program. A build that is not loaded says "not loaded" and is not checked.
8. **Review block and footer.** The review block states exactly what posts: the catalog action, the field, old → new, the size, the use count on the target build and "Other builds are unchanged by Save". The footer holds Save on ‹build› (Ctrl/Cmd+S), Cancel, and a note that draft undo is draft-only while program undo is per transaction in EditHistory.
9. **Propose to build-b, build-c.** This appears only after Save reaches its terminal result. It is a separate group with one row per build that has an accepted identity edge for the type. Each row carries the edge word, a preview of the change on that build, the layout check and an Include checkbox. A recipient whose layout differs from the donor's is blocked and says why ("blocked: layout differs (next +0x18 vs +0x10)"). Propose to ‹builds›… opens ConfirmDialog naming each recipient and its use count. Each recipient gets its own job and outcome (PropagationTransfer draws the transfer). Nothing is applied automatically.

**Modes**

- **Structure and union.** Everything above. A union's rows all sit at +0x0 and its size is the largest member. The per-build column shows each member's size.
- **Enum.** One row per constant, named in COBRA_CASE. Build columns show each value side by side, never merged; "absent" is a word, and a value present only on one build is marked "+ only on build-c". The header has the enum size and a Hex toggle. The actions are Add value, Delete value, and edit name, value or comment. Sort order is a viewer setting.
- **Typedef and pointer.** The base type, then the pointer-typedef settings: offset (a shifted pointer, from Adjust Pointer Offset), address space, image-base relative, and component path (Force Field). The pointer width appears per build, from each build's language. A width difference is a solid compile-variance witness and blocks proposals.
- **Array.** Element type and count. A count is never copied between builds blindly; each recipient previews its own count.
- **Function definition.** Created from a function on one build, with return type, parameters and the calling convention from that build's spec. It opens SignatureEditor for storage. It is not offered on builds whose function uses a convention that the definition cannot express (for example custom register storage from LTCG).
- **Inferred (Auto Create or Auto Fill).** Inferred rows are dashed and read "hypothesis". Their basis is the access address and width on the build they were inferred from. They are never proof of layout (NP). A row becomes a normal row only once the operator names or retypes it. Even then, the other builds' size checks still gate any proposal.

**Confirm tier** (35 Confirming edits)

- **Confirmed in place** with Enter or Save: renaming a field, editing a comment or the description, renaming the type, and adding or editing an enum value on the target build.
- **ConfirmDialog:** a field retype, any change that resizes, overwrites or clears components, a packing or alignment change, deleting components, unpackage, create array, and every proposal. The dialog names the type, the build and the known use count, or "uses not indexed".
- **Save stays enabled.** When the draft equals the stored type, Save posts nothing and says "No change to submit".
- **Modification conflict (MC).** If the stored type changes while a draft is open, a ⇄ notice shows both versions. The choices are "Save mine over gen ‹n›", "Keep the arrived layout" and Cancel. Neither is pre-picked, and arrival order is not a tie-breaker. The choice posts through the catalog's conflict-resolution action.

**States**

- editing (a draft exists, and Save is armed);
- invalid, with ✕ and a message that names the field and the fix ("Size 3 is not valid for `uint`; use 4", or "`2nd` is not a C identifier");
- no change to submit;
- awaiting the ConfirmDialog;
- pending, admitted, running, then finished or failed, shown on the header as an OutcomeCell with its job link;
- ambiguous outcome ("Checking whether the operation completed"), during which Save and Propose are disabled for this type;
- conflict (⇄);
- read-only, for a built-in or read-only archive, where Save is `aria-disabled` with its reason;
- waiting at gate, when the writer is held elsewhere and its owner is named;
- not loaded, for a comparison build.

**Linking**

- **Publishes:** `type=` (with `build=` for the target) when opened by Go. The draft is durable workspace state, never in the URL. A field row focus replaces `type=CacheEntry.name_len` after the settle.
- **Follows:** nothing. The editor stays bound to its type and target build. A draft stays with its type when the selection moves and returns with it. It cannot be held, because held panes are read-only and never open editors.
- **Targets rendered:**
  - a field's datatype → that type's editor on the same build;
  - the source function (function-definition mode) → the Code Browser at that build and address;
  - a use count → the uses of the type on that build;
  - the recipient builds → the counterpart type on that build, with its edge word;
  - jobs → the dock Jobs record.
- **Peek source:** Alt+↓ on a build cell reads that build's stored layout as last read, "as read ‹time›". On a datatype link it reads the stored layout of that type.
- **Absent copy:** "absent" (plain word) · "not loaded" · "uses not indexed" · "No change to submit" · "blocked: layout differs (‹why›)" · "not previewed".
- **Target-size exception:** none. Rows are 28px, controls 24px or more, and 44px below 700px.

**Keyboard**

- APG Grid with cell focus. Arrows move between cells. Enter or F2 enters edit mode on a cell and Esc leaves it, restoring the text. Tab moves between cells only in edit mode. Ctrl/Cmd+S saves (the `save` command).
- Keymap ids (registered; composite scope, active inside the component grid):
  - `typeEditor.moveUp` and `typeEditor.moveDown` (Alt+Shift+↑ and Alt+Shift+↓; plain Alt+↓ stays Peek);
  - `typeEditor.insertUndefined` (`u`);
  - `typeEditor.duplicate` (`d`);
  - `typeEditor.array` (`[`);
  - `typeEditor.clear` (`c`);
  - `typeEditor.delete` (Delete);
  - `typeEditor.gotoOffset` (`o`);
  - `typeEditor.hex` (Shift+H);
  - `typeEditor.draftUndo` and `typeEditor.draftRedo` (Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z, edit scope and grid only; they never undo a program transaction).
- Every action is also in the link menu (Shift+F10) and the palette.

**Accessibility**

- The editor is a `form` named by its heading. The component grid is `role="grid"`, named "Components of ‹type›, draft on ‹build›, offsets per build". It is described by the key, and field names are row headers. Cells that edit carry `aria-readonly="false"`. Invalid cells carry `aria-invalid` and `aria-describedby` to their reason.
- Per-build cells read in words ("build-c, offset 0x18, size 4, shifted"). Glyphs are `aria-hidden` and backed by words.
- The bit view is `role="img"` with the bit ranges in its name.
- The review block is plain text before Save (WCAG 3.3.4). ConfirmDialog follows the APG Alert dialog pattern.
- A conflict is `role="alert"`. Validation errors are polite. Nothing is announced on pending, and the outcome is announced once.

**Parity rows covered**

- D14 retype a field from the field token; D20 pointer-typedef offset and component path; D21 inferred structure rows; D22 edit a data type from a type token.
- T05 create and edit types; T10 the structure and union editor, with every listed action; T11 the enum editor; T12 typedefs, pointers and arrays; T13 function definitions.
- E06 create an array or structure from a selection, and the quick Edit Field.
- Also T19: the hex display here is a per-viewer toggle; the rest of the editor options live in OptionsPanel.

**Prior art**

- Ghidra's Structure Editor: the component grid, non-packed filler, packing and alignment, bitfield view, and actions. Its Enum Editor and pointer-typedef settings also carry over.
- IDA shifted pointers: `__shifted` and `ADJ()`.
- Binary Ninja: create a member at an accessed offset.
- reccmp: field correspondence.
- The research note [reference RE UI patterns](../../../../research/2026-09-29-reference-re-ui-patterns.md), A2–A4: rows keyed by field identity with a column per build, filler shown, and gaps and inferred members marked as inferred.
- What changes here: the explicit target, the per-build layout check, and proposals gated by confirmation.
