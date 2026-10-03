# Task2.4 — independent combined source review

Status: **READY_FOR_CONTROLLER**. Spec decision: **PASS** for the complete bounded source packet. Quality/security/data-integrity decision: **PASS**. No Critical or Important finding established in the reviewed production or final authored regression sources. The source baseline remains `f1846bd3`; the controller's later document-only checkpoint `b989ad20` does not change that comparison.

This reviews the owned uncommitted source against HEAD `f1846bd3`, the complete adopted `next-decomp-schema-contract.md`, its independent review and the controller task brief. It is source reasoning, not SQLite, test, installed or runtime acceptance. Production ownership remained with the implementer; regression ownership remained with the separate regression worker. Only this review file was written.

## Findings

### Critical

None identified.

### Important

None identified at the required confidence threshold.

### Minor / deferred

None established as a source defect. The documented skeleton-state consistency scan and existing optional row-decoding catch are preserved bounded behavior; this review does not invent an optimization or reinterpretation requirement.

## Spec and correctness assessment

1. `store.py:44–79,309–424` owns the canonical declarations without changing baseline `SCHEMA`. Admission recognizes the original 14-column declaration, 15-column CREATE and historical ALTER spelling, and verifies exact xinfo metadata, index ownership and singleton state. Reserved main spellings, TEMP ASCII-case shadows, object-name collisions including triggers, unsupported columns and local objects refuse. Main qualification prevents an attached object supplying a missing main table. Inspection helpers contain no initialization or transaction ownership. v9/v10 logical selection remains independent of current physical v11 metadata; future/unsupported versions refuse.

2. `migrations.py:269–329` preserves migration10's forward operations and freezes only its repeat predicate to10. Migration11 captures absent/skeleton/AST before mutation, adds only missing declared structure and its new singleton, and checks the postcondition before the unchanged runner records ledger/version. It performs no historical row UPDATE, fingerprint generation, NULL-basis replacement or producer import. Direct repeated11 binds to11 rather than a moving latest registry. Failure durability remains owned by the unchanged per-step runner.

3. `decompile.py:103–207,257–299` validates before feature computation and again inside its owned BEGIN IMMEDIATE/private savepoint. Logical state transition and one-key replacement share the operation. Falsy writes retain twelve NULL fields and the original result; truthy and whitespace inputs retain the original payload. Successful persist still commits caller work. The caller savepoint remains until commit, so an acknowledged pre-durability failure can roll back only the operation while its outer transaction survives. Cleanup errors propagate; transaction loss and a successful-but-unacknowledged commit are explicitly uncertain rather than reconstructed rollback. Attach closes its owned handle on failure. Ensure commits only its standalone transition, preserves caller ownership, and leaves absent/AST modes untouched.

4. `decompile.py:138–161,209–255,276–299` isolates independent part initialization and dispatch. Relevant TEMP shadows and mixed/corpus destinations refuse before part DDL. A raw unledgered decomp cannot masquerade as an independent part store. The independent key, features, nullable AST installer and explicit writer commit remain; PART_SCHEMA and public signatures are preserved.

5. `match_store.py:95–154,295–318` admits the selector before incidental func mutation and outside the existing optional decoding catch. Both Binary and receipt use the same table-global selected column. AST NULL/empty values do not fall back to skeleton; skeleton candidates remain a separate channel. Successful-row filtering, truthiness, SQL non-NULL/nonempty receipt count, same-ID sum, compatibility names and matcher algorithms remain unchanged. The selected SQL identifier comes only from the bounded helper, not caller text. No P-code or recovery provenance is fabricated.

6. `dashboard/recovery_status.py:114–126` retains absence=None per build/by-build with aggregate0, and installed-empty=0. Successful witnesses still count distinct addresses with ok1. Source availability, compilation and byte verification are unchanged. `dashboard/preparation.py:2244–2292` changes only the authorized projection: v2 includes logical mode and actual selected value while retaining skeleton/metrics/order. Exact receipt inventory equality then invalidates v1, selector transitions and relevant fingerprint changes. Global mode legitimately affects both selected binaries; unrelated-binary data leaves those inputs unchanged. The physical STABS inventory panel remains unaffected.

