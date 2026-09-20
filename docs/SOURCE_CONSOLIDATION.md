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

## Consolidation status and remaining boundaries

| Area | Current observation | Next repair boundary |
|---|---|---|
| Provider enrollment | Repeated package/manager enrollment lists identified and consolidated in `03e8a89` | Existing providers package now owns the ordered tuple; manager and exports derive from it |
| Capability policy | MCP duration now belongs to ToolMetadata; argparse duration/confirmation belong to owning parsers | Dashboard projects metadata, preserving existing classifications; resource ownership remains separate |
| Pipeline projections | Contract owns stage tokens, actions, labels, aliases and display gates; steps and browser derive their projections | Internal workflow stages, receipts, proof gates and catalog field definitions remain distinct owners |
| Resource admission | Parser/ActionSpec metadata now owns identity scope; remove-binary/reclassify-matches are covered | Database-wide and directed-pair claims overlap correctly under the existing scheduler lock; external processes remain a distinct boundary |
| Resume | Repeated stage-relevance predicates now have one local definition; existing stage fingerprints and plugin proof checks remain their own owners | No new cache, relaxed proof gate or changed fingerprint format |
| Workspace paths | Corpus workspace resolution delegates to the shared default owner; recovered-source fallback reuses external-root resolution | Historical warehouse, container, bootstrap and saved-selection layouts remain unchanged |
| Input/shortcut wiring | All eleven shortcut families derive names/options/callbacks from their owning Click commands | Explicit omissions, semantic aliases and boundary-specific precedence remain intentional policy |

These are source findings and bounded source-level repairs, not claims of live
defects reproduced through 8080. Broader resource admission, corpus resume and
legacy identity changes require their own contract verification. The identity writer
set initially had seven entries, not five. The earlier corpus.run assertion was
incorrect for the dashboard entrypoint: its parser has no --db and its dashboard
caller passes none. DB-keyed identity locking is not applicable without a
separately traced resource contract. Do not inject an unrelated selected database
or unsupported argument. Invalidated evidence must rerun even
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
- `c05ec77`: the pipeline contract owns the eight-stage presentation, with derived
  numbering, aliases, action maps and browser items. All nine non-pipeline quick
  sets remain unchanged. Missing catalog actions disable only derived stage items.
  Alias mappings are unchanged; diagnostic/serialization order follows stages.
  Actual Python/JS adapter checks and independent review passed, not live-browser
  proof. Preceding snapshot `0587b74` preserves canonical frontend context-loading
  work and is not attributed to this refactor.
- `5567d83`: two repeated stage-relevance predicates are shared inside the existing
  fingerprint owner. Final review caught and corrected a handwritten dependency
  constant in the evidence harness. The source-derived rerun passed all 209 full
  dictionary/hash comparisons, exact stage-dependent identity-key presence, and
  source-project success/error branches. No production fingerprint regression was
  identified. This does not add new resume behavior or strengthen receipt proof.
- `475fe2e`: compatible corpus workspace defaults share one resolver; existing
  public delegation and dashboard search order are preserved. All 120 path-output
  comparisons passed without filesystem checks or state relocation.
- `e450617`: the remaining seven copied shortcut factories reuse the same helper,
  preserving their 35 established shortcut selectors. Net 218 production lines
  removed in this task. Native Click capture checks cover all selectors, options,
  hidden-field omissions, false/zero/empty values and the prior four families.
  Baseline callback-destination defects are explicitly characterized and fixed;
  broken baseline commands are not described as working-behavior parity.
- `b4ba829`: final review exposed a cross-task gap in nested command spelling.
  Click's native `group_class = type` propagates the existing resolver to nested
  groups. Twelve actual derived shortcut spelling cases passed; resolver order,
  ambiguity rejection and command-surface exclusions remain unchanged.

All thirteen implementation tasks have independent task-level approval. Cumulative
review and the single final fix-wave re-review passed at `b4ba829`; no blocking
findings remain. This completes the planned source cleanup in the isolated branch,
not live integration or deployment. The complete runnable evidence and decisions
remain in `.superpowers/sdd/2026-09-20-forgiving-input-cleanup/`.

The source inventory (456 Python files, 218,515 lines) and earlier allocation maps
remain investigation history, not a current inventory or file-reduction quota.
The container/decoder tasks removed 1,121 lines; that task-local count is not
whole-product completion evidence.

## Execution and evidence limits

### Recovery follow-up: unused AST work

After restoring the existing NVMe dashboard with explicit user authorization,
live K1 job `7d44c7ca408a` exposed a normalization bottleneck. `clang_scribe`
launched Clang per candidate, but `_apply_ast_edits` never populated its edit list.
The isolated branch now retains the local dialect transformation and public entry
point without that subprocess, temporary source, or unused traversal. Missing-Clang
diagnostics are preserved. Metadata now says `used: false` and explains that no AST
rewrites are implemented, rather than treating a successful parse as a rewrite.

Seventy-two pure in-memory baseline/current source-output comparisons passed in
both normalization modes with present, missing and failing AST results. Forty-eight
baseline AST requests used inert capture stubs; the new production path has none.
This is output-equivalence and call-elimination evidence, not a measured runtime
speedup. The first check had a missing `NM` alias in its extraction harness; the
corrected check passed. Runnable evidence is in the SDD progress ledger.

This follow-up was self-reviewed, not part of the thirteen-task independent review.
It has not been deployed into NVMe or injected into the active external worker.

Work stays in the isolated worktree. Preserve canonical changes and the separate
NVMe runtime. No filesystem tests, fixtures, temporary test inputs, additional
servers, recovery workers, systemctl, process restarts, or direct recovery CLI
runs are authorized by this cleanup. Pure inline checks do not prove live
dashboard behavior, job continuity, compiler results or recovery parity.

These checks did not verify deployment or behavior in the live 8080 runtime. The
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
