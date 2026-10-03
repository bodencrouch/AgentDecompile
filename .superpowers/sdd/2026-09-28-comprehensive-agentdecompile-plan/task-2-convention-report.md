# Task2.5 — canonical convention ownership source handoff

**READY_TO_COMMIT**, 2026-10-03. Implementer handoff for the adopted
[next corpus DDL contract](next-corpus-ddl-contract.md), pending independent final
review and controller integration. This is source readiness only, not a migration,
test, installed-consumer, live, ABI or recovery acceptance result.

Dispatch baseline supplied by the controller: `a3e164fe`. During implementation
the controller integrated U9 as `d87c0f8fc7df1369548e2915dbf460b5d4260d13` and
explicitly released the decomp regression file. These are supplied identities;
this implementer performed no Git action. The U9 matcher-input-v2 test function
and its shared `historical` fixture remain AST-identical to the released file.
No dashboard, native or other worker production file was changed.

## Implemented boundary

The store owns the exact historical seven-column convention declaration.
Migration `(12, convention_schema_ownership)` admits actual ledger11 plus prior
STABS/decomp postconditions, installs only absent storage, and checks the complete
postcondition before the unchanged runner records12. Existing values, rowids,
nullable numeric fields and unknown class/source strings have no rewrite path.
Direct repeat12 validates without repair; prior repeat10/11 bodies are unchanged.
Baseline SQL and migrations1–11 remain unchanged.

`require_convention_schema` is a pure, explicitly bounded12 guard. It rejects
incomplete storage, wrong/future/outdated ledger, relevant reserved main/TEMP
spelling and shadow collisions, non-table input owners, altered table declarations
or xinfo metadata, and undeclared main or TEMP objects owned by the convention
table. Unrelated extensions and unrelated TEMP scratch are admitted. Canonical
read-only opening adds this guard to its existing path-bearing refusal behavior.
`decomp_read_state` admits exactly12 using the existing complete11 state predicate;
historical9/10 and future13 boundaries remain explicit.

`derive_conventions` retains its public signature, ABI maps/helpers, calculations,
row order and result. Nonapplying raw/minimal handles remain read/computation-only.
Applying validates before computation and again inside BEGIN IMMEDIATE or a
private caller savepoint. Main-qualified one-key writes replace the installer.
Success commits caller pending work, including zero rows. Failure cleans up only
the owned operation while the transaction survives, including BaseException;
scope-creation failure gains no cleanup ownership, and lost transactions or lost
commit acknowledgements report uncertainty. Computation remains outside the write
scope: no stable donor snapshot or callback-side-effect rollback is claimed.

Frozen deletion12 adds the explicit ledger row and mandatory convention table
(28 known, 20 mandatory, eight optional), exact convention xinfo metadata, and
retains complete11 decomp/state checks. Historical9–11 keep convention storage
optional. The executor, deletion order, counts and conservative surviving-donor
refusal are unchanged. No dynamic migration registry grants deletion permission.
No matcher-input-v3, cache rebaseline, ABI revision or new source receipt is added.

Independent review identified a TEMP trigger with an arbitrary name targeting
`main.func_convention_derived`: a reserved-name-only query missed its side effects.
The final guard also checks TEMP `tbl_name`. Paired authored cases reject that
trigger before derivation, preserving selected/unrelated rows and caller work,
and admit unrelated TEMP scratch. Review also caught a malformed WITHOUT ROWID
fixture snapshot problem; malformed snapshots now handle non-rowid tables without
weakening canonical historical rowid-preservation assertions.

## Exact changed paths

Production:

- `src/agentdecompile_recovery/corpus/store.py`
- `src/agentdecompile_recovery/corpus/migrations.py`
- `src/agentdecompile_recovery/corpus/propagate_conventions.py`
- `src/agentdecompile_recovery/corpus/delete_registry.py`

Authored/updated regression source, all unrun:

