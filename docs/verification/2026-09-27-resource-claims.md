# Qualified local output ownership — 2026-09-27

Status: independent scoped source review approved after one fix round; included
in development wheel `.12`, whose installed regression selection passed 113 checks.
Partial P0.3 and D36. No serving activation, live recovery or whole-image claim.

## Delivered boundary

The catalog job store now declares the mutable resource for one audited action:
`corpus.export-reagent-snapshot` owns its `destination` output tree. The actual
exporter reads SQLite in read-only/query-only mode, closes the connection and
writes its private destination synchronously. Generic parameter-name inference
was removed: it incorrectly reserved read-only compiler scripts, missed real
hyphenated output arguments, and stranded successful exports in quarantine.

The trusted default executor must observe local process-session clearance bound
to the exact job, attempt, resource claims, argv digest and stable process identity.
Only that qualified lifecycle can release the output reservation. An injected
executor returning success or missing/mismatched clearance leaves quarantine.
Execution root and claims freeze before dispatch, so changing the configured root
cannot redirect a queued job away from the tree it reserved.

Equal and ancestor/descendant filesystem paths conflict across resource kinds.
Restoration validates canonical paths and known kinds. Unknown historical external
release labels retain their claims; logical-build clearance cannot clear them.
Ambiguous duplicate/overlapping owners are refused before reservation maps are
partly installed. This avoids silently losing the first owner during restoration.

## Evidence

At source preflight, the existing 8080 service refused connection. No replacement
service, alternate port, recovery, game or compiler operation was started.

The implementer's isolated source run completed with exit 0: **52 passed in 2.19s**.
The real-contract case uses the actual argparse-derived catalog specification,
command builder, default subprocess executor and CLI exporter against a one-row
SQLite fixture under `/dev/shm`. It checks the emitted manifest, bound clearance,
terminal release, frozen root and restoration. The real exporter case also checks
`~/out` with a literal `cwd/~` present; canonical params, argv and resource keys
must agree and no output may appear in that literal directory. Other cases exercise retained
ownership, missing/mismatched proof, overlap and malformed/ambiguous receipts.
This is an actual offline export with synthetic input, not a real-target receipt.

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/dev/shm/ad-resource-contract-stage/src .venv/bin/python -m pytest -q -o addopts= -p no:cacheprovider --confcutdir=/dev/shm/ad-resource-contract-stage /dev/shm/ad-resource-contract-stage/test_job_resource_quarantine.py --basetemp=/dev/shm/ad-resource-contract-stage/tmp-review1-final
```

`git diff --check` passed for the assigned source/test paths. No broad suite or build ran.
Independent review found a tilde interpretation mismatch in the initial 51-test
version. The correction canonicalizes the destination and rebuilds the actual
command before admission; the 52-test result covers that corrected source. The
reviewer approved the correction and found no remaining P0/P1 within this explicit
snapshot lifecycle. They inspected source and test mechanisms without rerunning
the implementer's tests. The parent independently rechecked the final file hashes.

Baseline HEAD: `20c1941b1e8c00931bc5103da07c47b210eb8ec3`; changes are uncommitted
alongside preserved pre-existing work. Exact final source hashes:

| File | SHA-256 |
|---|---|
| `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py` | `4cfef91601e14d26ec371913a7273854beebf39041b189f48f0812bcd2abaaab` |
| `tests/test_job_resource_quarantine.py` | `a80663b9af595e5d21552bceb039e19175e6416208bc622b8bf26c5e600d7287` |

The task brief, implementation report and review package are retained outside the
codebase in `/home/brunner56/Documents/AgentDecompile-resource-contract-*.md`
and `AgentDecompile-resource-contract-review.diff`.

## Remaining boundary

General compiler/Wine/project/store bundles, complete generation fencing,
uncertain remote-owner reconciliation and cross-root/distributed authority remain
open. Declared path coverage does not prove lifetime control over external writers
or namespace changes. This slice is packaged in `.12` but has not been activated. P0.3,
D36 and M0 remain partial; all other contract acceptance states are unchanged.

The subsequent [nested MCP budget increment](2026-09-27-nested-mcp-budget.md)
also changes `jobs.py` and reruns these resource regressions. The hashes above
identify this reviewed source increment; the later receipt records its own final
source and package identities rather than presenting these historical bytes as
the current file.
