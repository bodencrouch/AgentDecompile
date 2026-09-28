# IdentityEdge

The state of an identity relation between two instances, drawn as a line style: candidate, accepted, rejected, unresolved.

**Consumer provides** the two instances, the edge state, the evidence channels and alternatives.

- Accepted: solid `lane-identity-ink`. Candidate: dashed. Unresolved: dotted `fact-unknown`. Rejected: struck with ✕ in `fact-failed`.
- An edge changes from candidate to accepted only when its acceptance event exists; similarity proposes, independent evidence accepts.
- Keep split, merged, inlined and one-to-many relations explicit; never force 1↔1.
