# Task 2.1 report: canonical schema owner and read-only admission

Status: **READY_TO_COMMIT** for controller source review. No staging or commits performed.
Base supplied by controller: `dd7f2af04a0f08ba5b917a6045b3a1a76a248511`.
Shared HEAD advanced during work to `515d3de6c65709a31f538a57bc6ae853d6fcd7e3`; a read-only base-to-HEAD path comparison showed no committed changes to any owned implementation/test/docs path.
Scope: the adopted `next-schema-unification-contract.md`, staged U82 compatibility only.
Full U2, U22 and literal U82 deletion remain open.

## Implemented behavior

- `corpus.store` remains the baseline SQL and connection owner; existing `migrations.py` remains the only versioned migration executor. No migration version, schema literal, binary column, registry, delete list or route changed.
- `store.connect(path, *, read_only=False, create=True)` preserves required explicit path, row factory, 30-second timeout, writable migration/backfill and existing transaction cleanup. `create=False` uses an escaped absolute file URI with SQLite `mode=rw`; read-only always uses `mode=ro`. Neither branch makes parent directories or uses a file-existence check as permission to create.
- `SchemaCompatibilityError(ValueError)` reports selected resolved path, observed/supported versions and existing 8080 workbench catalog migration guidance. Future versions refuse before WAL/migration/backfill. Read-only admits exactly the current version, a real migration ledger table with its four required columns, and ordered raw `(version, name)` pairs matching `MIGRATIONS`. Unknown ledger extension columns and NULL historical basis hashes remain acceptable. Version/name comparison performs no coercion or ledger repair.
- Read-only admission runs connection-local timeout configuration, version/schema reads and ledger reads only. It has no migration, backfill, BEGIN, DDL or DML branch. Unexpected SQL failures propagate; owned-handle cleanup retains the existing `BaseException` rollback/final-close structure.
- `corpus.db` is now a small deprecated facade. `DB_PATH` retains the exact historical module-derived expression. `SCHEMA`, `ensure_priority_index` and `j` alias canonical definitions. Explicit paths forward unchanged without warning and preserve writable creation. Omission emits a visible `FutureWarning` with the historical resolved path, discloses refusal to create missing files and canonical writable migration behavior, and forwards with `create=False`. No alternate resolver/default/fallback is introduced.
- All three exporter identity-store connections and both package/materialize inventory connections now request `read_only=True`. Their imports, selected paths and other output behavior are unchanged. `name_precedence` and `mizuchi_bridge` retain their writable calls and explicit DDL helpers.
- Canonical module documentation and a short pipeline note document `donor`/`member`, legacy read-side `anchor`, and preservation of NULL/unknown historical values. There is no new CHECK constraint, role normalization or inference of missing hashes/basis.

## Exact owned changed paths

1. `src/agentdecompile_recovery/corpus/db.py`
2. `src/agentdecompile_recovery/corpus/store.py`
3. `src/agentdecompile_recovery/corpus/export_mizuchi_db.py`
4. `src/agentdecompile_recovery/corpus/package_binaries.py`
5. `src/agentdecompile_recovery/corpus/materialize_binaries.py`
6. `tests/test_store_connect_transactions.py`
7. `tests/test_store_migrations.py`
8. `tests/test_corpus_db_compatibility.py` (new)
9. `docs/CORPUS_PIPELINE.md`
10. `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-report.md` (this report)

Other agents' progress/plan/parity/P2 paths were not edited. Git index ownership stays with the controller.

## Regression source authored, all unexecuted

The new compatibility module contains 16 regression functions, with parameterized refusal, forwarding and caller variants. It specifies:

- Public symbol/helper alias behavior; explicit Path/string forwarding and warning absence; historical omitted-path warning/selection and existing-only canonical forwarding despite an unrelated environment selection.
- Missing historical file and missing parent refusal; deletion immediately inside the instrumented SQLite open, checking the exact escaped URI and `mode=rw`; read-only missing-path refusal for both create flag values.
- Explicit fresh creation and the known v0 fixture migration to current version/ledger; known table semantics compared without timestamp/raw-byte claims; seeded unknown extension table/column/row, role/game/platform, NULL role and absent content hashes preserved.
- A current read-only file with complete ledger and NULL historical basis hashes, retaining a stale family row; SQLite trace plus fail-on-call migration/backfill spies require zero write/BEGIN/migration/backfill attempts.
- Independent v0, intermediate and future version refusals; missing ledger, missing entry, wrong version, wrong name, malformed ledger columns and ledger-as-view refusals. Handle subclass instrumentation checks one close, and SQL trace allows only admission reads and connection-local timeout configuration.
- Future writable refusal before WAL/migration/backfill, preserving future data, user version and DELETE journal mode.
- Failure or interruption in a later synthetic migration preserves the first committed step, rolls back the partial second step and closes the one opened handle without fallback.
- Unsupported legacy table shape fails visibly with its existing data intact. Unrelated ledger SQL errors propagate as the original error object and close once; malformed SQLite raises a database error and closes once.
- Export build/estimate/main and package/materialize inventory spies verify exact read-only calls, stopping at admission before artifact moves/output or knowledge-store/Ghidra work.
- Source routing assertions retain package `corpus.SCHEMA` from `contract`, all five `db` imports, two writable callers, workbench selected/saved/configured order and job db-lock injection.

