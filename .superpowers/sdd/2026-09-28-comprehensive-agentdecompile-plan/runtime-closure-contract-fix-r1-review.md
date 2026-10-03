# P3.2 runtime closure contract — correction review r1

Date: 2026-10-02. Source-only combined contract, architecture and feasibility review of `runtime-closure-contract-r0.md`, `runtime-closure-contract-review.md`, `next-runtime-closure-contract.md` (226 lines), and `runtime-closure-contract-fix-r1.diff`, against the relevant existing grid/recovery source. Only this review file was written.

**Adoption verdict: require one narrow Important protocol correction before adopting the revised contract as implementation-ready.** The original three findings are substantively addressed. The correction introduces an incomplete nonce bootstrap that prevents the specified startup exchange from working as written. No Critical finding was identified. The confinement architecture, separate admission reader and qualified-only delayed seal remain reasonable within the expressly trusted supervisor/owner/verifier boundary.

## Important R1-1 — deliver the supervisor nonce before requiring it in HELLO

**Confidence: 100.** This is a concrete protocol dependency, not a speculative platform concern.

Contract references: `next-runtime-closure-contract.md:40,84-86,124-132`.

The supervisor creates a fresh 256-bit nonce in its private launch handle at line 124. Line 128 then requires **every** frame to contain that exact token, with supervisor state `await_hello -> check_ready -> send_start` and child state `hello -> ready -> await_start`. The child's first HELLO therefore needs the nonce before the supervisor sends anything. The same paragraph forbids any additional message type and rejects a differing nonce.

There is no specified route by which the child learns that value:

- The child argv is fixed at line 84 and the environment is exhaustively fixed at line 86; neither carries a per-job nonce.
- The seed/plan's allowed fields at line 40 do not contain it, and no independently readable bootstrap record is defined.
- FD 3 is the private message channel; FDs 4–6 have explicitly different launcher/filter purposes at line 126. No initial nonce delivery on FD 3 is defined.
- START follows HELLO/READY, so even delivering the nonce in START would be too late.

The existing backend supplies no implicit bootstrap for the proposed fixed shim: `src/agentdecompile_grid/worker/sandbox.py:104-109` defines the ordinary manifest fields, while `:381-413,416-430` consumes a manifest path and runs its generic dispatch. The revised contract deliberately avoids that manifest/import/store path and fixes a different entrypoint. Reusing the old backend cannot fill this protocol gap.

**Failure path:** a compliant fixed shim cannot construct its first authenticated HELLO; waiting for a nonce also cannot progress because the supervisor waits for HELLO. Fabricating or omitting the token correctly produces `ipc_binding_invalid` or a launch-barrier timeout. An implementer would have to invent an additional channel or alter the stated frame/state contract.

**Required correction:** choose and document one bootstrap. The smallest change is a supervisor-first, bounded `CHALLENGE` frame on the already inherited FD 3, containing only the generated nonce and fixed profile identity, before the child sends HELLO. Specify the exact payload, size bound, per-direction sequence numbers, updated states and rejection behavior; keep all task/result/plan bytes behind the validated READY/START barrier. HELLO and every subsequent child frame must echo the challenged nonce and retain the existing per-message credential/PID checks. Remove the contradictory “no additional message type” wording by enumerating this one additional type. An explicitly specified protected bootstrap record would also work, but is unnecessary for this socket protocol.

This is a local protocol correction; it does not require a new sandbox, privilege broker, admission system or change to the P2 predicate.

## Disposition of the original three findings

| Original finding | Disposition | Source-grounded assessment |
|---|---|---|
| **Important 1 — name and specify the new current-admission consumer** | **Addressed in the contract** | Lines 136–159 define V0/C/E, exact caps and tuple joins, an acyclic graph, and the separate `current-qualified-native-region-v1` / `agentdecompile.current-native-region-admission.v1` / `authenticate_native_region_execution` consumer. Lines 155, 198 and 226 explicitly withhold current P2 admission until its separate reader/configuration exist. This preserves the real P3.1 restrictions in `corpus/current_admission.py:260-264,323-327,412-425,434-451` instead of silently relaxing them. Producer qualification stays false and no RESULT extension is admitted. |
| **Important 2 — bind current policy at the actual deferred signing boundary** | **Addressed in the contract** | Lines 163–169 place the fixed guard at `transport.local.ChainAppender.build` before each qualified signature, require a fresh coherent authority read and exact object authentication on retries, and define boot-local tokens plus unsigned-restart quarantine. That is the actual seam: `transport/local.py:154-175` builds/signs on every CAS attempt; `worker/outbox.py:131-140,213-245` queues unsigned bodies and calls the writer later. The contract explicitly replaces `same_store`/`_confirmed` shortcuts for this branch, restricts the writer/transport, and distinguishes seal-time authority from later reader revocation. |
| **Important 3 — close the concrete admission/dispatch/staging boundary before reusing the loop** | **Original dispatch/staging/lifecycle correction addressed; new startup protocol defect above remains** | Lines 94–120 restrict v1 to actual P2 `verify` dispatch, intercept before ordinary `_make_job`, specify recovery-owned roles/caps including all three proposed P2 outputs, and normalize the actual empty verifier key exactly once. Lines 173–192 specify pre-read admission time, finite phase budgets, process-owned I/O, tree termination/export before `exited`, and retained quarantine for incomplete I/O. These resolve the original source mismatches at `verify/loop.py:190-201,221-227`, `worker/loop.py:343-356,441-459`, and `grid_lanes/parity_region.py:541-578`. The additional concrete IPC specification needs R1-1 before this part is fully implementation-ready. |

