# Compile verifier output binding: confirmed source gap

Date: 2026-10-02. Follow-up to `next-acceptance-adapter.md`. This is a bounded control-flow review only; the counterexample below was reasoned from source, not executed. No tests, imports, builds, compiler calls, services, live data inspection or source/index edits occurred.

## Finding

**Confirmed for the default kind-specific verification path:** `CompileAttempt.verify` can return `VERIFIED` for a result whose actual `outputs['obj']` bytes differ from the independently recompiled object, provided its separately stored receipt claims the recomputed masked-COFF hash. CAS integrity authenticates each object's bytes against its own address; it does not authenticate the relationship between two independently supplied objects. The enclosing framework does not supply the missing relationship check.

This is a source-level finding. No claim is made that a poisoned proposal exists in a live store or that a deployed worker currently selects this path.

## Exact control flow

| Current interface | Check performed | Missing check relevant to this finding |
|---|---|---|
| `grid_lanes/compile.py:242`, `CompileAttempt.run` | Normal producer stores actual COFF bytes and computes receipt `obj_sha256`, `obj_bytes`, `masked_coff_sha256` from them. | An independent verifier cannot assume all proposals were emitted by this honest function. |
| `agentdecompile_grid/worker/loop.py:619`, `_result_for` | For an honest worker run, checks task/basis/producer and existence of each advertised output. | Does not require the object output role or compare receipt fields to its bytes. An existing different object passes existence validation. |
| `agentdecompile_grid/worker/records.py:186`, `proposal_from_record` | Authenticates producer attribution and trusted signed envelope; parses output references. | Authenticated attribution is not receipt/output consistency. |
| `agentdecompile_grid/verify/loop.py:149-168` | Skips non-claim/revoked/already-decided proposals and enforces independent key lineage. | Does not inspect COFF bytes or receipt semantics. |
| `verify/loop.py:180`, `_method_for`; `:190`, `_make_job` | Default is `kind`; loads result object and constructs `SandboxJob(op='verify')`. | Does not compare the object's bytes with the compile receipt. |
| `agentdecompile_grid/worker/sandbox.py:381`, `run_manifest` | Verification branch parses the result and directly invokes `kind.verify(spec, result, store, scratch)`, then checks returned `Verification` type. | No generic output-schema validation or receipt/object relation is inserted. The task check in its `op='run'` branch is not a verification-branch check. |
| `grid_lanes/compile.py:296`, `CompileAttempt.verify` | Reads proposal receipt, independently calls `self.run`, reads recomputed receipt and compares the two receipts' `masked_coff_sha256` values for object outcomes. | Never reads `result.outputs['obj']`; does not derive its hash/size/masked hash. `obj_sha256_equal` is merely diagnostic and compares receipt fields, not stored object bytes. |
| `agentdecompile_grid/verify/loop.py:227-246`, `_collect` | Stamps task/result/verifier identities and emits VERIFIED when the returned outcome is VERIFIED. | No post-verifier COFF/output binding validation. |
| `agentdecompile_grid/objects/local.py:159`, `get`; `grid_lanes/_common.py:247`, `get_json` | Reads CAS bytes with integrity checking and parses receipt JSON. | Verifying the receipt object's digest says nothing about the separate COFF output object. The lane never reads that COFF output in verification. |

`agentdecompile_grid/tasks/results.py:116`, `result_from_record`, is also only envelope/type/reference parsing; it supplies no output/receipt semantic binding. The worker verification path uses the simpler `worker.records.task_result_from_record` decoder.

There is a separate optional generic `verify.methods.Recompute` implementation which compares output refs. It would reject a changed output when configured, but it is **not called in addition to** `CompileAttempt.verify` and is not the default kind path. Replacing the lane verifier with raw output equality is not the narrow fix: valid COFF timestamps intentionally differ while masked identity stays equal.

## Concrete nonexecuted counterexample

1. Start with a valid spec and known honest receipt for compiled object A, whose masked digest is H.
2. Store another valid COFF object B differing in non-timestamp bytes under B's own correct CAS digest. Construct a validly addressed proposal result with the same task/basis/status and a receipt object claiming H, but `outputs['obj']` referencing B. The receipt can retain A's raw digest or can claim B's raw digest; neither raw-digest claim controls the current verdict.
3. All referenced objects exist and their CAS digests are correct. Envelope, signature/independence and existence checks can therefore pass without a hash collision or corrupt CAS object.
4. The verifier recompiles the correct TU to A-prime with masked digest H. It compares receipt H against receipt H, returns VERIFIED, and never reads B.

An omitted `obj` output can also evade the lane's current verification branch because only the receipt is required; the honest worker's generic existence check iterates advertised outputs rather than enforcing the kind's required output roles. The substituted-valid-COFF example above is sufficient to establish the issue without relying on omitted-output behavior.

## Narrow implementation ownership and fix

