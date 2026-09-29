# OutcomeTag

A named non-success outcome: a terminal reason, not a forced match and not a claim of exhaustive failure.

**Consumer provides** the outcome and its per-member reasons.

- Closed set: absent · inlined_only · ambiguous · unsupported · insufficient_evidence · budget_exhausted · contested · unresolved · no_placement · unsupported_dynamic_code · missing_adapter.
- Mono word with a `fact-failed` dash. Unresolved data roots refuse, never zero.
- **In a row** (EntityRow, a ReadinessMatrix cell's Peek, an EntityBuildCard, a resolution job's OutcomeCell) the tag is the row's terminal word for that entity × build. It is a resolution outcome, not job lifecycle: an OutcomeCell says "finished" and, beside it, the OutcomeTag says what the ladder concluded. The two are never merged.

**Linking**

- **Publishes:** nothing.
- **Follows:** the entity × build of its row; holdable only with its host.
- **Targets rendered:** ambiguous, contested, insufficient_evidence, budget_exhausted and the other evidenced tags → the ladder run in the EvidenceRail for that entity × build; contested also names both candidate addresses as links marked "no winner". Link names read "Outcome contested, ladder C, build-d".
- **Peek source:** the stored ladder run for that entity × build.
- **Absent copy:** "absent" and "unresolved" are plain words and never links; a tag with no recorded ladder run is the word alone.
- **Target-size exception:** none; a linked tag is 24px tall.

**Accessibility**

- The dash is decorative; the word is the outcome. In a row the tag is described by its row, not announced separately.