No original finding is ignored or replaced with a false implementation/qualification claim. “Addressed” here means the proposed contract now supplies the requested decision; none of these paths has been implemented or exercised by this review.

## Focused checks of the correction

**Evidence graph and field compatibility.** The actual `verification_to_record` fields match V0 (`worker/records.py:153-158`), and the actual `verification_body` supports E through its existing `evidence`/`evidence_ref` alternatives (`:121-131`). C references V0 and authenticated object refs, while E references C; neither includes a later digest. Its phase durations stop before collection/sealing. The original child lane's `not_evaluated` fields remain intact. Actual P2 may verify an accurately proposed mismatch as `VERIFIED`; the revision correctly keeps `region_differs`/`mismatched` distinct from `region_equal` and does not equate all VERIFIED records with equal regions (`grid_lanes/parity_region.py:561-578`).

**Staging and nested evidence.** P2 really consumes six inputs, the selected proposal's three outputs, target/P1 envelopes, target snapshot/image and prerequisite outputs (`grid_lanes/parity_region.py:395-408,449-473,551-553`). Target selection/implementation are inline params, not external CAS refs (`grid_lanes/target.py:55-56,439-443`). The revised role table captures these distinctions. P2 retains prerequisite summaries and P1 proposed/recomputed receipt/raw refs (`parity_region.py:369-381,512-513`); the contract does not invent an independently exported target verification object. Source/helper reconciliation is retained rather than bypassed (`grid_lanes/target.py:366-425`).

**Dispatch and lifecycle.** The distinct immutable seed is necessary because ordinary `SandboxJob` rejects verify jobs without a materialized result (`worker/sandbox.py:94-100`). The revision names a qualified branch before that construction instead of assuming existing launch alone supplies the boundary. Mapping successful `exited` only after owned-tree termination and export matches `_reap`'s immediate collection/cleanup sequence. `kill-failed` retains allocation ownership and prevents another writer; it is not interpreted as completed cleanup. The listed phase ceilings total 600 seconds and retain an absolute token expiry across delayed seal retries. Implementations must preserve those explicit qualified-branch rules; the existing generic scheduler/outbox are not already proof of them.

**Signing and recovery.** The revision correctly selects `ChainAppender`, rather than assuming the default `log.outbox` appender has the guard. Guard/token absence must refuse qualified E, including the referenced evidence form; existing unqualified writes retain their behavior. Successful append consumes the token, uncertain append requires bounded reconciliation, and restart cannot reconstruct authority from pending JSON. The current-reader slice is explicitly deferred, so its absence is not reported again as an implementation omission in this narrower first slice.

**Protocol and confinement.** Fixed credentials, mandatory namespace-init/entrypoint pidfds, separate status/sync/filter channels, completion-by-ref after tree termination and refusal on unavailable owner-readable process evidence are coherent decisions under the declared platform premises. The concrete blocker found is the missing initial nonce delivery. This review does not infer host support from those decisions or from existing source.

## Review boundary

Read-only local text/source reasoning only, plus writing this report. No tests or test collection, builds, typechecks, project imports, database operations, cryptographic/key execution, runtime/checker/provisioning execution, live requests, process operations, Git operations, source changes or subagents. No external mechanism pages were fetched during this re-review. Existing authority and mechanism claims were treated as the contract's stated premises, not as newly qualified host behavior. Concurrent work was preserved.

After the nonce bootstrap is specified, the reviewed correction is suitable for controller adoption of the narrow P2 verify → collection → guarded local signature implementation slice. That adoption must retain the explicit separate current-reader/provisioning gate and all existing source/compile/corpus/whole-image/runtime acceptance boundaries.
