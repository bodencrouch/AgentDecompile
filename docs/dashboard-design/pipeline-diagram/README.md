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
| `agentdecompile-recovery-pipeline.drawio` | The editable diagram. Open with draw.io desktop (`drawio <file>`), the VS Code "Draw.io Integration" extension, or app.diagrams.net. One layer per row, one group per card. |
| `agentdecompile-recovery-pipeline.svg` | The same diagram as plain SVG; opens and edits in Inkscape or any browser. |
| `agentdecompile-recovery-pipeline.png` | A rendered copy for quick viewing. |
| `generate_pipeline_diagram.py` | Source of truth. Edit the text and layout here, then run it to regenerate the SVG. |
| `svg_to_drawio.py` | Turns the generated SVG into the `.drawio` file (native cells, layers, groups, connectors). |

Regenerate everything:

```bash
python generate_pipeline_diagram.py
python svg_to_drawio.py agentdecompile-recovery-pipeline.svg agentdecompile-recovery-pipeline.drawio
xvfb-run -a drawio --no-sandbox -x -f png -o agentdecompile-recovery-pipeline.png agentdecompile-recovery-pipeline.drawio
```

Both scripts are deterministic: the same source produces byte-identical output.


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

The hand-authored SVG is the source of truth for this companion. Convert it with
`svg_to_drawio.py` and render with `rsvg-convert` as above. XML, labels and rendered
geometry were inspected; generating these artifacts does not exercise the product.

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
matcher veto merged as source on 2026-09-27 (commit d14949e) but has no wired
production consumer, the four new modules have no wired consumer either,
`.18` is a packaging artifact, and the DB/8080-ownership facts are host state,
not pipeline design. If the matcher veto merges, the recovery-overview diagram's
identity-fusion lane (Lane A) will need a new decision node for a vetoed tie
inside the score-margin window once a production caller uses the veto; that
edit is not made here.

## Regenerated — 2026-09-28

- The overview's stage 6 card now states the trust boundary: binary-derived text is evidence, never instructions.
- The resilience companion has a new band for distributed compute failure classes (H7, H8, H10, H11, H13).
- The SVG, draw.io and PNG for both were regenerated from their generators. A rerun gives byte-identical SVGs.
- The Documents overview copy was synced to the new overview SVG.

## Supplied originals reconciled — 2026-09-28

The [two supplied September 21 SVGs](history/2026-09-21/README.md) are preserved
with exact hashes and source paths. They are historical inputs; the current
overview and its later contract refinements remain in place.
