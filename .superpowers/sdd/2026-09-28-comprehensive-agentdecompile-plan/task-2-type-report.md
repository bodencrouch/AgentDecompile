# Task2.6 — canonical type ownership source handoff

**READY_TO_COMMIT**, 2026-10-03, for independent review and controller integration.
This readiness covers the owned production/documentation source only. Separate
regression authors own all test paths; their authoring and review are not claimed
by this report. No migration, test, installed-consumer, native, ABI or recovery
acceptance was executed.

Authority is the complete adopted [type contract](next-type-ownership-contract.md),
[contract review](type-ownership-contract-review.md) and [implementation brief](task-2-type-brief.md),
with U2/U23 requirements and preceding STABS/decomp/convention contracts and source.
The controller corrected the brief's stale base `fc9828e1` to integration baseline
`bd979ae3`; accepted convention12 `eb153101` and U9 `d87c0f8f` are controller-supplied
identities, not Git verification by this worker. The source snapshots below were
captured before this worker's edits. No other worker's changes were reverted.

## Implemented schema and compatibility boundary

`store.py` owns `TYPE_TABLE_DDL`, `TYPE_INDEX_SQL`, `TYPE_ORIGIN_DDL` and
`TYPE_INVENTORY_STATE_DDL`. `TYPE_FIELD_DDL` is inspection data matching the
unchanged migration6 declaration, not another field installer. Known six-column,
seven-column CREATE and historical ALTER type shapes are admitted through explicit
declarations and ordered xinfo metadata. Type/origin/field/state indexes and
triggers are bounded to the declared index and exact PK autoindexes. Reserved
ASCII-case collisions, occupied names, relevant TEMP names and arbitrary-named
TEMP objects targeting owned tables refuse; unrelated scratch remains outside
this guard. Missing main inputs cannot be supplied by attached storage.

Migration `(13, type_schema_ownership)` requires an owned transaction, exact12
ledger and complete earlier owner shapes before any DDL. It installs missing
type/origin/index storage, adds only nullable origin to a recognized six-column
table, and records original global presence once. The unchanged runner owns
ledger/version/commit and its existing basis hook. Baseline, steps1–12, all prior
repeat bodies and the runner are unchanged. Direct repeat13 validates exact13
without repair; future registry growth does not change its bound version.

The global singleton is `absent` or `installed`. Absent requires zero type and
origin rows, while independent typed-field rows remain untouched. Installed may
be empty globally or for one binary. No row counts infer a replacement marker;
no historical rowid, origin string, donor text, field payload, ledger basis or
definition is rewritten by the migration. The marker is installation history,
not captured evidence, native provenance, per-binary coverage or ABI qualification.

Pure `require_type_schema` requires complete current13 plus prior STABS/decomp/
convention postconditions. `type_inventory_state` returns the admitted state;
`type_inventory_available` gates current/future consumers while preserving raw
historical physical presence. Canonical read-only connect includes type admission
and existing path-bearing error wrapping. Public convention admission advances
to13, while its migration12 repeat is unchanged. The decomp reader adds exactly13
with the existing complete11/12 rules; historical9/10 and future14 remain bounded.

Frozen deletion13 independently adds explicit ledger13, canonical seven-column
storage and required state/index/xinfo/consistency. Its 29 known tables comprise
23 mandatory and six optional tables. Historical9–12 maps, profiles, optionality,
owner/dependency checks and the deletion executor remain unchanged. Type/origin/
field rows retain their existing deletion rules; the global singleton survives,
including removal of the last binary. Surviving adopted rows and donor text are
not cascaded or reinterpreted. The live migration registry grants no deletion14
permission.

## Actual writer and consumer routing

- Export validates before Ghidra startup/access, preserves original extraction,
  emitters and six-field REPLACE payloads, and stages all rows and typed fields.
  Only successful binary/name field sets are replaced. Omitted origin remains
  NULL; surviving origin annotations are intentionally not rewritten.
- `plan_adoptions` is now a strict current13 pure reader before configuration or
  donor scans. It retains the existing NULL/native filter, traversal, donor
  choice, same-size policy, stats, order and result. No installer, ALTER catch,
  commit, rollback or materialization remains in planning.
- Adoption apply validates before iterating payloads, stages the same notes/type/
  origin rows, and writes them in original per-adoption order. Empty successful
  application also materializes installed state.
- `_type_write_scope` uses owned BEGIN IMMEDIATE or a private caller savepoint,
  revalidates within scope, and commits successful work including caller pending
  work. `_materialize_type_inventory` shares that scope. Surviving caller work is
  preserved on operation failure; BaseException and cleanup errors propagate.
  Failed scope creation obtains no cleanup ownership. Lost transaction or commit
  acknowledgement reports uncertainty instead of reconstructing caller work.
- `insert_native_types(con, rows)` stages six-field tuples, rejects malformed
  lengths or NULL required values before writes, uses fixed main-qualified
  INSERT OR IGNORE, returns actual inserted count and never replaces fields or
  curated keys. IGNORE cannot silently accept part of a malformed batch. The
  generated layout script opens an existing file directly, admits before program
  access, stages definitions, checks cancellation, calls this helper and closes
  its handle. Its rendering, context-hint claim and metadataPolicy remain. It
  still captures no typed fields; header failure after commit is not rollback.
- `definitions_for` retains its zero-SQL empty-names fast path. Nonempty current13
  logical absence raises `sqlite3.OperationalError("no such table: ghidra_type")`;
  installed-empty and historical/raw projections remain unchanged. Header
  admission follows the existing basis/build validation and precedes definition
  reads/output; all original header/manifest statements and output literals remain.
