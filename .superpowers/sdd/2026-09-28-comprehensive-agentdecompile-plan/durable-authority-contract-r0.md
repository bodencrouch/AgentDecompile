# U9 next contract: preparation authority must survive through commit and handoff

Status: **READY_FOR_CONTRACT_REVIEW**. Report-only source reconciliation, 2026-10-02. No implementation or acceptance execution is claimed.

## Architecture overview and scope

Implement one missing predicate in the existing preparation coordinator:

> A preparation may replace its durable row or hand off a new child action only through its current, process-local capability holding that run's actual OS lease, against the last successfully committed row revision. A storage failure or lost capability closes that authority until continuity is explicitly reconciled. A stale callback cannot write, dispatch, reset spending, or release a successor's lease.

This is a preparation-row and preparation-to-job admission fence. It is not a new task engine, general corpus acceptance authority, distributed lock service, provider incident ledger, or complete U9 implementation. In particular, preventing a *new handoff* is different from stopping an already accepted child or proving an external resource is free.

The relevant architecture is preparation → action catalog/job store → provider/compiler adapters, with pure admission/retry accounting embedded in preparation JSON. Preserve those boundaries and public action names. Operations continue through the existing 8080 catalog when separately authorized; this report made no live calls. The future implementation must corroborate serving-source ownership before Python edits under AGENTS.md.

## Authority and requirement sources

- Read `AGENTS.md`, `README.md`, `USAGE.md`, `STRATEGY.md`, `docs/plans/README.md`, and `docs/RUNTIME_REUSE.md`. `STRATEGY.md:90–105` separates resource ownership, publication, continuation and qualification. Runtime reuse remains a separate evidence axis.
- Read the full `unit-9-requirements.md` and named `unit-9-authority-extract.md` in this directory. U9 owns R16–R20/R31 and all A01–A20, FP-01–FP-30, M0; none is discharged by this report. Historical statuses and embedded receipts are not fresh results.
- Current master requirement definitions: `docs/plans/2026-09-28-comprehensive-agentdecompile-plan.md:61–65` (R16–R20), `:81` (R31), and its C01–C24 reconciliation table. Do not confuse these IDs with the separately namespaced frontend R16–R20/R31.
- Exact source clauses: `docs/plans/2026-09-22-task-acceptance-and-continuation-design.md:342–370` (attempt persistence/restart); `:376–409` (admission, MCP lineage and uncertainty); `:443–470` (publication versus access ownership). Current acceptance rows A07/A08/A14 are at `:674–675,:681`; extract `source_line` values are historical locators, not current line numbers.
- `docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md:45–71` requires one retry owner, conservative ambiguous spending and honest detector uncertainty; `:83–105` preserves shared-provider incidents and durable wakes as distinct obligations; `:179–192` governs store loss/continuity and rejects timeout-based failover. Current FP-17/18/22/25 rows are `:259–260,:264,:267`.
- M0 acceptance remains real coordinator and isolated child-process qualification in `docs/plans/2026-09-22-autonomous-capability-product-roadmap.md:143`.
- Searched `docs/solutions/README.md` and the documented-solution tree for preparation/ownership/admission; no matching solution was found. No additional implementation authority was inferred.

## Retained source capabilities

Paths below are repository-relative and line numbers describe the inspected source, not a pinned release.

