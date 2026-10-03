# Task2.6 type regression source report

READY_TO_COMMIT for independent source review and controller integration. This is
an authored, unrun regression packet against the shared schema13 implementation;
it is not a test-pass, migration, native capture, consumer, installed, or live
acceptance claim. Production ownership remained with the source implementer and
controller; this task changed no production source and performed no Git operation.
The controller supplied source baseline `bd979ae3`; no Git lookup was performed.

## Exact changed paths

- `tests/test_store_migrations.py`
- `tests/test_corpus_db_compatibility.py`
- `tests/test_corpus_delete_registry.py`
- `tests/test_corpus_stabs_migration.py`
- `tests/test_corpus_decomp_schema.py`
- `tests/test_corpus_convention_schema.py`
- `tests/test_cli_input_errors.py`
- `tests/test_corpus_calibrate_global.py`
- `tests/test_workbench_workflows.py`
- `tests/test_corpus_cave_qualification.py`
- `tests/test_corpus_export_hookpack.py`
- `tests/test_corpus_type_schema.py` (new)
- `tests/test_corpus_type_consumers.py` (new)
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-type-tests-report.md`

The authorized `tests/test_propagate_conventions_abi_gate_stored.py` needed no
change: its applying fixture already migrates to current, while nonapplying/raw
fixtures remain unchanged. Its entire source equals the before-test snapshot.
The protected U9 matcher-input-v2 test function and its historical helper remain
exact source matches, retaining authority and projection assertions. Existing
convention edits are limited to explicit12 history/current13/future14 seams.
The pre-existing five-column cave type projection now uses a genuine runner12
fixture; it is not presented as supported schema13 migration history.

## Authored coverage

The new schema module defines 30 test functions with parametrized histories and
failure boundaries. The consumer module defines 10 functions with paired states.
These are source definitions only; no collection or case execution occurred.

| Accepted matrix | Authored observations/assertions |
| --- | --- |
| Historical adoption | Actual runner12 absent/six/seven-CREATE/seven-ALTER, empty/populated and optional origin/index combinations; orphan-origin refusal; NULL/native/adopted/empty/unknown origins, unknown donor text, same-name struct/union keys, old rowids, NULL and historical basis values, ordered nested field JSON, old decomp selectors, unrelated columns/tables. Fresh runner failure retains committed1–12. |
| Admission | Current13 pure guard/planner; malformed type/default/collation/PK/reorder/generated/extra/STRICT/WITHOUT ROWID/view/virtual shapes; missing/extra fields, wrong index, pre13 state, arbitrary main/TEMP owner triggers, mixed-case reserved TEMP tables/views, malformed state/ledger, attached substitute, raw/unledgered, actual readonly/locked12 and actual future14. Caller work/snapshots and no early config/capture/payload access are asserted. Unrelated extension/scratch acceptance is paired. |
| Writer success | Actual native helper, adoption and export persistence with owned/caller transactions, durable second-reader assertions, successful empty materialization, unopened/opened no-program nonmaterialization; native IGNORE count and curated collision, omitted-origin NULL after export replacement, exact adoption note/origin payload, cross-kind keys and foreign rows/annotation/field preservation. Synthetic Ghidra objects isolate producer input while real persistence remains under test. |
| Writer failures | First/later inserts, origin write, selected field deletion/insertion, state update and precommit; Exception/BaseException and caller/owned scopes; capture cancellation/collision/field-mapping/payload failure; scope creation, revalidation after staged schema change, cleanup refusal, lost transaction and committed-but-unacknowledged uncertainty. |
| Migration failures | Pending13 CREATE, origin ALTER, origin/index/state creation, singleton/ledger/version writes and predurability COMMIT; cleanup failure and committed acknowledgement distinguish exception from rollback. Direct repeats10/11/12/13 retain their own version under future registry14; missing13 state never repairs. |
| Reader behavior | Actual `/types` router with injected selected-snapshot context uses one handle for availability/count/page. Absent/installed-empty/populated, selected empty binary, missing database, generic admission failure, paging/filter/STABS and historical six-column503 followed by13 NULL-origin projection are asserted. Corrupt13 absent-plus-rows and actual14 refuse API/header/definitions/hookpack; ctxtypes retains its `{}` fallback. |
| Artifacts and raw readers | Empty-name definitions request touches no SQL; raw5/6/7 preserve definitions/ctxtypes projections; missing inventory differs from installed-empty header/recovery fallback. Header and manifest bytes, recovery injected source, ctxtypes map and hookpack nested-field entities are compared12→13 under a fixed synthetic basis. Actual v2 export wrapper additionally compares complete serialized bytes. Bundle uses isolated non-type collaborators to assert its two real inventory refusal reasons, no output and caller-scope preservation. |
| Planning receipt | Existing-header, existing no-db recipes, current absent/empty/populated/planned and header failure assert fragments, partial/error states, planned counts with adopted zero, header artifacts, unchanged durable and pending DB snapshots, read-only SQL, handle closure and forbidden capture/apply/start collaborators. |
| Generated layout | AST inspection of the actual returned body literal pins raw mode=rw open, row factory, admission before currentProgram traversal, staged rows, both cancellation checks, helper before header, close in finally, type distinctions and metadataPolicy; direct SQL writes/DDL/commit and implicit store connect are absent. The body is neither generated by invocation nor executed by the fixture. |
| Deletion | Existing full deletion matrix now runs genuine9–12 plus canonical13 fixture definitions, with independently frozen historical type/origin SQL. Current required objects/state, future14, scoped counts and surviving rows, provisional caller success, and last-binary absent/installed state retention are asserted. |

The type planner is a strict13 reader in these fixtures, matching the full adopted
contract and source. The existing nonapplying convention planner remains raw.
No missing-origin fallback is introduced into the tests. The fixture basis is a
synthetic comparison input, never a recovered or accepted basis receipt.

## Source-only validation performed

Used text/AST inspection of the contract, implementation APIs, existing fixtures
and authored changes. Parsed all 13 changed Python files with stdlib `ast.parse`;
checked duplicate top-level test names, trailing whitespace and shared test-helper
imports against declared AST names. Compared the two protected U9 source segments
and stored ABI file with their before-test snapshots. Read the generated-script
literal and implementation SQL/transaction boundaries without invoking them.

Local review material:

- `/tmp/task-2-type-tests-before/`: before-test source snapshots of authorized existing files.
- `/tmp/task-2-type-tests.diff`: bounded stdlib textual diff of this test packet.
- `/tmp/task-2-type-tests-source-checks.txt`: exact source-check results.

No tests, collection, project imports, generated script, DB open/query/migration,
file hash/crypto/signing, build/typecheck, compiler, runtime/process operation,
API/live call, provisioning, systemctl, restart, alternate port, synchronization,
activation or publication was performed. Temporary files above contain source and
source-check text only. Tests contain future SQL/hash/artifact calls as regression
specifications; none of those calls were executed during authorship.

## Remaining acceptance

Every fixture is unrun. AST parsing cannot establish SQLite transaction/DDL
behavior, exception compatibility, FastAPI thread/runtime behavior, artifact byte
parity, dependency availability or installed Ghidra integration. Independent
source review and controller integration are still required. Later separately
authorized focused execution must establish the historical, failure and actual
consumer assertions; the source checks are not substitutes.

Generated-layout behavior is intentionally limited to parity inspection by this
brief. Future isolated currentProgram/cancellation/header-after-commit stubs and
installed/native capture qualification remain open, along with real catalogue
workload and whole-image recovery acceptance. The bundle negative isolates its
unrelated exporters, and header/hookpack parity uses synthetic bases; these do not
qualify cave evidence, native compilation or full bundles. Broader recovered/reuse
keys, logical binding, helper DDL and full U2/U23/U82 obligations remain outside
this packet. No known unaddressed source-authoring defect is claimed closed by
execution; any review finding must be resolved before acceptance.


## Independent review fixes

Resolved the two Important regression-source findings in the bounded follow-up:

- Restored the unrelated missing-image STABS CLI fixture to its original source.
  Moved the synthetic header basis and content identity into the intended missing-
  inventory header CLI fixture, whose signature already requests `monkeypatch`.
  This lets that fixture reach the intended `ghidra_type` error without an
  undefined fixture name or an earlier basis/content-identity failure.
- Corrected the API spy expectation to seven `query_db` calls on the same handle:
  two for each of the two Ghidra requests, and three for STABS because its
  `table_exists` probe also calls `query_db`. The snapshot count remains three.

Parsed only the two changed Python files with stdlib AST and checked the edited
function/source segments. The STABS fixture is source-identical to the original
pre-packet snapshot. No fixture, import, DB, hash, runtime, Git or other execution
was performed. The fix-only textual diff is
`/tmp/task-2-type-tests-review-fixes.diff`. READY_TO_COMMIT for source rereview;
all executable acceptance remains unrun.
