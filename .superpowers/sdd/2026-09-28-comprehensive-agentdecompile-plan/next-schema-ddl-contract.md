# U2/U22 next DDL ownership slice: STABS schema adoption

Status: implementation-ready proposal for controller adoption, 2026-10-02. Source inspection only; no implementation, migration, database equivalence, test execution, installed behavior or runtime acceptance is established. This investigation owns only this file. Task2.1 and Task2.2 are reviewed source seams; their database behavior remains unqualified.

## Decision and first missing predicate

Adopt one narrow predicate: **a successful canonical migration to version 10 guarantees the existing STABS table, both existing STABS attribution columns on `func`, and their declared indexes; STABS operations never install persistent schema themselves.** The existing migration runner owns the additions and records `Migration(10, "stabs_schema_ownership", ...)`. Preserve migration 1–9 identities and behavior. Do not add binary/platform columns, create a second runner, perform raw extraction, or claim all U22 ownership complete.

This is the namespaced `portable-plan-2026-09-21:U22/U82` obligation retained in `unit-2-schema-extract.md`, not integration U22's optional AI work. U82's duplicate `db.py` initializer is already replaced by the reviewed facade; literal facade deletion and its external caller accounting remain separate.

STABS is the smallest dependency-coherent first slice because `stabs_type` and `func.source_file/object_file` already belong to migration 1. Only `func.stabs_name`, `func.stabs_type` and `ix_func_srcfile` remain installed outside the ledger. This has real current callers, needs no table rebuild, and can preserve every existing row including NULL/unknown attribution. Moving all optional tables into a new baseline would conceal distinct compatibility and data migration obligations.

A complete source slice necessarily includes the versioned deletion profile and nonmutating writer admission: `apply_pending` can return an older version under lock/read-only tolerance, and current deletion supports only v9. Neither a version bump alone nor removal of `CREATE` calls closes this predicate.

## Observed source inventory

Locators below are relative to `src/agentdecompile_recovery/corpus/` unless fully prefixed. Line numbers locate the inspected source and may move. `NN` means NOT NULL; unspecified fields are nullable. These describe source declarations, not a queried live schema.

### Canonical owner and escape hatches

| Site | Current source contract and actual callers |
|---|---|
| `store.py:21–167`; `migrations.py:83–95` | Migration 1 executes baseline `binary`, `func`, `calledge`, `logical_function`, `identity`, `stabs_type`, `match`, `eval` and their indexes. `_baseline` calls `ensure_func_columns`, `ensure_match_columns`, `ensure_priority_index`. Baseline remains an initialization input, not a public substitute for the ledger. |
| `store.py:259–275` | `ensure_func_columns` adds `func.block_hashes,cfg_nodes,cfg_edges,hash_reloc,hash_instr,hash_mnemonic,hash_raw,symbol_provenance` as TEXT, then calls `ensure_binary_columns`. Outside migration 1, `extract.py:288` and `match_store.py:98` still call it. |
| `store.py:278–290` | `ensure_match_columns` adds relation TEXT NN DEFAULT 'one_to_one', src_end/dst_end INTEGER, kind TEXT, confidence REAL, algorithm TEXT. Migration 1 and migration 9 call it; `propagate.py:57–59` also calls it. |
| `store.py:305–317` | `ensure_binary_columns` adds `content_sha256` and `recovery_family` TEXT then runs the separate data backfill. `extract.py:219` calls it outside baseline; family backfill also runs on writable `connect`. Unknown/missing hashes are not inferred. |
| `store.py:411–415` | Explicit `ensure_priority_index` still executes `ix_func_priority_cover ON func(binary_id,addr,size,n_instr,name)` outside migration through `mizuchi_bridge.py:272` and `external_bridge.py:225`. |
| `db.py:14–41` | Compatibility-only `DB_PATH`, aliases for SCHEMA/index/JSON helper, and delegation to `store.connect`; no independent DDL initializer remains. Five direct compatibility importers accounted for by Task2.1 retain their paths/roles. |
| `migrations.py:98–278` | v2 analyzer identity columns; v3 `basis_supersession`; v4 canonical review schema; v5 `func.return_storage/function_properties` and `func_param`; v6 `ghidra_field`; v7 `bsim_query/bsim_hit`; v8 recorded-channel relabel; v9 match metadata and index. Preserve this history; historical data transformations are not permission for new backfill. |
| `match_review_schema.py:21–108,132` | Three review tables, indexes and triggers installed through v4; read-only `require` validates them. This is already ledger-owned and is not part of this migration body. |

