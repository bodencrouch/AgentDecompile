# ImageDeltaMap

Whole-image rebuild drawn as the work: the image's regions in file order, with remaining deltas marked where they are.

**Consumer provides** the section/region map of the fresh rebuild, per-region equality, and differing ranges.

- Regions in file order scaled to size; equal regions `chassis`, differing regions `lane-fault-fill` with the byte count.
- Deltas localize to headers, layout, imports, relocations, resources or function and data regions. The whole-file hash is the only terminal fact.
