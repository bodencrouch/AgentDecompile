# Task 1 implementation report: U1 slice 1.1

Status: source implementation complete; executable acceptance unverified.
Implementation base: `860731e59e6cb1c20ec8f977d5486872b66dbaad`.
Implementation head: `612e13151805642f33521dbc2e5f1caacccc72ce`.
Commit: `612e1315 fix(recovery): bind corpus contribution to selected target content`.
Workspace: `/home/brunner56/.codex/worktrees/6e95/AgentDecompile`.
Scope authority: the task-1 brief, slice 1.1, plus current repository mission constraints.

## Implemented behavior

`source_contribution._db_row` retains its four positional arguments and adds the
optional keyword `target_sha256`. The standalone `db is None` path returns
`None` without asserting selected-corpus identity. A database-bound request must
supply a lowercase 64-character hexadecimal complete-image digest.

The helper opens the selected database read-only and issues an explicit `BEGIN`.
It reads the selected `binary.content_sha256` and selected `func` extent in that
transaction. Binary content requires an exact singleton row, valid digest and
equality to the producer-observed complete target image. Function extent still
requires the exact singleton `(address, size)`. The returned `selectedRow` now
contains `binarySha256`, retaining path, binary ID, address and size. No database
file fingerprint, slug, logical name or semantic identity graph was added.

Refusals are `missing_or_invalid_selected_binary_content_identity`,
`selected_binary_content_mismatch`, and
`selected_database_row_changed_or_ambiguous`. SQLite open/schema/query errors
become explicit `ValueError` refusals; the evaluator's existing handling retains
zero credit and candidate diagnostics. Unknown identity is never backfilled.

All five internal callers pass the expected complete-image digest:

- Initial production uses `digest(target_raw)` captured from actual target bytes.
- Publication repeats that physical binding and compares the complete returned
  selection against the captured `selectedRow` before capability registration.
- `validate_compile` uses the retained `record['target']['sha256']` and compares
  the current complete selection to the recorded one. An older row lacking
  `binarySha256` cannot compare equal and cannot earn selected-corpus credit.
- Selected-corpus reconstruction evaluation uses `item['target']['sha256']` and
  retains the exact producer selection and candidate binary-ID equality gates.
- Revalidation preflight uses `doc['target']['sha256']` before invoking the
  genuine producer. Its later recipe and producer checks remain intact.

Public entry-point signatures and routing remain unchanged. The source diff
does not change compilation, COFF parsing, final-writer accounting, actual
reconstruction writes, semantic admission or terminal whole-image acceptance.

## Regression specifications added, not executed

The existing positive matching/dashboard/watch fixture and revalidation recipe
fixture now record the digest of the complete synthetic target in a `binary`
row. New sources specify:

1. Two genuine regions with twelve contributed bytes and two qualified
   functions through matching-status and dashboard, with selected content
   recorded and semantic/terminal compiler claims false.
2. Image B with equal function spans but different complete-image content
   refuses an A producer before toolchain/compiler invocation.
3. Missing binary table/column/row, duplicate selected binary rows, NULL, empty,
   uppercase and malformed digests, and unreadable SQLite refuse selected
   credit. Independent no-DB observations retain anonymous-region credit;
   artifacts and database contents remain available without digest backfill.
4. Missing/invalid expected digest, address/size mismatch, duplicate function
   rows and missing function table refuse the helper.
5. A selected digest mutation after genuine COFF parsing and before publication
   prevents `_COMPILES` registration while retaining the orphan object.
6. A selected digest mutation after production withdraws both selected
   candidates through validation and the two consumers while complete output
   byte equality remains true; independent evidence for another binary survives.
7. Adding/editing unrelated binary/function rows, including another selected
   binary's different extent, preserves the original contribution.
8. Correct physical binding cannot rescue a same-filename source edit,
   discarded candidate, floor-overwritten candidate, imported JSON or forged
   reconstruction. Independent second-source contribution survives.
9. Revalidation preflight rejects wrong/unknown content and missing binary
   schema before producer invocation, with zero qualified contribution,
   separate image equality and no unit objects.

These are future executable specifications, not success receipts. Existing
toolchain/implementation-dependency and import-authenticity sources were retained.

## Exact validation performed

Only read-only source/diff checks and standard-library AST parsing were performed.

- Read the bounded task brief and implementer prompt; inspected applicable
  `src/CLAUDE.md`, repository entry documents and `docs/solutions/README.md`.
- Inspected the physical digest precedent in `cross_place_admission.py` and
  the retained producer/evaluator plus matching-status/dashboard consumer source.
- Read the complete owned diff for self-review.
- Ran `git diff --check --` with the four owned source/fixture paths: exit 0,
  no output. Ran `git diff --cached --check` after staging those paths: exit 0,
  no output.