| Retained mechanism | Exact source | Reuse and limit |
|---|---|---|
| OS lease and conservative process identity | `src/agentdecompile_recovery/corpus/dashboard/preparation.py:190–205,264–291,883–919` | Actual nonblocking flock/Windows lock; host/PID/start checks. PID liveness and serialized ownership metadata do not mint a capability or clear external access. |
| Durable replacement | `preparation.py:216–232` in the directory above | File flush/fsync, atomic replacement, POSIX directory fsync already exist. Preserve them. Atomic replacement alone does not fence stale writers. Windows crash durability is not established by source. |
| Objective accounting | `admission_budget.py:8–84` | Stable objective identity, validated counters, unique dispatch reservations, idempotent acknowledgement and allocation revision/history. Unknown intents remain spent; unlimited still counts. Scope is action admissions, not token/CPU/money usage. |
| Action reserve-before-handoff | `preparation.py:1174–1229` | Intent and attempt spending are written before job start; acknowledgement follows returned job identity. Preserve the crash gap as unknown, not a free retry. |
| Private MCP dispatch authority | `preparation.py:235–255`; `mcp_budget.py:19–45,94–103`; `actions/jobs.py:1693–1726` | Capability checks exact lease object, open handle and `_ACTIVE`; every nested call reserves before dispatch. Executor preserves unresolved-effect evidence. This is stronger than ordinary preparation writes today, but per-executor containment is not a shared provider circuit. |
| Retry and receipt reuse | `retry_policy.py:13–61`; `preparation.py:1090–1167,1328–1353,2131–2152` | Three-attempt policy; unknown/active actions do not replay; terminal jobs may reconcile; changed matching basis preserves legacy attempts. Scientific acceptance is separate from successful job reuse. |
| Explicit allocation change | `preparation.py:2342–2371`; `admission_budget.py:61–84`; `mcp_budget.py:105–122` | Drain active coordinator, acquire OS lease, compare expected allocation revision, preserve spent reservations. This policy should remain. |
| Queued/inventory admission and recovery | `preparation.py:488–581,921–1008,2421–2436` | Durable inventory request, in-memory wake plus polling, persisted row history, confirmed-dead-owner resume. No durable event cursor/outbox or backup continuity claim follows. |
| Child ownership remains with jobs | `actions/jobs.py:1000–1062,1425–1470,2203–2297` | Job admission/persistence and held/quarantined disposition are separate from preparation row lease. The reported external-owner error wording does not authorize adoption. |

## Concrete missing predicate and failure traces

1. `_write(row)` accepts any supplied snapshot and resolves the *current* workspace dynamically. It neither requires the lease nor compares row revision/owner generation. An old callback can overwrite newer spending and checkpoints after another generation resumes. Several calls also occur outside `_LOCK` (`stopped`, end-of-workflow); an RLock is process-local in any case.
2. The MCP capability checks authority, but `execute.action` reserves and calls `jobs.start_job` for non-MCP actions without the corresponding current-lease check. It leaves `_LOCK` between durable intent and handoff. A stale action can therefore create a new job even though the nested MCP guard would refuse a remote call.
3. `control` reads a snapshot and, at `preparation.py:2414–2417`, writes a revised deadline before `submit` acquires the OS lease. A concurrent allocation revision/resume can be overwritten. Queued admission writes at `:564,:568,:575` and legacy supersession at `:879` also bypass per-row lease ownership.
4. `_release_lease(run_id)` pops by ID, not expected identity. `execute`'s finalizer writes then discards `_ACTIVE` and releases by ID (`:1962–1975`). A stale finalizer can disturb successor state; conversely a failed final `_write` skips cleanup entirely. The parallel matching pool can use `shutdown(wait=False)` on interruption (`:1894–1910`), so late work is a concrete callback boundary worth qualifying.
5. Failed MCP `_write` refuses that call but does not poison the capability. A later successful write can resume using the same mutable snapshot without an explicit continuity decision. General writes have no stable authority-loss outcome; broad error handling attempts another final write.

These are source-derived failure mechanisms, not observed live incidents. The selected slice closes these preparation-local paths; it does not infer missing architecture solely from naming.

## First implementation contract

### File ownership and dependency direction

One implementer owns `src/agentdecompile_recovery/corpus/dashboard/preparation.py`, plus the narrow private handoff seam in `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py` that hands the root capability into `execute` without lookup-by-ID. No frontend, schema DB, matcher, compiler, provider protocol or generic retry-policy rewrite. Add a focused future acceptance file `tests/test_preparation_authority.py`; adjust the existing preparation accounting fixtures to acquire authority honestly. Existing pure `admission_budget.py`, `mcp_budget.py` and `retry_policy.py` semantics are retained.

Keep authority helpers private to preparation. Pass a private callable/object to jobs as already done for `_mcp_reserve`; jobs must not import preparation authority classes into module-global initialization. Do not serialize capabilities in job params, argv, environment or receipts. This maintains the existing dependency direction and avoids a new circular dependency or public SDK contract.

### Capability and row identity

