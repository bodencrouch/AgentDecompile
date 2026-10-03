# Task2.3 — canonical STABS schema ownership

Status: READY_TO_COMMIT for controller review/integration. Source implementation and authored regression sources only; no database, test, installed or runtime acceptance is claimed. Base: `81d455517ddf9e25dcc7c3320cee00f3dee41709`. No commits or staging performed.

## Implemented contract

The adopted scope is the STABS-only slice of `next-schema-ddl-contract.md`, under portable-plan-2026-09-21:U22 / integration U2. Broader persistent DDL adoption remains unfinished.

- `store.py` now owns the canonical STABS table, both table-index declarations, source-file index, and historical attribution-column tuple. `SCHEMA` interpolates the canonical declarations. A literal/AST source reconstruction against the base proved the emitted baseline SQL is byte-for-byte identical. Neither migration-1 semantics nor baseline nullable fields changed.
- Migration `(10, stabs_schema_ownership)` requires an existing owned transaction, exact observed v9 ledger/column shape, canonical STABS table, required baseline func attribution/owner columns, and recognized optional nullable TEXT STABS fields before its first DDL. It adds only missing `stabs_name`/`stabs_type`, ensures the three declared indexes, and checks the complete postcondition before the unchanged runner inserts the ledger row and version stamp. Missing `stabs_type` is refused, never recreated. No UPDATE/backfill/data extraction is added. A direct repeated v10 body validates the complete current ledger/schema without repairing it. Other observed versions refuse.
- Shared `migrations.require_ledger` is read-only, checks exact ordered version/name pairs and the four expected ledger columns including default/PK/generated metadata, and leaves historical NULL basis hashes untouched. SQL/I/O exceptions propagate unchanged. Existing migration functions, runner behavior, and migration 1–9 registry prefix were AST-compared against the base and are unchanged.
- `store.require_stabs_schema` is a nonmutating current-version guard. It reports STABS requirement plus observed/supported versions without inventing a path for caller-owned handles. It rejects temp shadowing, malformed/virtual/view STABS objects, changed STABS table declarations, wrong/occupied indexes, undeclared local triggers/indexes, and unsupported present func fields. Unrelated func extensions remain untouched. Read-only connect reuses this check and wraps schema failures in the established path-bearing `SchemaCompatibilityError`; it does not migrate or backfill.
- All public STABS writer entry points validate before writes: `ensure_columns`, `replace_stabs_types`, direct `apply_manifest_records`, `link`, and direct `propagate_source_files`. The helper is validation-only and has no commit. Public `STABS_TYPE_DDL`/`ADD_COLUMNS` aliases remain. TEMP donor preparation remains local and unchanged after admission.
- `replace_stabs_types` builds/deduplicates the payload before mutation, owns BEGIN IMMEDIATE/commit when no caller transaction exists, and uses a unique savepoint inside a caller transaction. BaseException cleanup rolls back only the owned scope; rollback failures propagate. Selected-binary deletion, nullable-row deduplication, and other-binary retention are preserved. `apply_manifest_records(commit=True/False)` retains its explicit commit contract and CASE logic. Propagation's existing commits/transaction ownership were deliberately not redesigned.
- `delete_registry.py` keeps its independently frozen v9 DDL maps, additions, inventory and ledger. An explicit v10 delta requires both STABS fields, all three indexes, and the exact new ledger row. Only versions 9 and 10 are admitted; future live migration-registry changes cannot grant deletion permission. Existing ownership/dependency/count/rollback behavior and the noninitializing opener are unchanged.
- `CORPUS_PIPELINE.md` explains the narrow source contract, strict admission, old-handle migration requirement, dual deletion compatibility, and unfinished other DDL owners.

## Caller and transaction review

Source searches found no additional direct installer for these exact STABS objects beyond the assigned files. Frozen inspection declarations in delete_registry are not executing initializers.

| Caller | Retained source behavior |
|---|---|
| `cli.py` apply-stabs / propagate-source | Uses canonical `store.connect(args.db)`, then existing ensure/writer calls. No routing or parameter change. |
| `dashboard/workflow.py::merge_evidence` | Canonical connect then ensure guard before its explicit BEGIN IMMEDIATE; validation no longer commits anything. |
| `stabs_manifest.py::generate` | Caller handle remains caller-owned; ensure now validates before parsing or output. Its prior initial binary SELECT is unchanged. |
| `stabs_link.py::link` | Calls ensure before scanning inputs. Reviewed-manifest equality, architecture selection and human attribution rules are AST-identical to base. |
| `stabs_types.py::persist_types` / `persist_types_from_macho` | Retained replacement call is now admitted by the shared guard before persistent mutation. Parsing behavior and public return contract remain unchanged. |
| Direct manifest / propagation callers | Guards are inside the public entry points, including before propagation TEMP scratch creation. Raw, unledgered or tolerated-v9 handles cannot bypass wrappers. |

