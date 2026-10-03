# Task9.1 durable preparation authority — source handoff

Date: 2026-10-02; interrupted source-fix packet resumed 2026-10-03. **READY_TO_COMMIT for fresh independent source review**, subject to that review and the controller's final regression-source reconciliation. This is not runtime acceptance, activation, or full U9/M0 completion. The controller transferred regression authoring to a separate worker; this producer has not edited or executed tests.

## Owned production paths

- `src/agentdecompile_recovery/corpus/dashboard/preparation.py`
- `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py`
- `src/agentdecompile_recovery/corpus/dashboard/actions/catalog.py` — controller-authorized October 3 extension limited to frozen defaults and slug-query binding.
- `src/agentdecompile_recovery/corpus/dashboard/workflow.py`
- `src/agentdecompile_recovery/corpus/dashboard/react_api.py`
- `src/agentdecompile_recovery/corpus/dashboard/workbench.py`
- This report: `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-9-durable-authority-report.md`

The source baseline is the controller-provided Task2.4 commit `5578ae9c`. The later controller documentation checkpoint does not change that production baseline. Native-helper work and every other producer's edits were left alone. No new dependency or public action was added.

The resumed controller reports HEAD `5ceefab6`, including reviewed native/decomp work and documentation outside this producer's ownership. Existing dirty production work was retained and inspected in place. This resumed worker did not run Git, recreate the interrupted work, edit tests, or inspect/activate the serving process.

## Resumed source findings: DA-S1 through DA-S5

These are source dispositions awaiting the independent review and separately authored paired regression cases, not execution receipts.

| Finding | Current source disposition |
|---|---|
| DA-S1, command-lock contention | `_PreparationControlWait` is distinct from authority failure. Acquisition-only `BlockingIOError` yields `preparation_control_busy`, HTTP 409, phase `control`, wake `control_command_lock_available`, `retryable:true`, `retryAfterSeconds:1`, `noEffect:true`, `durable:false`. It does not poison the authority/witness or add continuity suspension. All catalog/direct/open/root/control and iterative consumers preserve the typed wait. The admission worker uses a bounded per-run next-probe map and retains eligible healthy waiting entries. No fresh control snapshot means no dependent handoff or command acknowledgement. Each acquisition is nonblocking and the exception unwinds the descriptor/gate; there is no synchronous contention retry or lock held while waiting for a worker. The adopted contract's short acquisition under the authority gate remains. Command acquisition permission/descriptor IO and post-write IO are latched in `_COMMAND_FAULTS`; this latch is rechecked under the acquired command lock. Invalid user parameters remain ordinary validation. Previously committed action intents remain spent; the no-effect classification describes the refused control acquisition, not a refund of earlier work. |
| DA-S2, malformed individual rows | `_load_row` rejects arrays/null/scalars before dictionary access. `_read` validates exact file/run identity, finite numeric timestamps/deadline, nullable deadline, integer priority 0–100 and string status. Overflowing numeric values become validation refusal. Queue ranking occurs inside each row's protected classification. Inventory, admission and startup recovery isolate shape/type/key/overflow errors with bounded diagnostics, no failure-report row write and continuation to independently healthy later entries. Read-only listing skips invalid rows. Invalid established accounting during lease acquisition closes the newly acquired handle and invalidates the dependent witness instead of leaking a raw type error/handle. |
| DA-S3, pre-body lost authority | `_check` poisons the exact currently registered authority before raising for owner/session/lease/slot loss, including a closed lease observed by the guard before the main execute try block. The pre-body run-ID mismatch also poisons that captured current authority. `_poison` compares registry identity before touching the healthy witness/fault registry. The jobs wrapper's exact root-finished callback retires only its token and cannot release a successor's lease; faulted authority retains its physical ownership record and cannot regain health through resume. No failure-report write occurs. |
| DA-S4, advisory-extractor cleanup | The extractor clears its guarded progress reference only after normal completion. An exception from the action or guarded checkpoint commit skips cleanup and preserves its original typed cause, phase and 503/409 projection. Healthy cleanup still uses the named guarded mutation callback; there is no raw canonical edit. |
| DA-S5, namespace latch race | `_issue_new_objective` rechecks both irreversible namespace fault and issuance-limit latches after successful OS-lock acquisition and before discovery, scan, bootstrap or append. A contender that passed the optimistic precheck cannot issue after a previous holder wrote valid-looking bytes and then failed durability. Existing healthy row operations still bypass new-issuance namespace latches. |

