# Task 21.1 implementation report

Status: READY_TO_COMMIT. Source slice implemented; controller review and integration remain. No staging or commits were performed by this implementer.

Authority: `task-21-brief.md`, Slice21.1, and `next-filtered-matrix-slice.md`, read before implementation. Dispatch source basis was `1d468be572b2c8f161ced8527445b49ad352f321`; other owners' concurrent changes were preserved. The source-only mission overrides the generic SDD implementer template's test/run/commit recipes.

## Implemented contract

- `build_report` and `progress_report` now accept optional keyword-only `logical_id: int | None = None`. The exact internal integer must be positive and at most `9007199254740991`; booleans, strings, floats and out-of-range integers refuse before reading a corpus. `None` retains unfiltered behavior.
- The existing progress-report HTTP route uses `getlist("logicalId")`. Absence means `None`. A present value must have one canonical ASCII decimal representation without a sign, leading zero, whitespace or extra occurrence. Explicit empty/repeated/malformed/out-of-range input returns the existing structured HTTP 503 unavailable envelope. It never retries without the filter.
- Selected requests require slug, corpus identity and the content-hash version. The selected binary is re-derived from the existing read snapshot; duplicate slug matches refuse, and the builder independently rechecks one recorded binary ID/root and exact content-hash version. Corpus/version/schema/read/deadline failures retain unavailable/stale outcomes and their causes.
- Selected reports and their projections carry exactly `selection_scope: {"kind": "logical_function", "logical_id": <integer>}`. The scope and the recorded `selection_root` stable key enter the canonical report payload before hashing. These inventories and measures describe only selected physical members. No scope/root fields are added to an unfiltered report, and the unfiltered projection shape remains unchanged.
- The selected projection starts with the one validated recorded root, including its `canon_key` or existing `logical:<id>` fallback. A real zero-member selection yields exactly one zero row. Missing/duplicate/malformed roots and malformed/conflicting membership refuse rather than becoming observed zeros. Selected projections have `unbound: null` and `unbound_status: "not_requested"`.

## SQL and classifier boundary

Selected mode validates ordinary table definitions and consumed columns for `binary`, `func`, `identity` and `logical_function`. A present `recovered_function` must also be an ordinary usable table with consumed columns. Views/virtual tables/missing columns refuse; an absent optional source table retains unclassified behavior.

The selected identity read obtains only claims for `(logical_id, binary_id)` and validates exact IDs, nonnegative integer addresses and uniqueness. Physical function reads are filtered before fetching:

```sql
SELECT f.addr,f.name,f.size,f.ranges FROM func f WHERE f.binary_id=?
AND EXISTS (SELECT 1 FROM identity s WHERE s.logical_id=? AND s.binary_id=? AND s.addr=f.addr)
ORDER BY f.addr
```

Parameters are `(binary_id, logical_id, binary_id)`. Function addresses must be unique and equal the selected membership address set; missing/duplicate functions refuse. No `DISTINCT` hides malformed rows.

All identity claims at selected addresses are then read, including foreign logical claims:

```sql
SELECT i.logical_id,i.binary_id,i.addr FROM identity i WHERE i.binary_id=?
AND EXISTS (SELECT 1 FROM identity s WHERE s.logical_id=? AND s.binary_id=? AND s.addr=i.addr)
ORDER BY i.addr
```

Parameters are `(binary_id, logical_id, binary_id)`. This query deliberately does not constrain `i.logical_id` to the selected ID. Duplicate/conflicting claims refuse before classification.

Advisory candidates use the existing target/source qualification, with selected membership enforced before fetching:

```sql
SELECT r.addr,r.source_sha256 FROM recovered_function r
WHERE r.binary_id=? AND r.target_sha256=? AND r.real_c=1
AND EXISTS (SELECT 1 FROM identity s WHERE s.logical_id=? AND s.binary_id=? AND s.addr=r.addr)
ORDER BY r.addr,r.source_sha256
```

Parameters are `(binary_id, target_sha256, logical_id, binary_id)`. The existing source/receipt tier classifier and `reconcile_inventory` remain the only producers. Unknown and multi-range extents remain unknown, with selected byte totals/tier byte counts/per-unit byte measures null where coverage is unknown. Independent union accounting remains unchanged; overlapping per-bucket unions cannot be added into whole-image coverage. Function/source tiers are not reclassified merely because an extent is unknown.

No cache, schema migration, batching service, parallel classifier, independent acceptance provider or synthetic corpus generation was introduced. Every request reads current source/identity rows in its own existing snapshot. Projection provider remains `not_connected`; verified function and byte counts remain null even if an existing independently qualified receipt classifies a source member.

## Current consumers

The static `LogicalMatrix` and React `LogicalNavigator` requests now send `logicalId`. Both cell validators require:

- Canonical safe selected ID and the existing exact corpus/build/content-hash version gates.
- Equal exact report/projection selection descriptors, and `unbound: null` with `not_requested`.
- Exactly one row whose integer logical ID equals the selected ID; missing, duplicate and mixed-scope rows refuse.
- Matching report/projection build basis and digest, exact hash syntax/length, existing member count-to-set equality, disjoint tier sets, unavailable/null verified metrics, provider and stale/error gates.

