# SignatureEditor

The Edit Function Signature editor for one function on one explicit build. It covers name and namespace, the calling convention from that build's own compiler spec, return type, parameters, varargs, No return, inline, custom storage (it hosts StorageEditor), call fixup, thunk target and purge. It has a call-site override mode. Per-build conventions sit side by side, and proposals to counterparts pass through an ABI gate.

**Use it** from the function name's link menu in DecompileView or the Listing: Edit signature… or Retype return… (D13, D17). For the call-site mode, open it from the callee token: Override signature at this call…, Edit signature override… or Remove signature override (D18). The Listing's function header opens it for purge (F10), and a thunk row opens it for the thunk target (F04). It opens inline under the signature line and pushes the code down. The static 8080 surface may render it as a dialog anchored to the signature, with identical words, fields and states. It is the design-system counterpart of the source FunctionEditor named in the capability inventory.

**Consumer provides**

- **The function:** the entity, its build, address and basis generation, the stored prototype (name, namespace, return type and storage, parameters with type and storage, the convention, varargs, No return, inline, custom storage, call fixup, thunk target, purge and signature source), and the writer state.
- **The spec:** from the selected build's own compiler spec, its calling conventions, registers and stack model, and named call fixups. Nothing comes from another build.
- **Counterparts:** for every other build, the counterpart with its identity-edge state and the prototype and storage as last read (or "not loaded"), and any recorded variance witness (for example a compiler-flag or rich-header receipt).
- **Callers and actions:** the known caller count on the target build, or "callers not indexed". The catalog actions from `GET /api/v1/actions` for setting the prototype, convention, storage, attributes, call fixup, thunk target, purge, namespace, and for call-site overrides. No action id is named here.
- **Results:** after Save, the job, its receipt and the re-read prototype.

**Anatomy**

1. **Header.** The function name, the catalog action's label (never marked "(catalog)"), and the signature source change ("analysis → user-defined").
2. **Target bar**, bound when opened.
   - It shows the framed target build chip, the function address link, the basis generation and the writer line.
   - A standing sentence reads "Conventions, registers and call fixups come from build-a's compiler spec."
   - The target never follows the selection.
3. **Fields.**
   - Namespace, with the PascalCase hint (S12).
   - Name.
   - Calling convention: a list of only the conventions in this build's spec, plus "unknown" (F06).
   - Return type, with its storage and an Edit storage… button that opens StorageEditor under the row (D13, F07).
   - Call fixup: the named fixups in this build's spec, or "none" (F09).
   - Purge: bytes, or "unknown" (F10).
   - Attributes: checkboxes for Varargs, No return, Inline and Custom storage (F08).
   - Thunk: "not a thunk" or "thunk of ‹target›", with Set thunk target… and Clear thunk… (F04).
4. **Parameter grid.** One row per logical parameter, keyed by identity, not by ordinal alone: ordinal, name (camelCase hint), type (the draft), and one storage column per build, with the target column framed.
   - The last row gives each build's convention and purge.
   - Storage that differs from the target carries ± and a variance class: compile variance, entropy variance, source variance or unknown.
   - A variance class is solid only when source, toolchain and flag identity are recorded for both builds, and then it names that record. Otherwise it is a dashed "hypothesis (heuristic)" that names its basis and what was not checked.
   - A build where the function is unresolved (build-d in the example) reads "◌ unresolved" in every cell. Nothing is read, guessed or carried over from another build's address.
   - Example of a hypothesis: an LTCG custom convention on build-c, where the basis reads "LTCG objects in build-c's rich header; parameters arrive in EAX and EDX". A removed dead parameter on an LTCG build is compile variance by hypothesis, never source variance by default.
   - Add, remove and reorder parameters with Alt+Shift+↑ and Alt+Shift+↓.
   - With Custom storage on, each parameter's storage cell opens StorageEditor. Without it, storage reads "auto" from the convention.
5. **Review block.** It states exactly what posts: the catalog action, old → new prototype and attributes, the target build, the caller count and "their cached decompile is marked stale and nothing is re-decompiled", and "Other builds are unchanged".
6. **Footer.** Save on ‹build› (Ctrl/Cmd+S), Cancel, and the confirm-tier note.
7. **Propose to build-b, build-c, build-d.** This appears only after Save reaches its terminal result.
   - Each recipient row shows the counterpart link with its edge word, a preview of the prototype on that build, and the ABI gate result.
   - A recipient passes only when its convention, registers and stack model admit the same storage.
   - A blocked recipient says why ("custom register storage; a __thiscall prototype would misplace name and size").
   - Names and types may be proposed separately from storage.
   - Propose… opens ConfirmDialog naming each recipient and its caller count. Each recipient gets its own outcome.

**Call-site override mode**

- The editor is bound to one call instruction in one function on one build, and names the call address, the containing function and the callee.
- It edits only the override prototype. Save override confirms in place (D18, CF-in). Remove override confirms in place too.
- The counterpart call on another build is reached only through recorded anchors ("reached through anchors only; not overridden by this edit"). There is no override proposal by offset.

**Confirm tier** (35 Confirming edits)