Regression coordination specifically requested paired permission-versus-contention, post-write uncertainty, malformed-null/list/ranking/overflow with healthy later entries, pre-body lease loss plus finished/resume, original extractor persistence failure, and event-ordered under-lock namespace fault/limit races. Regression ownership remains separate; no case was executed by this worker.

## Fresh-review corrections: DA-S6 and DA-S7

Identity compatibility refinement: submit captures the selected DB path once in its original spelling for `_context_id`, matching inventory notification IDs and existing objectives. A separate resolved DB path is used for physical execution. Relative/symlink selections do not acquire a different objective ID merely because execution is frozen; this avoids missed inventory acknowledgement and budget-identity reset.

**DA-S6: captured workspace inputs and child execution.** The fresh reviewer found that facts reuse, candidate selection and shared-folder routing still used dynamic `live_db`/`live_root` defaults after authority creation. All three `execute` queries now pass `authority.db`; `_execution_program_bindings` accepts optional keyword-only `root`/`db`, uses the selected DB for import bindings, and scans only the captured root when supplied. Its ordinary callers retain their existing defaults. Submit's context ID and inventory-generation lookup also accept/use the captured DB/root. Comparison inventory's optional dynamic query is unreachable from authority receipt paths because recording requires detached inputs and reading without inputs returns before query; the matcher-input-v2 payload remains unchanged.

The controller authorized the sixth source path, `actions/catalog.py`, solely for this captured-workspace default seam. `env_defaults(*, root=None, db=None)` can derive the workspace defaults from the captured root/DB without consulting live root/DB selection. The authority records that defaults dictionary once; explicit preexisting knowledge/MCP configuration retains its established role. `apply_defaults(..., *, defaults=None, db=None)` consumes that dictionary and binds slug-to-program lookup to the captured DB. No-argument/default callers preserve existing behavior and action schemas/field precedence are unchanged.

Every preparation child-start branch passes a private `_execution_context` to jobs. `start_job` uses its defaults and DB, checks explicit params/context and the filled DB against the frozen DB before starting, then pins the child's `JobRecord.execution_root` through `JobStore.start(..., _execution_root=...)`. A conflicting explicit DB raises before dispatch; valid relative DB paths are resolved against the captured root and canonicalized. Explicit workflow artifact paths retain their deliberate roles. The context is consumed locally and is neither serialized in params/history nor assigned as the child's root preparation lifecycle authority. Facts/probe wrappers forward the same private argument. The default ordinary-job path remains live-context based.

The source census found no dynamic root/DB selection in `workflow.continue_recovery`, which already receives explicit root/DB; its child callback now inherits the captured job context. `load_match_pairs` and target/BSim environment options are separately configured policy inputs, not live workspace selection. General configuration epochs, shared-provider routing and restore qualification remain deferred. Future paired regression sources cover A-to-B active selection changes while A queries/routes/defaults/slug lookup/child cwd stay A, B remains untouched, and an explicit conflicting DB produces zero starts.

**DA-S7: preserve the first fault across nested MCP returns.** `_PreparationAuthority.failure_decision` retains the first bounded adapter projection when the exact registered authority is poisoned. A later `_check` rethrows that original typed decision only for the same registry/lease identity and authority session in `continuity_required`. This preserves the original persistence 503 and `intent` phase when the MCP executor returns its provider refusal normally and parent bookkeeping checks authority again. Later poisoning cannot replace the first decision or cause another write. A stale callback whose registry/lease/session no longer matches still receives authority-lost 409 and cannot invalidate its successor. Provider-specific wrapper fields continue to include the bounded preparation cause.

