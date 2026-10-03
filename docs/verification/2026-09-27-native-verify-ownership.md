# Native package-verifier ownership — 2026-09-27

Status: source independently approved after two lifecycle repair rounds and one
test-fixture correction. The `.14` installed selection passed 139 checks and final
independent artifact review approved. This advances bounded P0.3; general compiler, Wine,
project and store ownership remain open.

## Intended delivered behavior

The existing `recover.verify-package` catalog action reserves its actual output
tree before mutation. Its versioned native Clang profile controls the child Python
startup, compiler arguments, environment, scratch directory and pinned compiler
and resource identities. The child validates the metadata it actually consumes.
Selected source, metadata, manifest and target-slice inputs cannot alias outputs.
Supported C and C++ verification retain separate compilation results and process
lifetime evidence; compilation success alone cannot release ownership.

Release requires the trusted default executor's observation bound to the same
job, attempt, command, output claim and qualified process session. Historical
unguarded executions remain conservative. A diagnostic module-origin record
helps verify installed execution but never grants clearance authority.

## Source evidence

The corrected broad selection passed **127 tests in 52.48 seconds**. Subsequent
helper refinements passed **38 tests in 33.17 seconds** against the frozen helper.
These runs precede the lifecycle repair and are not final-snapshot acceptance.
The first broad run had seven fixture-path expectation failures; the retained
claims showed outputs stayed inside the test's owned workspace. The fixture was
corrected to distinguish catalog-provided defaults from absent context.

Independent lifecycle review found that modern requests rejected before dispatch
could restore as permanently quarantined owners. Actual queued jobs already have
an attempt UUID, so absence of a process record does not distinguish them from
historical uncertain execution. Repair one adds explicit versioned non-dispatch
evidence, including initial queued persistence, and requires durable invalidation
before invoking any executor. Missing or mismatched evidence remains conservative.
The first repair run exposed asynchronous initial receipt persistence; the
implementation now writes non-dispatch observations synchronously. Scoped review
then found a cancellation window between freezing command inputs and updating
their bound observation. Repair two publishes both atomically, with an actual
start → wait for occupied output → cancel → restore regression.

The source selection before the installed fixture correction passed **139 tests in 37.30 seconds**: 49 native
ownership checks, 52 existing resource checks and 38 adjacent MCP/accounting
checks. Both independent source review scopes are approved, with no open P0/P1.
Final reviewed hashes are recorded in `frozen-hashes.json` beside the raw logs:

- `native_verify_contract.py`: `2ef32d421d4179d9f231835042f9cc1f4bdc50e0747828bbbdfe35832cc47f5e`.
- `package_verify.py`: `8e10aab5e333ccb5a079db05c2b913c5a89f62892cfed12210574ff4d8841080`.
- `jobs.py`: `631585b67bcd566ec0cbcadb4d38183ea143c9aedfcb68f6743e65d589ca6ad8`.
- `introspect.py`: `e6de993ad3ea92c4e51eb31d312246d755a27f1c397f02eb86e4cd2798838cae`.
- `test_native_verify_ownership.py`, after the separately reviewed fixture correction: `e31136c500ed2b703cd2737b4cd4bfe32434c6093fd5d5e7965235a100c2f832`.

Source, review and packaging reports are retained under
`/home/brunner56/Documents/AgentDecompile-native-verify-*.md`. Raw source logs are
under `/home/brunner56/native-verify-ownership-evidence/`.

## Installed qualification

The genuine `.14` wheel built and installed into a separate runtime. The first
installed selection passed 137 checks and failed two synthetic surviving-child
fixtures in 34.70 seconds. A retained startup probe showed the child was alive
but had not installed its SIGTERM handler through 4.01 seconds; the fixture's
fixed cancellation/timeout timers ran before readiness. The independently reviewed
test-only repair isolates nested Python startup, requires a bounded post-handler
readiness signal and checks PID/start identity for cleanup. It preserves the same
quarantine assertions. Its two affected source checks passed in 13.42 seconds.
Product bytes stayed unchanged; the wheel was not rebuilt or reinstalled.

The corrected full installed selection passed **139 tests in 33.75 seconds**.
Five actual native-child witnesses identify the installed modules and exact guarded
`-I -S` bootstrap/payload. Seven parent/ordinary-process origin receipts also
resolve to installed bytes. These diagnostics support execution provenance;
session-bound executor observations remain clearance authority.

The genuine PEP 517 wheel is `2.0.1.dev0+autonomy20260927.14`, retained under
`/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-native-verify-ownership/`.
Wheel SHA-256: `3f24bb4dabebe81c96009d83045cb199e110a5bc8865c166f9f685c2531e2094`.
Source/test reproduction archive SHA-256:
`5258561d2f1dc766b20d17e92ef54670cd04a2ff1518917ba8aeaa36ddd6d858`.
The parent independently checked all 601 members against the accepted `.13` base
with wheel-version path normalization: 594 byte-equal, four approved overlays and
three generated version/metadata members, with zero removed members. All 42
static/webui assets are preserved. Both installed attempts, exact commands, the
startup probe and original/final fixture evidence remain retained. Final independent
artifact review approved all member/source/test lineage, actual child/session
evidence, 604 archived source-manifest entries and both retained fixture sets.
The review is a companion to the frozen archive; the archive was not rewritten.

## Remaining boundaries

The narrow profile excludes arbitrary compiler flags, wrappers, Wine and external
code-comparison providers. It does not establish complete transitive include
confinement, a hostile-filesystem sandbox, detached-writer coverage, ABI correctness
or whole-image recovery. Interpreter, implementation and administrator-owned
toolchain files must remain stable during an attempt.

8080 had no listener at preflight. No service or live recovery was started, and
this source/package work does not establish activation or live qualification.