Existing focused sources were adapted narrowly: the legacy reader now expects `SchemaCompatibilityError`; the rollback-failure fake supplies the newly required version read; the existing read-only backfill test name now describes skipping backfill. Existing writable family-backfill transaction and no-hash preservation regression arrangements remain in place rather than duplicated.

## Verification actually performed

- Read applicable AGENTS/source instructions, SDD implementer prompt, complete task brief and adopted contract, plus the relevant canonical store/migrations/caller/test source.
- Python standard-library `ast.parse` of all eight owned Python files succeeded. The check read source only, with no project imports or execution of project/test code.
- `git diff --check` scoped to owned tracked source/tests/docs returned success with no whitespace diagnostics. The new test and report also received source-only whitespace inspection.
- Read-only diff and call-site searches confirmed one baseline SQL literal across store/db, no shim initializer/`executescript`, unchanged historical path expression, atomic `rw`/`ro` opening branches, read-only migration/backfill exclusion, all five updated read connections and two unchanged writable connections.
- Both newly added relative pipeline documentation links resolve to existing source files.
- Inspected diff against the supplied base for owned implementation paths; no migration registry/version/delete or dashboard/corpus package-route changes are part of this patch.

**Not performed:** tests, collection, fixture or database creation, SQLite queries, builds, typechecks, proof scripts, project imports, compiler/checker/Ghidra work, process/runtime/catalog/service operations, systemctl, restart, alternate port, activation, publication or PR creation. No test-pass, database-equivalence, installed-consumer or live-acceptance result is claimed. The current mission explicitly supersedes SDD's generic run-tests/commit recipe; no RED/GREEN execution evidence exists.

## Self-review

Completeness: the facade delegates both positive and refusal paths; there is no retained second initializer. Missing-file refusal is enforced by SQLite opening mode, not a race-prone existence check. Read-only control flow excludes all existing mutators. Future-version checks occur before journal setup. Ledger admission checks raw ordered identities while preserving unknown historical basis values.

Findings corrected during self-review: require a real ledger table rather than accepting a view with the same column names; update the old rollback fake to accommodate the version read; rename the old reader test so it no longer implies that connecting attempts a tolerated backfill write. Add malformed SQLite and unrelated SQL-failure coverage explicitly.

Quality/scope: no third schema module, copied default, schema bump, unrelated refactor or compatibility caller deletion. The canonical connection function owns the handle until return and retains prior cleanup and writable lock tolerance. Documentation names the deliberate missing-file and writable legacy-initialization behavior changes. No active owner/source-root or deployed-state claim was inferred from this checkout.

Remaining limits: authored regressions are unrun and require separately authorized test/migration qualification. Existing writable migration lock/read-only tolerance can still return an older version when another writer blocks progress; this patch neither widens it nor claims full migration. Existing cleanup behavior, including a rollback failure superseding an initialization error while closing in `finally`, is unchanged.

## Remaining acceptance gates

- Controller source/spec/code review and owned-path integration; no commit made by implementer.
- Authorized execution of the focused regressions, supported historical migration qualification and installed/runtime consumer admission. Source inspection is not database equivalence or deployed behavior.
- Literal U82 removal requires every compatibility consumer to use an explicit selected-path API, removal of no-argument/default reliance, public symbol/alias caller accounting and an explicit breaking-removal/deprecation decision before deleting the shim.
- Full U22 ledger ownership of other DDL sites, `logical_name`/recovered-function helpers, exhaustive per-binary delete registry, historical migration coverage and identity/basis work remain open.
- U2 wider ordering, deterministic basis/export/cache and generic platform requirements remain open. No new binary/platform field may cite this partial slice as closure of all U82/U22 prerequisites.