### Persistent corpus DDL outside that runner

| Owner / exact shape | Current DDL and callers; material risk |
|---|---|
| `stabs_link.py:18–29`, duplicate of `store.py:127–137` | `stabs_type(id INTEGER PK,binary_id INTEGER NN,source_file TEXT,object_file TEXT,name TEXT NN,kind TEXT,stab TEXT NN,func_addr INTEGER,UNIQUE(binary_id,source_file,name,kind,stab,func_addr))`. No FK; nullable components deliberately survive and are deduplicated by the replacement payload logic. `replace_stabs_types:81` creates it plus `ix_stabs_type_bin(binary_id,kind)` and `ix_stabs_type_src(binary_id,source_file)`, commits, then replaces one binary's rows. `stabs_types.persist_types:16–35` calls it; `persist_types_from_macho:38` feeds parsed Mach-O rows. |
| `stabs_link.py:32–45` | `ensure_columns` conditionally adds `source_file,object_file,stabs_name,stabs_type` TEXT to `func`, creates `ix_func_srcfile(binary_id,source_file)`, commits. First two are already baseline fields. Callers: `stabs_link.link:175`, `stabs_manifest.py:124–126`, CLI `apply-stabs`/`propagate-source` at `cli.py:1051–1065`, and `dashboard/workflow.merge_evidence:454–460`. Known operating wrappers obtain canonical writable connections; the public helpers also accept caller-supplied handles. Tolerated incomplete migration still needs refusal. |
| `export_types.py:16–27,323–342` | `ghidra_type(binary_id INTEGER NN,name TEXT NN,kind TEXT NN,size INTEGER,definition TEXT NN,n_fields INTEGER,PK(binary_id,name,kind))`; `ix_ghidra_type_bin(binary_id)`. `export` checks that ledger-owned `ghidra_field` exists, then executes schema, replaces type/field rows and commits. Entry caller `kx_cli.py:427–434`; also `pipeline.py:240–260`. Typed-field presence alone does not prove ledger/version/shape admission. |
| `propagate_types.py:14–24,38–47` | `ghidra_type_origin(binary_id INTEGER NN,name TEXT NN,donor_slug TEXT NN,donor_game TEXT,size INTEGER,PK(binary_id,name))`. `plan_adoptions` executes both type schemas and adds optional `ghidra_type.origin TEXT`; it swallows every exception from ALTER, then `_has_origin` changes donor filtering. `apply_adoptions:102–124` writes both tables and commits; pipeline calls plan/apply at `pipeline.py:266–267`. Existing six-column native table and seven-column table with origin are real supported source shapes. A migration must retain origin NULL/`native`/`adopted:*` meaning without inventing provenance. |
| `pipeline.py:240–245`; generated `dashboard/workflow.layout_script:634–646` | Additional type-schema installers, easy to miss when only inspecting export/propagation. Generated script directly inserts six native type fields with `INSERT OR IGNORE`, commits, and builds a header. Pipeline installs schema before counting rows. Both must move with the later type ownership slice; not changed here. |
| `decompile.py:95–115,118–120,203–217` | Persistent `decomp(binary_id INTEGER NN,addr INTEGER NN,ok,n_tokens,n_lines,max_nest,n_calls,n_locals,n_deref,n_index,n_field INTEGER,ctrl,ops,skeleton_hash,ast_fingerprint TEXT,PK(binary_id,addr))`; `ix_decomp_bin(binary_id)`. `persist_code` and `attach_store` execute MAIN_SCHEMA; shared helper adds nullable `ast_fingerprint` if absent. No production call to these public main-store writers was found in bounded src/scripts searches; this does not establish absence of external users. Actual readers below prove stored compatibility matters. |
| `ingest_recovered.py:30–78,86–193` | `recovered_function`: program/name/path TEXT NN, binary_id/addr/size/logical_id INTEGER, convention/machine_code/evidence/source_sha256/target_sha256/semantic_status/semantic_reason/semantic_evidence TEXT, real_c INTEGER NN; current PK `(program,name,binary_id,addr,path,source_sha256)`, index logical_id. `reuse_candidate`: src_program/src_name TEXT NN, dst_binary_id/dst_addr INTEGER NN,dst_name TEXT,size/real_c INTEGER NN,basis TEXT NN; PK `(src_program,src_name,dst_binary_id,dst_addr)`, index `(dst_binary_id,dst_addr)`. `ensure_recovered_function` supports actual legacy keyless report, `(program,name)`, and `(program,name,binary_id,addr)` layouts, adds seven known columns, conditionally rebuilds, and preserves invalid-NULL populated legacy rows. `ensure_recovered_schema` additionally installs reuse schema and commits. Callers include ingest at `:434,:615,:720`, CLI `:1332–1336`, `mizuchi_bridge.py:102`, `external_bridge.py:95`, `export_run_report.py:31`. Rebuild/legacy row preservation cannot be replaced with blind CREATE IF NOT EXISTS. Current delete profile intentionally refuses old keys. |
| `name_precedence.py:153–170` | `logical_name(logical_id INTEGER PK,name TEXT,tier INTEGER,tier_name TEXT,from_binary_id INTEGER,source_file TEXT,signature TEXT,n_members INTEGER,detail TEXT)`. `run(apply)` installs via legacy facade even for reporting. This is a persistent derived cache, distinct from the identically named TEMP report table. |
| `propagate_conventions.py:98–110,214` | `func_convention_derived(binary_id INTEGER NN,addr INTEGER NN,deco_class TEXT NN,stack_bytes INTEGER,fastcall_n INTEGER,class_source TEXT NN,n_source TEXT NN,PK(binary_id,addr))`; derive writer executes SCHEMA. Cross-build source provenance lacks donor IDs; no general dependency deletion is implied by adopting DDL. |
| `dashboard/workbench.py:457,468,485,651`; `dashboard/preparation.py:2027` | `binary_content_identity(source_path TEXT PK,sha256 TEXT NN)`; `binary_source_alias(source_path TEXT PK,binary_slug TEXT NN,sha256 TEXT NN)`; `program_binding(source_path TEXT NN,locator TEXT NN,program TEXT NN,updated REAL NN,PK(source_path,locator))`. Registration/type-independent program binding is persistent corpus-side state. Alias ownership is stored slug; source identity and bindings survive binary deletion under reviewed policy. |
| `fix_func_counts.py:47–56`; `kx_cli.py:437–443` | Applies optional `binary.code_func_count INTEGER` plus measured count updates. It is an existing writer, not authorization to add further platform columns. Split DDL adoption from count recomputation in its eventual migration contract. |

