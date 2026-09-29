# PatchEditor

The byte-level editor for one explicit build. Its modes are Assemble (patch instruction), Patch data, Bytes, Clear, Disassemble and Create data. Every mode shows a before and after preview of the bytes (original file, current, after), names its exact build target, confirms before writing, and reads the bytes back after the terminal result. Nothing is ever applied to all builds or proposed to counterparts.

**Use it** from the Listing or HexStrip link menu on an instruction, data unit, undefined bytes or a byte range:

- Patch instruction… and Assemble… (X01);
- Patch data… (X01);
- Edit bytes… (N12);
- Clear… and Clear with options… (E04);
- Disassemble… (E01);
- Create data… (E05, E06; arrays, pointers and strings).

The spec maps E01, E04 and E05 to the Listing link menu → ActionStrip. PatchEditor is that verb's preview panel: the ActionStrip still carries the one Run path. The editor opens inline under the Listing row, pushing the rows below down. The static 8080 surface may render it as a dialog anchored to the row, with identical words, fields and states. It replaces Ghidra's Assembler, the Byte Viewer's edit mode, and the Clear, Disassemble and Data dialogs.

**Consumer provides**

- **Target:** the target build (always one, from the invoking row's build; there is no default and no "all builds"), the address or range, the containing function and the basis generation, and the writer state.
- **Memory block:** the block with its initialized, writable and overlay state.
- **Bytes:** the original file bytes at the range (from the program's original-byte record), or "original bytes not recorded", and the current bytes.
- **Language:** the build's language for assembling (candidate encodings with their lengths), decoding and data layout (pointer width, endianness, charsets), and the code units a write would overwrite.
- **Counterpart:** the counterpart address reached through a recorded anchor, with its current bytes as last read.
- **Actions:** the catalog actions from `GET /api/v1/actions` for patching bytes, clearing, disassembling and applying data types. The inventory found no bounded patch tool, only `execute-script` `setBytes`, so these are "catalog action needed". No action id is named here.
- **After Save:** the job, its transaction receipt, and the post-write read.

**Anatomy**

1. **Header.** The mode, the address, and the catalog action label marked "(catalog)".
2. **Target bar**, required and bound when opened:
   - a framed target chip with the build (for example `build-a`);
   - the containing function;
   - the memory block and its state ("initialized · writable in the program");
   - the writer line;
   - the standing sentence "There is no "all builds" target. Another build is a new editor opened on that build."
   If the invoking context has no build (an address link without `build`), the editor does not open. It shows "Address ‹addr› has no build; it exists in build-a, build-c", with one link per build.
3. **Mode tabs** (APG Tabs, manual activation): Assemble, Patch data, Bytes, Clear, Disassemble and Create data.
   - **Assemble.** The current instruction, the assembly input (assembled with this build's language, which the hint says), and a radio group of encodings, each with its bytes and length. A longer encoding names the instructions it overwrites ("Overwrites MOV ECX, [ESI+0x10] at 0041c8b4; that instruction is cleared and not re-disassembled"). A shorter one names the leftover bytes. Assemble… accepts several lines and previews each.
   - **Patch data.** The data unit's type and a typed value input. The value is encoded with this build's endianness and width.
   - **Bytes.** Hex entry over a range, following HexStrip's grid and keys, with a count entry for the range.
   - **Clear.** Clear code bytes, or Clear with options: a checklist of instructions, data, symbols, comments, properties, user, analysis, import and default references, functions, registers, equates and bookmarks. Clear flow and repair is a separate verb. The words "Bytes are kept; only the listed markup is removed" are always shown.
   - **Disassemble.** Follow flow, Restricted to selection, Static, and the processor-mode variants the build's language offers. The preview decodes bytes only and is a dashed "hypothesis until posted". It states where decoding stops.
   - **Create data.** A type input (with array syntax and completion from this build's type manager), the data settings (format, endianness, charset), and the interpreted value preview. Counts and pointer widths are per build, and counts are never copied between builds.
4. **Bytes preview** (`dl`): "original file", "current" and "after" rows in mono, with changed bytes underlined in `fact-stale` (plus the words "Changed byte underlined: 0041c8b2 74 → EB (1 byte)"). Where current differs from original, both are shown, so an earlier patch stays visible.
5. **Review block.** The catalog action, the exact bytes and range, the build, "After the terminal result the bytes are read back and compared with this preview", the stale-decompile note ("nothing is re-disassembled or re-analyzed") and the claim boundary "Patched bytes are not recovery evidence".
6. **Footer.** Patch ‹build›… (or Clear, Disassemble or Create on ‹build›), Cancel, and "Never proposed to counterparts".
7. **Counterparts**, for comparison only. The counterpart's bytes at the anchor-mapped address ("via anchor 0041c8b2 ↔ 0041b242") and "To patch build-c, open PatchEditor on build-c". There is no propose step and no "apply to all".

**Confirm tier**

- **ConfirmDialog:** every byte write (patch instruction, patch data, bytes), which is destructive under N12 and X01. Clear and clear with options (E04) are also destructive. The dialog names the build, the address or range, the byte count and old → new bytes. It says undo is only a program transaction in EditHistory, and that other builds stay untouched.
- **ActionStrip Run** (single target, posts once): disassemble at one address and create data at one address. Disassembling or creating data over a selection is a batch, so it uses ConfirmDialog.
- **Validation before anything posts:**
  - an unassemblable line ("`JMPX` is not an instruction in build-a's language");
  - a value out of range;
  - a write outside an initialized block;
  - a write across a block boundary;
  - a range with no build.
- **Post-write read.** After the terminal result the editor reads the range back once and states "Read back equals the preview" or "Read back differs from the preview", with the differing byte. Nothing is corrected automatically. The transaction receipt is linked from the job.
- **No analysis (NA).** Patches, clears and disassembly never trigger auto-analysis. Follow-on analysis (function creation, reference recovery) is a separate verb admitted as a job.
- **Modification conflict (MC).** If the bytes changed since opening ("current" is now different), the preview is refreshed with a ⇄ notice, and Save is refused until the operator reviews it. It never writes over an unseen change.

**States**

- editing;
- invalid;
- no change to submit (the after bytes equal current);
- awaiting ConfirmDialog;
- pending, admitted, running, then finished or failed, shown as an OutcomeCell on the Listing row with its job link, for example `a3f9`;
- read back equal;
- read back differs;
- ambiguous outcome ("Checking whether the operation completed"), during which writes to this range are disabled;
- conflict (⇄);
- waiting at gate;
- read-only block ("block .rdata is not writable in build-a's memory map; change it in MemoryMapTable");
- original bytes not recorded.

**Linking**

- **Publishes:** nothing. The draft is durable workspace state, never in the URL.
- **Follows:** nothing while open. It is bound to one build and range. It cannot be held.
- **Targets rendered:**
  - the address or range → the Code Browser at that build;
  - the containing function;
  - an overwritten instruction → its Listing row;
  - the counterpart → that build's function through its anchor;
  - the job and its receipt → the dock Jobs record and the receipt card.
- **Peek source:** Alt+↓ on an overwritten instruction reads the cached listing. On the counterpart, it reads its stored bytes.
- **Absent copy:** "original bytes not recorded" · "Address ‹addr› has no build; it exists in ‹builds›" · "undefined bytes" · "No byte change to submit" · "Read back differs from the preview".
- **Target-size exception:** none. Controls are 24px or more, and 44px below 700px. Bytes-mode cells follow HexStrip's rule.

**Keyboard**

- The mode tabs follow APG Tabs with manual activation. The encodings are a radio group. Enter in the assembly field previews, and Ctrl/Cmd+S (or Enter on the primary button) opens ConfirmDialog. Esc follows `escapeOrder`.
- Proposed keymap ids (code scope; keys only open the editor, never write): `code.patchInstruction` (no default key; link menu and palette "Patch instruction"); `code.patchBytes` (no default key); `code.clear` (no default key; Delete is not bound, because a single key never destroys); `code.disassemble` (`d` in the `ida` profile only, matching its habit; default has none); `code.createData` (no default key).

**Accessibility**

- A non-modal inline `role="dialog"` named "Patch ‹mode› at ‹address›, ‹build›". The Listing row carries `aria-expanded` and `aria-controls`.
- The bytes preview is a `dl` named with its range and build. Changed bytes are also stated in words in the sentence after it, never by underline alone.
- The Clear checklist is a labelled checkbox group with 24px targets.
- ConfirmDialog follows APG Alert dialog, with focus on Cancel. The post-write read notice is `role="status"`, because the operator's own action caused it.

**Parity rows covered**

- N12 byte-viewer memory editing (Bytes mode).
- X01 Assembler: Patch Instruction, Assemble… and Patch Data.
- Also, as the preview panel of Listing verbs run through the ActionStrip: E01 disassemble (with the static, restricted and processor-mode variants); E04 Clear, Clear With Options, and Clear Flow and Repair; E05 create data with data settings; and E06 arrays, pointers and strings.

**Prior art**

- Ghidra's Assembler (Patch Instruction, where candidate encodings are offered), the Byte Viewer's editing mode, Clear With Options, and the Disassemble variants.
- IDA's Patch program (Assemble and Change byte) and its patched-bytes list.
- x64dbg's Assemble and Fill.
- What changes here: one explicit build and never all builds, original-byte and before/after preview, a post-write read, and "Patched bytes are not recovery evidence".
