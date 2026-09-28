# Listing

The continuous instruction listing: flow, address, bytes, mnemonic, operands and xref hints.

**Consumer provides** rows from existing analysis (address, bytes, mnemonic, operands, labels, flow and xref counts) and the current address.

- Sits in a `well` with `shadow-inset`; set in `code`. Addresses in `address`, mnemonics `ink-strong`, bytes and xrefs `ink-muted`, symbol operands `lane-identity-ink`.
- The current line uses `selection`; the decompile pane highlights the matching token when a mapping exists, and says so when it does not.
- Keep bytes and processor context visible: the listing is interpreted evidence, not ground truth.