`delete_registry.py:27–374` contains frozen SQL **inspection declarations**, not another initializer: the source must not be counted as executing the CREATE text it compares. Its strict ownership, dependency and transaction policy remains authoritative for removal.

### Independent persistent stores and temporary state — do not migrate into corpus

| Source / objects | Boundary |
|---|---|
| `decompile.py:74–92,159–201` | `decomp_part` uses `repo_path,addr` PK and the same nullable metrics/text fields as decomp; `persist_part(part_path,...)` explicitly opens an independent file. Shared `ensure_decomp_columns` currently visits both names. A later decomp slice must separate this installer from corpus admission. |
| `decompile_text.py:8–26` | `ctext(repo_path TEXT NN,addr INTEGER NN,ok INTEGER,signature TEXT,code TEXT,PK(repo_path,addr))`; independent path through `connect_ctext`. |
| `ingest_ghidra_knowledge.py:14–35,117–119`; generated `dashboard/workflow.py:574–575` | Knowledge destination `func_knowledge`, `ingest_status`, and `knowledge_attempt(program,entry_hex,error,PK(program,entry_hex))`. Program/entry identity is not integer corpus binary ownership. |
| `dashboard/entity_activity.py:289–300` | Explicit `workbench-activity.sqlite`: activity_event and activity_observation plus scope/signature indexes. Separate journal. |
| `src/agentdecompile_grid/view/applier.py:162–203,210` | Independent view version 1: grid_view_position(partition), grid_tasks(task_id), grid_results(task_id,result_ref), grid_view_events(partition,seq,event). `ensure_tables` intentionally avoids executescript to preserve the applier transaction. |
| `src/agentdecompile_recovery/grid_lanes/cascade.py:303–330`, `compile.py:441`, `parity.py:775`, `verbs.py:427` | Grid hook tables grid_match_score, grid_compile_receipt, grid_parity_receipt, grid_verb_receipt use task/content/basis references. Text source/destination digests are not corpus integer FKs. Scratch corpus materializations at `verbs.py:339,374` do not make the grid view schema a corpus schema. |
| `stabs_link.py:241`; `report_propagation.py:22,61,65`; `mizuchi_bridge.py:310`; `external_bridge.py:257` | TEMP stabs_donor_addr; TEMP logical_name/multi_build and temp index; TEMP priority_candidate. Connection-local scratch remains local. Deletion currently refuses all temp objects to prevent shadowing; do not weaken that rule. |
| `ingest_recovered.py:184–187` | recovered_function_candidate_migration is a transient rebuild artifact, not an accepted completed corpus table. |

