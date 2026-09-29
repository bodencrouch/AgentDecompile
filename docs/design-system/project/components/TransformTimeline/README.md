# TransformTimeline

TransformTimeline explains one function across one build pair as an ordered list of transformations, from the inferred source through what the compiler and linker did to the observed bytes. It is labelled "Reconstructed explanation, not observed compiler passes".

**Use it** in the Code Browser's secondary pane, or as a rail section for the selection, when a function differs between two builds and the question is why. It follows the logical entity and the `cmp` pair, and it is the ordered companion to CompilerLayer, which shows the same annotations in place.

**Consumer provides**

- the entity and the build pair (`cmp`), with each build's recorded source digest, toolchain and flags;
- the candidate source revision, if any, as the "From" endpoint;
- the stored annotations for both builds (the CompilerLayer records), each with its stage (front end, optimizer, code generation, link), evidence, presence per build and affected ranges;
- the observed byte ranges of both builds.

## Anatomy

- **Header:** entity, build pair, follow mode.
- **Claim line**, always first and in bold: "Reconstructed explanation, not observed compiler passes." It is followed by "Order is the conventional stage order (front end → optimizer → code generation → link), not an observed sequence", and, where it applies, "The legacy toolchains here emit no optimization remarks." The pane never pretends passes were observed.
- **Filter:** a FilterChip "Show · changed anything between b and d". It is on by default, hides transformations that are the same in both builds, and counts them ("5 of 8 · 3 the same in both builds are hidden"). The footer names what is hidden and links "Show all".
- **Ordered list.** "From" is the inferred source with its hypothesis chip ("candidate source, not the original"). Then one item per transformation:
  - the stage kicker;
  - the transformation title;
  - the evidence chip;
  - the cross-build word with each build's form ("b: inlined at 3 instructions · d: call");
  - the difference class line;
  - **range buttons** per build (`aria-pressed`) that highlight the affected Listing ranges;
  - the research link.
  "To" is the observed bytes of both builds.
- **Empty and unknown:** "No transformations reconstructed for build-c" as an unknown StateNotice when no detector output exists. Nothing is drawn from guesses.

## States

- Evidence per item: witness or record (solid) · hypothesis (heuristic) (dashed, basis named) · unknown.
- Cross-build per item: `≡` same in both builds (hidden by the default filter) · `±` differs: consistent pattern · `±` differs · `−` absent in build-x.
- Difference class per item:
  - same source, compiled differently (cause named);
  - same source and flags, build state differs (entropy);
  - source changed;
  - unknown.
  For a pair whose source and flags both differ (build-a ↔ build-b here), most items read Unknown, and the component says so on the provenance line.
- The item under the cursor, or the one whose ranges are highlighted, is current (`aria-current="step"`, selection fill and bar).
- Pane: follows on Enter (it is an expensive, derived pane) · "Shows ‹entity›; selection is now ‹entity› · Enter to load" · stale basis.

Difference classes use VariantRelation's glyphs and words: `≈` same source, compiled differently (compile variance) · `∼` same source and flags, build state differs (entropy) · `≠` source changed · `?` unknown · `≡` identical. Evidence words are shared with ToolchainEvidence: **witness** or **record** (solid frame), **hypothesis (heuristic)** (dashed frame, basis named), **unknown** (italic word, no frame). A build-wide cause (a flag, LTCG, /GS, /Oy, EH model, ICF) links to ToolchainEvidence (`ws=evidence&panel=toolchain&build=…`) instead of restating its evidence.

## Linking

- **Publishes:** a range button replaces `addr` in the primary location with the range start and marks the range (reflection). That is a cursor move, so it uses replaceState. Enter on an endpoint address or the "From" source link is Go. "Show all" is a Go that removes the filter.
- **Follows:** `entity` and `cmp`, on Enter. Holdable (proposed hold kind `xform`).
- **Targets rendered:** address (observed bytes, per build) · symbol (inlinee, folded entities) · compiler diagnostic or source line (`f=src.line:…`, the candidate "From") · research section (native `/docs` link).
- **Peek source:** the stored annotation record and its evidence; the candidate source excerpt when cached.
- **Absent copy:** "No transformations reconstructed for build-c" · "absent in build-d" · "unknown" · "No candidate source; the timeline starts at the observed bytes of both builds" · "The legacy toolchains here emit no optimization remarks."
- **Target-size exception:** none; range buttons are 24px, and 44px below 700px or with a coarse pointer.

## Keyboard

- The list is a composite with one tab stop. ↑/↓ move between items; Enter on an item presses its first range button and moves the Listing cursor to the range start; Tab reaches the item's own buttons and links.
- Alt+↓ peeks the item's evidence; Shift+F10 opens the link menu (Reveal in: CompilerLayer, MatchExplain).
- `g then t` (proposed) moves focus to the timeline from a code well.
- Esc follows `keymap.json` `escapeOrder`.

## Accessibility

- An `<ol>` named "Transformations, build-b and build-d, in conventional stage order". The claim line is the first text in the pane and is included in the list's description.
- Every item names its stage, title, evidence level, cross-build word and class in text. Glyphs are `aria-hidden`.
- Range buttons name build and range ("Highlight range in build-b, 0041a4c1 to 0041a4c6"), and pressing one announces the landing once.
- Reduced motion has no effect, since nothing animates.

**Research:** [MSVC transformations §2–§6, §9.9](../../../../research/2026-09-29-msvc-optimization-for-decomp.md#9-ui-implications); [reference UI patterns B2, B3](../../../../research/2026-09-29-reference-re-ui-patterns.md).

**Prior art:** compiler-explorer `static/panes/opt-pipeline.ts` (per-pass before and after, hiding passes that changed nothing), `static/panes/opt-view.ts` (Passed, Missed and Analysis remarks with kind filters) · reccmp `docs/annotations.md` (compiler-generated entities kept apart).
