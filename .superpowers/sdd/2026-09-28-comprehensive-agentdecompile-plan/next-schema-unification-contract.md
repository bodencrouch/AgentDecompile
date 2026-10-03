# Next U2 slice: one corpus schema owner with staged U82 compatibility

Status: implementation-ready source contract; not implemented or runtime-qualified by this report. Scope is the duplicated `corpus/db.py` ownership seam and its immediate read consumers. Full U2, U22 and literal U82 deletion remain open. Repository AGENTS.md and `src/CLAUDE.md` apply. This investigation read source only and wrote this report; no database, process, catalog, service, project import, test or build was used.

## Decision and retained requirements

Keep `store.py` as the only baseline corpus DDL and connection/API owner, and `migrations.py` as its single versioned migration executor. These are one existing ownership boundary, not two independently selectable schema implementations. Replace `db.py` with a small delegating compatibility shim. Do not delete it in this slice. Do not move baseline SQL to a third module, add a new database default, renumber migrations, or rebuild existing tables.

The retained U82 excerpt says:

> **U82. Schema unification** (prerequisite for every new `binary` column). Two `binary`
> DDLs exist (`AD/corpus/store.py:19-36` vs `AD/corpus/db.py:19-34`); `db.py` has a
> product-named default path and one importer (`name_precedence.py:45`). `db.py` is deleted
> and the importer repointed to `store.connect`; existing stores need no DDL change; the
> `role` column keeps one documented vocabulary in `store.py`.

The retained U22 follow-on is broader:

> **Remaining:** the ledger owns every DDL site (`store.py`, `db.py` until U82,
> `export_types.py`, `propagate_types.py`, `stabs_link.py`, `decompile.py`); a per-table
> per-binary delete registry so `remove_binary` (`store.py:209`) removes every per-binary
> row; migration 2 adds `binary.basis_hash`, `decoder_revision`, `analyzer_version` and
> makes `content_sha256` a cascade precondition.

The active unit also requires preserving current public routing and unknown legacy meaning. The one-importer premise is obsolete: five current direct importers exist. Deleting the module now breaks those import paths and its no-argument API. Staging deletion is therefore an explicit compatibility decision. The slice removes duplicate schema authority; it does not claim literal U82 completion or that existing legacy files already have the current schema.

## Source evidence sufficient for this slice

All paths below are repository-relative; line numbers locate the source inspected for this report and may move during implementation.

| Source | Observed contract |
| --- | --- |
| `src/agentdecompile_recovery/corpus/db.py:14,164,173,185` | Module-relative `DB_PATH`, independently executed `SCHEMA`, defaulted `connect`, duplicated priority-index helper and JSON helper. |
| `src/agentdecompile_recovery/corpus/store.py:16,162,391,398` | Newer baseline schema, required-path connection, canonical helpers. `connect` already rolls back and closes its owned handle on initialization failure. |
| `src/agentdecompile_recovery/corpus/migrations.py:83,269,336` | Baseline consumes `store.SCHEMA`; migrations 1–9 exist; each step commits its body, ledger and version together. The lock/read-only tolerance can return before the requested version when a ledger already exists. |
| `src/agentdecompile_recovery/corpus/store.py:287,304` | Existing additive helper and separate `recovery_family` backfill; unknown rows without content hashes remain unclassified. |
| `src/agentdecompile_recovery/corpus/export_mizuchi_db.py:57,180,429,498` | Direct `db` import; build, estimate and main each open implicitly; identity-store use is SELECT-only. |
| `src/agentdecompile_recovery/corpus/mizuchi_bridge.py:39,101,244,272` | Direct import, implicit connection, recovered-function schema helper and explicit priority-index helper. This is not a pure read-only consumer. |
| `src/agentdecompile_recovery/corpus/name_precedence.py:45,153,169` | Direct import, implicit connection and a separate `logical_name` DDL site. |
| `src/agentdecompile_recovery/corpus/package_binaries.py:22,79` and `materialize_binaries.py:19,40` | Direct imports with explicit historical `ROOT / "db" / "kotorxid.sqlite"`; corpus DB is read for inventory. Artifact filesystem mutations are outside this contract. |
| `src/agentdecompile_recovery/corpus/dashboard/common.py:220`, `dashboard/actions/jobs.py:2097,2240` | Workbench resolves active/saved/configured database; identity-writer admission uses the effective database path and fills the job's `db` parameter. |
| `src/agentdecompile_recovery/corpus/corpus_env.py:42` | Generic configured/default corpus path exists independently of the historical compatibility path. |
| `src/agentdecompile_recovery/corpus/__init__.py:3` | Package-exported `SCHEMA` is imported from `contract`; it must not be confused with corpus SQL or repointed. |

