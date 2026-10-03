# U2 next ownership contract — type inventories and their real consumers

Status: **READY_FOR_CONTRACT_REVIEW**, proposal only, 2026-10-03. No adoption,
implementation or execution is authorized by this document. The controller
reports accepted convention12 commit `eb153101dc7b3b2bb4a9e2dc281e2ff23117e109`;
13 is the proposed next number, not a claim about a deployed database. Independently review this document before assigning a
fresh implementation owner. This author owns only this document.

Inputs: [AGENTS](../../../AGENTS.md), [U2](unit-2-requirements.md),
[U2 schema extract](unit-2-schema-extract.md), [U23](unit-23-requirements.md), the
complete [prior DDL contract](next-corpus-ddl-contract.md), and inspected current
source. The controller supplied U9 release `d87c0f8f`; its released workflow/API
text was read, not reset. Convention12 source remains unchanged by this task.

## Decision and scope

Adopt one coherent domain: `ghidra_type`, `ix_ghidra_type_bin`,
`ghidra_type_origin`, and the availability semantics their consumers already
expose. Append `(13, "type_schema_ownership")`; preserve baseline emission,
steps1–12, runner, old ledger rows/basis NULLs and repeat10/11/12 bodies. Existing
`ghidra_field` remains owned by migration6: validate its required shape and
preserve its contents, rather than re-create or renumber that migration.

Close the actual export/propagation/pipeline/generated-layout installer sites
together. Preserve emission algorithms and field/storage payloads; do not upgrade
same-size donor agreement into qualified ABI compatibility. This advances U2/U22
DDL ownership and protects the existing U23 type-data seam. It does not finish
U23 return/parameter-storage transport, native typed-field capture, target ABI
qualification, donor identity, or general type equivalence.

## Observed source boundary

Locators are current source text under `src/agentdecompile_recovery/corpus/`.
No module, database, generated script or helper was executed for this census.

| Owner/consumer | Observed behavior and consequence |
|---|---|
| `export_types.py:16–27,264–342` | Owns six-column type/index SQL. Export starts Ghidra before checking schema, assembles definitions and typed fields, requires a `ghidra_field` table, executes DDL, replaces selected type keys, deletes/replaces fields for successful binary/name pairs, then commits. No-program exits before installation. |
| `propagate_types.py:15–47,102–121` | Planning executes both declarations, attempts nullable `origin` ALTER and suppresses any exception; planning therefore changes storage/commits caller work. Donors with origin use only NULL/native rows. Applying replaces kind=`struct` rows and an origin record keyed by binary/name, then commits even an empty list. |
| `pipeline.py:190–305` | `write_calibrate_global_receipt` opens a writable canonical store, installs type SQL, calls no-program export, plans **and applies** adoptions, then builds a header. It does not start Wine/Ghidra, but it currently mutates the corpus while composing a receipt. |
| `dashboard/workflow.py:661–699` | Generated `layout_script` opens the store, installs type SQL, emits definitions and `INSERT OR IGNORE`s type keys, commits, then builds a header. Curated rows survive. It does not collect `ghidra_field`; do not claim that seam is already lossless native capture. |
| `export_types.py:246–261`; `recover_named_ghidra.py:409–446` | `definitions_for` returns `("", set())` without SQL for empty names. Otherwise missing type storage raises SQL error; installed-empty returns empty definitions. `inject_data_symbols` uses the returned definitions/resolved names before fallback declarations. |
| `build_types_header.py:63–153` | Requires declared basis/build content hash, reads ordered definition rows and writes header plus manifest. Installed-empty may emit a zero-type header; missing storage errors before output. Origin is not projected. Artifact receipt says compiled verification not_run. |
| `kx_cli.py:489–506` | `build-types-header` distinguishes unknown binary from missing table and returns2 with a clean missing-inventory error before header generation. A fresh canonical store currently exercises this path in `test_cli_input_errors.py:85–104`. |
| `export_bundle.py:88–137` | Its savepoint keeps the export read snapshot. Missing type storage maps to `headers: captured type definitions unavailable`; an empty build inventory maps to `headers: no captured type definitions for <slug>`. Both refuse before publication. |
| `hookpack_v2.py:299–317`; `export_hookpack.py` routing | The actual type projection reads stored definitions and optional typed fields. Absence and empty rows both yield no type entities. Origin is not projected; same name is not cross-build identity. Preserve this projection and typed JSON/order. |
| `ctxtypes.py:42–53`; `ghidra_bulk.py:1733`; `permuter_harness.py:366` | Prompt type loading catches missing-table/SQL errors and yields `{}`. With no rows, it also yields `{}`. Its consumers need no new schema installer or invented definitions. |
| `dashboard/react_api.py:476–505` | `/dashboard/api/workbench/types` reports absent storage as ok/unavailable. Installed-empty seven-column storage is ok/empty. Six-column storage queries nonexistent `t.origin` and returns503, even when empty. Filtering/paging and the STABS branch are separate existing contracts. |
| `dashboard/panels/stabs.py:595–617` | Physical table inventory lists tables; it may accurately list newly owned type/state storage without claiming a captured type inventory. |
| `delete_registry.py` | Types/origin are optional through12; child origin without parent refuses. `ghidra_field` is already mandatory. Donor slug is stored text, not a foreign key; deleting a donor historically preserves surviving adopted rows/origin records. |

