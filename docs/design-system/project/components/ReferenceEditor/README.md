# ReferenceEditor

The editor for references from one code unit on one explicit build: add and edit memory (including offset), external, stack and register references, and set ref-type, operand and primary. It also carries the instruction-flow, instruction-length and fallthrough overrides, and the batch verbs that create references from a selection or an offset table.

**Use it** from the Listing's link menu on an instruction, operand or data unit: References… and Add reference… (E07), Override flow… (E02), Set fallthrough… (E03), and Create offset references table… on a selection (E09). A stack or register operand opens it on that panel (E10). XrefPanel's outgoing rows offer Edit reference… as well. It replaces Ghidra's References dialog, the Add/Edit Reference dialog, and the Modify Instruction Flow and Set Fallthrough dialogs. It opens inline under the Listing row, pushing the rows below down. The static 8080 surface may render it as a dialog anchored to the row, with identical words, fields and states. E08 (create the default reference, delete all references on a code unit) stays a Listing link-menu verb through the ActionStrip; its result appears in this editor's reference list.

**Consumer provides**

- **The source:** the build, address, code unit text, operand list and basis generation; the stored references from it (kind, operand, destination, ref-type, primary, source (user, analysis, import or default)); and the writer state.
- **The build's own spec:** its address spaces, its register list and its ref-type list.
- **Stack binding:** the function's frame, used to bind stack references to variables (the same stored frame StackFrameEditor edits).
- **External binding:** external programs and locations, for external references.
- **Decoding:** the decoded instruction length and any flow, length or fallthrough overrides already stored.
- **Counterparts:** the anchor pair to the counterpart code unit on other builds, if one is recorded, with that build's references as last read.
- **Actions:** the catalog actions from `GET /api/v1/actions` for adding, editing and deleting references, flow, length and fallthrough overrides, and batch creation. `get-references` is read-only; the verbs are "catalog action needed". No action id is named here.

**Anatomy**