Use a private `_PreparationAuthority` created only after actual OS lock acquisition. It binds run ID, frozen preparation directory/workspace identity, exact lease handle, owner host/PID/start identity, unique generation, last committed `rowRevision`, canonical in-memory row, a per-authority reentrant gate, and state `current`, `continuity_required`, or `revoked`. The durable row gains a small `authority` metadata record `{schema:1,generation,rowRevision}`; these are continuity comparisons, not credentials. Do not equate generation, objective ID, action ID, allocation revision or process identity.

A capability registry must compare object identity, not merely equal fields. Execute receives the exact capability for its root job; it cannot look up a replacement by run ID. Matching callbacks and MCP reservations capture that same object. A capability cannot be constructed by reading JSON. New generation is minted only while owning the physical lock; budgets/retry histories are copied forward unchanged after validation.

Freeze the source/destination paths for this capability. A workspace switch cannot redirect writes into a different preparation tree, even if the run ID happens to match. No lock-file deletion/recreation while capabilities exist. The selected contract assumes cooperating current-version writers and local filesystem lock semantics; uncontrolled file replacement, mixed old writers and unmanaged backup restore require the later compatibility/activation gate, not a claimed fence from JSON alone.

### Private APIs and mutation linearization

- `_write(row, *, authority)` becomes a mandatory guarded commit; no optional bypass for production callers. An internal raw serializer may exist solely underneath it. It checks current registry/lease identity and open state, frozen row identity, supported metadata, exact on-disk generation/revision, and canonical row identity under the capability gate. Create is explicit and allowed only for a corroborated new objective; a missing expected row refuses.
- Serialize the next row snapshot without first advancing committed state. Use a generation/unique-write-specific temporary filename, preserve flush/fsync → replace → directory-fsync ordering. Advance the capability's committed revision only after the complete durable write succeeds. Every write exception marks `continuity_required` before returning, including a directory-fsync failure after replacement. Do not catch that failure and write an ordinary terminal status through another path.
- All mutations of the canonical shared row, including stage updates, matching progress, reserve/acknowledge and finalization, occur under the same capability gate. Detached row snapshots are observations only. There is one shared row per executing authority, avoiding sibling callbacks with independent stale revisions.
- `_handoff(authority, dispatchId, startCallable)` checks the same predicate after the intent commit and immediately before invoking the existing jobs admission call. Capability revocation/release and handoff serialize through its gate. Do not hold the process-global preparation `_LOCK` across job-store locks, provider calls or job waits. Gate scope ends when the admission call returns/raises, not when the child finishes.
- An accepted child retains its existing job-store ownership/lifecycle. Loss of the preparation capability refuses *new* root handoffs and nested MCP dispatch. It does not kill accepted children or claim that their effects stopped. The root preparation job is handed its exact capability through private in-process state before its thread starts, never inferred from JSON.
- Root handoff uses a private optional `preparation_authority` field on the job record/start seam, excluded from serialization and populated only by `submit`; the preparation backend passes it as a required keyword to `execute`. Direct `execute` without the capability refuses. Existing non-preparation jobs do not require it. A late preparation callback also cannot issue a new `jobs.cancel_job` request after authority loss: guard those calls with current capability and the original accepted child identity. Previously issued cancellation and accepted-child lifecycle stay with the job owner.
- `_release_lease(runId, *, expectedAuthority)` changes the registry, `_ACTIVE` and handle only when the exact expected object is current. A stale finalizer is an idempotent no-op for successor ownership. Revoke current authority before releasing its own handle; never release another object by ID. Failure handling cannot mask the original refusal with a second write failure.
- Fix every production `_write` caller, including queued-state changes and legacy supersession. Maintenance writes acquire a short-lived physical lease for the exact row, re-read it and commit through their own non-dispatch capability. No maintenance authority grants execution. Legacy writes require the legacy row's own lease; on contention leave it untouched and report/defer reconciliation. Do not hold a partial collection of project/resource locks while waiting.

Lock discipline must be explicit in implementation: acquire the per-authority gate before short registry `_LOCK` sections; never acquire a gate while already holding `_LOCK`. Refactor the current outer `_LOCK` callers accordingly. Do not invoke jobs admission while holding `_LOCK`; job-store code must not call back into preparation while holding its store lock. Review this ordering as part of the later source review.

