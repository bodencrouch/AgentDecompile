# Task 1 scoped re-review: correction round 1

- **C1 — Matching-status raises before producing the required refusal report: ADDRESSED.** `src/agentdecompile_recovery/corpus/matching_status.py:117` catches database open/query and row-conversion failures at `:121`, writes the shared refusal shape to both requested public outputs at `:129`, and returns normally. `_unavailable_inventory_report` at `:68` sets qualified credit to zero and records `selected_database_inventory_unavailable` with diagnostic detail. Inventory completeness is false and inventory/denominator values are null (`:80`); manifest functions are null. The output-request branch at `:127` reports refusal without replacing an existing output. Successful enumeration retains available/complete inventory at `:225`, including genuine count zero. Regression sources cover three failure forms and complete-empty selection (`tests/test_matching_contribution_consumers.py:315`, `:349`); execution is unverified.
- **C2 — Revalidation raises before its candidate rejection handling: ADDRESSED.** `src/agentdecompile_recovery/corpus/source_revalidation.py:135` records bounded file/open/query failures via `:143`; selected candidates skip producer invocation at `:160`. The failed-inventory branch at `:193` evaluates only the empty-candidate floor reconstruction and calls the shared refusal-report helper directly; it does not reopen/retry the database through matching-status or qualification. `evidenceState` at `:198` marks inventory refusal. SQLite query budget at `:139`, maximum function count at `:141`, and unchanged bounded regular-file reads remain enforced. Limit `ValueError`s are not caught by the availability handler and therefore remain hard pre-workspace refusals. Regression sources cover public refusal, no producer/capability publication, and preserved byte/function limits (`tests/test_source_revalidation.py:236`, `:277`); execution is unverified.

**New Critical/Important breakage in the fix diff: None found.** The new helper preserves separate raw equality while withdrawing selected credit and keeps unavailable inventory distinct from complete empty inventory. Normal available-inventory routing and public function signatures remain intact.

**Out-of-scope observations: None raised.** No fresh review of unchanged U1 producer, semantic, packaging, or recovery authority was performed.

**Scoped spec compliance: Compliant by source review.** Both explicit consumer-refusal gaps are closed. Zero qualified credit, explicit failure diagnostics, retained candidate artifacts, unavailable denominators, revalidation producer exclusion, and no retry after failed bounded inventory are represented by the reviewed control flow.

**Scoped task quality: Approved by source review.** The shared diagnostic helper gives the two consumers one refusal shape, connections close on both success and failure, and the explicit branch avoids continuing into normal inventory arithmetic. Executable acceptance remains open.

**Fix round verdict: All findings addressed; no new Critical/Important breakage found.** Review basis: supplied fix package `612e13151805642f33521dbc2e5f1caacccc72ce` through `2a16c3650c4992521990a9ecebc4d8f149483874`, original brief, C1/C2 review, and appended correction report. The fix diff was read once; no Git commands were run.

**Focused checks:** The new nullable response contract prompted inspection of its known caller paths in `dashboard/byte_parity.py:43` and `matching_watch.py:18`. Dashboard variants pass through the nullable imported denominator without Python arithmetic (`byte_parity.py:58`); the existing parity caller guards its use of `codeTotal` (`byte_parity.py:124`, established in the preceding review). Matching-watch does not consume matching-status's report for its arithmetic; it uses its independently obtained stats (`matching_watch.py:26`, `:46`, `:59`). No new arithmetic exception caused by the nullable report was found in these focused paths. This was not a broader consumer audit.

**Focused checks:** To verify that removed databases can reach the new handler and that bounds survive, inspected unchanged recipe path validation and `_bounded_file` only (`source_revalidation.py:43`, `:57`). Recipe canonicalization does not require database existence; bounded reads retain nonblocking/no-follow open, regular-file checks, and the byte limit. These concrete checks support the new failure branch; no imports or execution occurred.

**Verification limitations:** No tests, suites, builds, compiler invocations, Python/project imports, AST parsing, live/catalog/service operations, source/index/Git mutations, or subagents were performed. Only this owned report was written. The implementer's appended source/AST/diff evidence was read rather than repeated. All added regression specifications remain unexecuted; installed activation, runtime/live acceptance, fresh whole-image compiler acceptance, and full U1 completion remain unverified.

<oai-mem-citation>
<citation_entries>
MEMORY.md:274-276|note=[kept source review and live acceptance distinct]
</citation_entries>
<rollout_ids>
01a0e876-fcbe-7041-af54-f4c9fc9eb102
</rollout_ids>
</oai-mem-citation>
