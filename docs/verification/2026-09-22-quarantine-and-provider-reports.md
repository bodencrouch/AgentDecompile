# Catalog quarantine and external diagnostic reports — 2026-09-22

This is a bounded implementation receipt under the active
[session goal/audit](../plans/2026-09-22-session-obligation-audit.md). It extends the
[foundation receipt](2026-09-22-autonomy-foundation.md); the original wheel remains
historical evidence for its own hashes. The broader goal is not complete.

## Delivered behavior

The existing JobStore now reserves identity/pair/Ghidra keys with fsynced admission
intent in the existing `workbench-jobs` receipts. One lifetime flock per receipt root
serializes scoped admission authorities. A second store/process cannot independently
restore an empty scope and admit a conflicting writer. Held/quarantined and relevant
legacy interrupted receipts restore reservations before new scoped work; malformed
keys, corrupt receipts and unknown unresolved legacy actions refuse admission.

Unknown process outcomes, uncertain remote dispatch, executor exceptions and failed
terminal receipt commits retain resource reservations while releasing the worker
slot. An unrelated qualified resource scope can proceed. Receipt versions plus
serialized writes prevent a delayed asynchronous snapshot overwriting a newer
reservation. History owner-death observation is now a read-only projection, avoiding
another stale-write path. Receipt-only held state projects as quarantined.

MCP transport failure after starting the tool call records unknown ownership.
Initialization failure before dispatch stays separate. Acquisition/open/checkout
and repository retry stop on uncertain effects before replaying or marking ready.
MCP executor and archive wrappers preserve the uncertainty even when the local thread
returns. Preparation honors typed quarantine independently of misleading log JSON.
Both activity surfaces display unknown ownership; React suppresses its retry shortcut
for quarantined jobs and includes them in Needs attention.

The supervisor now declares mutation, long-running, database and Ghidra ownership
metadata in its generated catalog row. Only actual boolean `status=true` gets the
read-only inspection bypass; string truthiness cannot skip admission.

A new read-only `corpus.normalize-validation-report` action/CLI reads ReAgent
benchmark and reccmp comparison JSON. It hashes raw report bytes, validates known
schema shape and produces diagnostic proposals with `recovery_accepted=false`,
`provenance_verified=false` and unknown execution state. Expected-negative benchmark
success remains a candidate mismatch. Empty reports, duplicate keys, nonfinite
numbers, numeric overflow, excessive decoder nesting and unsupported formats are
invalid output. Omitted reccmp entities and unbound benchmark cases never become a
known complete denominator. No provider execution or accepted-corpus mutation is
performed by this reader.

## Validation observed

| Check | Result | Scope |
|---|---|---|
| Combined ten-file Python suite against staged source | 126 passed in 4.44 seconds | Controlled executors/transport and private fixtures; no live game/Ghidra/recovery |
| Same suite against installed wheel | 126 passed in 2.36 seconds | Packaged Python code, host dependencies; not a clean-machine dependency qualification |
| TypeScript | `tsc --noEmit` passed | Type checking |
| Production React | Vite build passed in 19.91 seconds | Generated assets; existing large-chunk warning remains |
| Static activity surfaces | Node syntax checks passed | Syntax, not browser interaction |
| Wheel build | PEP 517 isolated build succeeded | Development package, not serving deployment |
| Package content | 13 changed/relevant source members equal canonical bytes; generated React assets equal wheel members | Hash manifest below |
| Actual upstream outputs through AgentDecompile CLI | ReAgent outcomes `matched`, `mismatched`; reccmp one reported row/two provider functions/unknown eligible denominator | Real provider benchmark output and real serializer output; no reccmp binary comparison |

Suite files: `test_autonomy_cli_forwarding.py`, `test_durable_supervision.py`,
`test_preparation_retry_policy.py`, `test_preparation_matching_progress.py`,
`test_verification_cache_basis.py`, `test_verification_periodic_audit.py`,
`test_job_resource_quarantine.py`, `test_mcp_ownership_uncertainty.py`,
`test_job_progress.py`, and `test_external_validation_reports.py`.

Checks used `/usr/bin/python3`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`pytest --noconftest -c /dev/null -p no:cacheprovider`, the registered unit marker,
and explicit staged/installed `PYTHONPATH`. They do not claim the full repository
suite or broad integration conftest passed. Stage:
`/tmp/agentdecompile-autonomy-next-3hbfthg_`.

The [external-provider receipt](2026-09-22-external-tool-canaries.md) records actual
pinned ReAgent matching/expected-negative harnesses, a synthetic `ghidra-json` plan,
and reccmp positive/negative annotation lint. For an additional schema check, the
installed reccmp serializer produced a synthetic report with one matched and one
unmatched entity. The actual serializer omitted the unmatched entity but retained
function_count=2. AgentDecompile preserved that coverage limitation. This exercises
upstream serialization, not PE/PDB comparison.

Independent review identified and corrected unknown MCP returns, nested/late JSON,
malformed restored keys, multiple local authorities, stale async writes and malformed
normalizer input. Review agreement is not broader runtime acceptance.

## Built artifacts

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-22-quarantine/agentdecompile-2.0.1.dev0+autonomy20260922.1-py3-none-any.whl)

SHA-256: `091f6a1118eef257abc5e78e218a08cb39e77378b12d40ea33de935d74301f57`.

[Source/package hash manifest](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-22-quarantine/build-evidence.json),
[normalized ReAgent report](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-22-quarantine/normalized-reagent.json),
[normalized reccmp serializer report](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-22-quarantine/normalized-reccmp.json).

The canonical pre-existing version/parity changes remain preserved. Builds use
explicit development versions in private staging and include the existing working
tree context; these are not represented as clean release builds. No publication or
installation into a live serving checkout occurred.

## Remaining obligations

No general resource-clear API or automatic owner reconciliation is implemented.
Clearance is never inferred from age or a stopped coordinator. Different receipt
roots sharing external corpus/compiler/prefix/output state, external writers and
deliberately detached descendants remain outside this local authority's proof.
Full cross-resource fencing, objective/incident budgets, durable wake coordination,
complete dependency discovery and scientific acceptance/invalidation remain open.

The report normalizer is only part of an external adapter. Production provider
execution, immutable invocation/input binding, real cached-analysis export, supported
PE/PDB comparison, candidate acceptance, source contribution and live native/browser
capabilities remain unverified. No server, alternate port, game or Ghidra process
was launched. Provider installation built JPype as an upstream dependency; no JVM
or live analyzer was invoked. The active goal retains all these remaining requirements.
