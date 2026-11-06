# Autonomous continuation foundation — implementation receipt

Date: 2026-09-22. Scope: the product implementation explicitly requested after the
design-only phase. [Roadmap](../plans/2026-09-22-autonomous-capability-product-roadmap.md)
is the feature/acceptance authority; [usage](../../USAGE.md#durable-continuation-and-verification-controls)
describes the public controls. This receipt does not establish live recovery,
whole-image parity, runtime modding or completion of M1–M7.

## Implemented

- Existing recovery supervisor persists launch intent before dispatch, stable
  execution basis, per-basis failed-exit budget, cooldown and output-root ownership.
  Prior uncertain launches retain reservations. A reaped leader requires observed
  session/process-group clearance; occupied or unknown membership retains the scope.
  Logical repository identifiers remain unchanged. Provider hashing excludes the
  dashboard. Read-only status never creates state or launches work.
- Existing preparation preserves spent attempts across resume, repairs terminal
  receipt reconciliation, treats disappearing jobs as unknown, and retains ownership
  warnings. Shared-KB mtime no longer resets matching retries. Legacy failed spending
  transfers conservatively. Independent eligible pairs can continue. The exercised
  flow also exposed and fixed five-field inventory truncation where later code
  required the full row.
- Verification cache identity includes source and target content, relevant function
  metadata, verifier code, wrapper/preamble and declared compiler closure/environment.
  Incomplete closure withholds cached positives. Unclassified failures expire under
  a rate limit. Known compiler source/type rejection is distinguished. Output receipt
  invalidation happens under the held lock; failed lock acquisition preserves the
  prior owner's receipt. Periodic full audits default to time-based admission and
  charge failed attempts too.
- CLI/catalog parsers expose the controls; static and React preparation views show
  recorded decisions, reasons, attempts and wake conditions.

## Observed checks

| Check | Result | Evidence boundary |
|---|---|---|
| Combined six-file focused Python suite | 70 passed in 1.65 seconds | Controlled subprocess/catalog/compiler mocks and temporary data; includes real preparation coordinator execution with inert catalog jobs |
| Installed-wheel suite | Same 70 tests passed in 2.74 seconds with installed package on `PYTHONPATH`; consumer `__file__` confirmed installed directory | Bounded software checks on packaged code, not deployed recovery |
| Installed CLI | `verify-periodic --help` passed; supervisor `--status` returned snapshot and left nonexistent output path absent | No worker launch or state creation |
| TypeScript | `tsc --noEmit` passed | Type consistency, no browser interaction |
| Production React build | Vite 6.4.3 transformed 1,103 modules; built in 18.18 seconds | Compiled assets, no running server. Existing large Monaco/language chunks trigger the >500 kB warning |
| Static preparation JavaScript | `node --check` passed | Syntax only |
| Python wheel | Built `2.0.1.dev0+autonomy20260922` using isolated PEP 517 build environment | Package construction, not deployment or binary recovery |
| Package content | Eight changed backend/static sources match canonical bytes; all generated React assets match wheel members | SHA-256 manifest linked below |
| Document/diagram consistency | 46 local links resolved; SVG and draw.io parsed; rendered companion visually inspected | Artifact consistency, no product behavior claim |
| Diff formatting | `git diff --check` passed | Includes the current working diff; pre-existing dirty files preserved |

The test files are `test_autonomy_cli_forwarding.py`,
`test_durable_supervision.py`, `test_preparation_retry_policy.py`,
`test_preparation_matching_progress.py`, `test_verification_cache_basis.py`, and
`test_verification_periodic_audit.py`. Source was staged under
`/home/brunner56/.cache/agentdecompile-autonomy-m7w5gp5r`. The test command used
`/usr/bin/python3 -m pytest --noconftest -c /dev/null -p no:cacheprovider`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, the staged `src` on `PYTHONPATH`, and those six
files. This intentionally avoids the broad repository conftest/runtime integration
setup. It does not report the full project suite passed.

[Built wheel](/home/brunner56/.cache/agentdecompile-autonomy-m7w5gp5r/dist/agentdecompile-2.0.1.dev0+autonomy20260922-py3-none-any.whl)

SHA-256: `19ebcf5cea69a8701244728ec68c674ec2e4df7c24139b4008a38c762accfb94`.

[Package/source manifest](/home/brunner56/.cache/agentdecompile-autonomy-m7w5gp5r/build-evidence.json).
[Wheel build log](/tmp/agentdecompile-autonomy-wheel-build.log).
The wheel uses an explicit development version; the pre-existing canonical version
file was not rewritten by the build. The snapshot includes pre-existing working-tree
changes, including parity changes; this is not represented as a clean release.

## Limits and next acceptance

No 8080 listener or matching server was found during source preflight. No server,
port, game, Wine, Ghidra or recovery worker was started. Canonical source edits and
isolated installation do not activate the historical NVMe service checkout. No
external publication was performed.

The source-copy and some interpreter loads temporarily stalled in kernel disk I/O.
Both the nominal NVMe virtualenv Python and bundled Node runtime resolve back onto
MyBook. The completed checks used `/usr/bin/python3` and `/usr/bin/node` instead.
The source snapshot eventually completed; this is evidence of successful construction,
not proof of an entirely storage-independent runtime closure.

The supervisor lock covers this supervisor's output scope. It does not coordinate
all external writers. Session membership does not contain deliberately detached
children or replace a resource lease/cgroup. Provider hashing covers corpus provider
code, not a discovered complete runtime closure. Unknown outcomes intentionally
require reconciliation; the general automatic reconciler remains future work.
Verification TTL is a rate limit, not a total objective spending cap. Existing local
comparison masking and reference semantics remain unchanged and are not whole-image
acceptance. Compiler dependency completeness is declared, not automatically inferred.

ReAgent and reccmp were researched for their planned reconstruction/comparison
adapters. They were not run against binaries in this change: the implemented checks
are continuation/cache logic and no recovered candidate is being accepted. Actual
binary testing will require those adapters plus AgentDecompile and an eligible pinned
fixture under the existing catalog ownership procedure. The broader live behavior,
capture, supported-platform and browser acceptance matrices remain unexecuted.
