# ResolutionLadder

A bounded resolution ladder: methods tried in order, joined by dashed failover connectors, ending in named outcomes.

**Consumer provides** the ladder letter and problem, family, the ordered members (with locator kind where one applies) and the terminal outcomes.

- `pane` panel, `radius-card`, header in the family fill. Steps are 18px circles (family fill, family-ink stroke, bold number) at a 24px pitch; connectors dashed `dash-ladder` in `lock`.
- Terminal outcomes ("then: …") in bold `fact-failed`. An annotation step is a claim, never resolved.
- The app's EvidenceRail shows the same ladder as it actually ran, with the same letters and step numbers.

**Linking:** none (print diagram). Its nodes keep their pipeline-model ids (`ladder-A`…`ladder-F`, steps `ladder-C-3`). Where the app renders the same design step (Explain on a ladder row, the PipelineMap, go to `~ladder-C`), it links to `?node=` with that id, and in docs the name links to the outline anchor (`agentdecompile-recovery-pipeline.outline.md#…`). A concrete run of a ladder for one entity × build (EvidenceRail, EntityBuildCard, OutcomeTag) is evidence and links by its run receipt (`receipt=‹id›` with `project`, `entity` and `build`), never by `node`. The print canvas itself carries no links and no live data.

**Accessibility**

- Steps are an `<ol>`; numbers are text, not only circles. In the SVG each ladder is a `<g id="ladder-C">` and the outline is the primary accessible form.


## Behavior

- "then: unresolved — never a silent zero" (formerly the `≠ zero` chip on ladder C)