`store.connect(read_only=True)` currently opens SQLite `mode=ro`, but still calls `apply_pending` and `backfill_recovery_family`. Thus the docstring's promise that it never migrates is stronger than its control flow. It attempts writes and can tolerate an outdated schema with a ledger. Fix that discrepancy in this slice without redesigning writable migration concurrency.

## Exact implementation ownership

One implementer owns these changes as a coherent slice, accommodating other agents' edits without reverting them:

1. `src/agentdecompile_recovery/corpus/db.py`: compatibility facade only.
2. `src/agentdecompile_recovery/corpus/store.py`: opening modes, strict read-only admission and documentation of ownership/role meaning; preserve current writable transaction cleanup.
3. `src/agentdecompile_recovery/corpus/export_mizuchi_db.py`: mark the three identity-store connections `read_only=True`.
4. `src/agentdecompile_recovery/corpus/package_binaries.py` and `src/agentdecompile_recovery/corpus/materialize_binaries.py`: mark each identity-store connection `read_only=True`; retain the exact explicit path and output behavior.
5. `tests/test_store_connect_transactions.py`, `tests/test_store_migrations.py`, and new `tests/test_corpus_db_compatibility.py`: author only the focused regressions specified below. Existing fixture `tests/fixtures/store/legacy_schema_v0.sql` is evidence of that fixture version only, not every historical database.
6. `docs/CORPUS_PIPELINE.md`: a short compatibility note documenting the canonical API, historical fallback, refusal behavior and unfinished deletion gate.

No changes to `migrations.py` are required: consume its registry, constants and existing `apply_pending` implementation. Do not change `mizuchi_bridge.py`, `name_precedence.py`, dashboard routing, CLI routing, schema version, registry/delete behavior, other DDL sites, or new binary columns. The controller owns living-plan/progress updates. The present investigation owns only this report.

## Public API and path contract

### Canonical store

Preserve positional `store.connect(path)` and keyword-only `read_only=False`; add keyword-only `create: bool = True`:

`store.connect(path: pathlib.Path | str, *, read_only: bool = False, create: bool = True) -> sqlite3.Connection`

The required `path` remains required. `create=True` preserves explicit writable creation behavior. `read_only=True` always uses `mode=ro` and never creates, irrespective of the default `create` value. Writable `create=False` uses a properly escaped absolute file URI with `mode=rw`; it does not mkdir or use check-then-create logic. This prevents a file deletion race from turning an existing-file compatibility open into creation. `create` is an opening policy, not a second path resolver.

Retain row factory, timeout and successful return shape. Add `SchemaCompatibilityError(ValueError)` in `store.py` for schema-version/ledger admission errors. Its message identifies selected path, observed version and supported version, with explicit existing-workbench migration guidance. Do not invoke that guidance automatically.

### Legacy shim

Retain imports of `agentdecompile_recovery.corpus.db` and its public `DB_PATH`, `SCHEMA`, `connect`, `ensure_priority_index`, and `j` symbols:

- `SCHEMA` is an alias to `store.SCHEMA`, never another SQL literal. This is a baseline schema constant, not a supported substitute for versioned initialization. Preserving the symbol does not promise equality to the old, incomplete SQL string.
- `ensure_priority_index` and `j` delegate to/alias the canonical helpers, retaining signatures and return values. The index helper remains an explicit compatibility capability for externally owned connections; this slice does not claim every DDL invocation is ledger-owned.
- `DB_PATH` keeps exactly its historical module-derived value. Its sole definition belongs in this deprecated compatibility shim; do not copy it into `store.py`, `corpus_env.py` or another resolver.
- Use `connect(path=None, *, read_only=False)` so omission is distinguishable from an explicit path. An explicit path delegates to `store.connect(path, read_only=read_only)`; an omitted path emits a visible `FutureWarning` with the resolved historical path and delegates with `create=False`.
- Omission must not search for, select, merge, copy or fall back to any other database. It must fail without mkdir or file creation when that historical file is absent. Environment and runtime selections do not silently redirect a legacy call. Explicit paths retain precedence and do not emit the fallback warning.