1. **Header.** The source address and code unit text, and the catalog action label marked "(catalog)".
2. **Source bar**, bound when opened: the framed target build chip, the containing function link, the Operand picker (mnemonic, or operand N with its text) and the writer line.
3. **Reference list.** A grid of every reference from this code unit with these columns: operand, kind, destination (an address link that always carries its build), ref-type, primary, source, and a Delete button per row. Deleting one reference is a single-target edit that confirms in place.
4. **Kind tabs** (APG Tabs, manual activation): Memory, External, Stack and Register.
   - **Memory:** To address, which is an address on this build and is never re-resolved into another build. It also has an offset reference (base + signed 64-bit offset), ref-type (data or flow kinds from this build's list) and Primary. The rule is stated: "Only memory references may share an operand; stack, register and external references are one per operand."
   - **External:** the external program name, the external label or address, and the ref-type.
   - **Stack:** the stack offset. The panel names the variable it binds in this build's frame ("binds `slotIndex` in build-a's frame"), or "no variable at −0x10".
   - **Register:** the register, from this build's language only, and the variable or parameter it binds ("binds parameter `name` (custom storage EAX:4)").
5. **Flow and fallthrough, this build only.**
   - Flow override: none, branch, call, call-return or return (E02).
   - Instruction length override, with the decoded length beside it (E02).
   - Fallthrough address, with Auto override and Clear override (E03).
   Each states its effect in words: "changes how build-a's decompile reads this instruction".
6. **Review block.** The catalog action, source → destination, ref-type and primary, the build, the stale-decompile note and "Other builds are unchanged".
7. **Footer.** Save (Enter), Cancel (Esc) and the tier note.
8. **From a selection** (E09):
   - Add memory references from a selection. It previews one row per scalar operand whose value is a valid address on this build.
   - Create offset references table. It takes a base, an entry size (2, 4 or 8), a count taken from the selection, and Signed, and previews each computed destination with what is there ("instruction", "undefined bytes").
   - Both are a batch: "Create 4 references…" opens ConfirmDialog. Targets are never disassembled by this step.
9. **Counterpart.** An info line compares the counterpart code unit, reached through a recorded anchor ("build-c at 0041b21c, via anchor 0041c89a ↔ 0041b21c"), and lists its references as last read. The two are compared, never merged. References are program-local. A proposal to a counterpart is offered only when both the source and the destination are anchor-mapped, and it goes through ConfirmDialog with a preview on that build. Otherwise it reads "not offered: destination 0041f020 has no anchor on build-c".

**Confirm tier**

- **Confirmed in place** with Enter or Save: adding, editing or deleting one reference; setting the primary; a fallthrough set, auto override or clear (E03 is CAT and 1W).
- **ConfirmDialog:** a flow override and an instruction-length override. They change the function body and flow on that build, so the dialog says "nothing is re-disassembled or re-analyzed unless that is admitted as a job". Batch creation from a selection or table and any counterpart proposal also go through ConfirmDialog.
- **Validation before anything posts:**
  - a destination outside this build's address spaces;
  - mixing kinds on one operand;
  - a second stack or register reference on one operand;
  - a register not in this build's language;
  - an instruction length that does not fit the bytes.
  Each is reported inline with ✕ and the fix, and "Nothing was posted".
- **Modification conflict (MC):** both reference sets are shown side by side, with Save mine or Keep arrived. Neither is pre-picked.
- **No analysis (NA).** A flow change never triggers re-disassembly or auto-analysis. The Listing marks the affected range "◷ predates job ‹id›" until an admitted job runs.

**States**

- editing;
- invalid;
- no change to submit;
- awaiting ConfirmDialog;
- pending, admitted, running, then finished or failed, shown as an OutcomeCell on the Listing row with its job link, for example `a3f9`;
- ambiguous outcome ("Checking whether the operation completed"), which disables mutation for this code unit;
- conflict (⇄);
- waiting at gate;
- an empty reference list ("No references from this code unit on build-a");
- counterpart not anchored.

**Linking**

- **Publishes:** nothing. The draft is durable workspace state.
- **Follows:** nothing while open. It is bound to the build, code unit and operand. It cannot be held.
- **Targets rendered:**
  - each destination address → the Code Browser at that build and address;
  - an external location → its import row (SymbolTree Imports);
  - a bound variable → its decompiler variable;
  - the containing function;
  - the counterpart code unit → the Code Browser at that build (the anchor pair is named);
  - the job → the dock Jobs record.
- **Peek source:** Alt+↓ on a destination reads the cached listing at that address on that build. On the counterpart, it reads its stored references.
- **Absent copy:** "No references from this code unit on build-a" · "no variable at −0x10" · "undefined bytes" · "not offered: destination ‹addr› has no anchor on ‹build›" · "No reference change to submit".
- **Target-size exception:** none. Delete buttons and controls are 24px or more, and 44px below 700px.

**Keyboard**

- Tab moves through fields. The reference list is an APG Grid (↑/↓, Delete on a focused row arms that row's Delete button; nothing posts until Enter). The kind tabs follow APG Tabs with manual activation. Enter saves and Esc follows `escapeOrder`.
- Proposed keymap ids:
  - `code.references` (code scope; no default key, because Ctrl+R reloads the page; the path is the link menu or the palette entry "Edit references");
  - `refs.flowOverride` (palette only);
  - `refs.fallthrough` (palette only).

**Accessibility**

- A non-modal inline `role="dialog"` named "References from ‹address›, ‹build›". The Listing row carries `aria-expanded` and `aria-controls`.
- The kind picker is an APG tablist named "Reference kind". The reference list is a grid named "References from ‹address› on ‹build›". Delete buttons are named by their destination and operand.
- Review and consequence text is visible before Save (WCAG 3.3.4). Errors are linked with `aria-describedby`. ConfirmDialog follows APG Alert dialog.

**Parity rows covered**

- E02 flow override and instruction length; E03 fallthrough set, auto override and clear.
- E07 the add and edit references panels, ref-type, operand and primary; E09 references from a selection and the offset references table; E10 stack and register references and their variable binding.
- Also E08: the create-default and delete-all verbs run through the ActionStrip, and their results appear in this list.

**Prior art**

- Ghidra's References plugin: forward references, the Add/Edit Reference panels, and Create Offset References Table. Also Ghidra's Modify Instruction Flow and Override Fallthrough.
- IDA's cross-reference and user-xref dialogs.
- What changes here: one explicit build, destinations never re-resolved, counterparts reached only through anchors, and no analysis side effects.
