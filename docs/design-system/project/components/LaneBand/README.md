# LaneBand

A concurrent lane from the recovery overview: lane header on the family fill, a "connects" pill, the lane's cards, and a dashed OUTPUTS box.

**Consumer provides** the lane letter and title, family, italic subtitle, the connects sentence, the cards (StageCard anatomy) and the outputs with their consumers.

- Header `dia-lane-h` 34px at `opacity-lane-header`, `radius-band`, `ink-strong` title, subtitle in the family ink.
- Pill: `radius-pill`, chassis fill, family-ink stroke and text.
- OUTPUTS box: chassis fill, family-ink stroke dashed `dash-outputs`, heading "OUTPUTS → who consumes them", "→ " bullets.
- The family is written as a word in the header; the fill is never the only carrier.

**Linking**

- **Publishes:** nothing. Diagram-only: a lane never changes the selection, the build or admission, and it has no start or stop verb.
- **Follows:** nothing; the content is `pipeline-model.json`.
- **Targets rendered:** in app renderings (PipelineMap lanes, WorkflowControl's scope sentence, go-to `~lane-A`) the lane title links to its pipeline node, `?node=lane-A`, and each lane card to `?node=lane-A-card-1`…; stages named in the pill ("stage 1 identity", "stage 5") link to `?node=stage-1` and `?node=stage-5`. In docs the same names link to the outline anchors (`agentdecompile-recovery-pipeline.outline.md#lane-A`). Link names read "Pipeline node lane-A, Knowledge fusion".
- **Absent copy:** a lane this project does not run reads "not controlled here" in the app (WorkflowControl), never an empty band; external owners stay external.

**Accessibility**

- In the SVG each lane is a `<g id="lane-A">` in reading order; the text outline is the primary accessible form. In the app the lane title is a heading link and the subtitle is plain text, not italic-only meaning.

**Removes switching:** opening the diagram and then searching the app for the work a lane owns (J05).