### Controls and allocation continuity

Move `control`'s pre-submit row update into the lease-owning submit path: read the latest command and row *after* acquiring authority, merge only the permitted deadline fields, then commit. Never merge an entire caller-held row. Preserve `_revise_admission_budget`'s drained-owner requirement and expected allocation revision.

Commands remain separate desired-state records so pause does not require stealing an executing lease. Serialize cross-process command read/modify/write using a dedicated short-lived nonblocking command-file OS lock and a monotonically increasing command revision; preserve untouched fields, fsync before `controlAcknowledged:true`, and distinguish missing-new command from unreadable/corrupt command. For admission use a strict control read: unknown control state blocks handoff; public cached observation may report unavailable with its as-of revision. An admission holds the authority gate while briefly acquiring the command lock for its decision snapshot, then releases that lock before calling jobs. Control writers release the command lock before requesting any authority operation. Never wait for a worker while holding the command lock; contention is a retryable control-observation prerequisite, not an inferred resume.

The handoff gate takes one coherent latest control snapshot. A command committed before that decision is honored. A command racing after that decision governs the next admission; an already accepted child follows the existing drain semantics. `controlAcknowledged` means the command was durably recorded, not that a child stopped. Pause/resume/budget/priority never clear an authority fault or refund reservations. A failed command write cannot report acknowledgement. Stronger cross-host command ordering and durable wake delivery are followups, not achieved here.

### Error and storage-failure semantics

Use a private `_PreparationAuthorityRefused` carrying a bounded decision dictionary. Preparation failures use `nextAction` values `preparation_authority_lost`, `preparation_continuity_required`, and `preparation_persistence_failed`; all carry `wakeCondition: explicit_preparation_continuity_reconciliation`, run ID, generation, last committed revision and `phase` (`intent`, `handoff`, `acknowledgement`, `checkpoint`, `control`). No secrets, arbitrary params or whole ledger in the public refusal. MCP wrappers preserve their existing `provider_authority_lost` / `provider_budget_persistence_failed` values for compatibility and attach the preparation cause; do not turn them into transient failures.

At the existing jobs preparation route, catch this specific refusal before broad validation/storage catches and return `{ok:false,error,...decision}`: 409 for lost/conflicting authority or required continuity, 503 for unavailable persistence. Existing validation stays 400 and successful admission stays 202. An already-started preparation executor returns exit code 1 plus the same structured JSON; it must not report an ordinary terminal row as durably committed. No new catalog action or request field grants authority.

| Failure boundary | Required behavior |
|---|---|
| No durable intent, before handoff | Zero child starts. Retain candidate accounting as uncertain in memory; do not erase any visible durable reservation or silently refund. Close this capability. |
| Intent committed, authority lost before handoff | Zero new child starts. Intent remains spent. A separately established no-dispatch observation can explain the outcome, but no automatic refund/replay is introduced. |
| Admission throws after it may have accepted work | Treat outcome as unknown; preserve dispatch ID, charged intent and any known child ID. Do not interpret exception as proof no child exists. |
| Child accepted, acknowledgement write fails | Child remains owned by jobs. Durable intent remains charged; record bounded local diagnostic if possible without asserting durability. Stop new handoffs. Reconcile the same dispatch/job identity; never create a second child to recover an acknowledgement. |
| Acknowledgement committed, later checkpoint/finalizer fails | Preserve last durable acknowledgement, attempts and completed receipts. Close authority. No fabricated completed row, no automatic release of child resources. |
| Replace succeeded, directory fsync failed | Commit outcome is uncertain, not rollback. Do not overwrite with a stale row or advance the successful revision; require exact continuity reconciliation of old versus proposed revision. |
| Failure persists or expected row disappears | Observation-only status with `durable:false` and last-known/as-of revision where available. No tight retry writes, no new empty allocation, no automatic restart. |

A faulted capability retains its physical lock until its own safe ownership disposition is decided; retain it in a fault registry rather than losing the only reference in a failing finalizer. Do not hold `_LOCK` or the gate while idle. This quarantines only the affected preparation; separate healthy objectives may proceed if their providers/resources are independently safe. The sole shared store failing blocks all work that requires it; independent cached observation is not admission.

