# Simplification direction and evidence

The user withdrew the file-count target and clarified that spelling aliases are
only one example. The task is to remove duplicated, hardcoded behavior throughout
AgentDecompile while following the product's design evolution. Fewer files are
not an acceptance criterion; neither is replacing explicit safety policy with
automatic guesses.

## Reading the intent over time

Current canonical VISION, STRATEGY and AGENTS are authoritative for present
direction. Historical plans explain why changes happened; they do not override
newer decisions. The canonical checkout is
`/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile`.
Its strategy document is newer than this isolated worktree's copy.

| Evidence | Observed change | Inferred design principle |
|---|---|---|
| May analysis-coordinator design and completed simplification plan | Duplicate provider waiters were replaced by one analysis coordinator with explicit timeout failure | Put shared behavior and failure policy in one owner, not parallel service layers |
| July context-fusion requirements; August substrate architecture guidance | Context registration and provenance matured from reconstruct-oriented acquisition into independently addressable MCP capabilities | Reuse evidence across routes; capabilities must be composable rather than forcing every task through one recovery recipe |
| `fd1d660` | Dashboard ActionSpec/FieldSpec derived from public parsers and MCP schemas | Project interfaces from their owning capability definitions; do not maintain parallel catalogs |
| `ce8dc8f` | Shared corpus environment defaults replaced mandatory setup variables | Ordinary operation should work from one default owner; explicit overrides customize it |
| `99d0137`, `e599493` | Enrichment opt-out and explicit false survived wrapper/argv construction | Generated interfaces must preserve user decisions, not just generate controls |
| `dbefb6d` | Batch-window settings affect only dependent stage fingerprints | Changed inputs should invalidate affected work, not restart unrelated completed stages |
| `700315a`, `d302e2d` | Resume and compile reuse are bound to source, target, settings and real toolchain identity | Reuse valid work automatically, but never trust stale success flags |
| `236abd4` | Original context provenance survives acquisition through another route | Consolidation must retain origins, conflicts and claim strength |

These are source/history facts followed by interpretations. They do not claim
that every old proposal was user-approved or that every implementation is now
correct.

## Product-level rules

- **One owner, several projections.** CLI, MCP, dashboard and agents should use
  the same capability semantics. Derive fields, choices and wiring where the
  owning schema already knows them.
- **Policy is not spelling.** Case/separator variants are mechanical. Mutation
  authority, resource ownership, matching precedence, stage order and proof gates
  are meaningful policy; declare them explicitly once rather than infer them
  from command names.
- **Compose capabilities; retain the mission recipe.** The current recovery
  strategy has a specific cheap-first, compile-gated, cross-build workflow.
  That recipe must not prevent independent context, analysis or runtime reuse.
- **Reuse is identity-bound.** Existing Ghidra state and receipts should avoid
  repeated work only when their target, inputs, toolchain and proof still match.
- **Failures leave useful evidence.** Unsupported tools and partial runs must
  produce named outcomes without voiding valid neighbors or promoting advisory
  work into proof.
- **No invented defaults.** Derive ordinary workspace and format behavior from
  existing owners. Keep explicit false, zero and meaningful empty values; never
  silently select another target or database.

## Concrete remaining duplication

| Area | Current observation | Next repair boundary |
|---|---|---|
| Provider enrollment | Repeated package/manager enrollment lists identified and consolidated in `03e8a89` | Existing providers package now owns the ordered tuple; manager and exports derive from it |
| Capability policy | MCP duration now belongs to ToolMetadata; argparse duration/confirmation belong to owning parsers | Dashboard projects metadata, preserving existing classifications; resource ownership remains separate |
| Pipeline projections | Contract stages, step action defaults and browser quick actions repeat related definitions | Trace the differing recipes, then derive shared projections without collapsing genuinely different stages |
| Resource admission | Parser/ActionSpec metadata now owns identity scope; remove-binary/reclassify-matches are covered | Database-wide and directed-pair claims overlap correctly under the existing scheduler lock; external processes remain a distinct boundary |
| Resume | Single-target stage fingerprints and plugin proof reuse exist, while corpus-stage reuse follows different paths | Reuse established identity/proof checks; declare dependencies once rather than create another universal runner |
| Workspace paths | Corpus workspace resolution duplicates the shared fallback; historical materializers have a different source-tree warehouse contract | Share compatible defaults without silently relocating historical artifacts |
| Input/shortcut wiring | Normalization is shared, but redundant alias registrations and copied Click factories remain | Derive spelling matches and shortcut definitions from existing owners; retain genuine semantic distinctions |

