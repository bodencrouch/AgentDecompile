# Recovery pipeline diagram (local, editable)

One picture of everything the recovery pipeline is designed to do: open/resume plus eight named
stages with explicit feedback, the five lanes that run concurrently beside them (identity fusion, cross-build export, runtime reuse, verification, distributed compute), the bounded resolution
ladders, the serialization locks, the export bundle, and the legend.

The diagrams represent the [September 18–21 design baseline](../../plans/2026-09-27-weekend-design-scope.md)
and its explicitly dated later refinements. Preserve stages 0–8 and lanes A–E;
the September 22 execution/resilience/capability companions add views and contracts
without retiring the weekend entity/export/workstation/distributed scope. The
older pre-revision overview lacks lane E and must not replace the current version.
Source and Documents overview hashes were rechecked during the September 27
provenance audit; this authority correction does not require regenerating visuals.

| File | What it is |
|---|---|
| `pipeline-model.json` | Source of truth for **content**: every drawn string of all four diagrams, stable node ids and typed edges. See [content model](#content-model-outlines-and-accessibility--2026-09-29). |
| `agentdecompile-recovery-pipeline.drawio` | The editable diagram. Open with draw.io desktop (`drawio <file>`), the VS Code "Draw.io Integration" extension, or app.diagrams.net. One layer per row, one group per model node (nested where the model nests). |
| `agentdecompile-recovery-pipeline.svg` | The same diagram as plain SVG; opens and edits in Inkscape or any browser. |
| `agentdecompile-recovery-pipeline.outline.md` | Text outline: the primary accessible reading form, with one anchor per node id. |
| `agentdecompile-recovery-pipeline.png` | A rendered copy for quick viewing (resvg, 1:1 with the SVG canvas, DejaVu fonts only). |
| `generate_pipeline_diagram.py` | Source of truth for overview **layout and palette**; reads its text from `pipeline-model.json`. |
| `generate_execution_diagram.py`, `generate_resilience_diagram.py`, `generate_capabilities_diagram.py` | Companion generators; same split (layout here, content in the model). |
| `generate_outlines.py` | Writes the four `.outline.md` files from the model and verifies model ↔ SVG ↔ outline agreement. |
| `diagram_common.py` | Shared model loader, accessible SVG root, `<g id>` node wrapping, DejaVu metrics and the layout checks. |
| `svg_to_drawio.py` | Turns a generated SVG into its `.drawio` file (native cells, layers, node groups with outline tooltips/links, connectors). |
| `render_pngs.py` | Renders the four PNGs with resvg (resvg-py 0.5.0), 1:1 with each SVG canvas. |

Regenerate everything (run from this directory, in this order):

```bash
python generate_pipeline_diagram.py        # each generator runs the layout checks before writing
python generate_execution_diagram.py
python generate_resilience_diagram.py
python generate_capabilities_diagram.py
python generate_outlines.py                # writes outlines; fails on model/SVG/outline drift
for f in agentdecompile-recovery-pipeline execution-contracts resilience-contracts autonomous-capabilities; do
  python svg_to_drawio.py "$f.svg" "$f.drawio"   # picks up "$f.outline.md" for tooltips and links
done
python render_pngs.py                      # needs resvg-py 0.5.0 importable (pip install resvg-py==0.5.0)
python diagram_common.py check *.svg       # optional: repeat the layout checks on existing SVGs
```

All scripts are deterministic: the same source produces byte-identical output.


## Contract revision — 2026-09-22

The generator and editable outputs incorporate the supplied architecture review:
validated linkable regions and early round trips; recovery/compilation/comparison
units; incremental calibration; entity/variant/instance identity; compile-only
candidate admission; continuous parity with optional reccmp/ReAgent evidence;
known-build RVA-first resolution; operation-specific runtime capabilities; scoped
cache invalidation and deterministic replay of recorded proposals/observations.
Lane E from the newer repository diagram is retained. These are design targets,
not assertions that all adapters or acceptance checks are already implemented.

The [implementation plan](../../plans/2026-09-22-recovery-contracts-and-validation-plan.md)
records planned backend work and future validation. Artifact generation/rendering
is document authoring; design completion does not require a running workbench.
The user-facing `/home/brunner56/Documents/agentdecompile-pipeline.svg` is a copy
of the current canonical SVG; its pre-revision content is preserved beside it as
`agentdecompile-pipeline.pre-contract-revision-2026-09-22.svg`.

## Execution and evidence companion — 2026-09-22

[execution-contracts.svg](execution-contracts.svg), [editable draw.io](execution-contracts.drawio),
and [PNG](execution-contracts.png) focus on the contracts that span lanes A–E.
The source is [generate_execution_diagram.py](generate_execution_diagram.py).

The companion shows task-specific admission, three independent binding proofs
(bytes, identity, operation), short centralized acceptance, separate original-code
and recovered-source capabilities, fencing versus resource quarantine, durable
retry budgets, three progress measures, and conditional continuation. Its late-worker
example names the expected future proof; that experiment is explicitly **NOT RUN**.
Host-loss continuation requires a complete independent replica and capable worker.
The overview retains all five lanes and now removes unconditional lease-loss,
timeout-termination and result-exists acceptance claims from lane E.

To regenerate the companion, run its authoring script, then use `svg_to_drawio.py`
with `execution-contracts.svg` and `execution-contracts.drawio` as its arguments.
Render either SVG with `rsvg-convert <input.svg> -o <output.png>`. These commands
only create document artifacts; they do not exercise AgentDecompile.

The companion distinguishes filesystem artifact preparation from the short database
acceptance commit: validation/flush/rename precede the version/generation recheck and
manifest-reference/ledger commit. Task completion requires its declared predicates.
Representation totals are disjoint; evidence and operation capabilities may overlap.
Admission includes capped aging and reservations; the detailed policy is specified
in the [task and acceptance design](../../plans/2026-09-22-task-acceptance-and-continuation-design.md).

## Prevention, containment and recovery companion

The dated [cross-place admission detail](../../plans/2026-09-22-task-acceptance-and-continuation-design.md#cross-place-admission-and-recipient-candidates)
adds a Mermaid view of the same candidate/acceptance boundary: standalone, watch
and bulk producers share current source and recipient checks; immutable candidate
publication precedes separate recipient verification and replacement. The
[living ledger](../../plans/2026-09-27-implementation-progress-and-live-track.md#accepted-admission-active-implementation-cross-place-continuation)
records the September 27 source defect and in-progress repair. This detail does
not claim that the legacy copy path already meets the diagram or replace lanes A–E.

The [match-review acceptance detail](../../plans/2026-09-22-task-acceptance-and-continuation-design.md#match-review-decisions-against-the-observed-basis)
adds the coherent read → observed decision → atomic validation/audit path and its
stale/refetch branch. It supports U17/U106/U109 without replacing their full evidence
and Compare requirements. Review remains an optional override while other work
advances; this detail is not a claim of installed or live consumer qualification.

[resilience-contracts.svg](resilience-contracts.svg), [editable draw.io](resilience-contracts.drawio)
and [PNG](resilience-contracts.png) show detect/classify → durable decision →
repair/reroute/wait → independent acceptance → scoped resumption → preventive
policy feedback. The source is [generate_resilience_diagram.py](generate_resilience_diagram.py).

The companion names control-plane read-only behavior, resource quarantine, bounded
retry accounting, exact wake conditions, no blind replay of unknown commands,
and canary-driven policy rollback. A worked disconnect scenario states its future
proof and is explicitly **NOT RUN**. Local single-host adoption reuses existing
task/corpus contracts; distributed machinery is not a prerequisite.

The [failure prevention and recovery plan](../../plans/2026-09-22-failure-prevention-and-recovery-contracts.md)
is the detailed contract. Generate this companion using its authoring source, then
convert with `svg_to_drawio.py` and render with `rsvg-convert` as above.

## Autonomous capability product companion

[autonomous-capabilities.svg](autonomous-capabilities.svg),
[editable draw.io](autonomous-capabilities.drawio) and
[PNG](autonomous-capabilities.png) connect the current reliability foundation to
M1 effective scenarios, M2 generated operations, M3 F12 tooling, M4 creative
projects, M5 supported checkpoints, M6 native host qualification and M7 assessed
whole-game browser execution. The
[product roadmap](../../plans/2026-09-22-autonomous-capability-product-roadmap.md)
defines their acceptance boundaries.

M0 is labeled **implemented foundation / partially verified**, with broader
obligations and native live delivery explicitly open. M1–M7 remain future work.
The shared workflow resolves evidence, admits deterministic decisions, executes
isolated operations and accepts independent observations before continuation.
Human input is reserved for genuine exceptions; unknown effects require
reconciliation. Platform/browser investigation can proceed independently.

This companion was hand-authored until 2026-09-29; it is now generated by
`generate_capabilities_diagram.py` from `pipeline-model.json` (same layout and colours,
generic names; see the note below). Convert it with `svg_to_drawio.py` and render with
`rsvg-convert` as above. Generating these artifacts does not exercise the product.

## Software-state note — 2026-09-27 (continuation session 7a1c2b)

These are software-state facts only. No diagram source, SVG or PNG changed for this
note; see the ["diagram regeneration pending" note](#diagram-regeneration-pending--2026-09-27)
below for what would need to change if this work merges. Full detail is in the
[living ledger](../../plans/2026-09-27-implementation-progress-and-live-track.md#continuation-session-7a1c2b-2026-09-27-late-morning).

- **Matcher contract veto: proposed, not merged.** A calling-contract check for
  the matching lane exists as a diff against `match_store.py` plus a new
  `contract_features.py` extractor. It is still being turned into tests on a
  separate branch. Today's read-only RE work found two high-score matches
  (0.99 and 0.98) that the current struct/mnemonic-only matcher cannot
  distinguish because it cannot see calling-contract differences; both stayed
  `review` with no row changed.
- **Four new modules: source and synthetic tests only, no consumer wired in.**
  Recipient-specific acceptance (`recipient_acceptance.py`, 15 tests passed),
  the COFF relocation roundtrip (`coff_fixup_roundtrip.py`, 17 passed), the
  recovered-project manifest (`recovered_project_manifest.py`, 34 passed), and
  the runtime lifecycle owner (`runtime_lifecycle.py`, 18 passed). None of
  these has run against the live 8080 workbench or a live database; their
  proposed integration diffs have not been applied.
- **Package `.18`: built, not qualified.** The wheel exists and hashes to
  `134ee3f6…`. Its installed qualification rerun is blocked on a mandatory
  quiet-host capacity gate (one-minute load average must be below 40; the
  last observed poll was above 220), so no installed-qualification verdict
  exists yet.
- **8080 has no owner.** Nothing serves it. The kotorxid watchdog serves
  8791, 8173 and 3000 instead. No catalog-owned recovery operation, including
  the whole-image acceptance this pipeline's stage 8 requires, can run until
  someone starts the 8080 workbench.
- **Two copies of `kotorxid.sqlite` exist**, at
  `~/biodecompwarehouse/kotorxid/db` and
  `~/agentdecompile-nvme/agentdecompile_projects/db`, with different
  modification times. Which one is authoritative for 8080 is unresolved.

### Diagram regeneration pending — 2026-09-27

None of the four facts above changes any diagram topology today, because the
matcher veto and the four new modules are unmerged and have no wired consumer,
`.18` is a packaging artifact, and the DB/8080-ownership facts are host state,
not pipeline design. If the matcher veto merges, the recovery-overview diagram's
identity-fusion lane (Lane A) would need a new decision node for a vetoed tie
inside the score-margin window; that edit is not made here.

## Content model, outlines and accessibility — 2026-09-29

This is an accessibility and data-model refactor, not a content rewrite. Stages 0–8,
lanes A–E, ladders A–F, locks, the failover rule, export cards, legend and companion
boxes keep their text; the only content changes are listed under "Supersession" below.

**Content model.** [`pipeline-model.json`](pipeline-model.json) holds every drawn string
of all four diagrams as nodes with stable ids, plus typed edges (`depends_on`, `feedback`,
`failover`, `gates`, `consumes`, `feeds`, `wraps`, `produces`, `consumed_by`,
`serialized_by`). Every node has `id`, `diagram`, `kind`, `family` (a work family:
identity, recovery, unify, runtime, verify, intake; or a companion role: step, bytes,
operation, acceptance, gate, contain, note) and `title`; nested nodes name a semantic
`parent` for breadcrumbs. Ids include `stage-0`…`stage-8`, `gate-0`/`gate-1`/`gate-3`…`gate-8`
(stage 2 has no gate), the diamond `gate-4-5`, `lane-A`…`lane-E` with cards
`lane-X-card-N`, `ladder-A`…`ladder-F` with ordered members `ladder-X-N` (`slug` is the
bracketed locator kind, e.g. `anchor_rel`), `lock-1`…`lock-5`, `failover-rule`,
`export-*`, `legend-*`, the labelled edges `feedback-1-2`, `feedback-7-8` and
`stage-4-failover`, and the companion ids (`exec-step-1`…`3`, `contract-bytes|identity|operation`,
`accept-4`, `cap-5A`, `cap-5B`, `fence`, `quarantine`, `continue`, `challenge-late-worker`,
`resil-step-1`…`6`, `control-plane`, `data-provider`, `policy-canary`,
`worked-interruption`, `cap-step-1`…`6`, `milestone-M0`…`M7`). These ids are the shared
deep-link vocabulary for the GUI (Pipeline Map, pipeline breadcrumb): the same id is the
SVG `<g id>`, the draw.io UserObject id and the outline anchor. Edges drawn as arrows carry
`drawn: true`; every other edge carries `inferred: true` (see below).

**Outlines.** `generate_outlines.py` writes
[agentdecompile-recovery-pipeline.outline.md](agentdecompile-recovery-pipeline.outline.md),
[execution-contracts.outline.md](execution-contracts.outline.md),
[resilience-contracts.outline.md](resilience-contracts.outline.md) and
[autonomous-capabilities.outline.md](autonomous-capabilities.outline.md), the primary
accessible reading form. Each heading or node item carries `<a id="<node id>"></a>`;
meaning-carrying symbols are spelled out (≠ as "is not", ↔ as "refines, both ways" or
"one-to-one", ∥ as "in parallel", → as "then", ranges such as 1–8 as "1 to 8"). Each
outline's Relationships list marks arrows "(drawn arrow)" and text-derived edges
"(inferred)" with their basis. The script fails without writing when a model string is
missing from its SVG, or when the SVG `<g id>` sequence differs from the outline's anchor
sequence (same ids, same reading order).

**Accessibility guarantees of the generated SVGs.**
- Root `<svg role="img" aria-labelledby="<diagram>-title <diagram>-desc" lang="en">` with
  `<title>` and a 2–4 sentence `<desc>` (reading order and claim boundaries) as its first children.
- Every card, lane, ladder, ladder member, gate, lock, panel, export card, legend entry and
  labelled arrow is wrapped in `<g id="<node id>">`, emitted in reading order: the 4→5 gate
  diamond directly after stage 4, each feedback label next to its arrow, a compact key inside
  "HOW TO READ THIS IN 20 SECONDS" and the full legend at the bottom.
- Never colour alone: stage cards, ladder headers, lane bands and the export band carry an
  uppercase family word (IDENTITY, SOURCE RECOVERY, UNIFICATION & EXPORT, RUNTIME,
  VERIFICATION, INTAKE); feedback arrows carry "↺ feedback · …" labels; the legend now
  includes feedback (dash 4 4) and "OUTPUTS → who consumes them" (dash 5 4). The design-target
  line keeps its explicit "Design target:" prefix; italics are decoration only.
- All four diagrams use DejaVu Sans. The overview stack is
  `DejaVu Sans, 'Segoe UI', system-ui, sans-serif` (mono `DejaVu Sans Mono, Consolas, monospace`,
  currently unused); the companions and capability diagram use `DejaVu Sans, sans-serif`.
- No empty `<text>` spacer nodes. Before writing, each generator runs layout checks and
  refuses to write on any problem: (1) an estimated-width check (as in `svg_to_drawio.py`)
  for overlapping text of different nodes; (2) when `/usr/share/fonts/truetype/dejavu` is
  installed, a measured check using real DejaVu advance widths (read from the TrueType
  files, kerning ignored) for overlap between any two texts, text that leaves its card, band,
  pill or panel, and characters DejaVu cannot draw. Output never depends on the fonts; only
  check strictness does. The pre-change overview failed check (1) where the 4→5 gate labels
  overprinted stage 5 and where the legend "G" overlapped "failover / fallback".
- Layout fixes: the 4→5 gap widens to 164 px so the gate diamond sits on the dependency
  arrow with its labels inside the gap; the 7–8 feedback arrow now runs below the stage-4
  failover loop instead of crossing it; ladders widen to 460 px and shorten to their content;
  the overview canvas is trimmed from 3110 px to 2936 px (resilience 1460→1435, capabilities
  1450→1440). Switching the overview to DejaVu Sans needed no further layout change: the
  tightest measured right margin inside any card is 58.5 px.
- `svg_to_drawio.py` keeps the SVG's font family (first family; default DejaVu Sans) instead
  of forcing Inter, names the diagram from `<title>`, stores `<desc>` as the diagram
  description (root cell data) and emits each `<g id>` as a UserObject group with the outline
  text as tooltip and `<outline>#<node id>` as link.

**PNG rendering.** `render_pngs.py` renders each SVG with resvg through the resvg-py 0.5.0
binding (`pip install resvg-py==0.5.0`, or any copy on `PYTHONPATH`), loading only the DejaVu
TrueType files in `/usr/share/fonts/truetype/dejavu` (`skip_system_fonts`, default and
sans-serif family DejaVu Sans, monospace DejaVu Sans Mono). Output is 1:1 with the SVG canvas
(4400×2936, 1800×1510, 1800×1435, 1800×1440), the same scale as the earlier PNGs, which
were 1:1 renders of their older, taller canvases. The container has no DejaVu Sans Oblique
file, so italic text renders upright. This supersedes the `drawio`/`rsvg-convert` PNG
commands quoted in the older sections above.

### Inferred edges (review)

51 edges in `pipeline-model.json` were read from diagram text rather than drawn as
arrows. Each has `inferred: true`, a quoted `basis`, and `inference: "stated"` (the text says
it directly) or `"interpretation"` (a reading of the text). The outlines mark them "(inferred)".

Interpretations to review first (22):

- `lane-A consumed_by export-hookpack` — lane A outputs: '… and by the ABI + struct blocks of the pack'; 'the pack' read as hookpack v2
- `lane-A serialized_by lock-2` — lane A card 'Runs alongside recovery': 'serialized only at the shared corpus mutation point', matched to lock 2
- `lane-B produces export-hookpack` — lane B outputs: 'all of it lands in hookpack v2'; read as lane B producing the hookpack export
- `lane-B produces export-divergence` — lane B card 'Divergence (3-way, never forced)' and outputs 'divergence class per pair', matched to the Divergence report export
- `lane-C depends_on stage-1` — lane C connects: 'branches after stages 1–2 evidence'; 'branches after' read as depends_on
- `lane-C depends_on stage-2` — lane C connects: 'branches after stages 1–2 evidence'; 'branches after' read as depends_on
- `lane-C consumes ladder-A` — lane C card 'Pack → resolve': 'try members in order' and outputs 'WHICH ladder member resolved each'; read as lane C walking every ladder
- `lane-C consumes ladder-B` — lane C card 'Pack → resolve': 'try members in order' and outputs 'WHICH ladder member resolved each'; read as lane C walking every ladder
- `lane-C consumes ladder-C` — lane C card 'Pack → resolve': 'try members in order' and outputs 'WHICH ladder member resolved each'; read as lane C walking every ladder
- `lane-C consumes ladder-D` — lane C card 'Pack → resolve': 'try members in order' and outputs 'WHICH ladder member resolved each'; read as lane C walking every ladder
- `lane-C consumes ladder-E` — lane C card 'Pack → resolve': 'try members in order' and outputs 'WHICH ladder member resolved each'; read as lane C walking every ladder
- `lane-C consumes ladder-F` — lane C card 'Pack → resolve': 'try members in order' and outputs 'WHICH ladder member resolved each'; read as lane C walking every ladder
- `lane-C serialized_by lock-4` — lane C card 'Preflight → controlled call/install' acts on a live process; matched to lock 4 (one scenario bundle)
- `lane-D produces export-receipts` — lane D outputs: 'content-addressed receipts → identical-basis re-runs are cache hits', matched to the Receipts export
- `lane-D serialized_by lock-5` — lane D card 'Receipts & re-baseline': 'acceptance rejects stale versions', matched to lock 5 (short acceptance commit)
- `stage-0 serialized_by lock-1` — stage 0 How: 'gate writes; reads use stable versioned snapshots', matched to lock 1 (writes to one program's analysis DB)
- `stage-4 serialized_by lock-3` — stage 4 tag: 'isolated mutable outputs / PDB / Wine state', matched to lock 3
- `stage-7 produces export-projects` — stage 7 How: 'reccmp: supported MSVC / PDB diagnostics', matched to the export card's 'reccmp reports'
- `stage-8 produces export-projects` — stage 8 How: byte-accurate+floor vs max-C measured separately, matched to the export card 'byte-accurate C+floor and max-C … independent image receipts'
- `fence gates accept-4` — FENCE row: 'Keep artifact; refuse current acceptance/promotion'
- `accept-4 serialized_by lock-5` — box 4 'Independent acceptance, short commit' matched to overview lock 5 'short acceptance commit' (cross-diagram)
- `resil-step-6 feedback resil-step-1` — step 6 'Prevent recurrence without blind tuning' returns to step 1 'Prevent, detect, classify' (preventive policy feedback)

Stated directly in diagram text (29): `gate-0 gates stage-0`, `gate-1 gates stage-1`, `gate-3 gates stage-3`, `gate-4 gates stage-4`, `gate-5 gates stage-5`, `gate-6 gates stage-6`, `gate-7 gates stage-7`, `gate-8 gates stage-8`, `lane-A consumes stage-1`, `lane-A consumed_by stage-5`, `lane-A feeds export-readiness`, `lane-B consumes stage-1`, `lane-B consumes stage-2`, `lane-B feeds lane-C`, `lane-B feeds export-target`, `lane-C consumes lane-B`, `lane-C feeds stage-1`, `lane-C feeds export-readiness`, `lane-D wraps main-pipeline`, `lane-D wraps lanes`, `lane-D gates export-target`, `lane-E wraps main-pipeline`, `lane-E wraps lanes`, `accept-4 consumes contract-bytes`, `accept-4 consumes contract-identity`, `accept-4 consumes contract-operation`, `cap-5A depends_on accept-4`, `cap-5B depends_on accept-4`, `resil-step-4 depends_on resil-step-3`.

### Supersession — 2026-09-29

The capability companion is now generated (`generate_capabilities_diagram.py`) with the
same layout and colours, DejaVu Sans, and generic names: the product-specific adapter name
became "runtime adapters", the M6 platform/build line became "Exact native builds per
platform;" and the M7 prior-work line became "Inspect prior browser-runtime work.". Eight
empty spacer `<text>` nodes were removed. The two overview feedback labels became
"↺ feedback · 1 ↔ 2 refine scoped hypotheses" and "↺ feedback · 7–8 verify early scaffold
and candidates"; a key line, family words and two legend entries were added; dangling
"In → out:" labels on four lane cards without in/out lines were dropped. Everything else is
unchanged text, and no product, game or binary names remain in these artifacts.

New sha256 of every regenerated or new file (earlier hashes recorded in
`docs/verification/` receipts are historical and describe the pre-2026-09-29 artifacts;
those receipts are not edited):

| File | sha256 |
|---|---|
| `pipeline-model.json` | `759ea18d0ec2c9c56cbd8583d6acd967de26d6da4e16a72a57b7de363649e9b7` |
| `agentdecompile-recovery-pipeline.svg` | `0792216c30656fe3c163bd10c8f969898603495b74aa200f1052fab1bf5fc13a` |
| `execution-contracts.svg` | `128d69995f6185c8b012f6672f6a58f05b70586e511d3dc41e6a3c37401e8b9c` |
| `resilience-contracts.svg` | `a4e5596db72863336e89b5c1ef89622028ea44e22c1e381e74a8548fb96ef8d8` |
| `autonomous-capabilities.svg` | `faf124ee1f252b9abbb459e20982c4b20f1122b9f9a8bde50efce303f5cf0bf8` |
| `agentdecompile-recovery-pipeline.drawio` | `8bf7f6d05ca184bdfef5438020910df5bab47cf033ecc7f694004901f22efead` |
| `execution-contracts.drawio` | `25c1cd6285163a8e9e7557a75c91ae7608741261f04454b6658c4db04f32193f` |
| `resilience-contracts.drawio` | `f25b71d65b7d776255dc6a6b2a42ccb8a0ce23c7f448776b74693681bf02ce14` |
| `autonomous-capabilities.drawio` | `2316f91059bdd09ba144163f508250cf17c254b36713ba1b22e1a4c52ae48e7a` |
| `agentdecompile-recovery-pipeline.outline.md` | `848f94cf61b78e41740318aa8a0448af5e0c5c078de1b7d98a467d7a3f454d4b` |
| `execution-contracts.outline.md` | `ebb69bf3440542a4bf7eb87b8c729824b3d142aaaba8c70be437af500bfa2ff6` |
| `resilience-contracts.outline.md` | `81a235538e9eabe17bdce3000603300f75bf058dd6d9a777af072f795a7a43fe` |
| `autonomous-capabilities.outline.md` | `f8302a134bb061c95831bf43cbfaa05090180620cc751595bd39784673a37c35` |
| `agentdecompile-recovery-pipeline.png` | `be3f164591c881c09bcc77595fc6a37850616fbdf3d1fe03f08a29970db4841e` |
| `execution-contracts.png` | `61c1a1af831e492d25561fa1615ad5d48c17fb8aac6d39375a6f1e8321abdf57` |
| `resilience-contracts.png` | `0c75b08bd7719d31924e6ae98f9c7229ad8b19d34adb40c8cf314b24cfdde496` |
| `autonomous-capabilities.png` | `55d503491a6f639186dbec4e253f1feb9f09d03ca1f5217af0682e370af65de6` |
| `diagram_common.py` | `119913dcf5c1b10b0885bad9a92cb56209ff5b9567911d92a23b9fcb189e00f6` |
| `generate_pipeline_diagram.py` | `99b0c1ad7831d92c05039fe697e11ef84840ddbbdbbf2f01db6d57afce3025ed` |
| `generate_execution_diagram.py` | `29a9ca306d8200861ca089976da5cf99a8682835512ac1f9485528b28e5ef3b3` |
| `generate_resilience_diagram.py` | `03c643e89d478ee7403318a5304bf32418b18cc4ddb40e5a74239527b6271761` |
| `generate_capabilities_diagram.py` | `ff4f0b0e8a6d9182e9dde03c6fafcacd73960310e4cd042228729b240687e41b` |
| `generate_outlines.py` | `b4e5ac5bcd348d1559aa9b6ffe1e5d5f6df7a85d44252dce650c2f6a8a2c3be5` |
| `svg_to_drawio.py` | `6838eace7469ffa88ae32fadf3844f261da9958820dfba3e0e77fec248e3c681` |
| `render_pngs.py` | `889e5d9be489d2124a1215b01355b5b129195cc6e8de529f215e5277cdcc6a11` |

The user-facing copy `/home/brunner56/Documents/agentdecompile-pipeline.svg` is outside
this checkout and was not updated.

Verified here: two full regeneration runs (generators, outlines, draw.io conversion and
PNGs) produced byte-identical outputs; the estimated and measured layout checks report zero
problems for all four SVGs (the estimate fails when the old 34 px 4→5 gap is restored, the
measured overflow check fails when a stage card is narrowed); each SVG parses as XML with
`<title>` and `<desc>` as its first children; every model node id appears in both the SVG
and its outline in the same order; every pre-change SVG string is still drawn except the
changes listed above; the updated converter reproduces the previous `.drawio` cells exactly
from the previous SVGs apart from font family and diagram name; each PNG matches its SVG
canvas size. Not verified: draw.io rendering or UI behaviour of the tooltips/links, and
screen-reader output.
