# Task 21.1 review

Spec compliance: **Approved for the bounded source slice.** Code quality: **Approved with one nonblocking Minor finding.** No Critical or Important findings were identified in the supplied owned-path diff.

Reviewed base `1d468be572b2c8f161ced8527445b49ad352f321` through head `bb41404123636d456862aac7c0850427b4a111af`, using `task-21-brief.md`, `task-21-report.md`, and the complete 1,325-line `task-21-review.diff`. This is source review, not executed behavioral acceptance, consumer activation, or full U21 closure.

## Spec compliance

- The optional keyword-only selection preserves the unfiltered path and refuses non-exact/out-of-range integers; the HTTP parser distinguishes absence from explicitly invalid or repeated input. Evidence: `src/agentdecompile_recovery/corpus/objdiff_report.py:18`, `:102`; `src/agentdecompile_recovery/corpus/dashboard/progress_reports.py:14`, `:144`; `src/agentdecompile_recovery/corpus/dashboard/router.py:689`.
- Physical functions, all identity claims at selected addresses, and qualified candidate-source rows are restricted in SQL before fetching/classifying. Duplicate or missing members/functions and conflicting roots/claims refuse. Ordinary required schemas and malformed present optional source schemas are checked. Evidence: `src/agentdecompile_recovery/corpus/objdiff_report.py:25`, `:44`, `:60`, `:74`, `:83`, `:147`.
- Selected scope and recorded root enter the canonical payload before its digest. A validated empty root seeds exactly one row; selected projection refuses foreign membership and marks global unbound counts null/not_requested. Evidence: `src/agentdecompile_recovery/corpus/objdiff_report.py:219`, `:225`; `src/agentdecompile_recovery/corpus/dashboard/progress_reports.py:39`, `:53`, `:84`.
- Both existing matrix requesters send logicalId; both validators require matching report/projection scopes, one exact integer row, matching build/version/digest, member conservation, and unavailable/null verified metrics. Existing content-derived request keys and cancellation guards are retained. Evidence: `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/LogicalNavigator.tsx:25`, `:31`; `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/coverageMatrix.tsx:13`, `:16`, `:27`, `:30`; `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:3223`, `:3236`, `:3262`, `:3305`.
- The existing classifier and independent accounting remain the producers. Selected unknown/multirange extents retain unknown total/percentage/tier-byte measures without changing function tier assignment; the projection provider remains disconnected with null verified metrics. Evidence: `src/agentdecompile_recovery/corpus/objdiff_report.py:183`, `:193`, `:208`, `:221`; `src/agentdecompile_recovery/corpus/dashboard/progress_reports.py:31`, `:100`, `:128`.
- The owned regression sources cover the named positive/refusal and lifecycle cases, including SQL returned-row boundaries and deliberately late old-selection completions. They have not been executed. Evidence: `tests/test_selected_progress_reports.py:112`, `:145`, `:274`; `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/SelectedMatrix.test.tsx:82`, `:158`, `:174`, `:193`, `:207`.

## Strengths

- Selection validation happens before tier production, and the all-claims query deliberately exposes foreign logical claims instead of hiding them behind a selected-id-only join. This is a sound refusal boundary for legacy or damaged corpora (`src/agentdecompile_recovery/corpus/objdiff_report.py:60`, `:83`).
- Hashing includes both the explicit selection descriptor and recorded root, so an empty selection is still bound to a real entity and differs from an unfiltered inventory (`src/agentdecompile_recovery/corpus/objdiff_report.py:219`).
- The source tests exercise both consumer implementations with the same malformed scope/conservation cases and ignored-abort completion scenarios, rather than only checking query-string construction (`src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/SelectedMatrix.test.tsx:82`, `:174`, `:207`).

## Issues

### Critical

None identified.

### Important

None identified.

### Minor

- **M1 — Compatibility regression does not pin the previous payload/digest.** `tests/test_selected_progress_reports.py:129` compares the omitted-argument and explicit-None calls to the same new implementation. Both could change the legacy shape or digest identically and still pass. The diff itself preserves the unfiltered algorithm, so this is not a demonstrated behavior regression or a blocker. Strengthen the regression source with a reviewed fixed pre-slice payload/digest fixture, including a whole-report unknown/multirange case, so future changes can actually detect a legacy compatibility break. Execute it only when regression execution is authorized.

## Cannot verify from source review

- Python/Vitest results, TypeScript validation, browser DOM behavior, installed consumer behavior, actual query plans/latency and end-to-end performance remain unverified. The implementer's syntax checks are reported evidence; this reviewer did not rerun them. Test source is not a passing test result.
- Snapshot/schema/deadline refusal is supported by the source path and regression definitions, but no database was created or queried. Real corpus acceptance remains deferred.
- Existing acceptance-receipt classification was retained, not independently requalified. Nothing in this review establishes current accepted-source bytes, fresh compilation, a connected independent acceptance provider, terminal whole-image recovery, or publication authority.
- This source has not been activated. Full U21, its remaining metric/acceptance/publication obligations, and the consumer activation gate remain open.

## Review checks and scope

- Read the supplied diff once in five contiguous manageable chunks. No Git command, source mutation, tests, project imports, builds, typecheck, syntax reruns, proof scripts, database/runtime/browser/catalog/process/service calls, port changes, or publication actions were performed. The only write is this review file.
- Named outside-diff risk: same-snapshot reads and SQLite/deadline failures might escape the structured refusal path. Checked only `src/agentdecompile_recovery/corpus/dashboard/common.py:253`–`:276` and the truncated exception tail at `src/agentdecompile_recovery/corpus/dashboard/progress_reports.py:182`; the read transaction is established before yield, SQLite errors become CorpusReadError, and the caller returns unavailable.
- Named outside-diff risk: the classifier could lose independent union accounting. Checked only `src/agentdecompile_recovery/corpus/report_accounting.py:9`–`:58`; accounting still rejects nonconserved inventories and computes independent bucket/inventory unions with an explicit incomplete-byte state.
- Completed context omitted by diff hunks only: `progress_reports.py:100`–`:140` for unknown extent/provider finalization; `coverageMatrix.tsx:28`–`:44` and `workbench-app.js:3242`–`:3252` for conservation/provider gates; `workbench-app.js:3262`–`:3289` for the content-derived selection key and list lifecycle. Narrow locator searches supplied exact source line references. No complete changed-source file was reread and no parity or U4 paths were reviewed.

## Assessment

**Task quality: Approved.** The bounded implementation uses the established report pipeline, filters at SQL boundaries, binds the selected scope through the digest and both consumers, and keeps uncertainty/provider availability explicit. M1 improves future regression strength; it does not block this source slice. Approval does not close the deferred execution, activation, performance, or full-U21 acceptance predicates.
