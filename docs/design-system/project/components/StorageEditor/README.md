# StorageEditor

A genuine editor for custom parameter and return storage: ordered register and stack pieces validated against the selected program, opened inline under the signature line where the signature is read.

**Use it** from DecompileView's link menu (Edit storage… in the Edit group on a parameter or the return type) or the signature line, on the function's own build. It replaces a separate signature dialog.

**Consumer provides** the function, build and its parameters with datatype and current storage; the registers and stack model from the selected program's language and compiler spec; the catalog action that sets storage, read from `GET /api/v1/actions` (no action id is named here); the draft; and after submission the job, its receipt and the recorded storage.

- **Inline placement.** It opens under the signature line and pushes the code below it down; it never covers the signature. Esc restores the text and returns focus to the token (Keymap Esc order).
- **Target block**, bound when opened: the function, the build, the parameter ordinal ("parameter 2 of 3") and its current storage. Registers and the stack model come from the selected program; the block names their source ("from build-a's compiler spec"). Guide-example ABI sizes or register assignments are never hardcoded.
- Each piece is a row: kind (register or stack), register or stack offset, size. Invalid sizes, unknown registers, overlapping pieces or non-integer offsets are reported on Save with the reason inline, and focus moves to the first piece that needs a fix.
- **Save stays enabled.** When the draft equals the current storage, Enter or Save posts nothing and shows "No storage change to submit" (linked to Save by `aria-describedby`, and announced politely).
- **Review block**, confirmed in place: the catalog action by its label, old → new pieces, the build, and "Callers' cached decompile on build-a will be marked stale; nothing is re-decompiled." Callers then carry "◷ predates job ‹id›" until each is decompiled with Enter. Enter or Save posts once.
- **Acceptance checks.** The posted pieces equal the edited draft, and an unchanged draft posts nothing. After the terminal result the band or notice compares the recorded storage with the draft: "Posted pieces equal the draft" or "Piece 2 is +0x10; the draft was +0x0c". Nothing is shown before the terminal result. The defect these checks guard against, a parameter-storage button that resubmits unchanged storage, is reported in `docs/dashboard-design/2026-09-20-ghidra-guide-capability-inventory.md` from a source read; it has not been observed live.
- Edits are scoped to one concrete build. Drafts persist per function across navigation in durable workspace state and are never in the URL.
- **Parity.** The static 8080 surface may render the editor as a dialog anchored to the signature, with identical words, fields and states.

**Linking**

- **Publishes:** nothing. The draft is durable workspace state, not location.
- **Follows:** nothing while open; it stays bound to its function, build and parameter. A draft stays with its function when the selection moves and returns with it. Not holdable; held panes are read-only and never open it.
- **Targets rendered:** the function → the Code Browser at that build and address · the convention's source → the program's compiler spec in words · the job → the dock Jobs record.
- **Peek source:** none; the editor reads the program's stored language and compiler spec.
- **Absent copy:** "No storage change to submit" · "Register model not loaded for build-c. Open to read it." · "Posted pieces differ from the draft".
- **Target-size exception:** none; rows are 28px and controls 24px or more, 44px below 700px.

**Keyboard**

- Enter enters edit mode on a cell; Tab moves between cells in edit mode; Alt+Shift+↑/↓ reorder a piece (`storage.pieceUp`, `storage.pieceDown`; plain Alt+↓ stays Peek). Enter in the footer or Ctrl/Cmd+S saves. Esc follows the one order in `keymap.json` `escapeOrder`. F6 always leaves the region.

**Accessibility**

- A table with a caption naming the parameter and build; invalid pieces carry `aria-invalid` and `aria-describedby` to their reason; the footer status is `role="status"` because the operator's own action caused it.
- The editor is a non-modal `role="dialog"` named "Edit storage · parameter 2"; the invoking token carries `aria-expanded` and `aria-controls`.

**Removes switching:** J12 edit a signature, calling convention or custom storage and verify the dependent views, 5 → 1, plus one per caller verified (Enter decompiles it), from the plan ledger (U185).

## Behavior

- "↵ 1×: Enter or Save posts once, confirmed here." (formerly the `↵ 1×` chip in the review)
- "Nothing is corrected automatically." (formerly the `≠ auto-fix` chip on Posted ≠ draft)
- "⊸ bound: the target was bound when the editor opened."
