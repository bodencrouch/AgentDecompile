# VariantLedger

The terminal outcome grid: method (reconstruction, original-style rebuild) × variant (byte-accurate C+assembly-floor, max-C), each cell with its own receipt.

**Consumer provides** for each cell the whole-file equality fact, the fresh build identity and hash, the floor contribution count, the cell's receipt and producing job, and for a differing cell its differing regions.

- Four independent cells; never borrow a receipt between them. A cached receipt guides reuse but is not the terminal fresh rebuild.
- Until a build's hash equals the shipped binary, whole-image recovery is unproven; say so plainly.
- "equal" and "differs" are words beside their glyphs; the cell's ProvenanceStamp says fresh or reused.

**Linking**

- **Publishes:** nothing.
- **Follows:** `build`, after the settle; not holdable.
- **Targets rendered:** each cell's receipt → the receipt card · a differing cell's byte count → the ImageDeltaMap for that rebuild (`ws=recovery&panel=report&receipt=…`), and each region there → the Listing at the range start with the ObjectDiff pair · the producing job → the dock Jobs record. Link names read "Whole-file equality, reconstruction, byte-accurate C+floor, equal, receipt 5e0a".
- **Peek source:** the stored rebuild receipts and region summaries.
- **Absent copy:** "not run" (no link, no receipt) · "reused receipt · not a fresh rebuild" · "whole-image recovery unproven".
- **Target-size exception:** none; cell links are 24px.

**Accessibility**

- A table with row headers (method) and column headers (variant); each cell's fact is glyph plus word.

**Removes switching:** opening the Recovery workspace, then the rebuild receipt, then the image diff to see where a variant still differs (J34).