- Ran `git grep -n '_db_row('`: all production callers found in the two owned
  modules, plus the new helper regression specifications.
- Ran `git grep -n 'compiled_pair(.*db=' -- tests`: all DB-bound existing
  consumer fixture callers found in the owned matching-consumer source.
- Parsed the four changed Python files with `ast.parse(Path(name).read_text(),
  filename=name)` using `python3` with only standard-library `ast` and
  `pathlib` imports. Final source results: four `_db_row` calls in
  `source_contribution.py`, one in `source_revalidation.py`, five helper calls
  in `test_matching_contribution_consumers.py`, zero in
  `test_source_revalidation.py`. Printed production AST keyword lists all
  contain `target_sha256`. All four files parsed successfully.
- Reviewed staged path/stat scope and committed only the four owned paths;
  used `git -c core.hooksPath=/dev/null commit` so hooks could not execute
  forbidden tests/builds. The controller-owned dirty `progress.md` remained
  unstaged and unchanged by this implementer.

No tests, suites, builds, proof scripts, project imports, compiler invocations,
Ghidra work, live/catalog queries, process/service actions, pushes, publication
or `systemctl` were performed. TDD RED/GREEN evidence is unavailable because
execution is prohibited for this slice. No synthetic runtime result is claimed.

## Self-review and limitations

The complete-image digest binds physical corpus selection only. Anonymous
placement, semantic name proof, selected-function coverage, final-writer source
contribution and complete-image equality remain separate claims. The process-local
capability stores are unchanged; historical/imported audits do not regain trust.
The selected binary and function extent share one explicit read snapshot, and
unrelated mutable rows are excluded from the retained dependency.

Self-review corrected the direct publication-race specification to skip when
native clang is unavailable, matching the existing genuine-compiler fixtures.
It also added missing-function-schema refusal and physically bound source-edit,
discard/floor-overwrite and forged-audit specifications. No known source
correctness issue remains from this review; executable correctness is unverified.

Existing matching-status enumeration directly requires a readable `func` table
before it calls the shared evaluator. The new malformed-whole-database source
case therefore specifies refusal through the helper/evaluator/dashboard, not a
new matching-status CLI guarantee for a wholly unreadable corpus. Fixing that
pre-existing enumeration/error contract would require separate consumer scope.
Missing/invalid binary identity with readable function rows follows the new
shared refusal path. This distinction was established by source inspection only.

Serving provenance comes from the controller's independent refresh noted in the
brief. This local commit was not activated in the serving checkout; no live
consumer or unchanged process/state identity is asserted by this report.

## Unexecuted acceptance and remaining full-U1 gates

Every added executable regression remains unrun. Later specifically authorized
verification must record exact source revision, supported toolchain, producer
and consumer origins, and observation class. Synthetic fixture execution would
still not close catalog/game-target, installed/runtime/platform or full U1 proof.

This slice strengthens only the selected target-content predicates of R1/R2/R5,
RC-02 and the named D07/D09/D13/D21/D22 obligations in the brief. Full U1 remains
open for integrated evidence authority, independently qualified non-export
identity roots, Foo-labelled-Bar semantic refusal and positive independently
identified entity acceptance, policy/dependency fencing before publication,
producer/consumer provenance across the wider ingest/ledger/package pipeline,
and the fresh actual whole-image compiler acceptance with separate byte-accurate
C+assembly-floor and max-C variants. Existing floor equality is never that proof.

Deferred adjacent legacy-ledger compatibility, packaging API/provenance and
recipient-policy production-event wiring were not changed. Parent-owned living
plan, todo and delivery ledger updates remain the controller's responsibility.

## Review correction, round 1 of 5: C1 and C2

Correction base: `612e13151805642f33521dbc2e5f1caacccc72ce`.
Correction head: `2a16c3650c4992521990a9ecebc4d8f149483874`.
Commit: `2a16c365 fix(recovery): report unavailable selected inventories without credit`.

Read C1 and C2 in `task-1-review.md` verbatim. Both findings were accepted and
addressed within the controller's expanded consumer-boundary ownership. The
earlier report's matching-status enumeration limitation is superseded by this
correction; the original note remains above as history of the initial submission.

C1: `matching_status.main` now catches read-only database open/query and row
conversion failures before normal inventory-dependent report construction. It
emits both public report and manifest refusal diagnostics and returns normally.
The shared refusal report sets selected contribution to zero and explicit reason
`selected_database_inventory_unavailable`, retaining any candidate diagnostics
and raw image equality. `selectedCorpusInventory` records `state=unavailable`,
`complete=false`, `functionCount=null` and the underlying diagnostic. `code_total`,
manifest `functions`, inventory-dependent counts, coverage percentages, floor
denominators, receipt completeness and unknown max-C availability are null.
Zero qualified credit is therefore distinct from a successfully enumerated empty
corpus. A successful enumeration additionally records `state=available`,
`complete=true` and its observed function count. A requested output reconstruction
is explicitly refused on unknown inventory, preserving an existing output file.
The read-only SQLite connection is closed on both success and failure.