Planned `logical_signature`, `func_bsim`, and `vtable` have no current CREATE TABLE source in this corpus inventory. Do not fabricate their DDL, migration history or deletion predicates. Current BSim tables are named bsim_query/bsim_hit.

## Implementation ownership and APIs

One future implementer owns the following coherent patch; controller separately adopts and integrates it. Preserve others' changes.

1. `store.py`: make STABS declarations canonical without altering emitted migration-1 schema; expose one nonmutating STABS shape-admission helper. Retain required paths, public connection defaults, recovery-family behavior and role vocabulary.
2. `migrations.py`: append exactly one version-10 migration; a small reusable read-only ledger admission helper can be extracted from the existing `store.connect(read_only=True)` check to avoid duplicating version/ledger logic. It remains inspection, not a second runner.
3. `stabs_link.py`: retain public signatures and alias constants for import compatibility, remove duplicate persistent DDL ownership, and replace runtime installs with admission. Retain TEMP donor table behavior.
4. `delete_registry.py`: explicitly support frozen v9 and v10 STABS variants and matching ledgers; do not infer all future support from latest migrations.
5. Focused authored regression updates: `tests/test_store_migrations.py`, `tests/test_corpus_db_compatibility.py`, `tests/test_corpus_delete_registry.py`, `tests/test_corpus_stabs_link.py`, and a small new STABS migration test module if clearer. No test execution is authorized by this proposal.
6. A short `docs/CORPUS_PIPELINE.md` note on v10 adoption, compatibility/refusal and unfinished owners. Controller owns living-plan/progress changes.

No CLI/workbench route, generated recovery job, source extractor or catalog parameter change is needed: current callers still use the same functions. If source inspection during implementation finds an additional direct initializer for these exact STABS objects, include that site and report it; do not extend this into type or recovered-function migration.

Keep `stabs_link.ensure_columns(con) -> None`, `replace_stabs_types(con,binary_id,types) -> int`, `apply_manifest_records(...,commit=True)`, `link(...)`, and `propagate_source_files(...)` signatures. `STABS_TYPE_DDL` becomes an alias of the canonical declaration; `ADD_COLUMNS` may remain a compatibility alias of a canonical tuple documenting the four historical fields. No new DB path or product filter.

**Intentional API tightening:** `ensure_columns` becomes validation-only and no longer repairs arbitrary raw SQLite connections or commits caller work. Existing known callers use `store.connect` and receive the fields from v10. External raw/old handles must be explicitly migrated through the canonical owned path first; they receive a clear schema error. Do not silently call the runner from this helper. Likewise `replace_stabs_types` must not create missing schema before mutation.

## Canonical declaration and migration contract

Use one canonical STABS table declaration and the two existing STABS index declarations in `store.py`. Embed them in `store.SCHEMA` with identical emitted SQL semantics (no baseline new fields or version-history rewrite). The old `stabs_link.STABS_TYPE_DDL` aliases that declaration. Migration 10 must not import `stabs_link`, Mach-O parsers or Ghidra; a schema migration cannot require producer runtime imports. `store` is already imported by migrations, so avoid new import cycles; ledger-helper access can be local inside validation functions as it is today.

Version 10 has **no new table**, no new binary columns, no changed key, FK, role, format, default or row:

- Add `func.stabs_name TEXT` if absent.
- Add `func.stabs_type TEXT` if absent.
- Ensure `ix_func_srcfile ON func(binary_id,source_file)`.
- Require the existing canonical stabs_type table and its two canonical indexes; existing missing declared STABS indexes may be recreated within migration 10 after validating their names are unoccupied. A wrong existing object is never overwritten.
- source_file/object_file must already have their baseline TEXT shape. A purported v9 missing these baseline fields or stabs_type is corrupt/unsupported, not an undocumented legacy upgrade. Do not recreate a missing table and stamp it as migrated evidence.

