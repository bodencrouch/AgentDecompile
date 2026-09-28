# ClaimTier

The claim tier of an artifact, told apart by frame style and word: verified, advisory, context hint, byte authoritative.

**Consumer provides** the tier and, for verified, the hard proof that was in force.

- Verified: solid `claim-verified` frame. Advisory: dashed `claim-advisory`. Context hint: dotted `claim-hint`. Byte authoritative: double `claim-bytes` frame.
- Tiers never blur. Readability never implies parity. Byte-authoritative content is copied target bytes and is never promoted as recovered source.
- Acceptance thresholds are the caller's; the tier meanings are not.
