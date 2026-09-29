# ResolutionLadder

A bounded resolution ladder: methods tried in order, joined by dashed failover connectors, ending in named outcomes.

**Consumer provides** the ladder letter and problem, family, the ordered members (with locator kind where one applies) and the terminal outcomes.

- `pane` panel, `radius-card`, header in the family fill. Steps are 18px circles (family fill, family-ink stroke, bold number) at a 24px pitch; connectors dashed `dash-ladder` in `lock`.
- Terminal outcomes ("then: …") in bold `fact-failed`. An annotation step is a claim, never resolved.
- The app's EvidenceRail shows the same ladder as it actually ran, with the same letters and step numbers.

**Linking**

- **Publishes:** nothing. Diagram-only.
- **Follows:** nothing; the content is `pipeline-model.json`.
- **Targets rendered:** in app renderings (EvidenceRail rows, Explain on ladder rows, go-to `~ladder-C`) the header links to `?node=ladder-C` and each step to `?node=ladder-C-3`; terminal outcomes are OutcomeTag words. In docs the same names link to the outline anchors (`agentdecompile-recovery-pipeline.outline.md#ladder-C`). From a live ladder run, "Explain step 3" renders that node's text in place.
- **Absent copy:** none needed in the diagram; a live run that stopped says its OutcomeTag ("unresolved — never a silent zero") and "not tried (budget)" for steps it skipped.

**Accessibility**

- Steps are an `<ol>`; numbers are text, not only circles. In the SVG each ladder is a `<g id="ladder-C">` and the outline is the primary accessible form.

**Removes switching:** opening the diagram to learn what a ladder step in a live run means (J06).
