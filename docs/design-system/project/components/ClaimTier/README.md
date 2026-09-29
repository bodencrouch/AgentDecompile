# ClaimTier

The claim tier of an artifact, told apart by frame style and word: verified, advisory, context hint, byte authoritative.

**Consumer provides** the tier and, for verified, the hard proof that was in force (its receipt).

- Verified: solid `claim-verified` frame. Advisory: dashed `claim-advisory`. Context hint: dotted `claim-hint`. Byte authoritative: double `claim-bytes` frame.
- Tiers never blur. Readability never implies parity. Byte-authoritative content is copied target bytes and is never promoted as recovered source.
- Acceptance thresholds are the caller's; the tier meanings are not. Marks and notes (Marks, worklists) are context-hint tier and never evidence.

**Linking**

- **Publishes:** nothing.
- **Follows:** the artifact it labels; holdable only with its host.
- **Targets rendered:** the chip is not a link. Verified: the proof sentence names the receipt in force → its receipt card. Byte authoritative: the source region → the Code Browser at that build and address.
- **Peek source:** Alt+↓ on the receipt link reads the stored receipt header.
- **Absent copy:** "advisory · no proof receipt"; a tier is never upgraded to fill a missing receipt.
- **Target-size exception:** inline: links sit in the proof sentence.

**Accessibility**

- The tier is a word in the chip; the frame style is a second cue, never the only one.