The regression worker was notified of both API changes and the required nested-MCP/first-cause versus stale-successor paired cases. These corrections remain source work awaiting fresh review and future execution acceptance.

## Implementation boundary

`_PreparationAuthority` binds its process-local authority session, frozen root/preparation directory and DB path, exact OS lease, owner identity, generation, canonical row and last successful full snapshot/revision. Registry lookup compares object identity. `_HealthyContinuityWitness` retains the whole committed row, including both reservation ledgers, allocation histories, attempts and receipts. Healthy retirement keeps this witness while releasing only its own physical lease. No JSON, PID observation or restart creates one.

`_issue_new_objective` is the only birth-witness producer. A namespace lock precedes registry locks, authority gates, budgets, run leases and execution slots. Exclusive bootstrap is allowed only when both the birth log and preparation directory are absent. The append-only root-level birth log is never reset, compacted, truncated or deleted. The private witness is consumed by the first successful row commit. Historical namespaces, missing established rows, missing ledgers and lost authority sessions remain observation-only.

Birth validation streams complete canonical compact UTF-8 records with duplicate-key rejection, exact key sets and 32-lowercase-hex IDs. Limits are 4,194,304 bytes, 512 bytes per LF-terminated record and 10,000 issued objectives. Existing in-bound logs reach EOF before issuance decisions. Preappend checks enforce all limits without removing tombstones. Namespace limits and persistence faults do not poison an independently healthy row witness.

Confirmed namespace contention is caught only at the nonblocking lock-acquisition site. `_PreparationIssuanceWait` receives the exact 409 waiting projection, one-second retry eligibility and no-effect/durable-false fields. No issuer, ledger, row, capability, execution slot or fault latch is created in that branch. Permission/descriptor failures remain storage faults. Later append/flush/fsync `BlockingIOError` takes the storage-fault branch. The admission consumer throttles all new-issuance probes to at most one per namespace per second, using a bounded timestamp map and its existing worker. New issuance at a limit is suspended until the named capacity qualification.

`_write(row, *, authority, phase=...)` requires the canonical object and checks the full durable snapshot under the authority gate. A unique generation/write temporary file is flushed and fsynced, replaced, then followed by directory fsync. The committed revision advances only after all steps succeed. The private `uncertain` candidate is retained on failure; the healthy witness is invalidated before propagation. A refused/faulted executor never writes another ordinary terminal row. `_poison` cannot invalidate a successor authority's witness.

Every production writer now supplies explicit authority. Short preparation mutations use its gate. Workflow receives a detached snapshot and a required private mutation callback; named operations update only stage projection, family state, workflow initialization/outcome, fingerprint-bound knowledge fields, progress-file reference, target-image reference or toolchain. Program fingerprint/family and family membership/fingerprint maps are rechecked. Returned state is detached and consumed by workflow. No gate encloses a child wait, DB query, provider call or target materialization.

Comparison publication writes a unique generation/receipt-ID artifact, then publishes its reference through the guarded row commit. Failed reference publication leaves an unreferenced historical artifact. Reuse follows only a current committed reference and checks artifact identity and frozen input basis. It cannot promote an old fixed filename or newest orphan. Reused references remain historical evidence.

Inventory notifications remain independent desired state. New notifications use root-level `preparation-inventory-v1/` so a notification cannot create `preparations/` before qualified namespace bootstrap. The consumer also reads retained `preparations/inventory/` requests. Their existing replace-without-fsync and polling/wake limitations remain; this change makes no lossless-wake claim.

Commands use their own nonblocking OS lock, strict object/revision/operation/value validation, preserved fields, incremented `commandRevision` and atomic durable replacement before acknowledgement. A failed command write latches unknown command continuity in-process. Admission takes one coherent command snapshot and releases its lock before job admission. Deadline fields are merged only in the lease-owning submit path; allocation updates use a drained healthy witness and preserve budget revision/CAS semantics. A command does not clear a preparation fault.

