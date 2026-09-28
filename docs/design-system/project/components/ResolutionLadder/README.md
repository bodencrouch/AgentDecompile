# ResolutionLadder

A bounded resolution ladder: methods tried in order, joined by dashed failover connectors, ending in named outcomes.

**Consumer provides** the ladder letter and problem, family, the ordered members (with locator kind where one applies) and the terminal outcomes.

- `pane` panel, `radius-card`, header in the family fill. Steps are 18px circles (family fill, family-ink stroke, bold number) at a 24px pitch; connectors dashed `dash-ladder` in `lock`.
- Terminal outcomes ("then: …") in bold `fact-failed`. An annotation step is a claim, never resolved.
- The app's EvidenceRail shows the same ladder as it actually ran.