- CLI retains unknown-binary and missing-inventory exit2 branches; bundle retains
  absent-definition versus per-build-empty errors, snapshot and publication rules.
  Prompt context gates current/future state inside its existing `{}` fallback.
  Hookpack gates before type entities while retaining exact definitions, field
  JSON/order, and all other algorithms. Raw five-column projection fixtures are
  not treated as canonical migration histories.
- The `/types` handler uses one `corpus_read_snapshot` for presence, state, count
  and page, preserving filters, paging, STABS branch and result fields. Missing
  database remains unavailable. Current13 absence remains unavailable and
  installed-empty remains empty. Six-column historical API SQL failures remain
  until migration13 intentionally introduces nullable origin; invalid13/future14
  refuse with the existing503 response form. Physical inventory is unchanged.
- Calibration receipts open existing current storage read-only and close the
  handle even on failure. They neither install schema, call no-program export,
  apply adoptions nor commit corpus work. Candidates produce `state="planned"`,
  `planned=N`, `adopted=0` and a `propagation` gap; zero candidates stay present
  with both counts0. Logical absence produces missing export/header fragments
  with `reason="no-type-inventory"` and no header. Existing-header bypass is
  unchanged. Receipt/header artifact writing remains its explicitly allowed work.

No contract deviation or new consumer ownership was required. The brief's
shorthand about raw nonapplying planning is resolved by the adopted contract:
type `plan_adoptions` now strictly requires13; the existing nonapplying convention
computation API retains raw/minimal compatibility and was not edited.

## Exact changed paths

Production, under `src/agentdecompile_recovery/corpus/`:

1. `store.py`
2. `migrations.py`
3. `delete_registry.py`
4. `export_types.py`
5. `propagate_types.py`
6. `pipeline.py` — calibration receipt only.
7. `dashboard/workflow.py` — layout script only.
8. `dashboard/react_api.py` — types handler only.
9. `build_types_header.py` — logical admission seam only.
10. `kx_cli.py` — build-types-header presence branch only.
11. `export_bundle.py` — header availability seam only.
12. `ctxtypes.py` — type loading admission only.
13. `hookpack_v2.py` — type projection admission only.

Documentation: `docs/CORPUS_PIPELINE.md` and
`.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-type-report.md`.
No test, frontend, action, common snapshot, preparation-authority, matcher-input,
recovery algorithm or other production path was edited by this worker.

## Source-only checks and outcomes

- Standard-library AST parsing passed for all13 edited production modules. The
  generated layout's literal body was AST-parsed with a synthetic config prefix;
  the generator itself and generated code were never called.
- 308 AST/literal/link/whitespace assertions passed. The log is
  `/tmp/task-2-type-source-checks.txt`; saved pre-edit text is
  `/tmp/task-2-type-source-before/`; the focused unified text diff is
  `/tmp/task-2-type-source.diff`. These checks do not import or evaluate project
  code. No SQL declaration was executed.
- Preservation comparisons cover every original migration function/class,
  baseline and prior constants, first12 migration registry entries, old deletion
  maps/profiles/order/executor, existing public signatures, emitter functions,
  original header and definitions statements, planner filter/traversal/stats,
  original export extraction/payload assembly, prompt projection/fallback, and
  the entire hookpack algorithm after excluding its narrow added guard.
- AST/text comparisons confirm that workflow differs only in layout_script,
  react_api only in the nested types handler, and kx_cli only in its named
  build-types-header branch. Other production functions/constants remain intact
  outside the explicitly owned seams.
- Literal inspection confirms migration6 field SQL equals the new inspection
  declaration, generated layout has no installer/direct insert/commit, planning
  and export contain no executescript/ALTER, and the receipt contains no installer,
  export invocation, apply or corpus commit. Documentation relative links resolve;
  edited Python source has no trailing whitespace.
- A final AST parse and diff refresh followed the native helper's small staged
  batch validation addition. The previously checked frozen source was unaffected.
  A lightweight memory registry search provided orientation only; no remembered
  technical result replaces the current contract/source evidence.

No tests/collection/build/typecheck, project imports or execution, database open/
query/create/migration, hashes/fingerprints/crypto/keys/signing/compiler/checker,
process/runtime/live/API/catalog/provisioning/capture, systemctl/service/restart/
alternate port, synchronization/activation/publication, Git or subagent operation
was performed. Source-file read/write and standard-library source inspection only.

## Remaining acceptance and trust limits

All authored migration history/failure/concurrency and writer transaction cases
remain unexecuted. SQLite CREATE/ALTER spelling, rollback/savepoint/commit,
read-only/lock-tolerated handles, current API consumer responses, generated native
script behavior and artifact byte equality require separately authorized actual
execution. Independent regression authoring/review remains the controller's
separate packet; this implementer claims no passing tests or installed consumers.

Same-size donor agreement remains weaker than ABI/layout identity. Origin
annotations may be stale after export replacement; their binary/name key remains
narrower than type binary/name/kind. Field replacement remains binary/name across
kinds. Native layout still omits fields. Computation before a write scope obtains
no new cross-call donor snapshot guarantee, and successful writers still commit
caller pending work. These are disclosed retained contracts, not newly verified
provenance.

Wider recovered/reuse legacy keys, logical-name caches, binding metadata, helper
DDL, count fields, determinism/content keys/per-kind caches and facade removal
remain open, as do U23 return/parameter-storage transport, native typed-field
capture, target ABI qualification, installed/current consumer verification,
cataloged recovery work and STRATEGY whole-image C+floor/max-C acceptance. This
packet does not complete U2/U22/U23/U82 or establish terminal recovery.