C2: `revalidate` now catches the bounded database file-read/open/inventory-query
failure and records it before admitting any candidate producer. Every selected
candidate receives the explicit inventory-unavailable rejection. Existing
unselected candidates remain intentionally discarded. Missing database files
are allowed to reach this diagnostic boundary rather than raising during strict
database-path resolution; required canonical path and binary-ID equality still
apply. Original source/candidate artifacts remain untouched. No compiler or
`CompileObservation` capability can be produced on this branch. The existing
floor-only `ReconstructionObservation` return path remains available for separate
raw image equality with zero source contribution and no whole-image compiler
acceptance; the refusal diagnostic uses `refused-selected-database-inventory`.

The refusal report helper is reused directly after failed revalidation preflight,
so the failed inventory is not retried outside its resource budget. Database
regular-file/byte limits, selected-function count maximum, SQLite progress
handler, target/source bounds and private exclusive workspace rules remain in
place. Resource-limit `ValueError` refusals remain hard pre-workspace refusals;
they are not converted to unlimited fallback scans. The normal available-inventory
path still uses the actual public matching-status consumer.

Added future executable specifications through the actual public entry points:

- `matching_status.main` with missing `func`, malformed SQLite and an unopenable
  selected database (removed synthetic database), checking emitted report and
  manifest, explicit refusal reason/detail, unknown/null inventory, zero
  qualified credit, preserved raw equality, candidate object availability,
  independent anonymous contribution and an existing requested output file.
- A successful, genuinely empty matching-status inventory, checking complete
  count zero and `functions=[]`, distinct from unavailable/null inventory.
- `revalidate` with the same three database failures, checking its public
  `RevalidationResult` and persisted matching-status diagnostic, selected
  candidate rejection, no producer invocation or new `_COMPILES` registration,
  no unit object, retained original sources and separate floor image equality.
- Revalidation's function-count and database-byte limits remain hard refusals
  before workspace creation or any producer invocation.

These sources remain unexecuted. No test result or recovery acceptance is claimed.

Exact correction validation commands and observed results:

```text
git diff --check -- src/agentdecompile_recovery/corpus/matching_status.py src/agentdecompile_recovery/corpus/source_revalidation.py tests/test_matching_contribution_consumers.py tests/test_source_revalidation.py
exit 0; no output

git diff -- src/agentdecompile_recovery/corpus/matching_status.py src/agentdecompile_recovery/corpus/source_revalidation.py
read the complete production correction diff for self-review

git diff -- tests/test_matching_contribution_consumers.py tests/test_source_revalidation.py
read the complete regression-source correction diff for self-review

git grep -n 'selected_database_inventory_unavailable\|_unavailable_inventory_report\|MAX_DATABASE_BYTES\|MAX_FUNCTIONS\|set_progress_handler' -- src/agentdecompile_recovery/corpus/matching_status.py src/agentdecompile_recovery/corpus/source_revalidation.py
confirmed both public failure paths use the refusal shape; existing byte/count/query limits remain present

python3 - <<'PY'
import ast
from pathlib import Path
for name in ('src/agentdecompile_recovery/corpus/matching_status.py', 'src/agentdecompile_recovery/corpus/source_revalidation.py', 'tests/test_matching_contribution_consumers.py', 'tests/test_source_revalidation.py'):
    ast.parse(Path(name).read_text(), filename=name)
    print(name + ': AST parsed')
PY
all four files printed AST parsed; exit 0; standard-library imports only

git diff --cached --check
exit 0; no output

git diff --cached --stat
four owned files; 176 insertions, 16 deletions

git -c core.hooksPath=/dev/null commit -m 'fix(recovery): report unavailable selected inventories without credit'
created 2a16c365; hooks disabled to prevent forbidden execution

git rev-parse HEAD
2a16c3650c4992521990a9ecebc4d8f149483874

git status --short
only controller-owned progress.md remained dirty
```

Self-review checked that failure cannot continue into normal denominator
arithmetic, cannot publish selected contribution after a later successful retry,
cannot bypass resource limits through matching-status re-enumeration, and cannot
replace an existing requested output. It also checked unknown inventory against
the positive complete-empty case. No further source issue was found in this
bounded correction. Tests, compiler/project imports, builds, live/catalog or
process/service operations remain unexecuted; activation and all remaining
full-U1 gates listed above remain unverified. Controller-owned changes were
preserved and the ignored report remains local.
