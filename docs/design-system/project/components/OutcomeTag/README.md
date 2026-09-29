# OutcomeTag

A named non-success outcome: a terminal reason, not a forced match and not a claim of exhaustive failure.

**Consumer provides** the outcome and its per-member reasons.

- Closed set: absent · inlined_only · ambiguous · unsupported · insufficient_evidence · budget_exhausted · contested · unresolved · no_placement · unsupported_dynamic_code · missing_adapter.
- Mono word with a `fact-failed` dash. Unresolved data roots refuse, never zero.
- **In a row** (EntityRow, a ReadinessMatrix cell's Peek, an EntityBuildCard, a resolution job's OutcomeCell) the tag is the row's terminal word for that entity × build. It is a resolution outcome, not job lifecycle: an OutcomeCell says "finished" and, beside it, the OutcomeTag says what the ladder concluded. The two are never merged.
- **Uncertain targets (35).** "absent" and "unresolved" are plain words (`.ad-absent`), never an anchor and never a link to a guess. "ambiguous" and "contested" are the word plus a link to the ladder run that recorded them. A contested tag also lists both evidenced candidates as address links, each carrying its `build`, marked "no winner"; it never picks one. "contested" is a locator word: merges say "conflicting".

**Linking**

- **Publishes:** nothing.
- **Follows:** the entity × build of its row, after its host's settle. Not holdable itself; a held pane or Kept card keeps its own tags.
- **Targets rendered:** ambiguous, contested, insufficient_evidence, budget_exhausted and the other evidenced tags → the ladder run (EvidenceRail) for that entity × build, addressed by its run receipt (`receipt=`); focus lands on the ladder card. Contested also names both candidate addresses as address links with `build`, marked "no winner". Link names read "Outcome contested, ladder C run, build-d"; "Contested candidate 00452c10, build-d, no winner".
- **Peek source:** the stored ladder run for that entity × build.
- **Absent copy:** "absent" and "unresolved" are plain words and never links · "contested · no winner" · a tag with no recorded ladder run is the word alone.
- **Target-size exception:** none; a linked tag and each candidate address link are 24px tall. With a coarse pointer the host row's one 44px row-menu button carries the tag's menu; there is no long-press.

**Accessibility**

- The dash is decorative; the word is the outcome. In a row the tag is described by its row, not announced separately.
