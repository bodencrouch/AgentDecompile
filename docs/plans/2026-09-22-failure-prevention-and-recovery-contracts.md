---
title: Failure prevention and recovery contracts
type: design
date: 2026-09-22
status: design-complete-runtime-unverified
---

# Failure prevention and recovery contracts

This specification extends the existing task, receipt and acceptance authority; it
does not propose a second orchestration platform. Read it with the
[task and continuation design](2026-09-22-task-acceptance-and-continuation-design.md)
and [recovery contracts plan](2026-09-22-recovery-contracts-and-validation-plan.md).
Its purpose is to make historical failure lessons executable requirements for the
existing coordinator and adapters. **All checks here are future specifications,
not tests run, deployed safeguards or measured results.** No current host diagnosis
is implied by historical incidents. Nothing here authorizes software execution.

## 1. One authority and an immutable acceptance boundary

The existing coordinator persists observations and proposes decisions through one
versioned decision reducer. The acceptance authority commits claims after checking
policy, dependency versions and publication generation. Existing launchers become
adapters of that same decision protocol; they do not each invent their own retry,
resource or completion policy. Workers write private artifacts and observations,
never accepted corpus state. A task is complete only when all mandatory output
contracts have terminal results and every policy-required success predicate passes.
Partial evidence remains useful without completing the task or overall objective.

A recovery action may change environment, provider, task size, scheduling or input
hypothesis. It **cannot** change the requested acceptance bar, reinterpret unsupported
as passed, remove a mandatory recording, substitute a checkpoint for a full route,
or convert original-code use into recovered-source credit. An altered objective
requires a separately recorded user decision; the previous unmet objective remains
in history. Budget exhaustion terminates attempts while retaining unmet predicates.

Control-plane records contain `objective_id`, `task_id`, `attempt_id`, `basis_digest`,
`policy_revision`, `schema_revision`, `generation`, `event_id`, `observed_at`,
`detector_id`, `detector_health`, `failure_class`, `confidence`, `action_id`,
`retry_owner`, `consumed_budget`, `wake_predicate`, `escalation_reason` and referenced
immutable artifact digests. Corrections append events; they do not rewrite old
observations. Evidence with unknown scope stays unknown until checked.

## 2. Failure protocol

Every adapter declares prevention predicates, detectors, containment scope, permitted
recovery actions, wake predicates and escalation boundaries. The reducer never
accepts an unbounded catch-all retry. Actions are idempotent or have an explicit
reconciliation protocol. Only the coordinator owns outer retries; adapter-internal
attempts consume the same budget. A retry's new attempt ID does not reset its task,
objective, provider or resource-class budget. Stable incident and objective budget
keys survive new error strings, task IDs and proposed hypotheses. Charge/reserve
atomically with durable command intent before dispatch; ambiguous launched work
keeps its reservation until reconciled. Unknown failure is not presumed transient.

The transition is `observed → classified → contained → recovery_pending →
reconciling → eligible`, with `waiting_external`, `budget_exhausted` and
`unsupported` branches. Eligibility means a new attempt may be admitted, not that
its desired claim is accepted. Each transition names its supporting event and exact
input version. Replayed observations cannot consume budget twice, launch a duplicate
worker or grant a second acceptance commit.

Detection is itself a fallible dependency. A detector timeout, stale reading or
malformed response yields `detector_unknown`, never healthy or failed by inference.
Resource-dependent detection runs in bounded isolated workers with per-resource
probe limits. The reducer uses a declared freshness window and monotonic elapsed
time where applicable. Across host restart it conservatively reconciles deadlines
from persisted timestamps and boot identity; it does not trust a reset monotonic
clock. A failed detector blocks only decisions requiring its evidence. Existing
managed work follows its pinned lifecycle unless continuing it requires the missing
safety signal; read-only inspection of healthy cached evidence can continue.

### Shared recovery, durable wakes and decision criteria

A provider/resource outage has one shared circuit state and one single-flight recovery
probe, with a shared healing budget, jittered next eligibility and reserved control
capacity. A hundred waiting tasks do not authorize a hundred probes. Per-task limits
are subordinate to incident/objective/provider/resource ceilings; admission and
recovery both account for their resource costs. Metadata full/read-only is a store
failure: preserve previous truth, refuse unauditable mutation and apply F18 rather
than accepting through a volatile bypass.