`_ACTIVE` is an identity-token dictionary, independent of retained `_LEASES`/`_FAULTS`. A slot captures the authority and root intent, allocated job ID, worker-start-attempted, entered and finished observations. Root intent commits before `STORE.start`; the store records the allocated ID and start attempt through the private capability before calling the root thread's `start`. Pre-attempt failure retires only that slot. Post-attempt ambiguity retains it until the exact worker's completion/non-entry boundary. The live job record alone carries the capability; copies, history, public records and parameters omit it. Both execute finalization and the store's whole-worker wrapper retire by expected identity, covering pre-body and early job-store failures. Fault leases remain held. Accepted child resources and cancellation ownership remain with jobs.

The three existing child admission branches share `_handoff` after committed intent. MCP callbacks capture the same authority and exact slot. All three existing cancellation sites use the accepted dispatch/job identity under the same gate. Exceptions after possible admission poison authority without refund or replacement start.

List/status never discard capacity, create directories or heal authority. Queue, inventory and recovery loops classify each row separately; a failed entry gets a bounded diagnostic and no second write. Fault suspension is separate from namespace contention and issuance-cap suspension. Display diagnostics are capped at 100; evicting a display does not release fault ownership or restore admission. Startup recovery cannot resume historical/dead-owner rows without the retained same-session witness.

## Caller census and compatibility

| Boundary | Source behavior |
|---|---|
| Catalog preparation action | Typed wait/refusal before ordinary validation; shared 409/503 body. Healthy admission remains 202; ordinary validation remains 400. |
| Direct preparation endpoint | Same adapter/body/status and catch order; no request capability field. |
| Open/register preparation result | Enclosing success retained; shared body nested with diagnostic `httpStatus`. |
| Workflow-control job | Typed wait/refusal becomes exit code 1 and structured JSON. |
| Root preparation job | Exact private live-record authority is passed as required keyword; pre-body refusal is structured code 1. |
| Private submit/control/allocation | Typed decisions preserved. Root ambiguity never triggers a second start. |
| Queue/inventory/startup/maintenance | Per-entry isolation and bounded diagnostics; no catch-path row rewrite. Historical supersession is removed because historical rows cannot acquire authority in this slice. |
| Read-only list/status | Durable observations and optional bounded non-durable authority overlay; malformed individual rows do not abort healthy rows. |
| Ordinary non-preparation jobs | Authority defaults to `None`; serialization, admission, execution and ownership behavior retain their existing paths. The wrapper delegates to the original worker body and has no preparation callback for these jobs. |

Exact private signature changes:

- `execute(params, cancel, *, authority)`; only the live preparation backend supplies it.
- `_write(row, *, authority, phase='checkpoint')` and `_release_lease(run_id, *, expectedAuthority)`.
- `_mcp_reservation_capability(authority, *, dispatch_id=None, action_id=None)`.
- `record_comparison_receipt(..., *, authority)` and `read_comparison_receipt(..., *, authority)`; `_comparison_path` requires authority and receipt identity.
- `continue_recovery(..., *, mutate_state)` and `_extract_advisory_witnesses(..., mutate_state=...)`; the production caller census found only the preparation coordinator and the workflow's internal extractor caller.
- `_matching_input_digests(paths, progress=None, *, db=None)`. Existing default callers remain compatible; captured execution passes its frozen DB. The `matcher-input-v2` header/payload, `decomp_read_state` selector, function/edge/decomp columns, ordering and result projection remain as committed in Task2.4. This is not a claim that the entire function text is unchanged.
- `_execution_program_bindings(..., *, root=None, db=None)`, `_context_id(..., *, db=None)`, `_inventory_request(..., *, root=None)` retain noncaptured defaults.
- Catalog `env_defaults(*, root=None, db=None)` and `apply_defaults(..., *, defaults=None, db=None)` are the explicitly authorized sixth-file extension; no action schema changes.
- Jobs `start_job(..., _execution_context=None)`, both preparation start wrappers with the same private keyword, and `JobStore.start(..., _execution_root=None)` consume the captured child context without serializing it or granting root lifecycle authority to a child.

## Regression source handoff

The controller assigned the regression worker:

