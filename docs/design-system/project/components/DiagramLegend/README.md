# DiagramLegend

The legend every overview diagram carries: the arrow, failover, gate, lock and bracket glyphs, and the six family swatches.

**Consumer provides** nothing beyond placement; the entries are fixed.

- Arrows have explicit triangular heads (never SVG markers): `ink-muted` at `stroke-arrow`; failover dashed `dash-failover` in `lock`.
- Gate diamond: 36px rhombus, chassis fill, `gate` stroke, bold "G". Lock and bracket as in OwnershipPanel and the Diagrams section.
- Swatches 18×18, `radius-pill`, family fill with family-ink stroke.
- Every entry is a glyph plus words; the words carry the meaning in every mode, including forced colors.

**Linking**

- **Publishes:** nothing. Diagram-only.
- **Follows:** nothing; the entries are fixed.
- **Targets rendered:** in app renderings the legend is a key, not navigation: it sits on the same view as the graphic it explains, is tied to it with `aria-describedby`, and only its heading links to its pipeline node (`?node=legend`). In docs each entry keeps its node id as the outline anchor (`agentdecompile-recovery-pipeline.outline.md#legend-gate`, `#legend-family-unify`, …).
- **Absent copy:** none; a legend is never shown without its graphic.

**Accessibility**

- A list of entries; each drawn glyph is `aria-hidden` and its words are the text. The legend is referenced by the graphic's `aria-describedby`.