Searches covered all named production references in `src`, `scripts` and tests.
There is no separate U23 extract in this workspace; its requirements and source
locators in the active-task extraction carry the U23 clause. No absence claim
extends to unknown external callers.

## Concrete compatibility decisions

### Retain availability, explicitly fix the six-column API projection

Physical installation cannot erase the existing unavailable-versus-empty
contract. A minimal **global compatibility marker** is warranted by the API,
CLI, bundle and nonempty `definitions_for`/header cases above. It describes
whether type storage was logically installed, **not** successful Ghidra capture,
per-binary coverage, native provenance, current layouts or ABI correctness.

Canonical declaration proposed:

```sql
CREATE TABLE type_inventory_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode TEXT NOT NULL CHECK (mode IN ('absent', 'installed'))
)
```

Migration records `absent` only when the main type table was physically absent;
any supported preexisting table, empty or populated, records `installed`. It
physically installs both tables/index in either case. This is narrower than decomp
metadata: no fingerprint selector, origin classification or per-binary capture
state is introduced. Empty installed storage was already observable after an old
planner/installer; the marker must not be named `captured`, `verified` or `native`.

Complete13 requires exactly one valid singleton. `absent` requires zero rows in
both type and origin tables. Existing `ghidra_field` rows alone do not establish a
complete type definition and do not change mode. Preserve those rows. `installed`
may have zero rows globally or for a selected binary. Deleting the last binary
retains the global marker. Never infer/reset mode from current row counts.

A successful explicit export or native layout pass materializes `installed`,
including a successfully visited program yielding zero eligible types. No-program,
failed extraction/admission or a rolled-back writer does not. Explicit successful
`apply_adoptions`, including an empty list, also materializes `installed`; this
means the owned inventory was explicitly used, not that adoption/capture occurred.
Pure planning and receipt composition never materialize it.

The existing six-column API503 is an explicitly adopted compatibility repair:
**after successful13 migration**, the added nullable `origin` yields JSON null
for historical rows rather than `no such column`503. This is intentional, not an
accidental consequence hidden in DDL. Before migration, raw/historical six-column
API requests retain their existing503; no read path ALTER or pretend-migration
projection is allowed. Current13 missing/malformed origin storage is a schema
refusal, not a fallback-to-NULL success. No new API response fields or claims.

### Preserve data and replacement policies

Canonical `ghidra_type` retains the six existing ordered fields and composite
PK(binary_id,name,kind), with nullable `origin TEXT` as the **last** column.
Existing six-column tables gain it through the historical nullable ALTER shape;
seven-column tables preserve every value and rowid. Existing `origin` values NULL,
`native`, `adopted:<slug>`, empty and unknown strings remain exact. Do not normalize
NULL to native, fabricate donors or change source text, packing, definitions,
array/pointer metadata, field ordinals/offsets/sizes or JSON bytes.

