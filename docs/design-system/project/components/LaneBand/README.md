# LaneBand

A concurrent lane from the recovery overview: lane header on the family fill, a "connects" pill, the lane's cards, and a dashed OUTPUTS box.

**Consumer provides** the lane letter and title, family, italic subtitle, the connects sentence, the cards (StageCard anatomy) and the outputs with their consumers.

- Header `dia-lane-h` 34px at `opacity-lane-header`, `radius-band`, `ink-strong` title, subtitle in the family ink.
- Pill: `radius-pill`, chassis fill, family-ink stroke and text.
- OUTPUTS box: chassis fill, family-ink stroke dashed `dash-outputs`, heading "OUTPUTS → who consumes them", "→ " bullets.
- The family is written as a word in the header; the fill is never the only carrier.

**Linking:** none (print diagram). Its nodes keep their pipeline-model ids (`lane-A`…`lane-E`, `lane-A-card-1`…): where the app renders the same node (PipelineMap lanes, WorkflowControl's scope sentence, go to `~lane-A`), that rendering links it to `?node=` with that id, and in docs the name links to the outline anchor (`agentdecompile-recovery-pipeline.outline.md#…`). The print canvas itself carries no links and no live data.

**Accessibility**

- In the SVG each lane is a `<g id="lane-A">` in reading order; the text outline is the primary accessible form. The subtitle is plain text with a family-word prefix, never italic-only meaning.

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- Key (moved text): "≠ chip: what never flows or never happens."
- ≠ everything (chip removed): "a build donates a FIELD, never everything"
- ≠ overwrite (chip removed): "→ never overwrites a stronger field; conflicts stay visible for review"
