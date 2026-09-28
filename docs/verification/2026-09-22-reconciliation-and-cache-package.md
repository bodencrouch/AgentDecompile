# Committed-release reconciliation and cached ReAgent evidence — 2026-09-22

This bounded increment follows the [quarantine receipt](2026-09-22-quarantine-and-provider-reports.md).
The [session goal](../plans/2026-09-22-session-obligation-audit.md) remains active.

## Implemented behavior and limits

Two existing-catalog actions accept only `job_id`: `workbench.resource-reconciliation-report`
reports missing evidence, and `workbench.resource-reconcile` repairs a stale reservation
from an already committed full-action terminal release. Eligible repair also occurs
on the next scoped admission. Internal executor callbacks bind clearance to the job,
attempt, command digest, resource keys and process identity. Receipt generation and
terminality are checked again, then the repair decision is committed before maps are
released. Child stdout cannot supply clearance. Failed scientific work remains failed.

Only `corpus.logical-build` is initially qualified for this local lifecycle proof.
Unknown prior launches, remote MCP effects, compiler/Wine work, detached descendants
and external writers still require provider-specific reconciliation. This is not a
general release mechanism for uncertain ownership. Independent code review found no
unsafe-release blocker in this narrow predicate; tests also retain reservations on
failed writes before and after receipt replacement and reject malformed timestamps.

`corpus.export-reagent-snapshot` now exposes bounded selected existing cache rows
through CLI/catalog. It reads a coherent SQLite snapshot, creates a private new output,
preserves source/assembly and available metadata, hashes materialized rows/files, and
publishes the manifest last. Missing context stays missing. The existing cache schema
has no corroborated original-binary digest, so binary binding remains unverified.
The [real-cache consumer receipt](2026-09-22-reagent-cache-export.md) records actual
pinned ReAgent consumption of one existing cached function with nine evidence gaps.

## Verification

- Combined eleven-file source suite: **153 passed in 4.35 seconds**.
- Same suite against the installed wheel: **153 passed in 2.91 seconds**.
- Focused canonical-source ownership suite: **37 passed in 75.69 seconds**, including
  an observed storage wait; focused exporter/CLI suite: **13 passed in 38.85 seconds**.
- PEP 517 wheel build and isolated target installation succeeded using system Python.
- Fifteen changed/relevant source members match canonical bytes and wheel members.

The ten previous suite files are listed in the [preceding receipt](2026-09-22-quarantine-and-provider-reports.md);
this increment adds `test_reagent_snapshot_export.py`. Tests used private `/dev/shm`
staging/fixtures, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `--noconftest -c /dev/null`, and
explicit source/installed `PYTHONPATH`. `/tmp` fixture failures were observed before
moving these owned checks to `/dev/shm`; they are not represented as product failures
or silently omitted successful attempts. Full repository/live integration was not run.

Stage: `/dev/shm/agentdecompile-autonomy-20260922-2`.
The frontend source is unchanged; previously built assets were reused. No fresh
browser, live server, recovery, binary comparison or game-runtime result is claimed.
8080 had no listener at this increment's preflight; no replacement server was started.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-22-reconciliation/agentdecompile-2.0.1.dev0+autonomy20260922.2-py3-none-any.whl)

SHA-256: `3b1da4661fcda431f890020c3d03301a82162306ea29e5ecefc40fa3e5d9596c`.

[Package/source hash manifest](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-22-reconciliation/build-evidence.json).
The package includes preserved working-tree context and is a development artifact,
not a clean release or activation into a serving checkout.

## Remaining work

The audit still retains general provider reconciliation, complete resource fencing,
objective-wide budgets, durable wake coordination, dependency closure, source-contribution
and false-label acceptance gates, job-owned external provider execution, supported
PE/PDB comparison and all higher product milestones. These bounded tests do not close
those complete requirements. The pinned reccmp Linux comparison path invokes Wine
and cvdump; annotation lint/serializer checks are not substitutes for that qualified
binary-comparison lifecycle.
