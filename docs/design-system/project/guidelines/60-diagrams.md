# Diagrams

Four diagrams explain the product: the recovery overview, the execution and evidence contracts, the prevention/containment/recovery companion, and autonomous capability delivery. They share the Graphite palette and the six work families. They are design artifacts: every diagram that describes unrun checks says so in `status-claim` amber ("DESIGN ONLY", "NOT RUN", "FUTURE / NOT RUN").

Diagrams carry no product, game, binary or company names.

## One source, many renderings

`docs/dashboard-design/pipeline-diagram/pipeline-model.json` holds every diagram's content with stable node ids and typed edges. The four SVG generators, `svg_to_drawio.py` and `generate_outlines.py` all read it, so the SVG, the editable draw.io file and the text outline cannot drift. The outlines (`*.outline.md`) are the primary accessible reading form: headings anchored by node id, symbols spelled out in words ("is not", "refines, both ways", "in parallel"). Edges inferred from card text rather than drawn as arrows are marked `inferred` and reviewed separately.

## Accessibility guarantees

- Every SVG root has `role="img"`, `aria-labelledby`, `lang="en"`, and a `<title>` and 2–4 sentence `<desc>` as its first children.
- Every node is a `<g id="<node id>">` emitted in reading order (a gate directly after the stage it follows; feedback labels next to their arrows; a key line in the "HOW TO READ" panel before the content).
- Family is written as a word on every stage card, ladder header, lane band and the export band, not only drawn in color. Every dashed edge type has a legend entry and a text label.
- A collision check runs in every generator and refuses to write when text boxes of different nodes overlap.
- Regeneration is deterministic; a regeneration for accessibility or content-model reasons adds a dated supersession entry with new hashes and leaves earlier verification receipts as historical.

## Recovery overview

Rules: left → right is dependency order; vertical stacking is concurrency; every stage card answers **Trying to · How · In → out · Gate**; locks mark shared-state serialization; dashed means failover, feedback or an outputs box, each named in the legend (the diagram exception in guideline 20, Line styles); numbered ladders are fallback stacks.

- **Canvas** `chassis`. Title `dia-title` in `ink-strong`; subtitle `dia-subtitle` in `ink-muted`; the design-target line in `gate` amber. The prefixes "Design target:" and "Note:" carry the meaning. Italic is decoration and never the only carrier. A "HOW TO READ THIS IN 20 SECONDS" panel (pane fill, amber stroke, `radius-card`) sits top right.
- **Stage card** (StageCard): `pane` body, `node-stroke` at `stroke-card`, `radius-card`. A `dia-band-h` 30px header band in the family `-fill` with the stage number and `dia-card-title` in `ink-strong`; its lower corners are square. Section labels (`dia-card-label`) in the family `-ink`. Try lines `dia-card-try` in `ink`; How bullets `dia-card-how` with "• "; In → out lines `dia-card-how` in `ink-muted`; "Gate: " label and text in `gate`. Optional tag top right in `dia-tag` and the family ink.
- **Lane band** (LaneBand): `dia-lane-h` 34px header in the family fill at `opacity-lane-header`, `radius-band`, `dia-lane-title` in `ink-strong`, italic subtitle right-aligned in the family ink. A "connects" pill (`radius-pill`, chassis fill, family-ink stroke) sits above the right end. Lane cards follow; then an OUTPUTS box (chassis fill, family-ink stroke dashed `dash-outputs`) headed "OUTPUTS → who consumes them" with "→ " bullets.
- **Arrows**: `ink-muted` at `stroke-arrow`, explicit triangular heads (tip at the endpoint, base 10px back, half-width 4px). Never SVG markers. Labels 11px italic above the midpoint. Feedback arrows dashed `dash-feedback`.
- **Gate diamond**: 36px rhombus on the dependency arrow, chassis fill, `gate` stroke at `stroke-arrow`, a bold "G" inside; its bold label and sub-label sit inside the widened gap that holds it, never over a card.
- **Lock**: 18×14 body in `lock` at `opacity-lock`, `radius-chip`, shackle stroked `stroke-lock`, bold label to the right.
- **Concurrency bracket**: `gate` amber at `stroke-bracket`, label rotated −90°.
- **Resolution ladder** (ResolutionLadder): `pane` panel with a family header; steps are r9 circles (family fill, family-ink stroke, bold number) at a 24px pitch, joined by dashed `dash-ladder` connectors in `lock`; terminal outcomes bold in `fact-failed` at the bottom.
- **Export card** (ExportTargetCard): `pane`, `gate` stroke at `stroke-export`, `radius-card`, bold title, `dia-card-try` body.
- **Legend** (DiagramLegend): dependency arrow · dashed failover arrow · gate · lock · bracket · six family swatches (18×18, `radius-pill`, fill + ink stroke).

## Execution and resilience companions

- **Canvas** `chassis`; title `dia-companion-title`; status line `dia-companion-status` in `status-claim`; one-sentence tagline in `ink`.
- **Contract box** (ContractCard): `pane` fill, `line-node` stroke, `radius-contract`. Title `dia-box-title` in its role color; rows `dia-box-row` in `ink` at a 25px pitch. Step boxes are joined by `role-step` arrows at `stroke-contract-arrow`.
- **Role colors**: `role-step` (numbered process steps), `role-bytes` (BYTES, recovered source, resume), `role-operation` (OPERATION, original code), `role-acceptance` (independent acceptance), `role-gate` (the IDENTITY question, CONTINUE, POLICY), `role-contain` (FENCE, QUARANTINE, CONTROL PLANE, DATA/PROVIDER).
- **Worked example panel**: full-width `pane` box, bold title ("Concrete design challenge · …", "Worked interruption · …"), 19px lines, and a closing `status-claim` line that says what is not run.

## Capability delivery

- **Step cards**: `pane`, `line-node` stroke, `radius-milestone`; title 20px in `role-step`; body `dia-milestone-body`; `role-bytes` "→" between cards.
- **Banner**: full-width `pane` box with one amber `status-claim` sentence.
- **Milestone card** (MilestoneCard): `pane`, 1px stroke in the status color, `radius-milestone`; title `dia-milestone-title` in `ink-strong`; uppercase status kicker `dia-milestone-kicker` in the stroke color; body rows and an "Acceptance:" paragraph. Status color: implemented foundation `role-bytes`; future delivery (engine capability) `role-step`; future delivery (creative and playback) `role-acceptance`; future qualification and feasibility `role-gate`.
- **Footer**: `status-claim` design-status sentence ("M1–M7 are ambitions, not completed features.") and a muted contract reference.

## Reconciliation notes

- The execution companion titles IDENTITY in amber while the overview's identity family is blue. In companions amber marks a gate-like question; keep that role mapping and never use amber for the identity family itself.
- DejaVu Sans is the system face for all four diagrams and their draw.io files.
- Companion boxes stroke with `line-node` (#495364); overview cards stroke with `line` (#3a3f4a). Both are kept.
- The capability diagram is now generated from the model with generic names.