**Intentional compatibility tightening:** legacy no-argument calls previously created a product-named database when missing; they now refuse. This is justified by the active requirement to avoid hidden default creation while preserving known existing-store routing. The warning and docs must say so plainly. Existing legacy files opened for writing now pass through the existing canonical migrations instead of an independent old schema initializer; this is also a disclosed behavioral change, not a claim of unchanged initialization.

The three inventory/export consumers retain their `db` import and path/call chain in this stage, adding only `read_only=True`. Their outdated-store refusal is deliberate: a reporting operation must not migrate a corpus as a side effect. `name_precedence` and `mizuchi_bridge` remain writable compatibility consumers because their current operations include DDL. Do not relabel them read-only merely because their names describe reports or exports.

### Workbench/catalog authority

Existing action parameters and `dashboard.common.live_db()` remain authoritative for workbench requests. Retain explicit job `db` injection and resource-lock identity. `corpus_env.corpus_db_path` retains its existing explicit/configured/generic behavior. None of those paths acquire the shim's historical default, and the shim does not import dashboard selection state. Existing operation routes are not renamed or redirected, and no new action or CLI execution path is added. Operational migration continues to require the existing 8080 catalog and its current ownership/admission checks; this source slice does not perform migration or inspect the running catalog.

## Schema admission, data preservation and failure behavior

Perform version admission immediately after opening and configuring connection-local timeout/row factory, before WAL changes or any migration/backfill invocation.

| Input/mode | Required result |
| --- | --- |
| Explicit writable new path with creation enabled | Existing migrations initialize the canonical schema; no independent `executescript`; no migration version bump merely for delegation. |
| Explicit writable existing legacy/current store | Existing versioned path and backfill continue; preserve current lock-contention semantics and additive migration history. |
| Any store with `user_version > migrations.SCHEMA_VERSION` | Raise `SchemaCompatibilityError` before WAL/migration/backfill writes and close the handle; never downgrade or assume forward compatibility. |
| Read-only missing path | SQLite open fails; no directories/database created. |
| Read-only version below current, including version zero | Raise `SchemaCompatibilityError` immediately; no `BEGIN`, DDL, DML, migration or data backfill attempt. |
| Read-only current version with absent or incomplete/inconsistent ledger | Raise `SchemaCompatibilityError`; never repair the ledger on a reader. Require ordered `(version, name)` rows to equal current `MIGRATIONS` pairs. Missing/malformed ledger shape is an admission error, not permission to reconstruct history. |
| Read-only current version with valid ledger | Return the connection without calling `apply_pending` or `backfill_recovery_family`. Do not reject NULL historic ledger basis hashes; their existing meaning remains unknown. |
| Malformed SQLite/schema or unexpected SQL error | Propagate the real failure (or chain the underlying SQLite error for explicit ledger-shape incompatibility), rollback if necessary, close exactly once; no retry through a different database or writable mode. |

Keep canonical writable migration transaction guarantees: one committed step is durable; failure in a later step rolls back that step, not earlier committed steps. Do not promise atomic rollback of the entire series or of the pre-migration WAL mode change. Preserve `BaseException` cleanup and the original failure path; keep the newly opened handle owned until successfully returned.

Existing writable `apply_pending` can stop early for recognized lock/read-only failures after a ledger exists. This slice neither widens that tolerance nor labels such a store fully migrated. Strict read-only admission deliberately refuses that older version. Changing writable concurrency tolerance is a separately scoped decision.

Do not drop/rebuild tables, remove unknown columns, rewrite unknown role/game/platform values, manufacture content hashes, synthesize ledger basis, or classify unbound history as current proof. Existing versioned migrations and their already-defined backfills remain in force for explicit writable admission; the shim introduces no new data transformation. Unknown extensions remain untouched, and incompatible shape fails visibly.

Document role vocabulary in the canonical store: new manifest admission currently accepts `donor` and `member` (`registry.py:41`); `anchor` remains a recognized legacy read-side value (`logical.py:240`, `stabs_link.py:308`). NULL and unknown stored values must survive. Do not add a SQL CHECK constraint or normalize historical role values in this slice. This documents the current asymmetry without inventing a new classification.