For this first slice the wake is a **named unmet prerequisite**, not a new force-clear control. No automatic capability reactivation is permitted. A subsequent authorized reconciliation must compare last successful and uncertain candidate revisions, validate both accounting ledgers and preserved attempts, reconcile every possibly handed-off child, establish actual resource clearance where required, and acquire a fresh capability. If any comparison is missing, remain read-only. Same-process recovery, process restart and backup restore require separate evidence; a successful read/fsync alone is insufficient. Existing confirmed-dead-owner resume remains usable only for rows without continuity ambiguity; unresolved action receipts still follow the existing unknown-outcome refusal.

### Migration and compatibility

Legacy rows lacking authority metadata remain readable. Under an exclusive lease, a bounded migration can add metadata only after validating the existing row and ledger histories; keep `priorUsageUnknown` and existing action outcomes. Never treat missing/corrupt existing accounting as a new objective. Unsupported schemas and evidence of an interrupted/unknown owner remain blocked with the exact continuity prerequisite.

No source-only claim that an old concurrently running writer honors the new fence. Activation must exclude incompatible writers and qualify the real consumer separately. No backup rollback detection is promised from a revision stored inside that same backup. Missing established files versus genuinely first use requires independent workspace/objective continuity evidence; absent that evidence, refuse initialization rather than guess. This gap is a followup prerequisite for general restart/restore delivery, not permission to reset accounting.

## Meaningful later acceptance sources and matrix

**Not run in this task.** Existing test sources are reusable specification leads, not current evidence: `tests/test_preparation_objective_budget.py:35` covers the actual nested action path with intent/ack failure parameters; `:168,:194` cover allocation CAS and active/other-owner refusal. `tests/test_preparation_mcp_budget.py:87,:173,:286` cover persistence/lost capability, preparation→store→bridge continuity, and inactive-owner refusal. `tests/test_preparation_retry_policy.py:48,:97,:184,:214` cover uncertain accepted effects, actual execute refusal, unresolved wrappers and inherited matching attempts. Existing fixtures that call `_write` or `execute` without a real acquired private authority must be migrated, not granted a test-only production bypass.

Future receipt records exact source revision, injected boundary, observed durable generations/revisions, reservation/attempt maps, handoff count/child IDs and public error. Qualify the real coordinator call sites with inert job/provider doubles first; pure helper checks alone cannot prove caller coverage. OS lock and crash claims need separately authorized isolated child-process checks. No test/build/import/live execution is authorized by this report.

| Case | Positive | Paired negative | Unaffected control / obligation |
|---|---|---|---|
| Current owner write/handoff | Current lease commits revision n+1, reserves once, hands off once, acknowledges same child | Closed/replaced capability or forged serialized metadata writes/starts zero; successor bytes/revision unchanged | Separate valid run proceeds; A07/FP-07 local preparation part only |
| Late matching/finalizer | Current callback records its own checkpoint and releases its own lease | Old callback after new generation cannot overwrite budget, discard successor `_ACTIVE`, release successor lease or start non-MCP child | Successor remains writable; A07/A14/FP-07, not external clearance |
| Same-owner stale snapshot | Canonical row preserves sibling reservation/checkpoint | Detached old row or changed on-disk revision refuses; no last-writer-wins budget loss | Current canonical update succeeds; R19/R20 |
| Intent persistence | Committed reservation observed at start boundary before one job | Fail file flush/fsync, replacement, and directory fsync separately: zero start, authority latched; restored filesystem alone does not re-enable callback | Independent healthy store/run can admit; FP-18/FP-22 local subset |
| Ack and uncertain start | Idempotent same-dispatch/same-child acknowledgement spends once | Accepted start then thrown response or failed acknowledgement never duplicates dispatch; uncertainty survives finalizer and resume | Independent reconciled action uses its own remaining budget; FP-17/A12 |
| Control versus owner/revision | Drained allocation revision preserves all spending; deadline merges into latest row | Barrier interleave resume's old snapshot with allocation revision/new owner: old snapshot cannot overwrite it; malformed control blocks admission | Priority for a different run remains usable; A08/FP-22 local subset |
| Command merge/ack | Concurrent priority and deadline changes both survive serialized merge | Command fsync failure never reports acknowledgement; pause committed before handoff decision prevents admission | Already accepted child keeps declared drain lifecycle; FP-18, R24 compatibility |
| Workspace/generation identity | Frozen root remains stable for its run | Changed active workspace, row generation or missing expected row cannot redirect/reinitialize | Different legitimate run/root unaffected; FP-25 only local continuity comparison |
| Accounting/uncertainty regression | Finite/unlimited objective and MCP counters survive healthy resume/revision | Changed basis, wrapper, user resume, new PID or provider allocation do not erase unknown intent or old attempts | Independent objective with valid allowance proceeds; A04/A08/FP-22 |