All existing STABS public function argument ASTs were compared against base and are unchanged. No connection path/default, role vocabulary, binary/platform field, producer import, CLI, catalog or service route was introduced.

## Authored regression sources — unexecuted

- `test_store_migrations.py`: existing real fresh/known-v0 migration coverage retained; fresh STABS postcondition/no invented type rows added.
- `test_corpus_db_compatibility.py`: fresh and frozen known-v0 postconditions, read-only operation whitelist updated for read-only main.table_xinfo; six incomplete-v10 schema refusals and an actual target=9 reader refusal added. Existing NULL ledger-basis, malformed ledger, future version, SQL-error propagation and close behavior remain covered by authored sources.
- `test_corpus_stabs_migration.py` (one new module): actual target=9 fixtures; frozen expected v9/v10 ledgers; neither/either/both STABS columns with source index absent/present; exact old values/NULLs/IDs/other binaries and unknown func extension preservation; missing declared-index repair; wrong type/default/nullability/generated/PK, missing baseline fields/table, wrong keys/FKs/CHECK/default/extra column/view/virtual table/index, occupied name/local trigger/index and temp-shadow refusals; malformed/missing ledger; pending-step rollback after each ALTER/index/ledger/version operation and failed commit before durability; KeyboardInterrupt; durable prior v1–9 commits; lock/read-only tolerated-v9 writer refusal; direct body repeats/other-version refusal; no persistent writer installer source assertions.
- `test_corpus_stabs_link.py`: canonical fixture replaces raw baseline-only setup while retaining explicit raw-handle refusal; caller transaction preserved on ensure success/refusal; nullable deduplication and other binaries; owned commit versus provisional savepoint success; real insertion constraint failure, interrupted insert, commit failure, savepoint/release/rollback failures; manifest commit=False and ignored actions. Existing manifest/human attribution and architecture cases remain.
- `test_corpus_delete_registry.py`: existing full Task2.2 fixture/survivor/refusal/count/rollback cases are parameterized over independently built actual v9 and migrated v10. Frozen v9 optional additions are installed only in their deliberate legacy case. v10 positive coverage is distinct from falsely stamped v10, missing-v10 STABS/ledger refusals, and future version 11. Fixture retains WAL mode needed by existing snapshot-contention cases. No optional writer literal extraction was changed.

These are real-operation test sources intended for later authorized execution. They were not imported, collected or run. No RED/GREEN TDD receipt exists or is claimed. Test presence does not establish correctness or old-database equivalence.

## Source-only checks performed

1. Read the task brief, complete STABS contract, SDD implementer prompt and repository entry/authority references. Bounded memory search yielded no task-specific technical fact used in implementation; no memory-derived acceptance claim is made.
2. Read relevant source declarations and caller paths with `rg`/`sed`/`cat`; inspect owned `git diff` without staging or mutation.
3. Parsed all nine owned Python source/test files with standard-library `ast.parse`; no project imports or bytecode compilation. Result: all parsed successfully.
4. AST/literal-only comparison against base via read-only `git show`: reconstructed current SCHEMA exactly equals the original literal; all preexisting migration function ASTs and v1–9 registry prefix unchanged; all STABS argument ASTs and `_normalise_arch`, `select_slices`, `manifest_donor_rows`, `link` function ASTs unchanged; frozen v9 deletion DDL/index/addition/ledger/inventory assignments unchanged.
5. AST literal inspection confirms no persistent CREATE TABLE/CREATE INDEX/ALTER installer in the four STABS writer functions; ensure has no commit, rollback or executescript. TEMP donor creation remains present.
6. `git diff --check --` over the nine tracked owned code/test/doc paths returned no output (exit 0); direct trailing-whitespace checks include the new regression module. Source parsing and whitespace checks were repeated after the trigger-name fix.

## Self-review and remaining limits

Self-review found and fixed a schema-name collision edge: SQLite trigger names have a separate namespace, so collapsing all schema objects to a dict could hide an undeclared trigger sharing an index name. The validator now checks declared-name collisions and iterates the original rows for local trigger/index admission; authored collision regressions accompany it. Review also preserved WAL configuration in the new actual-v9/v10 deletion fixture, keeping its existing snapshot-contention assumptions explicit.

