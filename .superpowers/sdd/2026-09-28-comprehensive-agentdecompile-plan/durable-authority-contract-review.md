# U9 durable preparation authority contract review

Date: 2026-10-02. Reviewed `next-durable-authority-contract.md` (152 lines, 3,823 words), the brief, `unit-9-requirements.md`, and the complete A01–A20/FP-01–FP-30/M0 extract against current source text.

**Spec adoption: changes required. Quality/feasibility adoption: changes required. Implementation readiness: not yet.** The selected preparation capability/row/handoff predicate is a useful bounded slice and should be retained. Four Important gaps below need explicit contract decisions before implementation. No Critical finding, source change, runtime result, or full U9/M0 acceptance is claimed.

This is an independent combined source-contract review. It challenges technical assumptions and integration decisions; it does not reopen the upstream product premise or require another goal engine. Review depth is deep because this is a 3,823-word, multi-boundary persistence and ownership contract. Confidence 75 means a concrete material failure scenario supported by source, with implementation or execution still needed for full confirmation.

## Important findings

### DA-1 — Define a usable positive creation/migration predicate and an enforceable restart refusal predicate

**Confidence: 75.** Contract lines 69 and 112 say creation is allowed only for a “corroborated new objective” and requires “independent workspace/objective continuity evidence”; line 106 nevertheless keeps confirmed-dead-owner resume usable for rows “without continuity ambiguity.” Line 110 permits bounded legacy migration after validating histories. Neither the evidence source nor the decision procedure is specified.

Current `preparation.py:883–899,930–981` derives an ID from workspace/context, acquires a lease, and treats missing JSON as first use. It has no independent creation/continuity witness. `admission_budget.py:8–18` and `mcp_budget.py:49–61` initialize absent ledgers using `priorUsageUnknown`; structural ledger validation cannot distinguish a genuine old-schema omission from loss of an established ledger. `recover_interrupted` at `preparation.py:2421–2436` automatically resubmits confirmed-dead owners.

Concrete counterexamples:

- A legitimate first project has no preparation row and no specified independent witness. Literal enforcement refuses every such first use; accepting absence instead silently restores the original reset risk.
- A write fails before replacement, or replacement succeeds but directory fsync fails. The proposed fault latch and uncertain candidate live in the process-local capability/fault registry (lines 70, 101, 104). After process death, the surviving older or newer JSON can be structurally valid and have no durable indication of the observed ambiguity. Dead-owner status plus a valid row cannot prove that the capability never faulted.
- A legacy row missing one ledger can either mean the ledger predates that schema or that accounting was lost. A generic “validate histories” migration cannot decide which.

**Required bounded revision:** specify the first-slice eligibility table for genuinely new objectives, known current-format rows, same-process healthy resume, each supported legacy shape, dead-owner rows, missing established rows, and corrupt ledgers. Name the exact producer/input of any positive continuity witness and how its absence is handled. If durable continuity evidence is deferred, explicitly refuse all cases that cannot be distinguished after process loss and narrow the dead-owner-resume compatibility claim; retain a concrete supported positive path. Do not invent a fresh allocation or a public force-clear flag. This can remain a small prerequisite contract rather than a general restore system.

**Later acceptance:** genuine first creation and healthy supported migration admit once and preserve history; an otherwise identical missing-established-row case refuses. Restart after pre-replace failure and after replace/directory-fsync failure must not regain authority merely because the row parses and the old PID is dead. A separately qualified objective continues.

### DA-2 — The writer inventory stops before shared workflow mutations and comparison publication

**Confidence: 75.** Contract line 71 requires “All mutations of the canonical shared row” under the capability gate, while line 55 assigns only `preparation.py` and a narrow `actions/jobs.py` seam. The actual row escapes into `workflow.continue_recovery` at `preparation.py:1931–1935`.

`workflow.py:166–200` directly mutates the canonical family receipt, nested checkpoints and workflow states; `:112–116,143–164` mutates checkpoint cursors/fingerprints and the row's progress-file reference; `:246,353,436–440` has further checkpoint/family mutations. Guarding only preparation `_write`/`update` does not guard these mutations. Wrapping the entire `continue_recovery` call in the gate is not a safe shortcut: its `action` calls wait for jobs whose nested MCP reservation callback needs the same authority gate from another thread (`workflow.py:120–123`; `preparation.py:1229–1337`; `actions/jobs.py:1693–1726`). That can prevent the accepted child from progressing.