Remote ownership uncertainty and provider availability need separate clearance.
For the process-global MCP session, a per-job guard is insufficient: an uncertain
request in job A must also prevent job B or a direct bridge consumer from switching
that same session. Persist the incident under a credential-free, qualified provider
identity and incident generation; check it before new dispatch or budget charging.
Session reset, changed locator, new objective and successful initialization cannot
clear unknown remote effects. A bounded read-only reconciliation report identifies
the exact missing provider clearance evidence; it does not offer a generic force
clear. Cached inspection and genuinely independent providers remain available.

A proven fresh incident store may initialize an empty ledger. Losing or corrupting
an established ledger cannot be treated as a fresh healthy provider; preserve its
quarantine basis and require reconciliation. This shared containment is a future
implementation boundary beyond the current per-executor MCP budget guard, ordered
after the P0.4/P0.3 acceptance and ownership prerequisites. Availability-only probes
may resume calls only for failures proven to precede tool dispatch; a healthy probe
never resolves an uncertain dispatched operation.

Wake registration uses a durable event cursor/outbox protocol: record the wait basis
and cursor with the blocked transition, subscribe/replay events after that cursor,
and recheck the predicate before sleeping or admitting. Events arriving between
checking and subscribing cannot be lost. A bounded reconciliation sweep repairs
missed delivery without restarting work. External owners that cannot emit events
have a declared bounded observer with shared probe limits and freshness; silence
never clears ownership. Event delivery is at least once; reducer actions are
idempotent by event/action key.

Among safe supported routes that preserve the exact acceptance contract, select by
requested-capability unblocking value, expected resource/time cost with uncertainty,
and the declared deadline policy. This is a documented local decision criterion,
not proof of global optimality. Unknown profiles receive bounded diagnostic
exploration, not unlimited trial launches. Capped-age reservations, explicit urgent
overrides and an audit/control capacity reserve constrain ordinary ranking. Measure
outcomes and update versioned profiles prospectively; do not rewrite old decisions
to make estimates appear accurate.

Live preconditions are rechecked after acquiring the complete mutation resource
bundle, immediately at command execution on the supported engine thread. Bind the
request to scenario/world epoch and validated object lifetime token or equivalent
adapter-supported identity check. A changed epoch, destroyed/reused object or missing
party member refuses mutation and returns to prerequisite selection; a static fixture
digest or earlier preflight cannot authorize use of a stale live object.

If a required independent verifier is unavailable, the producer cannot certify its
own result. Preserve the proposal and wait for a compatible qualified verifier.
Disagreeing verifiers create a contested claim with raw observations and evidence
lineage; targeted diagnosis may resolve it, but majority vote or stronger prose is
not acceptance. Independent ready claims remain eligible. Receipt repair writes a
new immutable verified record linked to the damaged record; it never overwrites
history. Authority failover requires supported writer fencing and durable continuity,
never a timeout alone.

Policy routing changes use a preauthorized bounded canary: record baseline policy,
eligible workload population, maximum attempts/duration/cost, success metrics and
abort thresholds before activation. Crossing an abort threshold automatically restores
the known-good routing policy within that authorization, closes the canary and retains
all observations. A canary cannot alter acceptance predicates; even a faster route
must earn the same independent claims. Unknown canary outcome or unavailable metrics
stops expansion and returns routing to the authorized baseline when safe. No measured
improvement is claimed until comparable results exist.

## 3. Concrete failure contracts

In the tables, **wake** means an event whose predicate is rechecked before admission;
it is not a periodic instruction to retry unchanged work. **Escalation** records the
unmet dependency and decision needed. It never silently changes acceptance.