`ghidra_type_origin` retains its five fields and PK(binary_id,name). Distinct type
kinds can share a name; do not promote this narrower origin key into stronger
identity. Preserve unknown/dangling historical donor-slug text and all rows;
no inference, key migration, cascading donor delete or provenance backfill here.

Export retains six-field `INSERT OR REPLACE` behavior. On an existing seven-column
row, replacement leaves omitted origin NULL exactly as today. It does **not**
rewrite surviving `ghidra_type_origin` rows, even where old annotations become
stale; do not declare those annotations authoritative. Fields are replaced only
for successfully exported binary/name pairs, retaining existing cross-kind policy.
Native layout capture retains `INSERT OR IGNORE`, including preservation of
curated origin/definition values and zero inserted count for an existing key.
Propagation retains its exact donor filter, traversal/selection/stats/rows and
replacement/note/origin payloads. Schema ownership does not repair same-size-only
ABI assumptions or silently sort/rechoose donors.

## Migration13 and pure admission

Own declarations and pure inspection in `store.py`. Accept historical12 shapes:
absent type+origin; exact six-column type with absent/exact origin; or exact
seven-column CREATE/ALTER type with absent/exact origin. A missing canonical type
index may be installed. An occupied/wrong index refuses. An origin child without
a type parent refuses even when empty, matching frozen deletion dependency policy.
`type_inventory_state` present before13 is reserved/corrupt and refuses; no repair
or undocumented merge of external state. Five-column raw consumer fixtures are
reader compatibility, never admissible canonical migration history.

Before first mutation require owned transaction, observed12, exact ledger12,
complete prior STABS/decomp/convention shapes, real canonical input `binary`, and
exact migration6 `ghidra_field` declaration/xinfo. Preserve the prior owners'
reserved-object safeguards. Validate type/index/origin objects using bounded
known-declaration normalization and exact ordered xinfo (type, nullability,
default, PK ordinal, hidden/generated). Reject views, virtual tables, extra or
reordered fields, unexpected keys/constraints/FKs/collations/STRICT/WITHOUT ROWID,
main/TEMP reserved-name case collisions, all owned triggers, and unexpected
owned indexes. Permit only the exact main `ix_ghidra_type_bin` declaration and
SQLite-generated PK autoindexes entailed by the admitted type/origin/field
declarations (NULL SQL, exact expected owner/name); the singleton integer PK
requires no autoindex. TEMP owned objects remain refused. In particular an arbitrary TEMP trigger name
must be checked by `tbl_name`, not only by its own name. Relevant reserved inputs
include binary, ledger, both type tables, field table, index and state. Unrelated
extensions and unrelated TEMP scratch remain untouched; an attached table cannot
supply a missing main dependency. No generic all-corpus validator.

Use individual CREATE/ALTER/INSERT statements under the unchanged runner. For
six columns, add only nullable origin; for absent tables install canonical full
shapes. Install a missing declared index, then one state row from the observed
pre-step presence. Revalidate complete postconditions before runner ledger/version
writes. No feature producer, donor computation, field reconstruction, hash/basis
supersession, UPDATE/DROP/rebuild or data reclassification in this migration.
The existing ledger basis hook remains unchanged. Direct repeat13 binds explicit
ledger13 and validates complete state without repair/commit; older/future versions
refuse. Preserve all previous direct repeats unchanged under a future14 registry.

Provide `require_type_schema(con)` for strict current13 writing and canonical
read-only admission. It is pure: no transaction ownership/DDL/DML/commit/reopen.
Emit a named type requirement, observed/supported version and concrete reason;
SQL/I/O errors propagate. Strict read-only connect wraps shape failures in its
existing path-bearing error. Writable canonical connect retains its migration,
backfill and lock-tolerance behavior; returned old handles cannot write types.

**Required previous-owner integration:** `require_convention_schema` is currently
explicitly12; advance its public admission to current13 while preserving its
shape predicate and explicit migration12 repeat. Otherwise `connect(read_only=True)`
would reject every13 store. Extend `decomp_read_state` to exactly13 with complete
11/12 semantics; keep9/10 and future14 explicit. Existing current-version STABS
and decomp writer guards follow13; no backwards relabeling or state reset.

