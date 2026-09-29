# ObjectDiff

Verification drawn as the work: original and generated instructions aligned, with changed operands, registers, bytes and relocations highlighted.

**Consumer provides** the exact object pair, aligned rows with the original address of each, relocation interpretation, and the comparison receipt with its job.

- Two wells; differing operands are `mark`ed and the row carries ≠ plus the word "differs". Relocation-aware equality is stated explicitly.
- **Linked cursor** between the wells; F7 / Shift+F7 step differences; runs of equal rows collapse to "N equal rows" and expand in place.
- The ObjectDiff row is also where a SourceRepairDiff line and an ImageDeltaMap region land: the linked row is focused and marked.
- Fresh comparisons are distinct from historical receipts (ProvenanceStamp). A local zero is not full-image or behavior proof.

**Linking**

- **Publishes:** nothing.
- **Follows:** the primary entity and build (the object pair recorded for them), after the settle; holdable (Open beside holds the pair with its basis).
- **Targets rendered:** an original row's address → the Listing at that build and address · a relocation target → the Code Browser at that symbol · the comparison receipt → its receipt card · the producing job → the dock Jobs record · the basis → the ProvenanceStamp detail.
- **Peek source:** the stored comparison receipt rows; nothing is compiled or compared again.
- **Absent copy:** "not compiled · no generated object" · "no comparison receipt" · "No instruction mapping for this line."
- **Target-size exception:** spacing: address links sit one per code row.

**Keyboard**

- F7 / Shift+F7 next and previous difference; Enter expands an equal run; links follow the linked-views grammar.

**Accessibility**

- Each well is a labelled group; differing rows carry the hidden word "differs:" so the change reads without color or mark.

**Removes switching:** opening the Listing and the receipt list to relate a verification difference to the original instruction (J34, J39).