| ID / failure | Prevention and detection | Containment and automatic recovery | Exact wake and escalation |
|---|---|---|---|
| F01 False semantic identity under correct bytes | Require target bytes, independently supported entity identity and operation capability separately. Detector checks evidence-root graph and target boundary proof. | Reject binding; quarantine the semantic assertion and unsupported descendants; retain actual byte observations. Queue targeted identity task. | Wake on new target-side evidence root/version satisfying identity policy. Escalate absent evidence or exhausted discovery budget, not a platform-wide ban. |
| F02 Donor withdrawal or stale proposal | Pin dependency versions; track directed claim lineage. Acceptance transaction rechecks roots. | Withdraw affected current export references, mark unsupported descendants stale; preserve independent claims and history. Recompute only affected basis. | Wake on sufficient replacement roots or revised dependencies. Escalate contested roots without selecting by arrival order. |
| F03 Wrong scenario fixture | Declare build/save/module/party/script state and driver requirements. Inspect fixture manifest and live preconditions before important action. | Refuse launch/action as prerequisite missing; select existing compatible fixture or create a preparation task. Do not record behavioral failure. | Wake when fixture digest and required live predicates pass. Escalate missing fixture authority or capability, retaining original scenario goal. |
| F04 Duplicated or stale lifecycle setup | One shared launch adapter owns prefix/stage/recorder states; compare expected lifecycle revision and actual ownership. | Initialized prefix skips initialization; uninitialized prefix uses bounded owned setup. Unknown partial state becomes reconciliation task, never blind rerun. | Wake on validated lifecycle state and ownership clearance. Escalate irreversible/externally owned ambiguity. |
| F05 Occupied control channel | Separate read-only observation from exclusive mutation; bounded connection lifecycle and command IDs. Detect owner plus active request, not only socket presence. | Queue conflicting mutation, keep supported status available; close only coordinator-owned expired clients under declared lifecycle. | Wake on owner release or observed request completion. Escalate external ownership or unresolved command effect; no second mutation session. |
| F06 Non-idempotent command disconnect | Persist command ID, argument digest, scenario generation and pending intent before submission. Read command result and engine postconditions. | Mark outcome unknown; reconcile once by durable command state/independent oracle. Replay only if known not executed, or if operation is proven idempotent under current state. | Wake on decisive observed effect/non-execution or permitted fixture restoration. Escalate unobservable effect; do not promise exactly-once engine effects. |
| F07 Lease expires while old worker lives | Separate publication fencing from access ownership; use actual locks and stable process/start identity. | Revoke old publication, quarantine its mutable bundle; preserve late private artifacts as historical. Replacement requires disjoint safe resources or clearance. | Wake on corroborated end of access, owning-system release or new disjoint bundle. Escalate uninterruptible/external holders; expiry alone never releases. |
| F08 Device hangs or prepared copy incomplete | Verify complete input closure on healthy storage before launch; bounded isolated probes; launchable manifest only after validation. | Quarantine device-dependent jobs and partial bundles; use already verified independent replicas if complete. Continue healthy independent inputs/outputs. | Wake on verified device recovery or complete independent bundle. Escalate missing sole input; changing destination does not eliminate source dependency. |
| F09 Deterministic compile/match rejection | Key negative cache by relevant inputs/toolchain/hypothesis/policy; classify actual compiler/report outcome. | Persist negative result; no unchanged repeat. Diagnose behavior/type, ABI, compilation context, codegen then placement as applicable. | Wake on a changed relevant hypothesis/input or corrected verifier defect. Escalate exhausted candidate space/budget; compiler exit alone never proves parity. |
| F10 Transient compiler/provider failure | Declare error taxonomy and retry policy; require raw failure evidence, not generic nonzero exit. | Retain completed units; bounded backoff and fresh private attempt where safe; open provider circuit at threshold; select compatible provider. | Wake at recorded cooldown plus successful bounded probe or compatible-provider availability. Escalate budget exhaustion or missing credentials/permissions. |
| F11 Repeated zero goal progress | Record liveness, distinct durable unit outcomes and accepted capability delta separately. Detect unchanged hypothesis repeats and policy-defined zero-delta count. | Stop that hypothesis's admission; require evidence-based strategy change with predicted observable difference. Other tasks continue. | Wake on changed relevant hypothesis/basis or explicit authorized budget/strategy decision. User continuation alone cannot reset history. |
| F12 Legitimate long-running unit | Declare expected progress granularity, checkpoint contract, estimated range and deadline before launch. Compare current evidence with that contract. | Mark progress unknown when instrumentation cannot prove progress; do not equate absent final artifact with failure. At deadline follow owned cancellation/checkpoint/reconciliation policy. | Wake on completed durable unit, valid checkpoint, observed exit or policy-authorized revised profile. Escalate uninstrumented duration uncertainty; never manufacture progress from PID churn. |
| F13 Capacity exceeded or no suitable worker | Include process-tree memory/CPU/scratch, shared nested budget, uncertainty reserve, pressure trends and available enforcement. | Close admission for affected class; checkpoint-and-exit restartable owned work when supported; split valid units or route to suitable environment. | Wake on measured available capacity, compatible enforced worker or validated smaller profile. Escalate sustained insufficiency; neither swap occupancy nor a single quiet sample decides all work. |
| F14 Fairness or priority starvation | Persist ready age and class policy; capped-age reservation overrides ordinary same-class priority. Detect reservation deferrals. | Reserve next compatible window; permit only non-delaying backfill. Urgent override records authority/reason/expiry/rescheduling and preserves age. | Wake on reserved capacity window or expiring override. Escalate persistent dominant class/urgent stream; report absence of a fairness bound instead of claiming optimal scheduling. |
| F15 Behavior passes but recorder fails | Recorder preflight; oracle and video receipts carry same attempt/action interval. Detect missing, truncated or uncorrelated recording. | Retain scoped behavior evidence, reject combined video-qualified claim; schedule same-scenario action plus recording rerun if safe. | Wake on recorder health and complete fixture/capability prerequisites. Escalate unsupported capture; never splice old oracle to unrelated new footage. |
| F16 Publication interruption | Write private destination-side temporary artifacts; validate/flush; immutable blobs precede committed manifest. | Keep prior complete manifest; reconcile orphaned artifacts; finalize only if all content and acceptance dependencies still qualify. | Wake on destination health and verified complete artifacts. Escalate missing sole accepted artifact; do not assume cross-filesystem rename atomicity. |

