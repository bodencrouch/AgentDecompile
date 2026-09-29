# ClaimTier

The claim tier of an artifact, told apart by frame style and word: verified, advisory, context hint, byte authoritative.

**Consumer provides** the tier and, for verified, the hard proof that was in force (its receipt).

- Verified: solid `claim-verified` frame. Advisory: dashed `claim-advisory`. Context hint: dotted `claim-hint`. Byte authoritative: double `claim-bytes` frame.
- Tiers never blur. Readability never implies parity. Byte-authoritative content is copied target bytes and is never promoted as recovered source.
- Acceptance thresholds are the caller's; the tier meanings are not.
- **Context hint** covers names, imported context notes (context pieces placed by ContextPlacement), debug-info witnesses and design text: Explain renders `pipeline-model.json` in this tier, headed "From the pipeline design · model rev ‹8 hex›" with "Design description ≠ this item's evidence".
- **Marks and their notes are not claims.** Marks, mark notes and worklists are per-viewer annotations and view state. They carry no tier and no tier frame, are never evidence, and are never an input to context fusion, propagation, agent context bundles or exports. A mark's note is labelled with the word "note" (MarksList). It becomes a context piece, with its own tier, only when the operator adds it through the catalog's add-context action. Ghidra program bookmarks are a separate, read-only Bookmarks scope and carry no tier either.

**Linking**

- **Publishes:** nothing.
- **Follows:** the artifact it labels. Not holdable itself; a held pane or Kept card keeps its own tiers.
- **Targets rendered:** the chip is not a link. Verified: the proof sentence names the receipt in force → its receipt card. Byte authoritative: the source region → the Code Browser at that build and address (always with `build`).
- **Peek source:** Alt+↓ on the receipt link reads the stored receipt header.
- **Absent copy:** "advisory · no proof receipt"; a tier is never upgraded to fill a missing receipt.
- **Target-size exception:** inline: links sit in the proof sentence.

**Accessibility**

- The tier is a word in the chip; the frame style is a second cue, never the only one.