There is also a separate current receipt writer: `record_comparison_receipt` at `preparation.py:2298–2311`, called at `:1899`. It writes a reusable comparison receipt outside `_write`, uses dynamic workspace/DB paths (`:2237–2241`), and replaces a fixed temporary path without a capability. The row fence can reject the subsequent `update` after this writer has already published. Inventory notifications at `:488–500` are another separate writer; those are legitimate independent desired-state input, but need an explicit disposition rather than accidental inclusion in a claim that all durable writes are fenced.

**Required bounded revision:** enumerate these consumers and select a narrow integration boundary. For example, allow minimal `workflow.py` changes that route canonical mutations through a private short mutation callback, with no gate held over child waits, or define detached workflow state plus exact field-level guarded commits. Explicitly guard current comparison-receipt publication through the captured authority/frozen root, or describe a generation-specific historical receipt path that cannot become current reusable state. Classify inventory requests as separate desired-state input and retain their existing scope without claiming their wake/durability shortcomings are solved. No matcher/compiler/provider redesign is needed.

**Later acceptance:** revoke between a child result and workflow checkpoint/publication; no canonical mutation or current comparison replacement occurs. A healthy workflow completes its nested MCP reservation without waiting on a gate held by its parent. Switching active workspace cannot redirect the old callback's receipt into the new root. Independent inventory notification remains usable.

### DA-3 — Carry the new refusal through every existing public and private caller

**Confidence: 75.** Contract lines 90–92 define a private exception and structured 409/503 responses only at the jobs preparation route and the started preparation executor. Actual callers include:

| Caller | Source | Existing failure behavior |
|---|---|---|
| Catalog preparation route | `actions/jobs.py:2244–2253` | Catches `ValueError/OSError`, returns 400; explicitly covered by proposal |
| Direct preparation endpoint | `react_api.py:429–442` | Catches `ValueError/OSError`, returns 400; omitted from file ownership |
| Open/register admission | `workbench.py:386–402` | Catches `ValueError/OSError`, reduces failure to status/error/reason; omitted from file ownership |
| Workflow-control job | `actions/jobs.py:1209–1211,1439–1446` | Calls `control`, then generic exception handling loses structured refusal log |
| Admission/inventory worker | `preparation.py:503–527,537–581` | Limited catches, including a second unguarded `_write` on admission error |
| Startup recovery loop | `preparation.py:2421–2436` | One refused submit can abort later rows in the loop |

If `_PreparationAuthorityRefused` is a new plain exception, the unadapted endpoint/open paths can turn an expected refusal into an unhandled request failure. If it subclasses `ValueError` or `OSError`, those paths instead flatten it into a generic 400 or omit the wake/phase fields. The workflow-control job similarly loses the advertised structured decision. This is caller compatibility, not a request for new public routes.

**Required bounded revision:** declare the exception base and one bounded response/projection adapter, add minimal ownership of `react_api.py` and `workbench.py` if needed, and specify each caller's result. Preserve HTTP 409/503 versus validation 400 at both existing preparation endpoints; preserve open/register's enclosing success while returning a structured blocked preparation result. Workflow-control must return exit code 1 and structured refusal JSON, never success or only a generic exception string. Keep capabilities out of all these payloads. Include root `STORE.start` failure before thread start and ambiguous failure after thread start in the same private seam review; do not reconstitute capabilities from copied/history job records.

**Later acceptance:** deliver the same authority refusal through catalog, direct preparation endpoint, open admission and workflow-control. Each exposes the declared decision without serializing the capability; a normal non-preparation job retains its existing behavior.

### DA-4 — Make fault isolation concrete in scheduler capacity and iteration

**Confidence: 75.** Contract line 104 promises “This quarantines only the affected preparation; separate healthy objectives may proceed,” while retaining the failed capability's physical lock indefinitely until reconciliation. The source makes the distinction operationally important: `_ACTIVE` counts against the four-preparation limit at `preparation.py:986` and `:543–548`, while `_LEASES` also acts as an admission/revision exclusion. `list_runs(public=False)` can independently discard `_ACTIVE` by run ID at `:452–454`.

