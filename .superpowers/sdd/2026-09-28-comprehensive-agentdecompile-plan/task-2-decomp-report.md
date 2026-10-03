# Task2.4 — canonical decomp schema ownership

Status: READY_TO_COMMIT for controller source review/integration; independent production review and delegated regression-source completion remain controller-owned pending gates. This is source implementation, not migration, SQLite, test, installed or runtime acceptance. Input: the adopted `next-decomp-schema-contract.md`, its independent review, the prior STABS adoption/fix and the task brief based at `471c63c9`. No Git action was performed by this implementer.

## Implemented dependency boundary

`store.py` owns `DECOMP_TABLE_DDL`, `DECOMP_INDEX_SQL` and `DECOMP_COMPAT_STATE_DDL`. The baseline `SCHEMA` and its existing STABS declarations are unchanged. The physical decomp declaration remains the existing 15-column table: the two nonnullable owner/key integers, nine nullable integer fields including ok, four nullable text fields, the composite primary key, and the declared binary index. No foreign key, extra uniqueness or recovered/source claim is introduced.

Migration `(11, decomp_schema_ownership)` runs only within the runner's existing transaction. It admits the exact v10 ledger and complete STABS postcondition, inspects recognized main decomp shapes, and captures their global behavior before any DDL. The supported shapes are absent, historical 14-column CREATE, current 15-column CREATE, and the historical ADD COLUMN spelling. It creates only a truly missing table, nullable AST column when missing, a missing declared index, and the new singleton compatibility row. It never updates existing decomp rows or generates fingerprints. It validates the resulting shape/state before the unchanged runner records the ledger/version and commits.

The state row preserves logical `absent`, `skeleton_hash` and `ast_fingerprint` modes. Physical schema installation alone does not convert missing witnesses into measured zero, or stop legacy skeleton selection. Historical AST NULL, empty string, arbitrary text and whitespace values remain unchanged. An absent state containing rows and a skeleton state containing any non-NULL AST value refuse. The latter integrity check can scan the AST column; no performance measurement or additional index is claimed.

Migration10 changes only its direct-repeat branch: explicitly require ledger10 and the complete STABS shape, rather than a current-version public guard. Its v9→v10 operations remain unchanged. Migration11's repeated body explicitly requires ledger11 and complete shape/state. Neither repeated body repairs a claimed-current store; a synthetic future registry cannot move these repeat predicates. Steps1–9 and the runner are unchanged, including their lock/read-only tolerance, per-step durability and existing ledger basis hook. No prior NULL basis hash is rewritten.

## Admission and readers

- `store.require_decomp_schema(con)` is a nonmutating current writer guard. It checks ledger, STABS, physical decomp and singleton state, reports observed/supported versions and concrete reasons without inventing a caller-owned path, and lets SQL/I/O exceptions propagate.
- `store.decomp_read_state(con)` is a nonmutating bounded reader for supported ledgered v9/v10/v11 shapes. It returns None, skeleton_hash or ast_fingerprint. Historical stores carrying the new state table refuse. The canonical read-only connect remains stricter: complete current v11, including both STABS and decomp. Existing writable initialization, backfill and tolerated-old-handle behavior remain unchanged; an old handle cannot pass direct writer admission.
- Shape inspection uses main-qualified schema/column reads, known declaration normalization, exact table_xinfo and index ownership. It rejects views/virtual tables, unknown P-code extensions, altered fields/defaults/PK/generated metadata, constraints/collations, STRICT/WITHOUT ROWID, undeclared local objects, occupied names including separate trigger namespaces, and noncanonical reserved spelling. Relevant TEMP shadows are rejected using SQLite ASCII NOCASE semantics; attached objects cannot supply a missing main object.
- `Binary` resolves/admit-checks the selector before ensure_func_columns and outside the broad optional-row decoding catch. Its successful-row ordering, JSON decoding, skeleton channel and compatibility pcode_fingerprint field remain unchanged. The receipt uses the same selector and the same non-NULL/nonempty count, same-ID counting, fields and availability formulas. No COALESCE, trimming or per-row fallback was introduced.
- Recovery status reads the logical state in its existing snapshot. Logical absence keeps per-build/by-build witnesses None and aggregate0; installed-empty remains0; successful witnesses still count distinct ok1 addresses. Source availability, compilation, byte-verification and wrapper contracts are untouched. The STABS physical-table inventory panel is unchanged and remains physical inventory.
- `_matching_input_digests` changes only its matcher-input projection to v2, adding logical mode and the selected stored fingerprint to the same ordered rows. This invalidates v1 comparison inventories and selector/fingerprint changes without touching receipt equality logic, unrelated cache projections or determinism engines. All other preparation functions remained AST-identical at this packet's handoff. Its U9 mutation remains queued by the controller until production review settles, preserving serialized ownership.