Migration starts under the runner's existing BEGIN IMMEDIATE. Before its first DDL, require observed version 9 with the exact v1–v9 ledger (correct columns and ordered version/name pairs), and inspect the STABS objects and the attribution columns. Ignore NULL historic basis hashes exactly as Task2.1 does. Earlier version paths first run their existing steps to 9; this migration does not claim those paths support every historic database shape.

Keep step idempotence explicit: normal repeated runner calls skip v10. A directly repeated migration body under an owned transaction may validate a complete v10 ledger/postcondition and return without DDL; it must not stamp or repair an inconsistent claimed-v10 database. Every other pre-version fails. This preserves the runner's existing safe-repeat rule without admitting future versions.

Recognized pre-v10 func variants: neither STABS-only column, either one, or both, with each present one exactly nullable TEXT, no default, not PK/hidden/generated. Preserve values verbatim. Validate binary_id/source_file/object_file as the existing source-required base columns. Preserve unrelated func columns, known and unknown, without broadening deletion support for them. A source extension outside STABS must not be dropped to make the migration fit; full deletion may still refuse it.

For stabs_type, admit only the existing canonical table declaration and its keys/nullability; refuse views/virtual tables, changed UNIQUE/FK/CHECK/default/owner shape, extra columns or undeclared local triggers/indexes. The table has no post-baseline ALTER variants in the inspected writers. Strict declaration comparison can reuse the existing pure normalization in `match_review_schema._normalized` for this simple unchanged CREATE declaration; do not import the delete executor or invent a new general SQL parser. Permit only the already documented SQLite IF-NOT-EXISTS/whitespace normalization, not arbitrary semantic-equivalence guessing. Inspect `main` explicitly and refuse a temp object named func or stabs_type that could shadow later unqualified DML. An index name occupied by another table/object is a refusal, never CREATE IF NOT EXISTS success.

After additions, validate the postcondition before the runner records version 10. The ledger row and version commit with the DDL or not at all. Use individual execute calls, never executescript or an internal commit. A failed step rolls back only step 10; previously committed steps remain durable. WAL mode configuration before migration is not part of that atomicity promise.

No UPDATE backfill is needed: newly introduced values stay NULL. Do not derive STABS names from func.name, source_file from a slug, or types from another binary. Do not change recovery/basis identity, rewrite old ledger hashes, or record a supersession merely because DDL ownership changed. Raw-image parsing/re-extraction remains separately cataloged, admitted, resumable and costed work. This report neither schedules nor runs it.

## Read and writer admission, transactions and deletion

### Nonmutating admission

Provide `store.require_stabs_schema(con) -> None` (or an equivalently named single helper). It checks current supported version, exact complete ledger, required STABS shapes/columns/indexes and shadowing before the operation. It performs no DDL, DML, BEGIN, commit, backfill, close, connection reopening or migration. Errors must identify the STABS schema requirement and observed/current version; use the established schema-error family or a specific ValueError with stable reason, without fabricating a filesystem path for an in-memory/caller-owned handle.

The shared ledger inspector must preserve Task2.1 behavior and not turn a connection validator into a generic schema migration engine. `store.connect(read_only=True)` continues to reject old and future versions and validate the complete ledger, now v10. Its v10 path also validates this newly promised STABS postcondition; claimed-v10 missing columns cannot be admitted as ready. Other schema completeness remains outside this narrow check. A valid v9 read-only handle now refuses through the canonical strict reader, deliberately; deletion can still inspect v9 independently. Writable `connect` retains existing migration/backfill/lock semantics and does not turn tolerated incomplete migration into a false STABS success. Every STABS writer checks admission before touching persistent rows, including direct calls to `apply_manifest_records` and `propagate_source_files` (not only their current wrappers).

Migration 10 uses the underlying shape validator without demanding v10 before the runner stamps it. Do not invoke current-version admission from inside a pending migration. On fresh/known old stores, the baseline creates the table and migration 10 adds both fields; on existing canonical v10 the helper is read-only. Direct raw unledgered handles refuse, even if field names happen to exist.

