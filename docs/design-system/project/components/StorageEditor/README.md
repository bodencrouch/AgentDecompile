# StorageEditor

A genuine editor for custom parameter and return storage: ordered register and stack pieces validated against the selected program, placed inline where the signature is read.

**Consumer provides** the function, its parameters with datatype and current storage, the registers and stack model from the program's language and compiler spec, the draft, and after submission the job and the re-read storage.

- **Inline placement**: it opens under the signature line in the DecompileView (F2 or the token menu on a parameter), not on another page; Esc restores the text and returns focus to the token.
- Each piece is a row: kind (register or stack), register or stack offset, size. Invalid sizes, unknown registers, overlapping pieces or non-integer offsets block submission with the reason inline; Review change moves focus to the first piece that needs a fix.
- Submission reviews the catalog action before mutation (ActionStrip, then ConfirmDialog) and shows conflicts explicitly. When the draft equals the current storage, it says "No storage change to submit" and nothing is sent; a button never resubmits unchanged values.
- **Edited-storage acceptance check**: after the job's terminal result the storage is re-read and compared with the draft: "Re-read after job b7e2: storage matches the draft" or "differs: piece 2 is +0x10, draft was +0x0c". Nothing is shown before the re-read.
- Conventions and registers come from the selected program; never hardcode guide-example ABI sizes or register assignments. Edits are scoped to one concrete build.
- Drafts persist per function across navigation and are never in the URL.

**Linking**

- **Publishes:** nothing. Submission arms the ActionStrip; the draft is durable workspace state, not location.
- **Follows:** the primary `entity`, `build` and `addr` (the function); a draft stays with its function when the selection moves and returns with it. Not holdable; held panes are read-only and cannot edit.
- **Targets rendered:** the function → the Code Browser at that build and address · the convention's source → the program's compiler spec in words · the submitted job → the dock Jobs record · a conflicting value → NameProvenance or the conflicting edit for that entity and build.
- **Peek source:** none; the editor reads the program's stored language and compiler spec.
- **Absent copy:** "No storage change to submit." · "Register model not loaded for build-c. Open to read it." · "Re-read pending · job b7e2".
- **Target-size exception:** none; rows are 28px and controls 24px or more.

**Keyboard**

- Enter enters edit mode on a cell; Tab moves between cells in edit mode; Esc leaves edit mode and restores the value; Alt+↑/↓ reorder a piece. F6 always leaves the region.

**Accessibility**

- A table with a caption naming the parameter and build; invalid pieces carry `aria-invalid` and `aria-describedby` to their reason; the status line is `role="status"` because the operator's own action caused it.

**Removes switching:** opening a separate signature dialog and then the Listing to check that dependent views updated after a storage edit (J12).