## Focused regression specifications — author, do not execute

The active mission forbids test execution, fixture/database creation, builds, typechecks and proof scripts. These cases describe test source to author in a separately authorized implementation turn; they are not passed results.

Positive cases:

1. Public shim symbols import successfully in an authorized test environment; `db.SCHEMA is store.SCHEMA`; helpers return the canonical JSON/index behavior; explicit string and Path calls forward the exact selected path.
2. Explicit fresh writable file and the known v0 fixture reach current schema/ledger through canonical migrations; compare known current schema semantics, not timestamps or raw SQLite bytes. Preserve seeded unknown table, column, row and role values. Do not generalize fixture coverage to all historical versions.
3. Omitted-path writable call against an existing historical file warns with that exact resolved path and uses `create=False`; an unrelated configured/runtime database is never chosen. Explicit-path call still permits creation through the canonical API.
4. Current-version read-only file with complete ledger opens and supplies SELECT results. Trace or instrument admission to establish zero migration/backfill calls and zero BEGIN/DDL/DML attempts, even when legacy recovery-family rows would otherwise need backfill.
5. Export `build`, `estimate`, main enumeration, package inventory and materialization inventory all request read-only connections. Fake/spy connection tests preserve the original path and call routing without performing artifact moves or requiring Ghidra.
6. Writable current-version behavior retains existing family-backfill transaction ownership, unknown-without-hash preservation and closed transaction on return. Reuse existing focused test arrangements rather than duplicate their full implementation.

Refusal cases:

1. Omitted legacy path absent, parent absent, or file removed before SQLite open: no mkdir, no new database, no fallback. Use opening-mode instrumentation for the race guarantee; a pre-open `exists()` assertion alone is insufficient.
2. Read-only v0, intermediate ledger version, or future version: clear incompatibility and closed handle; no migration/backfill/WAL write attempted. Cover current version with missing ledger, missing entry, unexpected version/name, and malformed ledger columns independently.
3. Future-version writable file: failure occurs before journal/migration/backfill mutation; unknown future data remains intact.
4. Migration failure, unrelated SQL operational error and interruption: rollback active transaction and close owned handle; no swallowed failure, leaked connection, second open or legacy SQL fallback. Previously committed migrations remain committed by the existing per-step contract.
5. Same public calls against unsupported historical shapes fail visibly rather than drop/rebuild or infer missing identity/basis values. Missing content hashes and unknown role values are not themselves permission to rewrite them.
6. Source-level route assertions keep package `corpus.SCHEMA`, dashboard selected-db precedence, current action IDs/parameter paths and compatibility import names distinct. No deletion/repointing of unrelated schema or registry symbols.

## Allowed verification and completion boundary

For this mission use bounded source reads, text searches and read-only diffs only. Check the owned diff for one baseline SQL literal, no shim `executescript`, unchanged historical path expression, URI `mode=rw`/`mode=ro` handling, no read-only write branch, required canonical path, all five importers retained and all five read-consumer connection sites updated. Inspect test source and documentation links; report test cases as authored/unexecuted. Do not import the project, create fixtures, invoke SQLite, run tests/typechecks/builds/proof scripts, query processes/catalogs or activate server code.

The remaining literal U82 deletion gate is explicit: replace every compatibility consumer with an explicit selected-path API, remove its reliance on `DB_PATH`/no-argument opening, account for public module/symbol users and supported aliases, document the breaking removal/deprecation decision, and then remove the shim. Current source inspection cannot establish external user absence; this is a deletion gate, not a blocker to delegation now.

U22's complete DDL-site ledger ownership, `logical_name` and recovered-function helper ownership, exhaustive per-binary delete registry, full historical migration qualification, remaining identity/basis work and U2's wider determinism/generic-platform obligations stay open. `store.remove_binary`'s hardcoded table list is not accepted as exhaustive. No new binary/platform column may use this partial slice as evidence that all U82/U22 prerequisites are closed.

There is no unresolved premise blocking this bounded implementation contract. The active controller has selected staged compatibility and explicit missing-file refusal; no database equivalence, current installed behavior, external caller inventory or full-unit completion is claimed.
