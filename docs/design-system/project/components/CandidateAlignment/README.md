# CandidateAlignment

Matching drawn as the work: counterpart blocks from two builds aligned, with the strings, references and anchors under comparison highlighted.

**Use it** in the ReviewDetail of a MatchReview row (embedded-in-row variant), in the Compare workspace, and in a Peek of a candidate edge.

**Consumer provides** the two instances (entity @ build and address), aligned blocks, the evidence channel of each highlight, alternatives with margin, and the edge state.

- Two wells side by side; shared anchors are marked (underlined, bold `ink-strong`) on both sides and named in words for assistive tech ("shared anchor").
- The evidence channel names each highlight: exact hash, relocation-normalized hash, rare ref, CFG, BSim, ABI. Alternatives and margin stay visible.
- **Linked cursor**: moving in one well moves the aligned row in the other. Differing rows carry ≠ plus the word "differs"; runs of equal rows collapse to one "N equal rows" line that expands in place.
- **Embedded-in-row variant**: inside ReviewDetail it drops its own header and follows the focused review row after the settle.
- **Open beside** opens both endpoints as a held pair in SplitCompare; the review queue keeps focus and selection.
- The edge changes state only after its acceptance event. Candidate generation is not acceptance.

**Linking**

- **Publishes:** nothing; Open beside writes `cmp` and creates a Held pair without changing the primary selection.
- **Follows:** the pair its host selects (ReviewDetail row, Compare pair), after the settle; holdable through Open beside.
- **Targets rendered:** each endpoint → the Code Browser for that build, same entity, with `build`, address and its edge word (candidate or accepted) · a shared symbol anchor → the Code Browser at that symbol on that build · each alternative → its instance, with its margin · the edge → its receipt card when one exists.
- **Peek source:** the cached listing rows of both endpoints already read for this pair; nothing is decompiled or matched.
- **Absent copy:** "No aligned block on build-b." · "Not loaded. Open build-b to read it." · "no alternative within margin" · "candidate · no acceptance event yet".
- **Target-size exception:** spacing: anchor links sit inside code rows 18px tall; each row has at most one link per side.

**Keyboard**

- F7 / Shift+F7 step to the next or previous difference in both wells; Enter on "N equal rows" expands it.
- Links follow the linked-views grammar; Shift+Enter on an endpoint opens it beside.

**Accessibility**

- Each well is a labelled group ("build-a 0041b213, 6 rows"); shared anchors carry the hidden words "shared anchor", differing rows the word "differs". The edge line style is `aria-hidden` beside its state word.

**Removes switching:** opening both builds' listings in turn to check the blocks and bytes before deciding a match (J07).