## Reader routing without breaking lightweight callers

Expose a pure13 inventory-state reader, separate from physical table inventory.
For genuine13 it requires full current postconditions and returns absent/installed;
malformed state and future14 refuse. No implicit upgrade. Existing noncurrent
readers that already accept lightweight/raw handles retain their prior physical
SQL path. Do not apply full corpus admission to every historical `definitions_for`,
header, ctxtypes or hookpack call: existing cave fixtures use five-column raw type
rows for pure projections. Those fixtures are not canonical migration support.

At the exact affected consumer seams, branch to the new logical-state check only
for current13 (and refuse recognized future versions rather than ignoring state):

- `definitions_for`: retain empty-names fast path before any new SQL; for nonempty
  names, current13 absent raises the same missing-type `sqlite3.OperationalError`
  category/message as the old missing table. Installed-empty returns empty; raw/
  historical query behavior is unchanged. `recover_named_ghidra` needs no new
  source logic; verify actual resolved-name/fallback behavior through it.
- `build_header`: retain basis/build validation order; immediately before reading
  definitions, enforce current logical availability. Absent refuses before any
  artifact, installed-empty retains its zero-type header/manifest result. No
  automatic materialization or manifest/basis format revision.
- CLI `build-types-header`: use logical presence for13 at its existing table check,
  retaining missing/unknown-binary exit2 text and output-file absence. Historical
  physical behavior remains through its explicit canonical-open migration route:
  a previously missing inventory migrates to13 absent, preserving the clean error.
- Bundle: current13 logical absence maps to its existing captured-definitions-
  unavailable refusal; installed-empty still gets the per-build no-definitions
  refusal. Keep its read savepoint, ordering, staging and publication policy.
- `/types`: one `corpus_read_snapshot` for presence/state/count/page avoids different
  connections observing mixed logical/data states. Reuse `table_exists/query_db`
  with the supplied connection where appropriate; preserve STABS behavior and all
  paging/filter fields. For13 absent return existing unavailable JSON; for installed
  return existing empty/populated JSON with raw origin values. Shape failures return
  existing503 error form. Missing database remains unavailable as before; bind that
  specific case explicitly rather than changing it accidentally to generic503.
- `ctxtypes.load_types` adds only a version/state admission inside its existing
  exception-handling boundary before its type SELECT: valid13 absent returns `{}`,
  installed13 reads unchanged rows, and corrupt13 or future14 is unavailable via
  the documented `{}` fallback. It must not emit invalid rows or install schema.
  Raw/historical calls retain their existing physical SQL/error fallback.
- `hookpack_v2.build_hookpack_v2` adds a narrow version/state gate before its type
  projection (and before exported type entities are constructed). Valid13 absent
  contributes zero entities, installed13 retains the exact type/field projection,
  and malformed13 or future14 propagates refusal before returning a pack. Raw/
  historical paths keep existing table-presence and field behavior. Added origin/
  state columns are not exported; no schema ownership or cache format change is
  delegated to the projection. `export_hookpack.py` routing remains unchanged.
- Physical inventory stays physical; it may list the new tables/marker. It must
  not be repurposed as logical availability or capture proof.

## Writer and planner transaction contracts

`plan_adoptions` becomes genuinely read-only, with unchanged signature and
calculation order/result for equivalent supported inputs. Require current13
before config loading/donor scans, remove all executescript/ALTER/exception-swallow
paths, and use canonical origin presence without rewriting donor logic. Mode
absent has empty type/origin storage: report the existing empty-plan structure
without materializing state. Raw/outdated planners now refuse explicitly; this
is an adopted tightening because their former planning behavior installed schema.
Planning never commits, rolls back or creates caller work.

