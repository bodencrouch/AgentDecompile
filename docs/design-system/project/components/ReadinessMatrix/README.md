# ReadinessMatrix

Entity × build readiness: locator status and observed status as separate glyph axes, row-for-row equal to the readiness report.

**Consumer provides** rows keyed by stable key, one column per build, each cell's locator status, member and observed status, plus the per-build environment facts.

- Each cell: the LocatorGlyph, then a thin rule and the observed status in `type-code-small`.
- Coverage phrasing names scope: "resolvable on {build-a, build-b}, ambiguous on build-c, absent on build-d".
- A plain-language "what you can do on this build" line sits under each build header.