A fault registry alone does not specify whether faulted preparations continue consuming execution slots. Four retained failures could therefore prevent every healthy preparation from admitting. A single refusing queued write can also escape `_drain_admissions`, and its exception branch currently retries `_write` on a stale row (`:573–575`). `recover_interrupted` can stop on its first refused row. These are concrete shared scheduling boundaries, even when no global lock is held while idle. Deferring hung-I/O isolation is reasonable; isolating a returned refusal is part of the selected behavior.

**Required bounded revision:** separate retained lease/quarantine membership from live coordinator capacity. On authority fault, retire only the expected authority's execution-capacity membership when its coordinator finishes, retain its lease/fault reference, and never free successor capacity or child resources. Include `list_runs`'s ID-based discard in the identity-safe lifecycle conversion. Handle each maintenance/admission/recovery refusal per row without a second row write or terminating the shared iteration; faulted rows wait for the named reconciliation predicate rather than being repeatedly re-admitted. Keep diagnostic output bounded.

**Later acceptance:** with four faulted retained leases, a fifth independent healthy preparation can still use available execution capacity while all four leases remain held. A failure in the first queued or recovered row leaves the next healthy row eligible. Stale observation/finalizer callbacks cannot remove a successor's `_ACTIVE` membership.

## Retained decisions that withstand review

- Actual OS lease acquisition, object-identity capability binding, frozen row root, and explicit generation/revision comparisons form a coherent local fence under the stated cooperating-writer assumptions. Generation is correctly separated from objective identity and resource clearance.
- Gate-before-registry ordering and avoiding job-store admission under global `_LOCK` are sound requirements. Refactoring all current outer-lock entry points is necessary; this report does not claim deadlock freedom before implementation.
- Reserve-before-dispatch, idempotent same-dispatch acknowledgement, allocation CAS/history, and spent unknown outcomes already exist and should be preserved (`admission_budget.py:8–84`, `mcp_budget.py:49–122`, `preparation.py:1174–1229`). Unlimited still counts. Retry history and changed matching bases must not reset these ledgers (`retry_policy.py:13–61`, `preparation.py:2131–2152`).
- A write failing after replacement is correctly treated as uncertain rather than rollback. Closing the capability before returning, retaining proposed versus last-committed revision, and refusing a second final write address the in-process failure window. DA-1 concerns how this survives a later process loss.
- Keeping ambiguous admission spent and accepted-child ownership with jobs is correct. Known job IDs may aid reconciliation; an exception is not proof that no child started. Jobs resource disposition and release at `actions/jobs.py:1420–1475,1522–1544` must remain separate from preparation authority.
- Separate command locking, strict admission reads, command revisions, and acknowledgement only after durable write address the existing control race. The declared linearization point lets a later racing pause govern the next admission; it does not promise immediate cancellation of an accepted child.
- The three child-start paths (`preparation.py:1214,1216,1218`) and three cancellation paths (`:1278,1291,1304`) are explicitly suitable for the captured-authority wrapper. Root execution uses `JobStore._run`'s internal record at `actions/jobs.py:1076,1200–1202`; public `_copy_job`/history records should remain unable to authorize execution.

## Coverage and completion boundary

The row-writer inventory includes MCP reservation `:246`; queued maintenance `:564,568,575`; legacy supersession `:879`; submit `:957,988,994,1006`; execute start/stage/pause `:1022,1058,1067,1076`; action reconciliation/retry/reserve/ack/progress `:1138,1160,1178,1186,1204,1229,1288,1340,1350`; matching/workflow/finalization `:1861,1940,1972`; allocation `:2364`; and pre-submit control `:2416`. Separate receipt/inventory/control writers and cross-file canonical mutations are covered by DA-2. Release/registry paths are `submit` cleanup `:909–911`, `_release_lease :914–919`, finalization `:1962–1975`, and observation cleanup `:452–454`.

Revisions should preserve the existing bounded first slice and its staged followups. The report does not demand provider circuits, distributed fences, backup epochs, general wake infrastructure, or acceptance-policy redesign now. All A01–A20, FP-01–FP-30 and M0 remain required and open; named partial contributions are not closure of those obligations. A subsequent contract review should check DA-1 through DA-4 before adopting this as implementation-ready.

Only source/document text reads and this owned Markdown write were performed. No source edits, Git operations, tests or collection, builds, typechecks, project imports, DB/key/crypto operations, runtime/process inspection, live calls, provisioning, or subagents. No serving-source identity, deployed behavior, actual OS-lock operation, crash recovery, or external-child ownership was verified. Repository and session constraints, rather than historical memory, govern the present review.