### Preserve explicit transaction owners

- `ensure_columns` is validation-only: preserve an existing caller transaction and all pending rows on both success and refusal. It must not call commit.
- `replace_stabs_types` currently precommits before `with con`; eliminating DDL must not retain that hidden precommit. Build/deduplicate payload before mutation. With no active transaction, own BEGIN IMMEDIATE and commit/rollback the selected binary's delete plus insert. Within a caller transaction, use a unique savepoint, release on success and rollback only that savepoint on failure. Return the deduplicated count; caller-owned success remains provisional. Catch BaseException for cleanup; rollback failures propagate, never success. Preserve nullable-key deduplication and all other binaries.
- `apply_manifest_records` retains its explicit `commit` parameter and CASE logic; no broad transaction redesign. Validate before executemany. Its `commit=True` still commits by public contract; `False` participates without commit.
- `propagate_source_files` retains its existing TEMP donor preparation and explicit transaction ownership. Validate before temp creation or data writes; do not attempt to migrate while temp scratch exists. Do not make this slice a donor/identity algorithm or transactional propagation refactor.
- `link` retains reviewed-manifest equality, architecture slice selection and no-human-overwrite logic. No migration-generated attribution is allowed.

### Explicit dual deletion profile

Current `_schema_preflight` at `delete_registry.py:438–492` hardcodes user_version 9, 17 mandatory tables, ten optional tables, the full v1–v9 ledger, optional `func.stabs_name/stabs_type`, and recognized ix_func_srcfile. Add explicit version selection for **9 and 10 only**:

| Version | Required profile |
|---|---|
| 9 | Preserve reviewed profile unchanged: STABS-only func columns may be absent; ix_func_srcfile may be absent; exact original nine ledger entries. No schema writes during deletion. |
| 10 | Same 27-table inventory and ownership; require both STABS-only columns and ix_func_srcfile, canonical stabs_type/indexes, and the additional exact `(10,stabs_schema_ownership)` ledger row. |
| Other, including 11 | Refuse unchanged before data writes. Never substitute live MIGRATIONS as blanket future deletion authorization. |

Use a small explicit version-profile delta rather than duplicate the full 27-table SQL map. Existing table ownership/deletion order, unknown extension refusals, temp/attached database refusal, match-review validation, survivor dependency restrictions, counts, atomic executor and noninitializing opener stay unchanged. `stabs_type` still deletes by binary_id. Function attribution columns disappear only with their owning func rows. Nothing else becomes safe to delete because schema ownership improved.

## Positive and refusal regression source

Author meaningful cases; none is authorized to execute during this source-only mission.

1. Fresh canonical initialization and frozen known-v0 path reach v10 via actual migration registry. Verify the unchanged v1–v9 ledger prefix, one v10 row, required columns/indexes, no STABS attribution rows invented and unknown roles preserved. State that only the named old fixture was covered.
2. Construct actual v9 through `apply_pending(target=9)` rather than creating v10 and merely relabeling it. Exercise neither/either/both optional STABS fields and ix_func_srcfile absent/present. Seed real non-NULL and NULL attribution and stabs_type rows; all retain values and row identities. Reopen/reapply has no DDL/DML on the already-current migration path.
3. Unsupported existing stabs column type/default/generated/PK, wrong table/unique/index shape, missing baseline source_file/object_file/stabs_type, occupied index name, shadowing temp object, malformed or missing v9 ledger: refuse; no migration-10 DDL or row/version/ledger change survives. Keep an unrelated unknown func extension untouched when supported migration succeeds; deletion still refuses that extension.
4. Inject failure after each ALTER/index creation, ledger insertion and user_version write, and at the COMMIT call before durability. Check rollback of the pending step and exact prior data; earlier committed migrations remain. An error after a successful COMMIT cannot roll back durable data: report it as committed/uncertain acknowledgement, never reverted data or successful receipt. Preserve this distinction for owned replacement transactions as well. Include interruption and lock contention. The runner's tolerated old handle must fail STABS admission before its first operation write.
5. Strict read-only v10 plus complete schema opens without migration/backfill/BEGIN/DDL/DML; old v9 and future v11 refuse. Claimed-v10 missing STABS field/index/table or damaged ledger refuses. NULL legacy basis hashes remain accepted.
6. `ensure_columns` admits migrated caller-owned handles without commit; refuses raw/v9 handles without repairing them. `replace_stabs_types` still deduplicates nullable rows and replaces only selected binary types; owned commit, caller savepoint rollback, insertion failure, interruption and commit failure preserve the specified ownership boundaries.
7. Direct apply_manifest_records and propagate_source_files calls validate before persistent mutation; public signatures and manifest/architecture/human attribution rules remain. A minimal canonical store fixture replaces raw unledgered test setup only where necessary; retain an explicit raw-handle refusal case instead of silently deleting that compatibility coverage.
8. Deletion positive fixtures for actual v9 and migrated v10, identical target/survivor data and expected counts. v9 optional STABS absence remains supported; v10 absence/wrong ledger refuses without initialization. Preserve all Task2.2 survivor and rollback cases. Update the old `[0,8,10]` future-version test to distinguish valid v10, falsely stamped v10 and future 11; do not simply remove version checks.
9. Source/caller checks demonstrate no persistent CREATE/ALTER/index install or commit remains in ensure_columns, no persistent DDL remains in replace_stabs_types, and no new schema writes were introduced into direct manifest/propagation paths. TEMP stabs_donor_addr remains its existing independent scratch path.