## 4. Control-plane failure contracts

The coordinator's own inputs—event store, schema, policies, receipt validator,
clock/boot identity and ownership observations—must appear in its dependency model.
A scheduler that depends synchronously on a hung archival disk cannot deliver the
promised containment. Control-plane state belongs on healthy persistent working
storage; resilience beyond that failure domain needs an already verified replica.

| ID / failure | Prevention and detection | Containment and automatic recovery | Exact wake and escalation |
|---|---|---|---|
| F17 Coordinator crash/restart | Persist launch intent, reservation generation and budget charge before dispatch; durable completed units before acknowledging progress. | Restore events; reconcile actual managed/external owners before relaunch; discover private result manifests and revalidate. Idempotent event/action keys suppress duplicate dispatch and acceptance. | Wake each task only after its relevant owner/input/budget reconciliation. Escalate unavailable durable store or ambiguous live owner; no whole-queue blind replay. |
| F18 Coordinator store unavailable | Separate core store from archival operations; bounded asynchronous health probes and explicit store-health state. | Stop new mutations/acceptance requiring durable commits. Managed workers follow predeclared finite offline checkpoint/private-buffer allowance, then checkpoint/exit if possible. Cached read-only views display stale/as-of labels. | Wake on store restored and journal continuity validated. Escalate exhausted local buffer, unavailable sole store or unreconciled owner; never accept from volatile memory and claim durability. |
| F19 Corrupt/missing receipt or artifact | Validate schema, digest, provenance and referenced-content availability before use; maintain backups/replication receipts. | Quarantine bad receipt and dependent claims; restore exact verified copy if available, otherwise schedule scoped re-verification. Preserve corruption evidence. | Wake on verified restoration or fresh accepted replacement. Escalate no trustworthy copy; a checksum detects damage but cannot repair or authenticate semantic truth. |
| F20 Schema migration interrupted/incompatible | Version schemas; immutable snapshot/backup and planned reader/writer compatibility matrix; one migration owner. | Fence incompatible writers; perform staged migration with journal and validation before switching active schema reference. Roll back to intact old snapshot only before new incompatible writes or through validated reverse migration. | Wake on committed schema epoch supported by adapters and authority. Escalate lossy/unsupported migration; no automatic downgrade or reinterpretation of legacy unknowns as accepted facts. |
| F21 Policy defect or rollback | Pin policy revision per attempt/claim; stage policy changes against archived decision examples before activation. | Stop affected new acceptance; activate known-good policy only through authorized policy change. Reevaluate affected current claims against explicit required policy; retain historical receipts and reasons. | Wake on authorized validated policy revision and dependency reevaluation. Escalate no safe policy or intentional acceptance change requiring user decision. Old receipts do not silently inherit new meaning. Verifier disagreement stays contested and verifier absence never permits self-certification. |
| F22 Budget accounting unavailable or exceeded | Reserve budget before dispatch, settle actual usage after; shared hierarchy covers task/objective/provider/resources and child attempts. | Refuse new budget-consuming dispatch when ledger cannot commit. Unknown usage retains conservative reservation until reconciled. On limit, perform declared safe checkpoint/cancel, preserve evidence. | Wake on reconciled reservation or explicitly authorized budget increase. Escalate missing provider usage/enforcement; do not reset by new worker, conversation or tool wrapper. |
| F23 Detector/adapter defect or unknown failure | Schema/version checks, detector freshness/health and adapter conformance suite; preserve raw unclassified result. | Quarantine affected adapter decision path; no guessed success or automatic generic retry. Use compatible independently qualified adapter, or bounded diagnosis task with its own budget. | Wake on validated classifier/adapter fix or new discriminating evidence. Escalate unknown failure after diagnosis budget; independent ready work remains eligible. |

