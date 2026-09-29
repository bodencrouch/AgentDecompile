# IdentityEdge

The state of an identity relation between two instances, drawn as a line style: candidate, accepted, rejected, unresolved.

**Consumer provides** the two instances (entity @ build and address), the edge state, the evidence channels, the acceptance or rejection receipt, and alternatives.

- Accepted: solid `lane-identity-ink`. Candidate: dashed. Unresolved: dotted `fact-unknown`. Rejected: struck with ✕ in `fact-failed`. The state is always written as a word beside the line.
- An edge changes from candidate to accepted only when its acceptance event exists; similarity proposes, independent evidence accepts.
- Keep split, merged, inlined and one-to-many relations explicit; never force 1↔1.

**Linking**

- **Publishes:** nothing.
- **Follows:** the pair its host shows (CounterpartMatrix row, ReviewDetail, CandidateAlignment, a Peek); holdable only with its host.
- **Targets rendered:** each endpoint → the Code Browser for that build, same entity, with `build` and address · the acceptance or rejection → its receipt card · a withdrawn seed → the receipt that withdrew it. Evidence channels are words. Link names read "Identity edge build-a to build-b, accepted, receipt 2f61".
- **Peek source:** the stored edge record and its receipt header.
- **Absent copy:** "unresolved · insufficient_evidence" (plain, no endpoint link on the missing side) · "candidate · no acceptance event yet".
- **Target-size exception:** none; each edge is a 24px row.

**Accessibility**

- The line is `aria-hidden`; the state word and both endpoints are text, so the relation reads without the line style.
