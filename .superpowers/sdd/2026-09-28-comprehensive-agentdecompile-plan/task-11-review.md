# Task 11.1 review

Spec compliance: **PASS for the bounded source implementation.** Code quality: **APPROVED for the bounded source implementation.** Actionable findings: **0**.

## Scope and evidence

Reviewed the Slice11.1 requirements in `task-11-brief.md` before the implementation report and the owned-path diff package. Package base: `6e4b313d740380ea4d7af7389ce5dc0b5312643a`; head: `d966fefcaeef5cc185de4ac6bdaa371a5ab28301`. The package contains `src/agentdecompile_recovery/grid_lanes/compile.py`, `tests/test_grid_compile_binding.py`, and the implementation report. Unrelated concurrent cave/MCP commits are explicitly excluded. This is a task-scoped gate, not a whole-branch review or approval of broader Task11/R21–R22 delivery.

Read the supplied diff as the review evidence; the first combined tool response truncated its middle, so retrieved only the omitted production and test-fixture sections. No Git command or AST check was rerun. The producer `run` body was cut off by the verification hunk's leading context, so read its existing body and configuration helper at `compile.py:320–377` to judge configuration parity; this is the sole additional changed-file body inspection.

## Spec compliance

- The proposal and recomputation use the same lane-local binding helper. The helper requires matching task ID, result basis and successful claim status before reading receipt evidence (`compile.py:241`). Verification calls it before compilation and again after the independent producer returns (`compile.py:379`).
- Receipt CAS bytes are authenticated, parsed as a JSON object, and checked for the supported schema, kind, exact integer version and selected TU/toolchain/profile/optimization/flags/basis (`compile.py:220`, `compile.py:251`). Expected values use the existing producer's defaults and coercions (`compile.py:320`, `compile.py:327`, `compile.py:379`). Receipt-provided TU identity cannot replace the selected spec input reference.
- Object outcomes require the advertised object role. The helper reads its actual bytes through the store, independently authenticates its address with `ObjectRef.of_bytes`, compares its raw SHA-256 with the receipt, requires an exact nonnegative integer size, and derives the masked hash from those same bytes (`compile.py:220`, `compile.py:275`). The receipt's asserted masked hash must match that derivation. No missing proposal object is replaced with recomputed bytes.
- Acceptance compares the two derived masked identities after both pairs have passed binding. Raw equality remains evidence, rather than the acceptance criterion (`compile.py:379`). The existing timestamp mask and limited short/anonymous-object refusal function are reused; no broader parser or accepted format is introduced (`compile.py:202`, `compile.py:283`).
- Malformed outcome values cannot fall through the diagnostic branch. Diagnostics require a list of string codes and preserve the existing code-comparison semantics (`compile.py:267`, `compile.py:379`). This does not authenticate diagnostic text or establish source acceptance.
- Deterministic binding failures return named REFUTED outcomes; missing/unreadable evidence returns role-specific UNVERIFIABLE reasons, while demonstrated CAS corruption returns REFUTED. Recomputed failures are labeled separately. Independent producer `Refused` remains UNVERIFIABLE; unknown infrastructure failures are not converted to acceptance (`compile.py:211`, `compile.py:220`, `compile.py:379`).
- The authored regression source covers valid objects, timestamp-only differences, truthful and stale raw-hash substitution, receipt/configuration contradictions, missing roles, nonclaims, unavailable/corrupt CAS evidence, limited COFF refusals, malformed receipts, recomputation inconsistencies, unavailable pinned toolchain, infrastructure propagation and diagnostic scope. Its final parametrized case uses the real manifest/decoder/registered-kind verification seam (`tests/test_grid_compile_binding.py:1`; `sandbox.py:104`, `sandbox.py:381`). These are source coverage observations, not passing execution results.

## Quality and strengths

The change is confined to the affected lane, with one shared object/receipt validator used symmetrically. The evidence reader preserves a useful distinction between unavailable evidence and a proven contradiction, authenticates stores that do not check hashes themselves, and never manufactures bytes after failed reads (`compile.py:220`). Strict integer checks avoid accepting booleans, floats or numeric strings as object sizes (`compile.py:280`). The recomputation still uses the normal producer, so masked comparison remains anchored to a separately compiled result when real-toolchain acceptance is authorized (`compile.py:379`).

The regression source targets observable outcomes and evidence reads through the real verifier. Its in-memory CAS deliberately omits integrity enforcement, allowing the lane's own binding check to be exercised, while its controlled producer avoids compiler work (`tests/test_grid_compile_binding.py:1`). The report explicitly labels all execution acceptance unrun and keeps source, deployment and recovery claims separate (`task-11-report.md:3`, `task-11-report.md:70`).

## Named external-risk checks

- **CAS exception and address compatibility:** inspected `src/agentdecompile_grid/objects/base.py:64–101` and `src/agentdecompile_grid/core.py:38–61`. `ObjectMissing` is also a `KeyError`, so the unavailable-evidence catch handles the store's standard missing-object exception. `validate_ref` raises `InvalidRef`; `ObjectRef.of_bytes` and `digest` use the same SHA-256 address scheme. No defect found.
- **Spec guard/default compatibility:** inspected `src/agentdecompile_recovery/grid_lanes/_common.py:270–289` and the cut-off producer context at `compile.py:320–377`. Guard refusals and expected values match existing interfaces. The pinned-toolchain producer still raises through the existing `Refused` boundary before producing a result. No defect found.
- **Synthetic framework-seam fidelity:** inspected `src/agentdecompile_grid/worker/sandbox.py:78–109` and `:381–413`, plus the typed result envelope in `core.py:141–170`. The authored seam constructs a real `SandboxJob`, serializes its manifest, dispatches to registered kind verification, and receives verifier stamping; only store resolution and producer execution are controlled. No defect found.

## Issues

Critical: none. Important: none. Minor: none. No actionable IDs are assigned because no actionable issue was found.

## Unrun acceptance and limitations

No tests, test collection, suites, builds, compiler calls, project imports, AST reruns, source proofs, live CAS/DB inspection, catalog/runtime/service/process operations, Git mutation, commits or subagents were performed in this review. The implementer's AST/diff-check results are reported evidence, not independently repeated checks.

All synthetic regression execution and real selected-TU producer/independent-verifier compilation with retained exact object/receipt refs remain unrun. Those predicates cannot be verified from this source package. Separately authorized execution must discharge them before a runtime or delivery claim. The verdicts establish neither deployment/activation, target-image binding, objdiff/source acceptance, whole-image recovery, current-policy admission nor dashboard connection.

Historical memory was used only to corroborate the evidence-boundary convention; current requirements and conclusions come from this task package and focused source checks.

<oai-mem-citation>
<citation_entries>
MEMORY.md:270-280|note=[source and live acceptance boundaries]
</citation_entries>
<rollout_ids>
01a0e876-fcbe-7041-af54-f4c9fc9eb102
</rollout_ids>
</oai-mem-citation>