Export and adoption apply require current13 before Ghidra startup/program access,
iteration or payload writes. Thus even no-program calls on invalid stores refuse;
on a valid store the existing no-program result remains unchanged and leaves
mode untouched. Build payloads before write scope, then BEGIN IMMEDIATE or a
private caller savepoint. Revalidate under that scope before materializing state
and main-qualified writes. Keep the savepoint through successful commit so
pre-durability failures preserve surviving caller pending work. Success still
commits caller work, including zero rows. BaseException cleanup and rollback/
release errors propagate; scope-creation failures gain no cleanup ownership;
engine-lost transactions and committed-but-unacknowledged operations report
uncertainty without reconstruction. Do not close caller handles or claim donor
snapshot isolation across out-of-scope computations.

Put narrow shared type-write scope/state materialization helpers in `export_types.py`
(not a generic transaction framework). `apply_adoptions` can use those helpers;
its existing dependency on export_types already exists. A new focused native
insertion helper there owns admitted main-qualified `INSERT OR IGNORE`, returns
actual insertion count, and materializes state atomically. It must not accept a
free-form conflict-policy switch or silently replace rows/fields. Public existing
SCHEMA/ORIGIN_DDL imports remain aliases to canonical declarations, never executed
by public writers.

Generated `layout_script` uses an existing-file raw writable handle, row factory,
and strict type admission before accessing the program. It must not call a
migration/backfill through `connect` or execute DDL. Stage the same definition
payloads, then call the owned native insertion helper; cancellation or a malformed
batch cannot leave a partially committed inventory. Close its owned handle in
finally. Preserve monitor checks, current insertion policy/count, header result,
context-hint claim and metadataPolicy. A postcommit header-write failure cannot
claim capture rollback. This packet does not add missing native field capture.
Generated-script syntax/source checks are authored specs only; no Ghidra/JVM or
native script execution follows from this proposal.

`write_calibrate_global_receipt` becomes read-only with respect to the corpus:
open existing current storage read-only, close it in finally, remove installer,
no-program export invocation and apply_adoptions. It may still write its explicit
receipt/header artifacts using existing definitions. Plan adoptions for information
only. If candidates exist, `propagate` becomes `state="planned"`, `planned=N`,
`adopted=0`, existing stats, and the top-level receipt is partial with a propagation
gap; do not claim those rows were applied. For zero candidates preserve present
fragment with adopted0 (and planned0); absent logical inventory records missing
export/header fragments and a partial types gap, without generating a misleading
header. Existing-header shortcut remains unchanged and never opens/mutates DB.
Outdated/malformed/unavailable-current stores produce named fragment error/missing
results, not migration or capture. No new route/background work is introduced.

## Frozen deletion13

Add explicit ledger13 and an independently frozen type/state delta. Known tables
become29; mandatory23 and optional6: type, origin and the new state join the20
mandatory12 tables, while fields were already mandatory. Canonical13 requires
seven-column types, exact origin/index/state/field xinfo and prior complete11/12
rules. Accept historical ALTER and fresh CREATE declarations without relaxing
order/default/constraint checks. State absent with type/origin rows refuses.
Keep historical9–12 maps, optionality and metadata checks independently frozen;
future14 refuses even when live migrations grow.

Preserve delete order/executor/count keys: both type tables already delete by
binary_id, fields already delete, and the global singleton stays. Preserve existing
surviving adopted rows/origin donor text after donor removal; do not infer a new
cascade. Existing foreign-owner validation and conservative convention/identity
refusals remain. No type schema metadata can grant native/runtime trust.

## Exact proposed ownership and regression source

One fresh implementation owner must own this packet; controller serializes schema
numbering and shared test files. U9 release does not authorize overwriting later
changes in workflow/API. No concurrent native/ABI transport file is owned here.

Production paths under `src/agentdecompile_recovery/corpus/`:

1. `store.py` — declarations, field/type shape/state guards, current reader admission,
   convention13 advancement and exact decomp13 extension.
2. `migrations.py` — append13 only; prior steps and runner frozen.
3. `delete_registry.py` — explicit frozen13 delta, no executor rewrite.
4. `export_types.py` — alias, export admission/scope, native insertion helper,
   definitions_for logical-absence seam only; emission algorithms unchanged.
