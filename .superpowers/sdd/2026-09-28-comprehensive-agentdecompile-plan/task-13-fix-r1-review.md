# Task 13.1 fix round 1 review

## Finding verdict

**P1 — Permanent worker-slot retention after exact-child exit with surviving descendants: ADDRESSED.** Reviewed the supplied fix diff from `b871b845` to `d43a86fb`, the original finding and brief, and the appended implementer report.

- `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py:1430` now distinguishes a returning executor from retained resource ownership: returned execution receives terminal status/time even when its session remains quarantined. Exception handling likewise records a terminal executor outcome.
- `jobs.py:1458` terminalizes interrupted unwinds that bypass the ordinary projection. The nested finalizer at `jobs.py:1475` calls the existing admission-release helper once as the runner leaves, including persistence/unwind failure paths. That helper decrements runner capacity while retaining held/quarantined resource maps. Reconciliation does not acquire another decrement obligation.
- `jobs.py:1515` records an interrupted exact-child observer handoff without changing the observed owner or asserting child/session clearance. During a live monitor, the exact `Popen` handle is still polled and admission remains held. After return or interruption, the runner becomes terminal and the retained cross-place generation, owner and lease can reach the donor reconciliation checks. Resource quarantine remains controlled by the existing resource disposition and qualified clearance contract.

## Covering regression source

- `tests/test_job_owner_lifetime.py:88` covers clear, occupied and interrupted outcomes. It checks a separate worker stays counted, terminal receipt projection, exact owner retention, and preserved identity/Ghidra resource maps for unresolved outcomes.
- `tests/test_cross_place_catalog_lifecycle.py:385` covers both observed child exit and interrupted monitoring through real runner admission, monitor and receipt code with controlled executor/session seams. Its occupied-session reconciliation refusal requires `fresh_whole_session_clearance`, excludes the previous `live_executor_terminal` refusal, and preserves the lease and resource claims. Later clear-session reconciliation must release those claims without decrementing the unrelated worker or replacing the execution owner.
- These sources cover the original failure sequence and the required refusal/clearance boundary. They were not executed. The implementer report explicitly describes them as unexecuted and reports source checks only (`task-13-report.md:109`); no passing-test claim was inferred.

## New breakage in the fix diff

None established. No new Critical or Important finding in the bounded production or regression changes.

## Out-of-scope observations

None added. The original donor review, source inventory and unrelated acceptance gates were not reopened.

## Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.**

**Scoped spec compliance: Compliant for Task 13.1 source reconciliation after this correction.** The exact-child lifetime and donor supervision/resource authority are coherently integrated at the reviewed source level.

**Task quality: Approved for this bounded source slice.** U13 and all software execution, installed-consumer, browser, rollout, reloader, runtime/platform and whole-image acceptance gates remain separate and open.

Verification: read-only review of the fix package, prior finding, requirements and appended evidence; textual source line-location lookup only. No tests, imports, builds, live operations, service actions, Git/index operations, repeated broad checks or subagents. Only this review report was written. Runtime correctness and regression execution remain unverified under the current mission constraints.
