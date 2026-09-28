# VariantLedger

The terminal outcome grid: method (reconstruction, original-style rebuild) × variant (byte-accurate C+assembly-floor, max-C), each cell with its own receipt.

**Consumer provides** for each cell the whole-file equality fact, the fresh build identity and hash, and the floor contribution count.

- Four independent cells; never borrow a receipt between them. A cached receipt guides reuse but is not the terminal fresh rebuild.
- Until a build's hash equals the shipped binary, whole-image recovery is unproven; say so plainly.
