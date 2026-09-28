# CandidateAlignment

Matching drawn as the work: counterpart blocks from two builds aligned, with the strings, references and anchors under comparison highlighted.

**Consumer provides** the two instances, aligned blocks, the evidence channel of each highlight, alternatives with margin, and the edge state.

- Two wells side by side; shared anchors are marked (underlined, bold `ink-strong`) on both sides.
- The evidence channel names each highlight: exact hash, relocation-normalized hash, rare ref, CFG, BSim, ABI. Alternatives and margin stay visible.
- The edge changes state only after its acceptance event. Candidate generation is not acceptance.