A store outage can legitimately block the shared acceptance authority. The design
does not pretend that every task is independent of that authority. Computation may
continue only under its predeclared offline contract; accepted durable progress
waits for a functioning authority or a correctly fenced replicated replacement.
Multiple coordinators require a single active-writer/fencing protocol supported by
the actual store; a duplicate process is not failover. Corruption repair and schema
migration must preserve lineage, generation and retry history, not merely row counts.

### Audit cadence and external capability denial

**F24 — redundant full audits:** prevention uses relevant dependency keys and an
explicit bounded audit policy, rather than raw pass count alone. Detect unchanged
bases and log every full audit's trigger, expected cost and missed-invalidation
findings. Contain expensive audits to their reserved budget; reuse unchanged valid
checks and schedule the next full audit on a declared policy deadline or changed
correctness prerequisite. Wake on that deadline, relevant invalidation or the
requested terminal fresh-rebuild gate. Escalate uncertain invalidation correctness
for bounded investigation; the fresh final whole-image rebuild is never replaced
by cached receipts to save cost.

**F25 — external entitlement/authentication denial:** distinguish a job that never
started because of billing, credentials or authentication from compiler failure.
Record `external_action_required`, stop unchanged launch retries and preserve local
checks at their actual scope. Wake only on verified restored entitlement or an
explicitly allowed compatible service; otherwise escalate the exact external action.
The coordinator does not autonomously spend money, change credentials or infer CI
success from local results. Independently eligible local work can continue.

## 5. Ownership and escalation

Roles below describe responsibilities in existing components, not new always-on
services or new agent identities:

- **Coordinator:** admission, budgets, retries, generations, state reconciliation and wake events.
- **Acceptance authority:** typed claims, dependency lineage, policy consistency and atomic publication reference.
- **Adapter owner:** truthful provider outcomes, lifecycle preconditions, command reconciliation and resource requirements.
- **Storage owner:** prepared manifests, consistent snapshots, durability and replication evidence.
- **Scenario owner:** fixture requirements, semantic oracles, recording correlation and bounded teardown.

Escalation is an actionable record: affected objective/capability, failed predicate,
raw evidence references, independent work still eligible, attempted recoveries and
consumed budget, exact external change or authorized decision required. It is
emitted on a meaningful state transition, not on every poll. A user request to
continue may select work already eligible; it does not by itself repair evidence,
release resources, approve a weakened goal or reset limits.

## 6. Future paired acceptance checks — not run

Each check includes a rejection/containment case and an unrelated valid continuation
case. The latter requires available capacity, complete inputs and healthy required
control-plane dependencies; it does not require impossible progress during loss of
the sole authority. Evidence consists of raw injected observations, decision events,
artifact digests, state snapshots, accepted receipts and budget/ownership histories.