- New `tests/test_preparation_authority.py`.
- Narrow authority-fixture changes in `tests/test_preparation_objective_budget.py`, `tests/test_preparation_mcp_budget.py`, `tests/test_preparation_retry_policy.py`.
- Only `test_matcher_input_v2_tracks_selector_and_selected_values_and_receipt_equality` in `tests/test_corpus_decomp_schema.py`, preserving the earlier matcher projection assertions.

Fixtures must begin with an absent `ROOT/preparations`, obtain a real birth witness then actual run lease through `_issue_new_objective` / `_acquire_authority`, initialize both budgets in the canonical row, and use guarded commits. Execution fixtures bind `_ExecutionSlot` identity explicitly. Persistence injection belongs below `_write`, so the actual poison/uncertainty behavior remains under examination. Same-session resume uses the retained witness; a fault deliberately cannot regain authority through a fresh `_write`, lease handle or `_ACTIVE` set. Root callbacks and namespace/storage boundaries need distinct paired cases. No test bypass was added to production.

Every acceptance row in the adopted contract remains a future execution obligation, including current/stale owner, late callback/finalizer, stale snapshot, all intent/ack/fsync windows, control ordering, frozen workspace, preserved finite/unlimited accounting, birth/session eligibility, detached workflow/publication, every caller, root-start ambiguity, four retained fault leases plus a fifth independent slot, acquisition-only contention and exact/crossing/malformed-tail birth limits. Regression-source presence alone will not accept these cases.

## Checks performed and evidence limits

Allowed AST parsing succeeded for all five production files. A source AST census found 24 `_write` calls and no missing `authority` keyword. Literal inspection confirmed token-only `_ACTIVE`, fixed birth limits, bounded `readline`, matcher-input-v2 markers/ordering and omission of `preparation_authority` from copy/history/public serializers. Caller and mutation sites were reviewed as text. No project module was imported or executed.

The resumed AST pass again parsed all five production files and counted the same 24 preparation `_write` calls with explicit authority. `react_api.py` has an unrelated local response `_write` helper; its calls are not preparation persistence calls and do not receive authority. Text checks reconfirmed command-wait handlers at every declared adapter, per-entry catches, the namespace latch recheck, pre-body poison and extractor normal-completion cleanup guard. No test source was executed or collected.

After DA-S6/S7 and the controller's sixth-file authorization, AST parsing succeeded for all six production files. The preparation `_write` census remains 24/24 explicit authority. An AST census of captured `execute` found three direct `query_db` calls, each supplying `db`, and its routing call supplying both `root` and `db`. The private child context/defaults/DB conflict path and first-fault preservation were inspected as source text. No project code was imported or executed.

One initial read-only `git status --short` was used by the original interrupted producer for the dirty-file inventory; subsequent checks used text/AST only. No Git mutation, commit, branch, subagent creation or external publication was performed by this producer. Source writes were confined to the original five production paths, the controller-authorized sixth catalog path and this report; temporary text assembly files were kept under `/tmp`.

No tests, collection, builds, typechecks, proof scripts, DB open/query/create/migration, fingerprint/crypto/signing/key generation, compiler/checker/helper execution, capture, provisioning, service action or live recovery were performed. The parent supplied inherited healthy-8080 evidence for PID 2697197/start ticks 68973313, an NVMe serving cwd and watchedFiles=0/restarts=0. The loaded module file/revision was not verified. This checkout was not synchronized to the serving root, reloaded, restarted or activated; no systemctl use occurred.

For the October 3 resume, the parent supplied a fresh healthy-8080 observation with the same PID/start ticks, NVMe cwd, watchedFiles=0/restarts=0 and blank revision. That process observation remains inherited by this producer; loaded module/revision and activation are still unverified.

The selected source contract assumes cooperating compatible writers and qualified local lock/filesystem semantics. Windows lock/durability behavior, crash/process tests, backup/clone restoration, general historical migration, explicit continuity repair, bounded hung-I/O execution, lossless wakes, shared-provider circuits, wider resource admission and installed/live behavior remain unqualified. All U9 requirements, A01–A20, FP-01–FP-30 and M0 remain open.