5. `propagate_types.py` — alias, pure planner, admitted atomic apply.
6. `pipeline.py` — only write_calibrate_global_receipt store read/planning boundary.
7. `dashboard/workflow.py` — only layout_script generator/imported helpers contract.
8. `dashboard/react_api.py` — only types handler and required narrow imports.
9. `build_types_header.py` — logical absence gate, emission/manifest unchanged.
10. `kx_cli.py` — only build-types-header presence/error branch.
11. `export_bundle.py` — logical absence classification before definition count.
12. `ctxtypes.py` — load_types current/future availability gate within its existing
    exception fallback; projection and callers unchanged.
13. `hookpack_v2.py` — type-projection current/future gate only, existing entity/
    field/basis algorithms unchanged.

Docs: `docs/CORPUS_PIPELINE.md` plus a new bounded implementation report. No new
frontend, actions, common snapshot API or source recovery production rewrite is
required. Hookpack and ctxtypes changes are limited to the explicit admission
seams above. If implementation finds a new semantic consumer,
return its concrete evidence for contract amendment before widening ownership.

Regression paths to assign explicitly, all authored and unrun during source work:
`tests/test_store_migrations.py`, `tests/test_corpus_db_compatibility.py`,
`tests/test_corpus_delete_registry.py`, `tests/test_corpus_stabs_migration.py`,
`tests/test_corpus_decomp_schema.py`, `tests/test_corpus_convention_schema.py`,
`tests/test_propagate_conventions_abi_gate_stored.py` (only necessary current-writer
fixture effects), `tests/test_cli_input_errors.py`, `tests/test_corpus_calibrate_global.py`,
`tests/test_workbench_workflows.py`, `tests/test_corpus_cave_qualification.py`,
`tests/test_corpus_export_hookpack.py`, plus new `tests/test_corpus_type_schema.py`
and `tests/test_corpus_type_consumers.py`. Preserve U9 authority fixtures and its
matcher-input-v2 function. Freeze genuine12 fixtures; move synthetic future13 to14
only where truly future. Freeze historical type/origin SQL in deletion fixtures
rather than AST-evaluating new aliases or applying origin ALTER twice to13 stores.
The existing cave-qualification fixture currently calls canonical connect and then
creates a five-column type table. Freeze that specific projection specimen at an
actual pre13 runner target (or an explicitly raw handle) before creating its table;
it must not CREATE over fresh13 storage or be relabeled supported migration history.

## Authored acceptance specification

These are future source requirements, not passed results or execution permission.

1. Actual12 histories cover absent/six/seven-column (CREATE and historical ALTER),
   empty/populated, optional origin/index presence, multiple kinds/same names,
   NULL/native/adopted/empty/unknown origins and donor text, rowids, typed nested
   fields/ordered storage JSON, and unrelated extensions. Real runner reaches13
   preserving all old data/ledger rows/decomp selectors/basis values. Absent remains
   logically absent; installed-empty stays installed. Malformed old states refuse
   unchanged before DDL. Fresh prefixes retain baseline and prior history.
2. Actual consumer matrix across12→13 proves API unavailable/empty/populated,
   selected empty binary in a globally installed inventory, missing database,
   paging/filter/STABS and deliberate six-column503→NULL repair. CLI keeps clean
   absent error; definitions_for empty-names avoids SQL and nonempty absent raises;
   installed-empty remains empty/zero-header. Bundle retains its two distinct
   refusal reasons and no output. Header/manifest, recovery-definition fallback,
   hookpack type/field projection, ctxtypes and raw five/six/seven-column readers
   retain declared behavior. Paired corrupt13 absent-plus-rows and actual14 cases
   prove hookpack refuses and ctxtypes returns `{}` rather than emitting rows. Run these actual entry points only in separately
   authorized future checks; source doubles alone do not prove live consumers.
3. Pure current guard/planner retain caller transactions/snapshots and exact plan
   rows/stats for equivalent donors. Raw/outdated/future/malformed handles refuse
   before config/Ghidra/payload work; lock-tolerated/readonly12 cannot write13.
   Reserved main/TEMP names, views/virtual tables/defaults/constraints/reordering,
   extra indices/triggers (including arbitrary TEMP trigger names by owner),
   malformed fields/state and attached substitutes refuse. Unrelated extensions
   and TEMP scratch remain permitted. No missing-origin catch-all repair remains.
