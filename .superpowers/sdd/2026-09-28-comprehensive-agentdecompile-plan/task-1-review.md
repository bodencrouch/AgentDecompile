# Task 1 review: U1 slice 1.1

Spec compliance: **Issues found**. The selected content binding satisfies the owned producer/evaluator predicates, but two existing consumer pre-enumeration paths violate the task's explicit missing-schema/unreadable-SQLite refusal requirement (`task-1-brief.md:73`). The brief allows consumer correction for this explicit refusal contract (`task-1-brief.md:56`). These are missed requirements, not new regressions introduced by the digest comparison.

Task quality: **Needs fixes**. No defect found in the new digest/snapshot binding itself. The two public consumer error paths below need a bounded correction before this slice meets its stated contract.

Review basis: supplied `task-1-review.diff`, base `860731e59e6cb1c20ec8f977d5486872b66dbaad`, head `612e13151805642f33521dbc2e5f1caacccc72ce`; brief and implementation report. The diff was read once. This is a task-scoped source review; no whole-U1 closure is claimed.

## Strengths

- `src/agentdecompile_recovery/corpus/source_contribution.py:231`: `_db_row` preserves its positional interface and standalone path, validates both expected and selected complete-image digests, requires an exact singleton binary and function extent, and reads both selections within one explicit `BEGIN` snapshot. Its narrow returned binding includes `binarySha256` and excludes unrelated rows and database-file fingerprints.
- `src/agentdecompile_recovery/corpus/source_contribution.py:284`, `:322`, `:347`, `:426`, and `src/agentdecompile_recovery/corpus/source_revalidation.py:161`: all five production calls supply the captured/retained target digest. Publication and validation compare the complete binding; selection mutations refuse while unrelated row edits do not change that dependency.
- `src/agentdecompile_recovery/corpus/source_contribution.py:417`, `:442`, and `src/agentdecompile_recovery/corpus/dashboard/byte_parity.py:114`: raw image equality, per-candidate final-writer credit, false semantic identity, and selected-function qualification stay separate. No semantic witness, schema migration, public signature change, or terminal whole-image acceptance was added.
- `tests/test_matching_contribution_consumers.py:141` onward and `tests/test_source_revalidation.py:207` onward specify positive physical binding, wrong complete image with equal spans, unknown identities, publication/consumption mutations, unrelated-evidence survival, and retained source/floor/import gates. These are source specifications, not executed receipts.

## Important findings

### C1: Matching-status raises before producing the required refusal report

**Confidence: 100.** `src/agentdecompile_recovery/corpus/matching_status.py:92`–`:96` opens the selected database and queries `func` without exception handling. A readable SQLite database without `func` raises at the query; malformed SQLite raises on the query; an unopenable selected database raises at connection creation. Execution never reaches `evaluate_reconstruction` at `:101`, the zero-credit report construction at `:186`, or report/manifest writes at `:194`–`:201`.

The helper's new conversion of SQLite failures to stable refusal reasons cannot cover this earlier boundary. The implementation report acknowledges it at `task-1-report.md:130`, but the task expressly requires missing schema/unreadable SQLite to produce an explicit zero-credit refusal rather than crash in consumers. The requirement applies even though the direct enumeration predates this diff.

**Required correction:** Handle the bounded enumeration/open/query failure and route it into matching-status's public report/manifest diagnostics, with zero qualified selected-function credit and an explicit database/selection refusal. Retain the failed inventory as unavailable/unknown; do not represent the failure as a verified complete corpus containing zero functions. Preserve independent raw image equality and candidate/artifact availability. Keep public call signatures and routing intact. Add regression source that calls `matching_status.main` with missing `func` and malformed/unreadable SQLite and checks the emitted refusal diagnostics, zero qualified credit, and unavailable inventory.

### C2: Revalidation raises before its candidate rejection handling

**Confidence: 100.** `src/agentdecompile_recovery/corpus/source_revalidation.py:135`–`:139` opens the database and runs `SELECT count(*) FROM func` outside the per-candidate rejection handler at `:155`–`:175`. An existing malformed SQLite file passes the bounded file read at `:134` and then raises on the query; a valid SQLite file lacking `func` raises at `:137`. Neither reaches the changed target-content preflight at `:161`, any candidate refusal diagnostic, or `RevalidationResult` construction at `:183`–`:188`.

The added revalidation cases (`tests/test_source_revalidation.py:207`) remove `binary` or alter its digest while retaining `func`, so they do not cover this preceding failure. Correcting C1 alone cannot fix this earlier revalidation path. This is the same explicit scoped refusal requirement at a second public boundary.

**Required correction:** Handle the bounded inventory preflight failure through revalidation's public refusal diagnostics, with an explicit database/selection reason and zero qualified credit, preserving unknown inventory rather than claiming a complete zero-function selection. Ensure no compiler invocation/capability publication occurs for this refusal; retain original sources/candidates. Add regression source for malformed/unreadable SQLite and missing `func` through `revalidate`, checking the diagnostic result and absence of producer invocation. Preserve the existing bounded resource checks and public signature.

## Review checks and limitations

- Named risk **consumer failure before the new shared helper**: inspected only the relevant unchanged `matching_status.main` enumeration/evaluation/report path and `byte_parity_state` evaluation/denominator error handling. Dashboard handles this database failure; matching-status does not (`matching_status.py:92`, `byte_parity.py:127`).
- Cut-off hunk context **qualification and revalidation error propagation**: inspected `source_contribution.py:358`–`:488` and `source_revalidation.py:120`–`:188` because the diff ends mid-function. This confirmed the evaluator catches binding errors and exposed revalidation's earlier inventory boundary.
- Named risk **genuine fixture and altered-image test basis**: inspected the unchanged synthetic PE and `compiled_pair` helper (`tests/test_source_contribution.py:15`–`:51`). Both six-byte spans are unaffected by the final-byte mutation; the native-compiler fixture retains its availability skip. No fixture was executed.
- No tests, suites, builds, compiler invocation, Python/project imports, AST checks, live/catalog queries, services, source/index/Git mutations, or subagents were run by this reviewer. Only the owned review report was written. The implementer's source-only evidence was read, not repeated (`task-1-report.md:48`, `:110`).
- Executable acceptance, installed/serving activation, and live recovery remain **unverified**. After separately authorized execution, verify the existing new specifications plus C1/C2 consumer refusal cases. Synthetic execution cannot establish full U1 or fresh whole-image compiler acceptance.

<oai-mem-citation>
<citation_entries>
MEMORY.md:274-276|note=[kept source review and live acceptance distinct]
</citation_entries>
<rollout_ids>
01a0e876-fcbe-7041-af54-f4c9fc9eb102
</rollout_ids>
</oai-mem-citation>