- **Confirmed in place** with Enter or Save: name, namespace, inline, call fixup, thunk target, and a call-site override.
- **ConfirmDialog:** any prototype change (return type, parameters, convention, varargs, purge), because a callee-signature edit counts as cross-build and changes every caller. No return always confirms, because it changes the flow of every caller: "nothing is re-disassembled or re-analyzed unless that is admitted as a job". Clearing a thunk and every proposal also confirm. The dialog names the function, the build and the known caller count, or "callers not indexed".
- **Save stays enabled.** An unchanged draft posts nothing and says "No signature change to submit".
- **Modification conflict (MC)** shows both prototypes. "Save mine over gen ‹n›", "Keep the arrived signature" and Cancel are offered, and none is pre-picked.

**States**

- editing;
- invalid ("`2nd` is not a C identifier", "R8D is not a register in build-a's spec", "Purge must be a byte count or unknown");
- no change to submit;
- awaiting ConfirmDialog;
- pending, admitted, running, then finished or failed, shown as an OutcomeCell on the signature line with its job link, for example `a3f9`;
- ambiguous outcome ("Checking whether the operation completed");
- conflict (⇄);
- convention unknown ("Convention unknown on build-c", with Custom storage offered, never a guessed convention);
- waiting at gate (another writer, named as reported);
- not loaded, for a comparison build;
- unresolved, for a build with no located counterpart ("◌ unresolved"; that build is blocked in the Propose step).

After the terminal result, BeforeAfterBand shows old → new under the signature line. Callers carry "◷ predates job ‹id›" until each is decompiled with Enter.

**Linking**

- **Publishes:** nothing. The draft is durable workspace state, never in the URL.
- **Follows:** nothing while open. The editor stays bound to its function (or call site) and build, and a draft returns with its function. It cannot be held.
- **Targets rendered:**
  - the function address → the Code Browser at that build and address;
  - a counterpart → that build's function, with its edge word;
  - the thunk target → the target function (Enter follows it, read-only);
  - the containing function in call-site mode;
  - the job → the dock Jobs record.
  - The spec source is words, not a link.
- **Peek source:** Alt+↓ on a counterpart reads its stored prototype and storage, "as read ‹time›". On the thunk target it reads the cached listing at the target. Nothing is decompiled.
- **Absent copy:** "not loaded" · "absent" · "◌ unresolved" · "callers not indexed" · "No signature change to submit" · "Convention unknown on build-c" · "blocked: ‹why›" · "not previewed".
- **Target-size exception:** none. Controls are 24px or more (checkbox targets are 24px), and 44px below 700px.

**Keyboard**

- Tab moves through the fields. The parameter grid is an APG Grid: Enter or F2 edits a cell and Esc leaves it. Ctrl/Cmd+S saves. Esc follows `keymap.json` `escapeOrder` and returns focus to the invoking token.
- Keymap ids (registered):
  - `code.editSignature` (code scope; no default key in any profile, because `y` (ida profile) and `t` (ghidra profile) on a function name already mean set data type; the path is Shift+F10 → Edit signature… and the palette);
  - `signature.paramUp` and `signature.paramDown` (Alt+Shift+↑ and Alt+Shift+↓, grid);
  - `signature.editStorage` (no default key; the proposed Alt+S was not registered. It is palette and row menu only and opens StorageEditor for the focused parameter).

**Accessibility**

- A non-modal `role="dialog"` (inline) named "Edit signature ‹function›, ‹build›". The invoking token has `aria-expanded` and `aria-controls`.
- The attributes are a labelled checkbox group. Each checkbox has a 24px target with a 14px drawn box.
- The parameter grid is named and described by its key. Per-build storage cells read in words ("build-c, EAX 4 bytes, differs from build-a").
- Errors are linked by `aria-describedby` and set `aria-invalid`. The review block is visible before Save (WCAG 3.3.4). ConfirmDialog follows APG Alert dialog.

**Parity rows covered**

- D13 retype the return; D17 the Edit Function Signature dialog; D18 call-site signature overrides.
- F04 thunk target; F06 calling convention from the build's spec; F07 custom storage (hosted StorageEditor).
- F08 varargs, No return and inline; F09 call fixup; F10 purge. The other half of F10, the stack depth change at one instruction, is the Listing's (Function group, **Set stack depth change…**). On a call instruction that dialog asks Local or Global; **Global** opens this editor on the callee with the Purge field focused and prefilled with the entered value, and it confirms here through ConfirmDialog, as every callee-signature edit does ("Set purge of String::CStr to 4 on build-a · 31 callers"). A purge is a per-build fact of each build's code generation: it is compared across builds in the last row of the per-build conventions, never copied between them. Removing a function (the Listing's Delete function…) removes its purge with it.
- S12 the namespace field.
- Also F11: parameter rename and retype stay in InlineRename. This editor shows them in the grid for batch edits.

**Prior art**

- Ghidra's Edit Function dialog: calling convention, inline, No return, varargs, call fixup and custom storage. Ghidra's decompiler Override Signature, and its thunk functions.
- IDA's function prototype editing, including `__usercall` custom storage.
- The research note [MSVC optimization for decomp](../../../../research/2026-09-29-msvc-optimization-for-decomp.md), T5: the LTCG custom calling convention, and why Ghidra shows `in_EAX`. Also T12 on incremental-link thunks.
- What changes here: per-build conventions side by side with variance words, the explicit target, and proposals only through the ABI gate.

## Behavior

- "Purge: "unknown" is allowed." (formerly in the purge tip)
- "Never borrow another build's spec." (formerly the `≠ borrow spec` chip under the storage grid)
- "Following the thunk is a read: Enter on the target link." (formerly the `↵ read` chip on the thunk footer)
- "Names and types can be proposed to build-c separately; its storage stays its own."