| Check | Owner | Future injected case and required paired result |
|---|---|---|
| FP-01 | Acceptance authority | Correct target bytes under false label: reject semantic binding, accept unrelated independently identified entity. |
| FP-02 | Acceptance authority | Withdraw donor root: stale unsupported descendants and export references, preserve independently supported claim and immutable history. |
| FP-03 | Scenario owner | Required party member/module absent: refuse action as prerequisite missing, including a party/object epoch change after preflight; run compatible unrelated fixture. |
| FP-04 | Adapter owner | Initialized prefix through recorder and live driver: neither initializes again; fresh isolated prefix follows one bounded setup path. |
| FP-05 | Adapter owner | Stale observation connection occupies mutation channel: read-only status remains available; conflicting mutation waits while independent analysis completes. |
| FP-06 | Scenario owner | Disconnect after non-idempotent action: reconcile or retain unknown, never replay blindly; unrelated safe read continues. |
| FP-07 | Coordinator | Expired old generation returns matching bytes while alive: reject stale publication and retain quarantine; disjoint replacement task can finish. |
| FP-08 | Storage owner | Source device hangs during copy to healthy destination: partial bundle stays unlaunchable, already complete independent bundle runs; outstanding probes stay bounded. |
| FP-09 | Adapter owner | Same deterministic compile failure under new PID: one cached negative and no retry; changed relevant candidate is eligible. |
| FP-10 | Coordinator | Transient provider crash with nested wrapper retries: 100 waiting tasks share one recovery probe and bounded healing/attempt budgets; compatible provider performs independent ready work. |
| FP-11 | Coordinator | Repeated zero-goal-delta experiments with unchanged basis: admission stops for that hypothesis; changed evidence-backed strategy and independent task remain eligible. |
| FP-12 | Adapter owner | Long legitimate unit has no final report yet: no false failure/progress from PID alone; distinct completed checkpoints count, deadline follows declared lifecycle; short independent task continues. |
| FP-13 | Coordinator | Near-full swap with qualified small task, and spare swap with overloaded task: decide from complete profile/pressure/enforcement; admit first when qualified and reject second. |
| FP-14 | Coordinator | Large capped-age task surrounded by small high-ordinary-priority tasks: reservation wins within class; non-delaying backfill continues; urgent override history remains visible. |
| FP-15 | Scenario owner | Oracle succeeds but video is missing/wrong attempt: preserve behavioral claim, reject combined claim, accept independent complete recorded scenario. |
| FP-16 | Storage owner | Interrupt destination write/rename/manifest boundary: prior complete export remains readable; no partial reference publishes; unrelated destination can publish. |
| FP-17 | Coordinator | Crash after launch intent/budget commit before launch acknowledgment: restart reconciles actual owner, does not duplicate dispatch/charge; independently reconciled task resumes. |
| FP-18 | Coordinator | Sole event store unavailable: refuse new acceptance and unsafe dispatch; bounded private checkpoint/read-only cache contract holds; recovery validates continuity before acceptance resumes. |
| FP-19 | Acceptance authority | Corrupt one receipt/blob: affected claims quarantined, exact verified restoration or scoped re-verification required; unaffected receipt continues to qualify. |
| FP-20 | Storage owner | Interrupt schema migration and present old incompatible writer: reject writer, retain old consistent view when supported, resume/finalize once; unrelated compatible read remains available. |
| FP-21 | Acceptance authority | Bad policy admits a previously rejected false-label sample: block policy activation; authorized known-good policy retains prior semantics; valid sample still accepts. |
| FP-22 | Coordinator | Provider usage unknown after timeout and retry wrapper changes: retain conservative reservation, refuse over-budget launch; independent task with separate valid budget proceeds. |
| FP-23 | Adapter owner | Malformed/unknown detector result: classify unknown and quarantine that decision path; qualified alternate adapter or unrelated task continues, no guessed success. |
| FP-24 | Acceptance authority | Successful checkpoint combat proposed as full-route/video proof: reject scope promotion, retain checkpoint evidence; correctly scoped unrelated claim accepts. |
| FP-25 | Coordinator | Restore backup then receive late events and user continuation: preserve generations/retry lineage and durable wake cursors, reconcile events arriving across subscribe/crash windows without duplicate dispatch/acceptance; ambiguous external effects remain unreplayed until reconciled; do not reset limits; independently reconciled work proceeds. |