4. Export preserves replacement, selected typed-field replacement, all unaffected
   rows and omitted-origin NULL behavior; origin annotations stay unchanged. Native
   helper preserves curated keys via IGNORE, creates only missing keys and counts
   actual inserts; no fabricated field evidence. Adoption preserves exact note,
   donor filter/stats/origin payload and key semantics. Zero-row success, no-program,
   cancellation, first/later insert, field deletion/insertion, state write, mapper/
   producer and precommit failures cover owned/caller scopes, durable success,
   BaseException, creation/cleanup failure and lost transaction/ack uncertainty.
   Mutated schema between initial guard and scope must refuse before writes.
5. Inject pending13 failure after CREATE, origin ALTER, index/state install,
   singleton insert, ledger/version write and predurability COMMIT. Preserve newly
   committed1–12 and every old row. Cleanup failure/lost acknowledgement make no
   rollback claim. Repeat10/11/12/13 validates own version under a future registry;
   missing13 state refuses without repair. Actual14 refuses strict readers,
   writers and deletion; ctxtypes retains its explicit unavailable-as-`{}` result
   rather than throwing or projecting future rows.
6. Generated script inspection and future isolated stubs exercise currentProgram,
   no supported datatype, cancellation, curated collision, capture failure,
   admitted helper call, closure and header-after-commit failure. No direct DDL,
   implicit connect migration or raw unguarded insert remains in the generated text.
   Preserve preparation authority and metadataPolicy; native installed verification
   remains separate from generated source/stub evidence.
7. Receipt existing-header/no-db/current-absent/installed-empty/populated/planned-
   adoptions/error cases verify named fragments, partial states and artifact results.
   Compare database schema/data/ledger/pending work before/after; no Ghidra starter,
   migration/backfill, applies, commits or materialization may occur. Planned counts
   never become adopted counts. Handle closure includes failures.
8. Deletion genuine9–12 optional shapes remain valid;13 required type/origin/state
   missing/corrupt cases refuse atomically. Selected deletion counts, surviving
   adopted/origin rows, typed fields, caller provisional receipts, last-binary state
   retention and all unrelated rows remain correct. Keep actual future14 refusal.
9. AST/literal comparisons pin baseline, steps1–12/runner/repeats, ABI/emitter/
   projection algorithms, public existing signatures, decomp state semantics,
   matcher-input-v2/basis formats and frozen historical deletion maps. No new cache
   basis/ABI revision or verification receipt follows merely from type ownership.

## Remaining gates and performed work

Read the listed authorities and actual sources/consumer/test seams. Used only text
search/read operations for this proposal; no project execution was needed. Wrote
only this file. No source/test edit, Git action, subagent, test/collection/build/
typecheck/proof, project import, DB open/query/migration, hash/crypto/signing/key
work, process/runtime/helper/generated-script execution, API/catalog/live mutation,
capture/provisioning/systemctl/restart/alternate port, synchronization, activation
or publication occurred. Existing convention source remains untouched.

The marker and explicit planner/receipt/API changes require independent review
and controller adoption; they are not self-authorized implementation. Future
historical/failure/consumer execution, installed native/script qualification,
cataloged workload admission and STRATEGY whole-image acceptance remain separate.
Recovered/reuse legacy keys, logical-name caches, registration/binding metadata,
helper DDL, code_func_count, broad determinism/content keys/per-kind caches and
literal facade removal remain open. No full U2/U22/U23/U82 completion is claimed.


## Controller adoption — Task2.6

Adopted for bounded type schema source implementation after independent `type-ownership-contract-review.md`: specification, quality, feasibility, security, data-integrity and API-contract reviews PASS; zero outstanding Critical/Important and zero new Minor. Implementation remains source-only. Historical 9–12, current13/future14, absent-vs-empty type API, nonapplying raw planner, writer transaction and consumer boundaries in the reviewed contract are binding. No runtime, generated-script, migration, ABI, installed-consumer or full U2/U23 acceptance follows.