## Writers and transaction ownership

Public signatures and successful result dictionaries remain unchanged; `MAIN_SCHEMA` remains an import-compatible composition of the canonical declarations but is not executed by corpus operations. syntax_fingerprint's tokenization, keywords, anonymous token normalization, unmatched marker, prefix and BLAKE2b parameters remain AST-identical. The separate skeleton producer was not edited.

A private main-state DML helper switches to AST mode only within the admitted operation scope. Corpus operations validate before feature work, then revalidate within BEGIN IMMEDIATE or their private savepoint immediately before mutation. Main persistent DML is explicitly qualified. There is no corpus CREATE/ALTER installer in the writers or public helper.

`persist_code` keeps one-key INSERT OR REPLACE and exact falsy/truthy payload construction, including twelve NULL fields for None/empty strings and actual features for whitespace. Its success still commits caller pending work. The private savepoint remains until commit; pre-durability write/commit/interruption failure rolls back only that scope when SQLite retains the transaction. Owned scopes roll back their own work. Cleanup failures propagate. Transaction loss or a successful-but-unacknowledged commit raises an explicit uncertainty error; it is never reported as successful rollback or reconstructed caller work.

`attach_store` owns its canonical handle, explicitly materializes AST mode even when empty, commits that state and returns. Failure rolls back owned pending work and closes the handle. `ensure_decomp_columns` is an explicitly documented compatibility mutator: skeleton switches to AST, AST/absent are no-ops, standalone transitions commit, and caller transactions participate without commit. Old NULL AST values are never fabricated during the transition.

Independent `decomp_part` retains its declaration, key, payload, algorithms and explicit writer commit. Its installer is isolated from corpus schema admission. Destination/domain inspection refuses corpus or mixed handles before part DDL, raw unledgered corpus decomp refuses, relevant TEMP shadows refuse, and an empty compatibility handle stays a no-op. Part handles close on failure as well as success.

## Frozen deletion

The original TABLE_SQL, INDEX_SQL, OPTIONAL_TABLES, REQUIRED_ADDITIONS, OPTIONAL_ADDITIONS, v9 ledger, v10 ledger and DELETE_ORDER are unchanged. Explicit v11 table/mandatory/optional deltas and ledger11 require the canonical AST column, declared index and exact singleton state. State consistency is inspected independently of the live migration registry. Version12 and unknown schemas continue refusing. Existing TEMP/attached refusal, dependencies, ownership, row counts, transaction executor, savepoints and noninitializing opener remain unchanged.

Literal source accounting confirms v9/v10 retain 27 known /17 mandatory /10 optional tables. V11 has 28 /19 /9. Global decomp_schema_state is omitted from deletion order and retained, including after last-binary deletion; it is not included in affected data-row counts.

## Authored regression sources, not executed

The initial implementer authored the following and transferred all test-file ownership to the controller's additional regression worker before further test edits. The final delegated review/completion should be recorded below rather than inferred from initial authoring.