These are investigation findings, not claims of live defects reproduced through
8080. In particular, resource admission, corpus resume and legacy identity
fallback require focused verification before implementation. The identity writer
set initially had seven entries, not five. The earlier corpus.run assertion was
incorrect for the dashboard entrypoint: its parser has no --db and its caller
does not pass the optional database to the underlying pipeline API. Do not inject
an unrelated selected database or unsupported argument. Invalidated evidence must rerun even
without a force flag; valid completed work must not be overwritten gratuitously.

## Changes already made in the isolated branch

- Shared Click/registry/executor normalization and candidate lookup; removed 107
  equal-normalized provider alias literals. Semantic aliases and boundary-specific
  precedence remain distinct.
- `25a9c6b`: container implementation consolidated; repeated frozen dataclass
  copying replaced by stdlib `replace`. Four files and 54 lines removed.
  Qualified class module identities changed; external old pickle paths are not
  preserved. Independent task review passed.
- `638d617`: 38 identical decoder/helper functions and 18 tables now have one
  implementation; both producers retain their names through explicit imports.
  Net 1,067 lines removed. Candidate generation and verification remain separate.
  Shared global/table ownership changes unsupported producer-local monkeypatching.
  The initial generic check reached only 7/34 positive decoder paths; corrected
  runnable evidence covers 34/34 with 37 signed/rule variants, both old baselines,
  padding, truncation and malformed inputs. Independent re-review passed.

- `03e8a89`: provider enrollment now has one ordered owner; manager and exports
  derive from it. Exact 31-provider registration order and exported name set are
  unchanged; export-list order now follows registration order. Memory-only checks
  cover extending the owner and constructor-failure continuation through the
  actual extracted manager method. Independent spec/quality review passed.
  Net reduction: 62 lines. No automatic module scanning or plugin framework added.

- `8f27e7a`: four CLI shortcut families derive their names/options from the owning
  Click commands. Nine normalized-equivalent registry aliases removed; net 134
  production lines removed. Only two proven provider defaults become implicit;
  explicit positive/negative overrides remain. Independent review approved.
- `3b9535c`: metadata owns MCP duration and argparse duration/confirmation instead
  of separate dashboard command lists. Exact classifications checked across 77
  MCP tools, 76 corpus commands and 26 recovery commands. This adds 34 production
  lines while removing a synchronization obligation; it is not a line-count win.
  Independent review approved.
- `d750038`: identity scopes are declared on the owning operations and projected
  through ActionSpec. Two omitted identity writers are covered, and database-wide
  claims now conflict with pair claims. Existing distinct pairs remain concurrent.
  Admission release covers running-persistence, cwd and final-persistence errors.
  In-memory extracted lifecycle checks and independent review passed; no threaded
  scheduler, filesystem or external-process serialization proof is claimed.

The source inventory (456 Python files, 218,515 lines) and earlier allocation maps
remain investigation history, not a file-reduction quota. The two consolidation
container/decoder increments remove 1,121 lines; that is not whole-product completion.

## Execution and evidence limits

Work stays in the isolated worktree. Preserve canonical changes and the separate
NVMe runtime. No filesystem tests, fixtures, temporary test inputs, additional
servers, recovery workers, systemctl, process restarts, or direct recovery CLI
runs are authorized by this cleanup. Pure inline checks do not prove live
dashboard behavior, job continuity, compiler results or recovery parity.

No refactor here has been activated in the live 8080 runtime. The current
whole-image compiler/objdiff acceptance requirements, separately attributed
byte-accurate and max-C variants, and runtime-reuse evidence boundaries remain
unchanged.

Supporting canonical documents: VISION.md; STRATEGY.md; AGENTS.md;
docs/solutions/architecture-patterns/program-analysis-coordinator.md;
docs/solutions/architecture-patterns/vision-substrate-expand-islands-not-funnel.md;
docs/brainstorms/2026-07-17-context-puzzle-piece-fusion-requirements.md;
docs/plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md;
docs/plans/2026-09-09-0334-feat-evidence-fusion-matcher-plan.md;
docs/PROTOTYPE_OUTCOMES.md.