The controller confirmed the commit-failure clarification: regressions inject COMMIT failure before durability. An error after a successful COMMIT cannot be claimed as rolled back; it represents committed/uncertain reporting and is not an atomic rollback test. The implementation never converts cleanup exceptions into success, but cannot undo an already durable commit.

No tests, collection, build, typecheck, proof script, project import, DB open/query/create/migration, filesystem fixture, compiler/checker, runtime/process/catalog/service/systemctl/port, activation/provisioning or publication operation was performed. The controller's pre-edit process/source corroboration is inherited dispatch context, not a fresh observation by this worker. This checkout was not activated. All SQLite, historical-fixture, installed-consumer, concurrency and full-U2/U22 acceptance remains unverified. Only the narrow source slice is ready for controller review and a separately owned commit.

## Exact changed paths

- `src/agentdecompile_recovery/corpus/store.py`
- `src/agentdecompile_recovery/corpus/migrations.py`
- `src/agentdecompile_recovery/corpus/stabs_link.py`
- `src/agentdecompile_recovery/corpus/delete_registry.py`
- `tests/test_store_migrations.py`
- `tests/test_corpus_db_compatibility.py`
- `tests/test_corpus_delete_registry.py`
- `tests/test_corpus_stabs_link.py`
- `tests/test_corpus_stabs_migration.py` (new)
- `docs/CORPUS_PIPELINE.md`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-stabs-report.md` (this report)

## Fix round 1 — Important P1 mixed-case TEMP shadow refusal

Status: READY_TO_COMMIT for independent controller review. Reviewed input is `325ec899ac1535c2413ea6534f6346be1a48f328`; this round performed no Git operations or commits. The prior implementation report above remains historical source-check evidence, not a new execution receipt.

Addressed the sole Important finding from `task-2-stabs-review.md`. The STABS TEMP-name predicate now uses `name COLLATE NOCASE IN ('func','stabs_type')`; the migration-ledger TEMP-name predicate uses `name COLLATE NOCASE = ?`. This matches SQLite ASCII identifier resolution rather than ordinary case-sensitive schema text equality. Both table and view shadows are refused before any writer mutation or migration10 DDL, preserving the existing refusal policy instead of redirecting operations.

Reviewed the other newly introduced reserved-name comparisons for the same root cause. In the main schema validator, mixed-case reserved table/index/trigger spellings and mixed-case required/optional STABS column spellings now explicitly refuse before DDL. The comparison translates only ASCII A–Z, rather than applying Unicode case-folding that SQLite identifier rules do not promise. Canonical declarations and supported historical lowercase shapes remain unchanged. Existing main-ledger exact-name lookup already refuses a differently spelled table as absent before DDL; it was not broadened. Undeclared STABS-local objects remain rejected. There is no general schema-normalization or migration redesign.

Authored additions in `tests/test_corpus_stabs_migration.py`:

- Mixed-case TEMP tables and views for `FuNc`, `StAbS_TyPe`, and `ScHeMa_MiGrAtIoN`, populated from their actual main objects rather than empty incompatible shells.
- Actual target=9 runner refusal before DDL and direct migration-body refusal inside a caller-owned transaction; main/TEMP schema and contents, user_version, exact v9 ledger, and pending caller rows remain unchanged.
- Current v10 direct `ensure_columns`, `replace_stabs_types`, `apply_manifest_records`, `propagate_source_files` and `link` refusal before persistent/TEMP writes, commits, rollback, release or temp-store mutation. Cases retain main/TEMP contents, exact version/ledger and the pending outer transaction; caller rollback still removes only its provisional marker. `link` uses path sentinels so an admission bypass cannot proceed to filesystem work.
- Mixed-case reserved main index/trigger/column names refuse before migration DDL, covering the additional spelling audit.

Checks performed in this fix round: standard-library AST parsing and direct whitespace checks passed for all three changed Python files. During editing, in-memory before/after AST comparisons confirmed that only `store._require_stabs_shape` and `migrations.require_ledger` changed in production source: SCHEMA/declarations, migrations1–9, migration10 body and registry, runner, and all other functions remained AST-identical. Text inspection confirmed both TEMP predicates carry COLLATE NOCASE. No project module was imported and no test was collected or executed. No database, build, typecheck, proof script, cryptographic, runtime/live, provisioning, Git or subagent operation occurred.

Exact paths changed in this fix round:

- `src/agentdecompile_recovery/corpus/store.py`
- `src/agentdecompile_recovery/corpus/migrations.py`
- `tests/test_corpus_stabs_migration.py`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-stabs-report.md` (append only)

No additional focused test file was needed. SQLite behavior, historical compatibility, test results and installed/runtime acceptance remain unverified under the source-only constraints. The new regression sources express required behavior; they do not establish that it has passed.