| FP-26 | Coordinator | Unchanged inputs trigger repeated full-audit pass counter: policy suppresses redundant audit while a declared bounded audit or requested fresh final rebuild still runs; unrelated changed-unit work proceeds. |
| FP-27 | Adapter owner | CI job denied before start by entitlement: classify external-action-required, no compile failure or local-to-CI promotion; valid local tasks continue and restored entitlement wakes the CI task. |
| FP-28 | Acceptance authority | 18,578 compiling candidates plus partial receipts proposed as whole-image success: refuse promotion without fresh equality/contribution receipts; scoped compilation facts remain accepted. |
| FP-29 | Acceptance authority | Required verifier disappears or two verifiers disagree: proposal waits/contests without producer self-certification; qualified alternate or unrelated independently verified claim proceeds. |
| FP-30 | Coordinator | Canary exceeds predeclared cost/duration or error threshold: automatic preauthorized routing rollback preserves budgets/evidence and acceptance policy; baseline eligible work continues. |

FP-18 explicitly tests a real shared dependency rather than promising admission
without a functioning durable coordinator. FP-20 does not demand unsafe concurrent
writes during migration. FP-25 must record any lost-event window within the declared
replication objective; local flush or backup existence alone does not prove zero loss.

## 7. What would prove the effort

The feasibility referent is a replayable historical incident bundle producing the
specified decisions and then a controlled fault-injection run demonstrating those
decisions against real adapter/storage boundaries. Pure reducer replay checks policy
logic; it does not prove OS locks, process termination, durable flush, engine behavior
or remote fencing. Those require their corresponding future integration receipts.

The optimality comparison is against the existing distributed manual decisions on
matched workload/incident sets: false acceptance/refusal, repeated operator
interventions, time to next usable capability, accepted durable work, retry
amplification, lost completed units, recovery delay and coordination overhead.
Record denominators, workload basis, failures and resource costs. Do not claim the
new design is optimal or always faster before those measurements. A coherent future
backend is a reason to define the adapter contract now; it is not evidence that the
backend works.

The bounded guarantee is containment and honest continuation when suitable capacity,
permissions, valid complete inputs, healthy required authority and compatible workers
exist. Machine loss, sole-store corruption, uninterruptible holders, unobservable
non-idempotent effects and unavailable credentials can block dependent work. The
system must name those limits, preserve accepted evidence within its actual durability
contract and keep the original objective intact. It cannot guarantee uninterrupted
progress, exactly-once arbitrary side effects, universal binary recovery or automatic
repair of missing sole evidence.

## 8. Historical incident traceability

Incident identities and raw-source distinctions are owned by the
[history-grounded maintainability ledger](2026-09-22-history-grounded-maintainability-design.md).
This mapping preserves its eleven incidents without turning historical observations
into claims about current runtime state.

| Historical incident | Prevention/recovery contract | Future falsifier |
|---|---|---|
| H01 Repeated deterministic cascade error | F09, F10, F22; stable incident budgets and single retry owner | FP-09, FP-10, FP-22 |
| H02 Expensive full pass among unchanged incremental passes | F24; dependency-triggered and bounded audits, final fresh gate retained | FP-26 |
| H03 Busy channel and uncertain live resource | F05–F07; observation/mutation separation and quarantine | FP-05–FP-07 |
| H04 Copy to tmpfs blocked on same source | F08, F16; complete staging and publication | FP-08, FP-16 |
| H05 Zero-frontier route experiments | F11, F12; progress classification and strategy basis | FP-11, FP-12 |
| H06 Limited local evidence versus full multiplayer | Section 1 task/objective predicates, F15 | FP-15, FP-24 |
| H07 CI entitlement denial before execution | F25 | FP-27 |
| H08 Missing fixture actor | F03 and post-ownership live epoch check | FP-03 |
| H09 Duplicate prefix lifecycle | F04 | FP-04 |
| H10 Compiling source versus exact whole image | Section 1 immutable acceptance and F02/F24 | FP-28, FP-26 |
| H11 Shared nested resource pressure | F13, F14, F22 | FP-13, FP-14, FP-22 |