Existing equal-content binary request keys and abort/stale-completion guards were preserved. The whole-binary `TierProgress` progress-card request path was not changed.

## Regression sources added or adapted; not executed

`tests/test_selected_progress_reports.py` adds fixture-based sources for two-build selected membership, recorded empty vs absent root, SQL returned-row/filter boundaries with unrelated functions/candidates, default/explicit-None report compatibility and canonical scope hashing, independent extent unions and unknown/multi-range byte uncertainty, existing receipt classification/provider separation, exact internal IDs, malformed/missing/optional schemas, malformed/duplicate/conflicting roots/functions/memberships, fresh advisory/identity changes, selected target/corpus/version/filter mismatches, SQL/deadline failure propagation, and canonical/invalid/repeated HTTP forwarding/refusal.

`SelectedMatrix.test.tsx` uses existing Vitest and the repository's hook shim/VM source slicing. It adds mirrored React/static validator cases for scope/row/build/version/digest/conservation/provider/unknown-byte/zero-member gates; both requesters' selected query, equal-content refresh stability, and changed-selection abort with deliberately late stale completion. Hook-shim tests cannot substitute for browser DOM acceptance.

The directly touched `coverageMatrix.test.tsx` expected the obsolete sentence `Locator status is not shown.`. The current component no longer renders that sentence. The assertion now checks the current explicit unavailable-tier display with no exact selected basis; its read-only table and locator-status refusal assertions remain.

No regression was run and no RED/GREEN or passing-test result is claimed. The task's explicit execution prohibition prevents TDD execution.

## Source checks performed

1. Standard-library `ast.parse` read the changed `objdiff_report.py`, `progress_reports.py`, `router.py`, and new `test_selected_progress_reports.py` without importing or executing project modules: all four parsed successfully. The final source pass also checks that `build_report` has no `logical_id` Store binding that could shadow its parameter.
2. `node --check src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`: exit 0, no diagnostics. This is syntax-only and does not run the browser application.
3. `git diff --check -- <seven tracked owned paths>`: exit 0, no whitespace diagnostics. Read-only source whitespace checks cover both new regression sources and this report as well.
4. Read-only source/diff review corroborated the SQL filters, same-snapshot path, descriptor-before-hash ordering, positive safe-ID limit, structured refusal forwarding, matrix scope/row/member/provider gates, unchanged content-derived keys, and unchanged progress-card requester.

These checks are source/syntax evidence only. No project import, DB creation/query, filesystem test, test suite, typecheck, build, proof script, browser run, server/process/catalog request, systemctl, restart, alternate port or publication was performed.

## Self-review

- Caught and fixed parameter shadowing in the legacy unfiltered identity loop: its local `logical_id` now uses `root_id`, preventing an unfiltered request from accidentally entering selected mode. Added an AST no-reassignment source check.
- Required ordinary optional-source tables rather than silently treating a present view/malformed schema as missing source.
- Kept all selected-address identity claims in the SQL query to expose foreign logical conflicts, and refused missing/duplicate function rows rather than hiding them with joins or deduplication.
- Kept multi-range/unknown byte uncertainty in per-unit and report totals as well as the matrix; classifier tier and independent unions are preserved.
- Tightened canonical selected-ID comparison and exact digest length so JavaScript's end-anchor treatment of final newlines cannot admit a malformed selected basis.
- No known outstanding source defect remains from this self-review. Behavior remains unexecuted and requires controller review plus the deferred gates below.

## Exact owned paths

1. `src/agentdecompile_recovery/corpus/objdiff_report.py`
2. `src/agentdecompile_recovery/corpus/dashboard/progress_reports.py`
3. `src/agentdecompile_recovery/corpus/dashboard/router.py` — existing progress-report endpoint only.
4. `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js` — existing matrix requester/validator only.
5. `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/LogicalNavigator.tsx`
6. `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/coverageMatrix.tsx`
7. `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/coverageMatrix.test.tsx`
8. `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/SelectedMatrix.test.tsx`
9. `tests/test_selected_progress_reports.py`
10. `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-21-report.md`

Controller owns plans, progress, Git review/staging/commit and integration. Other owners' target-lane and Mach-O changes were not edited.

## Remaining gates

- Controller review, then controller-controlled integration/commit.
- Later explicitly authorized Python regression execution and Vitest execution, TypeScript validation/build, and installed-client/browser acceptance on both matrices.
- Authorized consumer activation must reconcile the executing source and use the in-process reload contract with unchanged process/state identities; this checkout has not been activated.
- Later measured end-to-end selected-matrix performance, including SQL query behavior/latency on real existing corpora; no measured speedup is claimed.
- Independent input-bound byte-acceptance provider, all remaining U21 metric obligations, terminal whole-image acceptance and explicitly authorized publication remain open. This bounded source slice does not close them.
