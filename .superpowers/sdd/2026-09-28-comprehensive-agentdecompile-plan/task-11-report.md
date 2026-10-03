# Task 11 report — slice11.1 compile output binding

Date: 2026-10-02. Status: DONE_WITH_CONCERNS (owned source implementation complete; all execution acceptance remains unrun by explicit mission instruction).

## Scope and authority

Read the exact task brief before editing, plus the SDD implementer prompt and skill. The explicit task/mission ban on tests, builds, project imports, compiler/Ghidra/service/catalog/process operations overrides the generic skill test-running recipe. No subagents were dispatched. Read the requested repository entry documents and the existing compile/common/core/object-store/sandbox source contracts. A quick memory pass corroborated the distinction between source, installed consumer, runtime and live acceptance; current scope and activation limitations came from the current brief.

Starting source base: `6e4b313d740380ea4d7af7389ce5dc0b5312643a`. Other workers own cave/export and MCP dispatch; their changes were preserved. This task does not close the broader U11 donated-compute task, grid-of-one cycle, other adapters, cloud transport/fleet, frontier/replay/compaction acceptance, target-image binding, source acceptance or dashboard connection.

Controller refined the shared-index protocol while this implementation was running: the controller owns all staging and commits. No `git add` or `git commit` was run by this worker. Changes are ready for the controller's owned-path commit.

## Implemented

Production ownership is exclusively `src/agentdecompile_recovery/grid_lanes/compile.py`.

Added three small lane-local implementation units: a named binding failure, CAS evidence reader, and receipt/spec/object-pair binding helper. The verifier now:

1. Uses existing `check_kind`, validates the TU content address, and derives expected TU/toolchain/profile/optimization/flags/basis values using the same coercion and defaults as `run`.
2. Requires exact task ID and result basis, and `ResultStatus.OK` before receipt/object acceptance. Refused/error/timeout/poison results cannot become verified through direct kind invocation.
3. Requires the receipt role, reads its actual CAS bytes, authenticates its address, parses a JSON object, and checks supported schema/kind/exact integer kind version. All selected input/configuration/basis fields must match the expected spec semantics.
4. Accepts only named `obj` and `diag` receipt outcomes. Diagnostic code shape must be a list of strings; the existing diagnostic-code comparison remains the diagnostic acceptance method. It does not authenticate diagnostic text or promote it to recovered source.
5. For `obj`, requires the actual object role and reads its bytes. The read authenticates the address even for a store that does not enforce digest integrity itself. It requires receipt raw SHA-256 equality and an exact nonnegative integer byte count (bool, float and string counts are refused).
6. Derives the masked hash from the actual proposed object and requires equality with that object's receipt claim. It reuses the original limited `masked_coff_sha256` short-object/anonymous-header guard unchanged.
7. Calls the normal independent `self.run`; existing pinned-toolchain `Refused` behavior remains UNVERIFIABLE and `Infra` is not swallowed. Applies all result/receipt/object checks again to recomputation.
8. Compares the two derived masked hashes. Raw hashes may differ when each matches its own receipt and the derived masked identities agree; raw equality is retained as diagnostic evidence.

Deterministic contradictions have specific REFUTED reasons: `task-id-mismatch`, `result-basis-mismatch`, `result-not-claim`, `receipt-missing`, `receipt-ref-invalid`, `receipt-cas-integrity`, `receipt-malformed`, schema/kind/version mismatch, `receipt-<field>-mismatch`, `receipt-outcome-invalid`, `receipt-diagnostic-codes-malformed`, `obj-missing`, `obj-ref-invalid`, `obj-cas-integrity`, `obj-sha256-mismatch`, `obj-bytes-mismatch`, `obj-masked-coff-mismatch`, and existing COFF refusal reasons. Missing/unreadable evidence uses role-specific `*-unavailable` with UNVERIFIABLE, distinguishing absent read evidence from demonstrated contradiction/corruption. Recomputed contradictions/unavailability carry a `recomputed-` reason prefix. Unknown adapter/programming errors propagate fail-closed rather than fabricate evidence or return acceptance.

## Regression sources authored, not executed

New owned file: `tests/test_grid_compile_binding.py` (20 test functions, multiple parametrized cases). Its store is an in-memory CAS with explicit failure injection; no filesystem store or real compiler is used. All object fixtures are synthetic ordinary COFF headers/sections. Controlled producer results permit exercising the real verifier while isolating compiler execution.

The authored cases cover:

- Identical actual object acceptance and actual object reads for both proposal and recomputation.
- Existing default/falsey configuration semantics and explicit profile/optimization/flag coercion.
- Timestamp-only differences with unequal authenticated raw hashes and equal derived masked hashes.
- Correctly addressed substituted object with honest masked claim, both with stale raw claim and with truthful substituted raw claim. The hypothetical recomputation is explicitly the honest object, and refusal asserts it is not called for the contradictory proposal.
- Receipt schema/kind/version/TU/toolchain/profile/optimization/flags/basis/raw hash/size/masked hash/outcome contradictions.
- Missing required output roles and all existing nonclaim result statuses.
- Kind/version/basis guards before evidence reads.
- Missing/unreadable/corrupt/integrity-error/invalid-address CAS evidence for receipt and object roles.
- Short-object and anonymous/import-header refusal; malformed JSON/UTF-8/nonobject receipts.
- Truthful different independent object producing `masked-coff-differs`.
- Inconsistent independently recomputed object/receipt pair, plus missing recomputed roles, wrong config/task/status, unknown outcome and unavailable object.
- Existing UNVERIFIABLE missing pinned-toolchain boundary and propagated `Infra` failure.
- Equal/unequal diagnostic-code comparison, malformed code values, and object/diagnostic outcome mismatch.
- Actual `SandboxJob.manifest` → `sandbox.run_manifest` → registered `CompileAttempt.verify` kind dispatch, for positive and poisoned proposals. Only store resolution and deterministic producer are controlled; verification logic, manifest/result decoding, registry dispatch and verifier stamping remain real source interfaces.

No RED/GREEN or passing-test claim is made. TDD execution was forbidden. These cases remain unexecuted regression sources. Even future successful synthetic dispatch execution would not establish real producer/verifier toolchain acceptance.

## Source-only checks and results

Ran stdlib-only AST parsing of both owned Python files with `python - <<'PY'`, importing only `ast`, `hashlib`, and `pathlib`, reading source bytes and calling `ast.parse`. Both parsed successfully. No project module or test module was imported, collected, compiled or executed. The same source inspection counted 20 authored test functions.

Ran `git diff --check -- src/agentdecompile_recovery/grid_lanes/compile.py tests/test_grid_compile_binding.py`: exit 0, no output. The new test file was also AST-read directly because untracked files are not represented in the ordinary tracked diff. Read the full production diff and test source for self-review. Compared production changes against the stated base with `git diff 6e4b313d740380ea4d7af7389ce5dc0b5312643a --stat -- src/agentdecompile_recovery/grid_lanes/compile.py`: 109 insertions and 8 deletions.

Pre-controller-commit working source SHA-256 values:

| Owned source | SHA-256 |
|---|---|
| `src/agentdecompile_recovery/grid_lanes/compile.py` | `a6f2188a167c277452b21665d093f57ceaf52f4cdb684f3d9361eef9e1fb456d` |
| `tests/test_grid_compile_binding.py` | `865d7a4577410a4718646e579aa88b6395ade5a00af0229d3e80661edb8e67cc` |

## Self-review

Traced the proposal path before recomputation, then all recomputed-helper failure exits, outcome equality branches, diagnostic handling and returned evidence. Confirmed both object masked identities are derived after independent role/address/receipt checks; no missing proposal object is replaced by recomputed bytes. Confirmed timestamp masking itself is unchanged and raw equality does not control acceptance. Added valid TU-reference checking after noticing `.hex` alone could throw an unnamed error for malformed spec addresses. Tightened regression producer setup so the substitution case explicitly retains an honest hypothetical independent result. Added separate recomputation-side regression sources to guard against applying binding checks only to proposals.

Read the sandbox verification dispatch source to ensure the framework-seam case follows its actual manifest and registered-kind interfaces. Checked the synthetic fixture arithmetic by source: ordinary header20 + one section40 + payload3 = 63 bytes, timestamp is bytes4–7, and section raw pointer60 is consistent. These are source checks, not executed parser/test evidence.

## Remaining concerns and acceptance boundary

All synthetic regression execution, real selected-TU producer/independent-verifier compilation and object/receipt-ref retention remain unrun. No live CAS objects or contaminated proposals were inspected. No imports, builds, toolchain processes, Ghidra, live/catalog/service/process/systemctl actions were performed. No server activation or restart occurred. The controller's prior process/source observations are orientation only; this worktree's edits are not activation of the serving modules.

The existing COFF guard remains limited and deliberately does not become a general COFF parser. Diagnostic-text authenticity redesign is excluded. The generic verifier, source contribution/admission, target-image binding and dashboard consumer were not changed. These source changes require controller review and separately authorized execution acceptance before delivery claims can expand.
