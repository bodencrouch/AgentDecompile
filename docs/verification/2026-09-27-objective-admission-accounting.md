# Preparation objective admission accounting — 2026-09-27

This implements part of P1.1 in the [session audit](../plans/2026-09-22-session-obligation-audit.md).
An action's changed inputs previously created a new local retry allowance without
an objective-level admission counter. Preparation now preserves a separate counter
and dispatch reservations in its existing durable receipt. Each reservation and its
submitting intent are persisted together before child dispatch. Acknowledgment attaches
the child ID without charging again. Uncertain dispatch remains spent.

`workbench.prepare` exposes optional `maxActionAdmissions`, a nonnegative integer.
Omission preserves Unlimited policy while still counting admissions. Existing receipt
allocations survive resume, changed hypotheses and different action wrappers. Migrated
history explicitly records `priorUsageUnknown`; the counter describes admissions since
allocation and does not invent a lifetime total. Rejected dispatch intents are
conservatively charged, so this is an admission-attempt count, not successful-job count.

Exhaustion returns `objective_budget_exhausted` with an explicit allocation-revision
wake condition. The existing `workbench.workflow-control` action adds operation
`admission-budget`, requiring `expectedAllocationRevision` and a new total
`maxActionAdmissions`. Explicit `unlimited=true` permits null. Revision preserves
consumed reservations and records the former allocation. Stale revisions are refused.
It acquires the existing OS run lease and refuses active owners: pause and drain an
active preparation before revising its allocation. This avoids an active coordinator
overwriting the revision from an older in-memory receipt.

Already queued, nonpaused work remains eligible for ordinary admission. A paused or
otherwise inactive run receives an explicit-resume response. The change creates no new
queue entry or child. Activity polling and control budget projections expose aggregate
fields; full reservation and allocation histories remain in the durable receipt.

## Verification and boundaries

The combined preparation/retry/catalog/resource-ownership suite passed **79 tests in
1.64 seconds against source** and **79 tests in 3.63 seconds against the installed
wheel**. Tests exercise real preparation coordinator dispatch with inert child jobs:

- Failed intent persistence prevents dispatch.
- Accepted child followed by acknowledgment persistence failure remains charged;
  restart does not dispatch a duplicate.
- Resume, changed inputs and changed wrappers cannot replenish a finite allocation.
- Competing reservations share the final slot; an independent objective can proceed.
- Revision requires the current allocation revision, preserves spending, and refuses
  active/local or competing OS lease owners.
- Existing queued eligibility, paused behavior, bounded budget projections and catalog
  parameter forwarding remain consistent.

Independent review examined dispatch ordering, crash boundaries and revision ownership.
Its queued-response and general-control projection findings were corrected and covered
before final packaging. No live recovery job, compiler workload or service was launched.
8080 had no listener at source preflight. The package is not activated in a serving process.

This is preparation action-admission accounting, not CPU, money, token or provider usage.
Nested subprocesses and standalone wrappers do not yet inherit a trusted shared budget.
General uncertain-owner reconciliation, provider circuits, objective progress acceptance
and all supported failure-matrix cases remain open. Linux tests do not qualify native
Windows lease behavior. The persistent goal remains active.

PEP 517 build and isolated installation succeeded. All three changed module byte streams
match canonical source, wheel members and installed files. Stage:
`/dev/shm/ad-objective-admissions-20260927`.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-objective-admissions/agentdecompile-2.0.1.dev0+autonomy20260927.5-py3-none-any.whl)

SHA-256: `1a02d4dc9f9eb2dc5d0e55f3a80b6ab1ef4fdcf39df722e3df0f3495683482e3`.

[Build evidence](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-objective-admissions/build-evidence.json).
