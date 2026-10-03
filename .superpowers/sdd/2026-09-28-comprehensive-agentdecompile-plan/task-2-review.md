# Task 2.1 review

## Spec compliance

**Verdict: compliant with the adopted bounded Task 2.1 contract, at source-review level.** No missing or extra implementation requirement found in the nine-path review package, base `dd7f2af04a0f08ba5b917a6045b3a1a76a248511` to head `7a0ffdfa157f69155df99cccbb108f2425ad50aa`.

- Canonical ownership and public compatibility: `src/agentdecompile_recovery/corpus/db.py:14` retains the historical path expression; lines 17–19 alias the canonical SQL/index/JSON symbols; line 23 retains the specified facade signature. Explicit paths forward unchanged without warning; only omission warns and requests `create=False` (lines 31–41). The independent SQL initializer is removed.
- Opening policy: `src/agentdecompile_recovery/corpus/store.py:179` retains the required path and keyword-only read-only argument and adds `create=True`. Lines 196–202 select escaped absolute URI `mode=ro` or `mode=rw` before the only directory-creation branch. Existing-only admission has no existence-check/create race or fallback resolver.
- Version and ledger admission: `src/agentdecompile_recovery/corpus/store.py:206` reads the version before WAL configuration or migration. Lines 209–225 reject unsupported versions and missing/malformed/inconsistent read-only ledgers; the ordered raw version/name pairs must equal the current registry. NULL historic basis values are not rejected or synthesized. Lines 226–230 reserve WAL, migration and family backfill for writable admission.
- Failure ownership: `src/agentdecompile_recovery/corpus/store.py:231` preserves `BaseException` cleanup, rollback of an active transaction, final close and re-raise. Successful ownership transfer remains at line 240. The existing behavior when rollback itself fails is retained, as expressly acknowledged by the implementation report.
- Actual consumers: `src/agentdecompile_recovery/corpus/export_mizuchi_db.py:180`, `:429` and `:498`, `src/agentdecompile_recovery/corpus/package_binaries.py:79`, and `src/agentdecompile_recovery/corpus/materialize_binaries.py:40` request read-only admission with their previous argument routing. Narrow connection-use checks found SELECT-only corpus access at those sites. `src/agentdecompile_recovery/corpus/name_precedence.py:169` and `src/agentdecompile_recovery/corpus/mizuchi_bridge.py:244` retain writable opens and their existing DDL needs.
- Scope and disclosure: `src/agentdecompile_recovery/corpus/store.py:9` documents role asymmetry without changing stored values or constraints. `docs/CORPUS_PIPELINE.md:48` documents the canonical API, warning, missing-file refusal, writable migration behavior, read-only refusal and unfinished deletion/DDL ownership. No migration, schema version, registry/delete implementation, dashboard route or package-level schema export is changed by this package.
- Regression source: `tests/test_corpus_db_compatibility.py:23` covers retained aliases; `:43` and `:56` cover explicit/implicit routing; `:77`, `:87` and `:109` cover noncreation including removal during open; `:123` covers fresh/known-v0 migration and unknown-data preservation; `:198` and `:221` cover read-only admission/refusals; `:255` covers future writable refusal; `:279`, `:315`, `:383` and `:414` cover migration failure/interruption, unsupported shape and SQL/malformed-file errors; `:337` and `:359` cover the five reader calls and retained routing. Existing transaction/migration tests receive only the necessary expectation/fake adjustments.

## Quality

**Verdict: approved for this source-only task gate.**

### Strengths

- `src/agentdecompile_recovery/corpus/db.py:17` removes duplicated implementation through direct aliases and a short forwarding function, preserving one canonical connection owner without adding another resolver or SQL module.
- `src/agentdecompile_recovery/corpus/store.py:209` fails before journal changes for future stores; its read-only/writable branch separation makes the absence of migration/backfill attempts directly inspectable. Ledger shape failures have contextual admission errors while unrelated SQL exceptions remain visible.
- `tests/test_corpus_db_compatibility.py:87` instruments the actual SQLite opening boundary rather than merely checking existence beforehand. `:198`, `:221` and `:255` combine SQL traces, mutator spies, handle-close checks and stored-state assertions. `:279` distinguishes durable earlier migration steps from the failing step instead of claiming whole-series rollback.
- `tests/test_corpus_db_compatibility.py:337` stops reader-call spies at admission, avoiding unrelated artifact moves or knowledge-store work. Tests and the implementation report explicitly distinguish authored coverage from executed evidence.

### Critical findings

None.

### Important findings

None.

### Minor findings

None requiring changes in this bounded slice.

## Checks and limits

- Read `AGENTS.md`, `src/CLAUDE.md`, the SDD task-reviewer prompt, the task brief, adopted schema-unification contract and implementation report. Read the complete supplied 1,053-line diff once in bounded chunks; did not regenerate a diff or perform Git mutations.
- Named risk: canonical delegation or cleanup might disagree with the unchanged migration executor. Inspected `src/agentdecompile_recovery/corpus/migrations.py:37`, `:83`, `:269`, `:297` and `:336` for ledger shape, baseline ownership, registry/version identity, version reads and per-step transaction/exception semantics. They support the new admission contract; writable lock/read-only tolerance remains unchanged and can still return an older version.
- Named risk: canonical helper aliases might change historical return behavior. Inspected only `src/agentdecompile_recovery/corpus/store.py:430` and `:437`; index SQL and JSON behavior match the removed helpers. The store diff ends before its success return, so inspected the narrow tail at `store.py:236` to verify the owned handle is returned only after successful initialization.
- Named risk: converting actual consumers to read-only could break hidden writes. Searched connection references in the five named importer files, then read only the additional exporter/package SQL fragments needed to confirm SELECT-only use and the two retained writer contracts.
- Named risk: the new known-v0 schema comparison might claim coverage of a different historical format. Inspected the fixture header and table declarations in `tests/fixtures/store/legacy_schema_v0.sql:1`; the test explicitly uses that frozen fixture and preserves unknown extensions. This does not qualify every historical `db.py` database shape.
- **Cannot verify:** no tests, collection, builds, typechecks, project imports, SQLite creation/queries, proof scripts, runtime/process/catalog/service actions or live activation were performed. The implementer's AST/whitespace results are reported claims; this review establishes source reasoning and regression-source adequacy, not test execution or database/runtime equivalence. Authorized focused regression execution and supported historical migration/consumer qualification remain separate acceptance gates.
- **Not closed by this verdict:** literal U82 facade deletion, external/public caller accounting, wider DDL-ledger ownership, exhaustive per-binary deletion, full historical migration qualification, U22 identity/basis work and U2 determinism/platform obligations. Their explicit deferral in the adopted contract is not a defect in this patch.

## Assessment

**Task quality: Approved.** The implementation matches the adopted compatibility and strict-reader boundary with small production changes and meaningful authored regressions. Approval applies to the reviewed source slice only; full-unit and live acceptance remain open.