A later controller must also inspect raw durable state after the simulated failure, not merely assert returned status. A report claiming no duplicate dispatch must show start-call count and retained dispatch IDs. No case here closes all of FP-17/18/25, A07/A14 or M0.

## Compliance, risks and staged followups

The proposal keeps accounting pure, capability enforcement in the coordinator, and execution/resource clearance in jobs/adapters. It preserves public catalog routing and measured budget dimensions. It adds no dependency on a frontend or goal engine. The bounded private jobs seam is the only potential import-cycle risk; retain callable injection rather than importing coordinator classes globally.

Material risks are a missed raw writer, changed lock order/deadlock, faulted-capability leakage, mixed-version writers, and mistaken promotion of row authority into external resource ownership. The source review must enumerate every `_write`, root `execute`, child admission, cancellation and release path. An already accepted job's cancellation remains governed by its original ownership contract; this slice grants no new cancellation permission. Synchronous filesystem operations can still hang while holding the affected authority gate: responsive bounded storage probes/execution are not solved by catching OSError.

Proposed stages preserve, rather than replace, the full obligations:

1. **Selected first slice:** current preparation capability/row fence, handoff boundary, stale cleanup protection and narrow control-writer reconciliation above. Contributes bounded local predicates to R18–R20, A07/A08/A14 and FP-07/17/18/22/25. Implementation/source review and later acceptance remain pending.
2. **Continuity repair and wake delivery:** independent objective/store incarnation, missing/corrupt row policy, compatible migration/writer activation, restore epochs, bounded storage health workers, finite offline checkpoint allowance, durable wait cursor/outbox and explicit safe reconciliation adapter. Preserve A03/A05/A06/A08/A13/A19 and FP-08/12/16–20/25. No full restart/backup or sole-store resilience claim before this stage qualifies.
3. **Shared provider/real resource admission:** consume existing jobs ownership predicates; implement the separately required shared-provider incident and single retry-owner circuit, nested resource accounting, complete input alternatives, atomic whole-resource acquisition, measured process-tree profiles, persisted age and urgent overrides. Preserve A04/A09/A10/A12/A14–A16/A18 and FP-03–07/09–14/22–23/26–27/30. Never adopt external owners or infer clearance from timeout.
4. **Acceptance and product qualification:** current-policy/independent-verifier short commit, lineage withdrawal, evidence repair, recorder/oracle correlation, deterministic arrival semantics and real consumer activation. Preserve A01/A02/A07/A11/A17/A20 and FP-01/02/07/15/19/21/24/28/29. U1 supplies exact identity/evidence predicates when consumed; unrelated unfinished U1 work is not a blanket blocker.
5. **Full U9/M0 review:** enumerate all A01–A20, FP-01–FP-30 and M0 with positive, refusal and unaffected controls against their actual inputs; retain omitted gameplay/resource/platform obligations and R31's separate M1 requirements. No stage closure by aggregate test count or successful row writes.

Routine local choices above (private capability, additive metadata, per-row gate, unique temp names, strict control reads and refusal identifiers) are proposed implementation decisions, not unresolved user preferences. Remaining platform/restore/provider contracts have explicit dependencies and cannot be silently filled with optimistic defaults.

## Evidence boundary

Only text source/document/test-definition inspection and this owned Markdown write were performed. No source changes, Git operations, tests/collection/build/typecheck, project imports, DB, keys/crypto, runtime/process inspection, live service action, provisioning or subagents. No serving revision or deployed safeguard was verified. The contract is ready for review; U9, all acceptance claims and M0 remain open.
