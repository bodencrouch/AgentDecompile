# Runtime closure contract — nonce bootstrap correction review r2

Date: 2026-10-02. Status: READY_FOR_CONTROLLER_ADOPTION of this narrow correction. Important R1-1 is addressed. No new Important or Critical defect was identified in the reviewed framing, startup states, per-direction sequence, private-channel authority or READY/START task barrier.

This review read `runtime-closure-contract-fix-r1-review.md`, the exact `runtime-closure-contract-fix-r2.diff`, and relevant protocol/profile/deadline context in `next-runtime-closure-contract.md`. It did not repeat the full architecture review or establish implementation/host qualification.

## R1-1 disposition

The previous deadlock was precise: the child needed the supervisor's private launch nonce in HELLO before the protocol provided any route to learn it. The amended paragraph at `next-runtime-closure-contract.md:128` now makes the supervisor send a bounded CHALLENGE first, and makes the child receive, validate and retain that nonce before constructing HELLO. The nonce therefore has a specified transport and ordering without an environment, argv, file or additional-channel escape.

The specified normal transcript is coherent:

| Direction | Frame | Direction-local sequence | Required transition / content |
|---|---|---|---|
| Supervisor → child | CHALLENGE | 0 | Supervisor sends its retained launch nonce and exactly `{profile_id}`; child accepts once from `await_challenge`. |
| Child → supervisor | HELLO | 0 | Child echoes the challenged nonce and fixed profile ID; supervisor obtains the kernel sender identity for entrypoint binding. |
| Child → supervisor | READY | 1 | Child supplies only the four fixed identity digests after fixed imports and hard limits; supervisor performs mandatory checks while task processing remains paused. |
| Supervisor → child | START | 1 | Sent only after READY validation and immediate pidfd/identity recheck; carries the existing exact task/result/plan/key/deadline metadata. |
| Child → supervisor | COMPLETE | 2 | Existing completion metadata; collection still authenticates fixed objects only after owned-tree termination. |

The supervisor no longer waits for a HELLO that the child cannot construct. The direction-local sequences do not collide: CHALLENGE advances only the supervisor's stream, while HELLO remains the first child frame. The allowed-kind enumeration now includes CHALLENGE, removing the old prohibition on the additional bootstrap type.

## Focused regression assessment

- **Exact framing and bounds:** the new frame uses the existing exact five-field strict canonical JSON envelope and exact one-field payload. Its 2-KiB cap is within the unchanged 64-KiB datagram ceiling. Sequence remains integer/non-bool. The child explicitly refuses malformed, oversized, duplicate, unexpected or extra-field challenges, missing nonce, wrong profile, EOF and deadline exhaustion. Existing global rejection of truncation, wrong order/nonce, ancillary descriptors and oversized input remains. No fragmentation or new parser mode is introduced.
- **Authority:** the nonce originates in the retained supervisor handle (`:124`) and is not replaced from HELLO or child claims. The amendment explicitly distinguishes private inherited-channel binding from independent supervisor identity proof. The existing per-child-frame SCM_CREDENTIALS check and mandatory actual outer entrypoint/init pidfds remain (`:126,130`); disclosure of the nonce to the selected shim does not substitute for those checks. There is no bearer-token-only admission or SO_PEERCRED shortcut added.
- **Task barrier:** CHALLENGE contains only the generated nonce and fixed profile identity. It cannot deliver task/result/plan data. READY still requires fixed imports and hard limits, and no task bytes may be parsed before START (`:132`). Supervisor process/root/mount/limit checks and immediate liveness recheck still precede START (`:130`). The amendment changes bootstrap ordering only; it does not move the actual P2 call or task parsing earlier.
- **Deadline/lifecycle:** CHALLENGE is an initial operation in the existing bounded launch-barrier phase. The 20-second launch-barrier ceiling and overall reserved 600-second deadline remain (`:173–186`); no new phase, timer reset or wait-without-ceiling is introduced. The phase table's HELLO/READY summary remains compatible with the more detailed CHALLENGE-first exchange.
- **Channel surface:** the anonymous inherited socketpair and fixed child FD3 remain the sole control channel. The status/sync/filter descriptors retain their separate purposes (`:126`). Fixed argv/environment constraints (`:84–86`) remain consistent because no nonce bootstrap value is added there.

The amendment's correctness is a contract-level conclusion. A future implementation must enforce the described exact parsing, per-frame credential checks, nonblocking/deadline behavior, process binding and START barrier; this text is not evidence that any such implementation or platform capability presently exists. The prior separate current-reader/provisioning gates and unqualified producer status remain unchanged and are not re-reviewed here.

## Review boundary

Only this review file was written. Local text reads and bounded line-numbered context inspection only: no Git operations, subagents, tests/collection/builds/typechecks, project imports, database operations, cryptographic/key operations, protocol/runtime execution, live requests, process inspection, provisioning or activation. Concurrent source and contract work was preserved.
