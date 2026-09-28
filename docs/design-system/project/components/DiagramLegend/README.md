# DiagramLegend

The legend every overview diagram carries: the arrow, failover, gate, lock and bracket glyphs, and the six family swatches.

**Consumer provides** nothing beyond placement; the entries are fixed.

- Arrows have explicit triangular heads (never SVG markers): `ink-muted` at `stroke-arrow`; failover dashed `dash-failover` in `lock`.
- Gate diamond: 36px rhombus, chassis fill, `gate` stroke, bold "G". Lock and bracket as in OwnershipPanel and the Diagrams section.
- Swatches 18×18, `radius-pill`, family fill with family-ink stroke.