7. `delete_registry.py:375–392,457–538` adds an explicit frozen11 delta, preserving9/10 maps, optional fields, ledger identities and mutation executor. v11 requires decomp/AST/index/state and checks contradictory absent/skeleton rows independently of live migrations. The metadata table is excluded from DELETE_ORDER and affected-row counts, so target/survivor/last-binary deletion retains global state. Existing stronger all-TEMP/all-attached refusal and survivor dependency behavior remain. Source inventory agrees with28 known/19 mandatory/9 optional for11.

8. `docs/CORPUS_PIPELINE.md:59–87` states the same version, transition, caller-commit, compatibility and evidence boundaries. It distinguishes source contracts from migration execution and installed/live acceptance.

## Independent source checks

Standard-library AST parsing passed for the seven production modules without project imports. Direct AST comparison against the saved pre-edit production copies confirmed unchanged baseline SCHEMA; all preexisting migration functions except the explicitly owned migration10 body; all preparation functions except matching input; all deletion functions except preflight; syntax_fingerprint; and the four public writer/helper argument and return signatures. The implementation report's broader132 checks were read as implementer evidence, not reclassified as this reviewer's execution.

Repository authority/entry references, adopted contract/review, production report and all assigned production diffs were inspected. A bounded memory search supplied no task-specific technical fact used in the verdict. Unrelated controller contract edits were outside this review's ownership.

## Authored regression review and acceptance limits

The worker's final small additions were also source-reviewed: all stored AST values, including unsuccessful rows outside matcher/receipt projections, are compared before/after migration; public status has an explicit failed/unknown-only zero-witness fixture. The final new regression source was AST-parsed again after these additions. No new finding was established.

The final stable regression packet contains five source paths: `tests/test_store_migrations.py`, `tests/test_corpus_db_compatibility.py`, `tests/test_corpus_delete_registry.py`, the narrowly authorized `tests/test_corpus_stabs_migration.py`, and new `tests/test_corpus_decomp_schema.py`. All five were independently AST-parsed as text and have unique top-level test names. Their historical decomp fixture DDL is independent of the current alias/deletion maps; actual target9/10 fixtures and runner-migrated11 are kept distinct. STABS compatibility fixtures stop at genuine10 where they test10, while current11 and actual synthetic12 fixtures preserve explicit refusal coverage. Deletion's malformed/missing decomp cases now expect the existing missing-index-first refusal at11 rather than weakening the mandatory profile.

The new authored tests call the actual Binary/candidate/receipt/status/cache helpers and preserve paired absent/installed-empty, skeleton/AST NULL/empty/arbitrary values, failed/successful rows, other binary and same-ID behavior. Writer payload producers are pinned, so the tests check routing/payload/state without recomputing fingerprints. They cover owned/caller success, savepoint failure, pre-durability commit/interruption, cleanup failure and successful-but-unacknowledged commit; migration11 failure after freshly committed1–10 is distinguished from its rollback matrix on existing10. Pure guards, claimed-current corruption, exact singleton damage, real future12, readonly refusal, explicit absent materialization, standalone/caller ensure, part payload/domain/TEMP/casing and last-binary metadata retention are authored. Cache checks exercise real receipt equality and v1 invalidation. These are meaningful source acceptance fixtures; no assertion here is reported as having passed at runtime.

The final production implementation report was read in full. Its explicit production-only readiness and deferred regression-worker integration align with this combined review; controller integration can now record the final source review decision. Exact reviewed production/docs paths are `src/agentdecompile_recovery/corpus/store.py`, `migrations.py`, `decompile.py`, `match_store.py`, `dashboard/recovery_status.py`, `dashboard/preparation.py` (matching projection only), `delete_registry.py` under the same corpus directory, and `docs/CORPUS_PIPELINE.md`. The report reviewed is `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-decomp-report.md`. No extra test path or production scope was introduced by this reviewer.

No tests/collection/build/typecheck, project import, DB open/query/create/migrate, fingerprint/key/crypto/compiler/checker, process/runtime/live/catalog/provisioning/capture, service/port action, activation or publication was performed. No serving checkout was synchronized. SQLite CREATE/ALTER spelling acceptance, rollback/savepoint behavior, lock tolerance, concurrency, comparison cache execution and installed consumers remain unverified until separately authorized execution. Source completion does not establish runtime readiness or terminal recovery, and wider U2/U22/U82 owners remain open.
