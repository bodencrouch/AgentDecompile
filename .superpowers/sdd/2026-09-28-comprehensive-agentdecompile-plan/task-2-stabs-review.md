# Task2.3 independent spec and quality review

Reviewed scope: the exact `task-2-stabs-review.diff`, base `81d455517ddf9e25dcc7c3320cee00f3dee41709`, head `325ec899ac1535c2413ea6534f6346be1a48f328`, against the complete `next-schema-ddl-contract.md`, `task-2-stabs-brief.md`, and `task-2-stabs-report.md`.

**Spec verdict: changes required. Quality verdict: changes required.** One Important issue prevents the promised shadow refusal and can leave a successfully migrated store with an incomplete persistent ledger. The other reviewed source seams follow the bounded contract. This is a source assessment, not SQLite acceptance.

## Findings

### Critical

None identified in the reviewed source scope.

### Important — P1: use SQLite identifier case rules when refusing TEMP shadows

- Primary references: `src/agentdecompile_recovery/corpus/store.py:200–203` and `src/agentdecompile_recovery/corpus/migrations.py:329–330`.
- Downstream references: `src/agentdecompile_recovery/corpus/stabs_link.py:82–86,119–125` and `src/agentdecompile_recovery/corpus/migrations.py:425–437`.
- Confidence: 100 (mechanical source mismatch between case-sensitive schema-name comparisons and case-insensitive SQL identifier resolution); autofix class: manual.

The new TEMP checks compare stored names with ordinary case-sensitive text equality (`name IN ('func','stabs_type')` and `name=?`). SQLite identifiers resolve without ASCII case sensitivity, while schema names retain their spelling. A valid v10 handle with a same-shaped `TEMP StAbS_TyPe` or `TEMP FuNc` therefore passes inspection of the canonical main schema, after which the unqualified replacement or manifest DML resolves to the temporary table. The operation can return success without updating the inspected persistent table.

The migration consequence is stronger: start from a valid actual v9 and create `TEMP ScHeMa_MiGrAtIoN` with the ledger columns. The new ledger guard does not see that shadow and validates `main.schema_migration`. Migration10 changes main's schema; the unchanged runner then inserts row10 through unqualified `schema_migration`, which resolves to the temporary table, before committing main's `user_version=10`. Main's ledger still ends at 9. This violates the adopted requirement that the ledger row and version commit together and prevents subsequent strict read-only/writer admission. This sequence is reasoned from source, not executed.

Suggested fix: make both TEMP-name predicates match SQLite's ASCII case-insensitive identifier resolution (for example `name COLLATE NOCASE IN (...)` and `name COLLATE NOCASE = ?`). Preserve refusal rather than silently accepting a shadow. No migration1–9 or runner rewrite is necessary for this v10 precondition fix. Review other new reserved-name comparisons for the same spelling assumption without expanding the migration scope.

Authored regression coverage should include mixed-case TEMP tables and views for `func`, `stabs_type`, and `schema_migration`. Exercise actual-v9 migration refusal before its first DDL and current-v10 public-writer refusal before any persistent or TEMP mutation, with both main and TEMP contents, version, ledger, and pending caller work unchanged. The current lowercase-only cases at `tests/test_corpus_stabs_migration.py:119–121` do not cover this boundary. Execution remains separately unauthorized.

### Minor

None identified that warrants a separate finding.

## Source contract assessment

- No `db/schema.rb` or `db/structure.sql` appears in the supplied diff; Rails schema-dump drift review does not apply.
- The supplied diff extracts the existing STABS table/index text into canonical store declarations and interpolates it at the same baseline position. The migration1–9 bodies and registry entries are outside changed hunks; migration10 is appended. No baseline field, key, backfill, binary/platform field, or producer import is introduced. This review inspected the supplied before/after text; it did not independently rerun the implementer's AST comparison.
- Migration10 requires a transaction, exact v9 version/ledger columns/ordered identities, and the recognized STABS shape before DDL. Individual execute calls preserve the existing runner's transaction boundary. Complete-v10 direct repeats validate instead of repairing; other versions refuse. The lowercase-shadow exception above remains material to those claims.
- The STABS shape validator checks the canonical table declaration, nullable TEXT attribution fields, existing owner column, indexes, occupied exact names, and undeclared STABS-local objects. Missing declared indexes are repaired only within migration10. Unknown unrelated func extensions are preserved. Newly added values remain NULL; no transformation or destructive rollback route is introduced.
- Strict read-only connect delegates to the nonmutating guard and retains version/error/close handling. Public guards precede manifest writes and propagation TEMP setup. `ensure_columns` no longer commits or installs schema. SQL failures remain errors rather than being converted into successful admission.
- Replacement computes and deduplicates payload before mutation, then owns BEGIN IMMEDIATE/commit or a unique caller savepoint. Delete plus insert shares that scope. BaseException cleanup preserves outer ownership; cleanup failures propagate. Commit-failure cases correctly inject failure before durability and do not claim that a completed COMMIT can be reversed.
- The deletion change is an explicit frozen v9/v10 delta, with v10 fields/indexes/ledger required and future versions refused. The existing v9 declarations, optionality, dependency rules, executor, and noninitializing opener are retained by the diff. Neither the live migration registry nor STABS adoption grants future deletion authority.
- Regression sources use actual target=9 initialization, named known-v0 coverage, meaningful row/value/NULL preservation checks, operation failure injection, old-handle refusal, direct public guards, and v9/v10 deletion fixture parameterization. They are useful authored cases, with the mixed-case gap above. Their presence proves no executed behavior.

## Named caller checks

Only the contract's named caller paths were followed: `corpus/cli.py` apply-stabs and propagate-source open through store.connect; `corpus/dashboard/workflow.py::merge_evidence` opens canonically and validates before its explicit transaction; `corpus/stabs_manifest.py::generate` retains its initial binary lookup then validation before parsing/output; `corpus/stabs_types.py::persist_types` and `persist_types_from_macho` reach guarded replacement; `stabs_link.py::link` retains its entry validation and reviewed-manifest/architecture flow. Direct apply_manifest_records and propagate_source_files contain the new guard. No broad external-caller completeness claim is made.

## Verification limits and performed work

Read repository authority and entry references, the complete assigned contract/report/diff, and the relevant named source/test ranges using bounded text reads/searches. A memory-registry search supplied no task-specific technical fact used in this review. Wrote only this review file.

No database was opened, queried, created, or migrated. No tests or collection, project imports, builds, typechecks, proof scripts, cryptographic checks, runtime/live/process inspection, provisioning, service/port changes, Git changes, source changes, or subagents were performed. No actual SQLite rollback, historical-database equivalence, installed-consumer behavior, concurrency acceptance, recovery acceptance, or full U2/U22 completion is inferred. The finding should be corrected and independently reviewed at source level before acceptance; later authorized SQLite execution remains necessary for behavioral qualification.
