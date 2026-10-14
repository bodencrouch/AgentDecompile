# K1 probe: queue admission, not missing binary bytes

Read-only audit by /root/views_action_audit; no retry or native operation.
Run 50b7a4f737c3363dd418a7941cca3ec8 retained two probe jobs:
c9b9ff8063d4 and ede302f89d05. Both have startedAt null, workerPid null,
empty log/data, unreserved resources and ended cancelled. The replacement
waited 900 seconds. That was queue/wait timeout, not measured extraction time.

Preparation's deadline begins at submission (preparation.py:1849), before
admission (actions/jobs.py:1535). The durable receipt does not record which
capacity/lock/paused-scope/scheduling gate withheld admission. execute-script
is conservatively state-writing (registry.py:1427); do not infer safety from
arbitrary script text to evade that policy.

Generic summaries at preparation.py:2084 and :2557 report inaccessible bytes or
no matched probe even though no probe returned. Empty observed probeMismatch
was set when invalidating an old checkpoint (:83), not observed on execution.
_ANALYSIS_PROBE emits programPath/executablePath, but output decoding and exact
acceptance guard were not exercised for these jobs.

Routing changed shared /K1/k1_win_gog_swkotor.exe to local repos.gpr with bare
k1_win_gog_swkotor.exe (:1167). Validate full DomainFile path and fingerprint
before accepting mapped evidence. Neither route executed; no missing external
EXE prerequisite is established. Old run 9c2b894874f863c4896585e388bc1109 still
retains K1 analysis/facts/BSim, full path, binaryId 11, fingerprint
9a44891011437deb6536d992bccdfe4b and a ready targetImage receipt. Attempt
proof-bound reuse of these artifacts, never copy flags or promote old proof.

Next scoped repairs: persist admission hold reason; distinguish queue from
execution duration while preserving declared wall-clock budgets; label unstarted
probes 'not admitted'; validate captured program mapping; reuse proven old
artifacts where identity permits. Current Work visuals must not animate these
records as executing Ghidra reads. Admission repair belongs with the sequential
jobs/checkpoint slice; probe summaries/mapping belong with preparation repair.

## Current admission receipt

Read-only Playwright GET /api/v1/jobs/current: running 0/maxConcurrent 4,
paused scopes 0, six waiting jobs (one match, five undeclared), identity holds 3,
Ghidra holds 2, output-tree hold 1. Matching c3fec5a9edda is queued/unstarted.
Its exact db/kotorxid.sqlite identity is held by failed/quarantined
772e68366608 (mcp.get-references); admission checks actions/jobs.py:1410.
Historical interrupted 25a378fa5fee (mcp.import-binary) has no locator and
therefore global Ghidra lock '*' (:2558), blocking all native actions today.
This current lock map is not proof of the exact historic probe-submission map.

Supported catalog actions: workbench.resource-reconciliation-report and
workbench.resource-reconcile (actions/catalog.py:198). Release requires committed
terminal receipt, recorded resource identity, same-attempt execution owner and
session clearance observations, and qualifying lifecycle contract
(actions/jobs.py:1068). Current quarantined holder has empty executionOwner and
clearanceObservation. Old PIDs missing / zero active workers alone are insufficient;
remote operations and detached children are excluded by that proof contract.
Do not fabricate observations, strip quarantine, bypass locks or repeat blocked
recovery admissions. No report/reconcile action was submitted in this audit.
