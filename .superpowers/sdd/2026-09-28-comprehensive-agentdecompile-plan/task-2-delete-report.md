# Task2.2 deletion registry implementation report

Status: READY_TO_COMMIT for controller review; source implementation only. No
commit or staging performed. Implemented against assigned base
`adf0bbb4d14c7a7721873fa42da6dbfc49f141a2` and the adopted
`next-delete-registry-contract.md`. Full U2/U22 remain open.

## Owned files and boundaries

- `src/agentdecompile_recovery/corpus/delete_registry.py` (new): frozen supported
  schema declarations, ownership/refusal policy, deletion-only opener and atomic
  executor.
- `src/agentdecompile_recovery/corpus/store.py`: only `remove_binary` and its
  docstring; delegates to the registry and documents provisional caller receipts.
- `src/agentdecompile_recovery/corpus/cli.py`: only the existing `remove-binary`
  branch; noninitializing open, nonzero errors, owned-handle closure.
- `src/agentdecompile_recovery/corpus/dashboard/workbench.py`: only
  `remove_registered_binary`; confirmation remains before opening, open errors
  enter the existing error envelope, cache clears only after committed success.
- `tests/test_corpus_delete_registry.py` (new): regression source, never executed
  or collected.
- This report.

Reviewed Task2.1 `store.connect`, `db.py`, other workbench callers, other CLI
branches, and the concurrent P2/admission lanes were not modified. No other
agent's changes were reverted. No actual binary, database, source artifact,
project, cache, or Ghidra data was opened or removed.

## Implemented behavior

The deletion profile recognizes 17 mandatory and ten optional corpus tables. It
admits only v9 with the complete exact version/name ledger and source-declared
column, key, nullability, FK/action and index shapes. Table declarations are
inspection data, never DDL executed by removal. Additive migration columns and
reviewed optional writer columns are distinguished; old recovered keys refuse.
Unknown tables, indexes, views, triggers, virtual tables, unsupported mixed-store
objects, attached databases and temporary schema objects refuse before writes.
Canonical review schema/trigger/singleton validation uses the existing read-only
`match_review_schema.require`; selected revisions additionally require valid
clock coverage and natural keys.

The conservative dependency gate refuses surviving identity or match rows,
surviving recovered logical IDs including unbound owners, and surviving derived
conventions. Ownership and key storage are checked without casting legacy values;
affected dangling logical references refuse. It does not infer a dependency DAG,
call binding/admission or claim an empty dependency list proves independence.

Target selection and preflight occur under owned `BEGIN IMMEDIATE` or a unique
caller savepoint. All operation counts are selected before the first data write.
The source-proposal pass selects the pre-removal program/name relation while
recovered rows are still intact, excludes first-pass destination deletions, and
retains proposals with surviving NULL-bound or other-build candidates. Unrelated
preexisting orphan proposals remain. The fixed deletion order removes all actual
owned rows, invalidates only affected/donor-derived logical names, updates only
affected logical member counts, and removes exactly one binary last. Immediate
absence/count checks precede commit/release. Canonical trigger-owned revision
removal is counted separately and verified; logical rows and audit rows explicitly
report zero deletions. Public result shape and selector precedence are retained.

Owned transactions roll back on `BaseException`, including commit failure.
Caller transactions roll back only the local savepoint on failure and remain
uncommitted on success. SQLite-invalidated outer transactions/rollback failures
surface as errors with original exception context, never success receipts. The
executor does not close caller handles. Both public routes use `mode=rw`, a Row
factory and 30-second timeout without initialization, migration, backfill,
journal changes, or directory/file creation.

## Regressions authored, not run

- Complete positive fixture drawn from canonical migrations and independently
  read optional-writer DDL; exact counts, repo/slug/precedence, FK ON/OFF,
  self-match/BSim ownership, one binary removal and repeat-removal error.
- Shared and NULL-bound recovered candidates with equal paths/digests; last-source
  versus surviving-source reuse, unrelated orphan retention, copied donor type
  provenance, exact alias ownership, source identity and program-binding retention.
- Empty logical group retention, scoped cache invalidation/count updates,
  historical metadata/audit equality and exact review clock advancement.
- Identity chains/shared groups, component envelopes, ancestry tokens, name-only
  identity, unrelated survivors, inherited recovered identity, donorless ABI and
  unknown/NULL match endpoint refusals with complete unchanged snapshots and no
  data-write trace.
- Every optional absence and mandatory absence, dependent optional parents,
  known additions/old optional layout, old/future versions, damaged ledgers,
  keys/FK actions/owner storage, unknown columns/tables/views/indexes/triggers,
  missing or modified review state, mixed/transient stores and attached/temp state.
- Failure injection at every direct delete/update ordinal, prior caller writes,
  successful caller rollback, owned commit/lock/count failure, canonical trigger
  execution failure, interruption, invalidated outer transaction, and real WAL
  snapshot-upgrade refusal (all authored only).
- Missing-path opener, no initialization/reconstruction helper calls, selector
  errors, CLI nonzero/no success output, HTTP confirmation/open/refusal/success
  cache behavior and route handle closure.

## Checks actually performed

1. Read-only source/DDL/writer/caller inspection with `rg`, `sed`, `cat`, and Git
   diff/status; read AGENTS, src/CLAUDE, both available SDD implementer templates,
   the assigned brief and the adopted contract in full. Used memory only for the
   source-versus-live evidence boundary.
2. Standard-library `ast.parse` of the five owned Python files; all parsed. No
   project module was imported and no Python bytecode compilation was invoked.
3. Read-only trailing-whitespace inspection of those five files; no issues.
4. `git diff --check`; no output, success. Inspected the exact three existing-file
   diffs and removal call sites to verify ownership boundaries.
5. Static source extraction produced the frozen DDL inventory; this read Python
   AST/literal source only and never loaded project modules or opened SQLite.

No tests, collection, suites, builds, typechecks, proof scripts, project imports,
database queries/creation/deletion, compiler/checker, Ghidra, runtime/process,
catalog, service/systemctl, restart, port, staging, commit or publication action
was performed. There is no RED/GREEN or regression-pass claim. Authoring test
operations is not evidence of executing them.

## Self-review and compatibility cost

Source self-review corrected lexer handling of comparison tokens in canonical
review CHECK constraints and kept quoted identifiers distinct from SQL keywords
while allowing SQLite's quoted rebuilt-table name. It also strengthened owner/key
storage and review natural-key validation, verified the scoped source-proposal
pass against NULL survivors and overlap, and reviewed BaseException/savepoint
failure handling. The static profile is deliberately strict: semantically similar
but unreviewed DDL is not silently accepted.

Most corpora retaining identity lineage are unsupported until a qualified global
dependency/immutable-root model exists. This is an intentional compatibility cost,
not a complete transitive invalidator. Schema-version support is deliberately
limited to the reviewed v9 layouts, including the full current recovered key.
Shared logical identity deletion, old recovered migrations, stable entity-key/
previous-key work, all-DDL consolidation and full U22 remain open. No installed
removal safety, live database compatibility, runtime activation, regression pass,
recovery acceptance, or complete U2/U22 result is claimed.