Test fixtures using source literals need attention: `tests/test_corpus_delete_registry.py:18–34` AST-extracts optional writer SQL. This STABS-only slice does not alter those seven optional literals, so it should not break that extractor. Tests that hardcode v9 as current must be separated into deliberately frozen-v9 fixtures versus latest fixtures, not mechanically replaced everywhere.

## Why other owners remain separate

- **Type export/propagation:** adopt ghidra_type, origin table/column, export's ghidra_field dependency, pipeline initializer and generated layout script together; remove swallowed ALTER failure and decide planning-read behavior. Known six/seven-column shapes and origin NULL semantics are load-bearing. No invented native/adopted backfill.
- **Decomp:** separate corpus MAIN_SCHEMA/guard from independent PART_SCHEMA. Adding nullable ast_fingerprint to an old table is not behavior-neutral: `match_store.py:139` and `:297–305` select the first available column globally, so adding a NULL column stops fallback to existing skeleton_hash. Readers also recognize pcode_fingerprint/pcode_hash/hash_pcode, but no current DDL producer for those extension columns was found; their provenance requires a separate compatibility decision. `dashboard/preparation.py:2278–2280` reads shape rows; `dashboard/recovery_status.py:119–121` distinguishes missing table (None) from empty table (0). A future migration must preserve evidence availability semantics and ASTv1 syntax provenance without claiming P-code or raw re-extraction. These are why decomp was not selected as the first slice.
- **Recovered/source proposals:** current rebuild helper has multiple real legacy keys, invalid-NULL preservation and caller savepoints. It cannot be stuffed into the runner's additive-only claim without an explicit qualified transformation/rollback contract. Other build and NULL-bound source candidates remain evidence.
- **Other persistent helpers:** name_precedence/logical_name, propagate_conventions, registration/source aliases/program bindings, fix_func_counts and store.ensure_* escapes each need explicit owner admission and compatibility treatment; inventory above gives the concrete source sites. Canonical connection ownership does not make those current explicit DDL calls ledger-owned.
- **Unknown or independent stores:** preserve and classify; do not merge grid/knowledge/text/activity/temp objects into the corpus baseline. Mixed corpus deletion remains a refusal.
- **U82 and wider U2:** public facade deletion, content-hash/cascade preconditions, decoder/basis identity, signature backfill, pre-fix identity supersession, stable keys/order and generic platform fields remain separately owned. This slice does not satisfy their acceptance by implication.

## Completion boundary and performed checks

Read the schema brief, U2 requirements and namespaced extract, both prior source contracts, Task2.1/2.2 implementation/review reports, repository entry/authority references and bounded source/caller/declaration searches. Memory was used only for the separation of source and installed/live evidence; every technical claim here was checked against current source. Wrote only this report.

No source changes, subagents, Git mutation, test/collection/build/typecheck/proof script, project import, database open/query/creation, runtime/process/catalog/compiler/checker/key/service/systemctl/restart/port or publication action was performed. Shell reads and text searches establish a source inventory and proposal only. The controller can adopt this concrete STABS slice now; full all-DDL ownership is an explicit remaining worklist, not a reason to stop at an unimplementable all-schema rewrite.