- `tests/test_store_migrations.py` — registry12 and fresh convention postcondition.
- `tests/test_corpus_db_compatibility.py` — current12 naming and malformed/missing convention read-only admission with no migration/backfill and closed failed handles.
- `tests/test_corpus_delete_registry.py` — independent frozen historical convention SQL, actual9–12 fixtures, mandatory12 absence refusal, retained complete11/12 checks and future13 refusal.
- `tests/test_corpus_stabs_migration.py` — actual historical11/current12/future13 distinctions and current-prefix expectations; genuine10 repeat unchanged.
- `tests/test_corpus_decomp_schema.py` — current12 expectations; genuine11 direct repeat under future13 registry; actual future13 refusal; new `test_convention_twelve_preserves_actual_v11_consumers` compares Binary/candidate/receipt, status, logical selector and matcher-input-v2 across11→12. The U9-owned `test_matcher_input_v2_tracks_selector_and_selected_values_and_receipt_equality` and shared `historical` function are unchanged.
- `tests/test_propagate_conventions_abi_gate_stored.py` — only applying cases use canonical stores; nonapplying minimal ABI fixtures and original outcomes remain.
- `tests/test_corpus_convention_schema.py` — 23 parametrized/nonparametrized test functions covering historical absent/empty/populated11 storage and all decomp modes; rowid/value/ledger-NULL/unrelated-extension preservation; raw/current nonapplying equivalence; applying exact keys, durable caller success and zero/refused-ABI output; malformed declaration/metadata/view/virtual/local-object/input-shadow refusals; pure guard success/refusal; real runner step12 CREATE/ledger/version/commit failures while freshly committed1–11 survive; owned/caller insertion/commit/interruption/mapper/schema-change/scope-creation/cleanup failures; engine transaction loss and lost acknowledgement; tolerated11 locked/read-only handles; direct repeat10/11/12 under future registry; actual future13; actual deletion9–12 with optional/required absent/empty/populated storage and last-binary state retention; TEMP trigger refusal and unaffected TEMP scratch; writer DDL absence.

Documentation:

- `docs/CORPUS_PIPELINE.md`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-2-convention-report.md` (this report)

`tests/test_propagate_conventions_abi_gate.py` is byte-for-byte unchanged. The
convention regression module is a new file; the other regression paths retain
their existing purposes instead of relabeling current stores as historical ones.

## Source validation performed

Read AGENTS, repository entry references, U2 requirements/schema extract, complete
adopted contract and independent contract review, and relevant current source.
A bounded memory registry search supplied the general source/live distinction;
no historical technical claim substitutes for current source inspection.

AST parsing succeeded for the 11 edited Python source files. Standard-library
AST/literal comparisons against source-text snapshots confirmed all20 original
migration functions/classes (including runner/repeat behavior), baseline SCHEMA,
prior owned declarations/shape inspectors, convention ABI helpers/maps, derivation
signature and core calculation statements, historical convention declaration,
frozen deletion maps/order/executor, and released U9 function/shared historical
fixture were unchanged. Text comparisons confirmed the standalone nonapplying ABI
regression module was unchanged. Reviewed focused textual diffs and searched for
stale synthetic migration12/future12 expectations; genuine11 commit-interruption
assertions deliberately remain11. No project module was imported to do these checks.

The authored cases contain future SQLite, consumer and failure-injection calls.
None was executed, collected, imported or counted as passed. Source inspection
cannot establish SQL normalization behavior, virtual-table availability, migration
atomicity, savepoint/commit behavior, lock tolerance, cache equivalence or live
consumer admission. Later authorized execution may expose fixture or production
defects despite this review.

## Limits and remaining ownership

No tests/collection, build/typecheck/proof, project import, DB open/query/migration,
fingerprint/hash/crypto/signing/key generation, process/runtime/helper execution,
capture/provisioning/API/catalog/live mutation, systemctl/restart/alternate port,
synchronization, activation, publication, subagent spawning or Git action occurred.
The supplied controller observation identifies a healthy8080 process on an NVMe
root with unchanged identity; this worker did not probe it. Its loaded module and
revision remain unverified, and these source files are not activated.

Historical/failure-case execution, installed/current consumer qualification,
explicit cataloged workloads/backfill and STRATEGY whole-image acceptance remain
separate gates. Types, recovered/reuse keys, logical-name caches, binding metadata,
helper DDL, count fields and the broader determinism/platform/cache obligations
remain open. This closes one source ownership packet, not full U2/U22/U82.