Own **only `src/agentdecompile_recovery/grid_lanes/compile.py`** for production changes. The associated future regression-source file can be `tests/test_grid_compile_binding.py` (new; authored separately when authorized). No generic framework, target-object producer, contribution/revalidation, dashboard, catalog, view/schema or index changes are required for this fix.

Add a small lane-local validation helper used by `CompileAttempt.verify`, retaining the existing recompilation and timestamp-masked comparison machinery:

1. Check kind/version through existing `check_kind`. Require `result.task_id == spec.task_id`, `result.basis_hash == spec.basis_hash`, and a successful claim status before attempting object acceptance. A nonclaim must not become VERIFIED by direct invocation of the lane verifier.
2. Read and validate the proposal receipt as an object of the supported compile receipt schema/kind/version. Bind its input/configuration fields (`tu_sha256`, toolchain identity, profile, optimization, flags and basis) to the selected spec's actual input/default semantics or the independently recomputed receipt. Receipt-supplied TU identity must not become an unverified source binding in the future adapter.
3. For an object outcome, require `outputs['obj']`. Read the actual bytes through the CAS interface; compute their raw SHA-256 using the existing digest/ObjectRef machinery and require equality with the output ref and receipt `obj_sha256`. Check receipt `obj_bytes` is an exact nonnegative integer equal to the actual size. Compute `masked_coff_sha256(actual_bytes)` and require equality with the proposal receipt's masked hash.
4. Reuse `masked_coff_sha256`, including its existing short-object and anonymous/import-library-header refusals. It is a limited COFF guard, not a general COFF parser; do not describe this patch as full structural validation or import the unrelated stricter source-contribution backend/parser. Independent masked equality to a real compiler output remains the producer check.
5. After normal `self.run(spec, objects, scratch)`, apply the same actual-output binding check to its object/receipt pair. Compare the two **derived** masked hashes. Permit raw digest inequality only when masked identity agrees; retain raw equality as diagnostic evidence rather than acceptance criterion. Return VERIFIED only after all receipt/spec/object checks succeed.
6. Deterministic malformed/missing-role/hash/size/configuration contradictions return a named nonaccepting verdict. Keep missing toolchain/recompute capability as existing UNVERIFIABLE behavior. Missing/unreadable/corrupt CAS evidence must never verify; distinguish unavailable read evidence from a proven binding contradiction in the reason/outcome rather than emitting fabricated zero/empty data. Do not catch broad failures and return success.

Preserve the existing diagnostic-outcome comparison semantics and fail-closed infrastructure handling. This slice does not promote diagnostics to source acceptance or attempt a separate diagnostic-text authenticity redesign. An object outcome may not fall through a generic diagnostic branch on malformed outcome values.

This closes one causal edge: the accepted compile object is the object whose bytes independently match the selected TU/toolchain compilation modulo the documented timestamp field. It supplies no target-image binding, objdiff/source acceptance, semantic identity, current policy/generation admission, whole-image rebuild or dashboard connection.

## Regression-source and acceptance contract (unrun)

- **Positive:** valid proposal and recomputation with identical actual object bytes verify; truthful receipt hashes/sizes and exact spec input fields are required.
- **Timestamp compatibility:** actual objects differing only at COFF bytes 4–7 verify after each raw digest/size is authenticated against its own receipt; raw equality is false, derived masked equality is true.
- **Substitution regression:** retain an honest masked digest in the proposal receipt but replace `outputs['obj']` with another existing, correctly addressed valid COFF object whose non-timestamp content differs. Refute even when receipt `obj_sha256` is changed to the substituted object's truthful digest. This is the critical old-pass/new-refusal case.
- **Missing and contradictory bindings:** omit `obj`; wrong raw hash; wrong byte count; claimed masked hash inconsistent with actual bytes; receipt/TU/config/basis mismatch; wrong task/basis/status; malformed/unknown receipt outcome. Each must have a named nonaccepting result.
- **CAS and COFF refusals:** absent/unreadable/corrupt object, short COFF, anonymous/import header, and malformed receipt must not become VERIFIED. No path silently substitutes recomputed bytes for missing proposal bytes.
- **Recompute boundary:** recomputation produces a valid but different derived masked hash → REFUTED; unavailable pinned toolchain → UNVERIFIABLE. A deliberately inconsistent recomputed object/receipt pair also cannot verify.
- **Existing behavior:** diagnostic comparison remains diagnostic, and timestamp-only differences remain permitted. The fix must not replace masked comparison with raw object equality or broaden accepted formats.
- **Framework seam:** a regression-source case should follow the `SandboxJob`/`run_manifest` kind verification dispatch with an in-memory CAS and controlled deterministic producer, demonstrating that the result travels through the real dispatch boundary. No compiler invocation is necessary for this regression source. Separately authorized real-toolchain acceptance must actually compile the selected TU on the producer and independent verifier and retain the exact object/receipt refs; synthetic dispatch evidence is not that proof.

Only this report was written in the follow-up. The production issue is confirmed by source control flow; all regression and real execution acceptance remains unrun.
