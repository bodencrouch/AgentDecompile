# Preparation-owned MCP dispatch accounting — 2026-09-27

Status: backend and consumer source independently approved; isolated development
wheel built and 113 installed checks passed. Independent artifact review approved.
Partial P1.1 and D31; no live acceptance claim.

## Contract and reason

One preparation action can invoke project/program setup, a primary MCP tool,
session recovery and check-in. The existing action-admission allowance charges
that root action; it does not count the nested calls. This increment introduces
an independent optional `maxMcpToolCalls` allowance in the existing preparation
receipt, exposed as `providerBudget` with scope
`mcp-tool-dispatches-since-allocation`.

Each actual `tools/call` needs a durable reservation before dispatch. Prerequisites,
retries and check-in count; local cached observations do not. Lost responses and
crashes do not refund spent intents. Resume preserves spending and allocations;
old runs disclose unknown earlier usage. This counts calls made by the dashboard
bridge, not tokens, money, CPU, external subprocesses or work inside a provider.

`workbench.prepare` accepts the initial cap. The existing
`workbench.workflow-control` catalog route adds `provider-budget`, using the
provider allocation's `expectedAllocationRevision`, a new total `maxMcpToolCalls`,
or explicit `unlimited=true`. Changes require the existing coordinator lease to
drain and preserve consumed reservations. The action-admission and wall-clock
controls remain separate.

Trusted dispatch authority is a private in-process capability attached before
job startup, bound to the original preparation row, coordinator lease and parent
dispatch. It is not request metadata or a capability restored from JSON. A late
child cannot write through a replaced/closed coordinator lease. Quota refusal
must remain a specific blocked reason and allocation-revision wake condition
through setup/retry wrappers. A refused check-in cannot certify an earlier
mutation as saved or clear unresolved ownership.

## Operator projection

Static and React preparation views show MCP usage alongside action admissions,
including compact React. Missing or malformed information remains unknown;
explicit null means unlimited, zero is a finite exhausted cap, and migrated
unknown prior usage remains a lower-bound caveat. Disconnected/resync/stale
observations retain their counts and timestamps with current usage marked unknown.
The existing catalog provides controls; this increment adds no second scheduler,
progress store or control panel.

## Source and installed evidence

Frontend worker: **38 focused checks passed** on the byte-matched retained
lockfile installation (Vitest 5.0.1), including React full/compact and actual static
htm SSR. Full-project TypeScript with real Monaco types, static JS syntax and a
fresh Vite production build passed. Existing large-chunk build warnings remain.
The earlier missing-Monaco typecheck and SSR key warnings came from the first
validation runtime; the matching-lockfile run supersedes that limitation and had
empty test stderr. This reused a verified local install, not a fresh installation.

The independent frontend review approved the exact four-file delta with no
P0/P1 findings. It inspected source/test mechanisms and saved execution evidence;
the parent confirmed unchanged source hashes after the locked verification.

Backend worker: **110 focused checks passed**, including the prior 52 resource
lifecycle cases and 17 new MCP budget cases. The new route reaches actual
preparation, JobStore, executor and bridge code with a fake RPC transport. It
checks durable intent ordering, nested setup/retry/check-in, stale authority,
revision/resume, private handoff and bounded public projection. The only warning
is the existing unit marker under an intentionally empty pytest configuration.
Independent review found nested uncertainty could be lost before a later quota
refusal. The correction retains object/list/JSON-string uncertainty and normalizes
duplicated transport wrappers so ordinary successful payloads are not falsely
quarantined. The 110-case result covers the correction. Scoped re-review approved it with
no remaining P0/P1, preserving both genuine uncertainty and ordinary successful
responses. Source hashes were independently matched to the final report.

Before packaging, the parent identified the same uncertainty boundary with spare
budget. Two fixtures reproduced an unresolved missing-session response being
replayed and an adapter reporting success after scoped uncertainty. The correction
now refuses repair/replay, blocks further bridge dispatch before another charge,
and checks retained uncertainty on every terminal executor return. **113 focused
source checks passed** after this correction, with the same existing marker warning.
Independent round-two review approved the correction with no remaining scoped
P0/P1. It checked unbudgeted uncertainty preservation statically; the terminal-success
regression uses a budget callback, so separate unbudgeted runtime coverage is not
claimed. Isolated packaging has resumed using these final hashes. The earlier
110-case approval is historical.

Locked frontend assets: `/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-mcp-budget-ui-locked/frontend-assets.tar.gz`.
SHA-256: `07c82a4507c32af923cf5b1a8bb4eae163d3ebd1e4df169add2e73c2b855dd9f`.
They are prepared for the isolated wheel stage, not activated assets.

Reports and briefs are retained outside the codebase under
`/home/brunner56/Documents/AgentDecompile-mcp-budget-*.md`.

## Installable artifact

The genuine PEP 517 development wheel is
`2.0.1.dev0+autonomy20260927.12`, retained in
`/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-nested-mcp-budget/`.
Its SHA-256 is `5dafeb779fdd711ff01a3e68ba1746dac4d45737286e418d2e9776773083dc3a`.
It explicitly reuses verified `.11` members, overlays the final reviewed backend
and static changes, and includes the locked frontend build above. The parent
independently checked every member against the provenance manifest, all five backend
overlays against current reviewed source, and all 23 locked static/React assets.

The 599 members comprise 564 byte-equal reused members, six reviewed overlays,
22 locked frontend assets and seven generated metadata/version files. Static JS
is classified as a reviewed overlay and also belongs to the 23-asset verification.
A fresh isolated `--no-deps` installation passed **113 checks in 14.93 seconds**,
with the one existing unit-marker warning. All 14 applicable declared runtime
dependencies satisfied their constraints. Installed-origin evidence and subprocess
coverage are recorded in the packaging report. Independent artifact review verified
all member/asset hashes, final source/test revisions, all four installed-origin
receipts and both actual snapshot-export subprocesses, with no scoped P0/P1. Source and installed counts overlap and must not be added.

The initial build interpreter lacked build/setuptools and the system interpreter
lacked setuptools-scm. An isolated build-tool environment acquired pinned declared
build dependencies and required transitive tooling; retained archives include
hashes and command logs. Canonical and system environments were not modified.

## Remaining boundaries

8080 had no listener at source preflight. No replacement service, alternate port,
Ghidra operation or live recovery was started. This is source preparation.

Shared provider recovery circuits, remote-provider internal fan-out, external
subprocess usage, incident-wide budgets and general uncertain-owner reconciliation
remain unfinished. A refused call is not evidence of whole-objective completion.
P1.1, D31, M0 and the full session goal remain open at their existing scopes.
