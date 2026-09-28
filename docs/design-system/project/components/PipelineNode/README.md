# PipelineNode

A stage or lane node in recovery diagrams and the work view, colored by lane.

**Consumer provides** the lane (`identity`, `recovery`, `unify`, `runtime`, `verify`, `intake`), the stage number and title, the "Trying to / How / In → out" rows, and the gate.

- Header uses the lane's `-fill` with `ink-strong` title; the body is `pane`. Corners are `radius-node`, the only rounded boxes in the system.
- Set in `cond`: `diagram-node` for titles, `diagram-note` for rows. Gates are labelled "Gate:" in `lane-unify-ink`.
- Lane color says which work, never whether it passed. Diagrams that describe unrun checks say NOT RUN in `fact-caution`.