- Actual target9/10 fixtures and independent historical CREATE/ALTER declarations; absent/empty/populated states, missing/correct indexes, NULL/empty/arbitrary AST values and unchanged rowids/fields/binaries/ledger rows/unrelated extensions.
- Real Binary/by_skeleton/by_pcode/candidate_pairs and receipt comparisons before/after migration, same-ID counts, public corpus_status/build/by_build/wrapper None-vs0 behavior, and actual matcher-input/receipt cache comparison helpers.
- Explicit ensure/attach/persist selector transitions; exact writer payload/result, owned/caller success, pre-durability write/commit/KeyboardInterrupt failures, cleanup failure and committed-but-unacknowledged behavior; independent part and mixed destination cases.
- Physical-shape refusals, ASCII-case main/TEMP table/view/ledger shadows, current-state contradictions, direct version-bound repeat behavior including a future registry, tolerated actual-v10 writer refusal, and retained singleton state after deletion.
- Existing current fresh/known-v0 assertions include decomp postconditions. Existing deletion fixtures now use explicit frozen decomp DDL for actual9/10 and the actual runner for11. Existing STABS migration tests distinguish actual target10 repeat compatibility from current11 writers and future12. Controller explicitly extended test ownership for this narrow STABS fixture correction.

No test, fixture operation, project import or fingerprint computation was performed. Authored assertions are intended acceptance conditions, not observed results.

## Source-only checks and exact limits

1. Read repository authority/entry references, complete adopted decomp contract and review, preceding STABS contract/report/reviews, U2 requirement/extract, named declarations/callers and controller admission receipts. A bounded memory registry search supplied no task-specific technical fact used in implementation.
2. Saved seven pre-edit source copies under `/tmp/task-2-decomp-source-before/` for local text/AST comparison; no Git or executing checkout access was used. Produced `/tmp/task-2-decomp-source.diff` with standard-library difflib.
3. Standard-library ast.parse passed for all seven production modules. Direct trailing-whitespace checks passed for production files and this report. The documentation retains its preexisting two-space Markdown hard break on line3; an initial whole-document whitespace assertion identified only that intentional line. No project code was imported or evaluated.
4. 132 AST/literal preservation assertions passed against those pre-edit copies. Details: `/tmp/task-2-decomp-source-checks.txt`. These cover baseline/STABS declarations; all earlier migration and runner functions; migration10's forward nodes and prior registry entries; public writer argument/return annotations; PART_SCHEMA, fingerprint constants and syntax_fingerprint; frozen deletion declarations/order and all unchanged deletion functions; matcher algorithms and Binary members other than __init__; every preparation function except the authorized projection.
5. Literal-only table inventory counting confirmed the specified old/new deletion counts. Local link checks found no missing relative target in docs/CORPUS_PIPELINE.md.
6. Source searches found no additional production caller/installer for the public corpus decomp writers beyond the adopted bounded inventory. The existing test_corpus_features Binary consumer already opens canonically; it did not require another fixture change. No external caller completeness claim is made.

The controller's saved admission receipts report healthy8080 PID2697197/start_ticks68973313 at `/home/brunner56/agentdecompile-nvme`, watchedFiles0/restarts0 and blank revision. These are inherited dispatch evidence, not fresh observations by this worker. Retained loaded-module provenance is explicitly historical; this checkout was not synchronized or activated.

No Git/staging/commit/PR, subagent creation, tests/collection/build/typecheck/proof, project imports, DB open/query/create/migration, fingerprint/key/crypto/compiler/checker, process/runtime/live/catalog/provisioning/capture, service/systemctl/restart/port or publication operation was performed by this implementer. All SQLite rollback/concurrency/historical-compatibility, installed-consumer, runtime and recovery acceptance remain unverified. Wider U2/U22/U82 and all other persistent DDL owners remain separate work.

## Exact packet paths

Production and documentation:

- `src/agentdecompile_recovery/corpus/store.py`
- `src/agentdecompile_recovery/corpus/migrations.py`
- `src/agentdecompile_recovery/corpus/decompile.py`
- `src/agentdecompile_recovery/corpus/match_store.py`
- `src/agentdecompile_recovery/corpus/dashboard/recovery_status.py`
- `src/agentdecompile_recovery/corpus/dashboard/preparation.py` (matcher input projection only)
- `src/agentdecompile_recovery/corpus/delete_registry.py`
- `docs/CORPUS_PIPELINE.md`

Authored test sources, then transferred for independent completion:

- `tests/test_store_migrations.py`
- `tests/test_corpus_db_compatibility.py`
- `tests/test_corpus_delete_registry.py`
- `tests/test_corpus_stabs_migration.py` (controller-approved narrow extension)
- `tests/test_corpus_decomp_schema.py` (new)

Report:

- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-decomp-report.md`
