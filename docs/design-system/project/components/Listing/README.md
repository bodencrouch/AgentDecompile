# Listing

The continuous instruction listing: flow, address, bytes, mnemonic, operands and xref hints, synchronized with the decompiler.

**Consumer provides** rows from existing analysis and the current address; the decompile pane's token mapping when one exists.

- Sits in a `code-bg` well with `shadow-inset`, `type-code`. Addresses `address`, mnemonics `ink-strong`, bytes and xrefs `ink-muted`, symbol operands `lane-identity-ink`.
- The current line uses `row-selected-bg`. When no listing ↔ decompile mapping exists, say so; never fabricate one.
- Bytes and processor context stay visible: the listing is interpreted evidence, not ground truth.
- Opening a listing never reanalyzes; an empty listing is a StateNotice, not permission to analyze again.
