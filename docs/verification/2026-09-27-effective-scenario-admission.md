# Effective-scenario operation-identity increment — 2026-09-27

Status: partial G3 implementation for the M1/M2 readiness sequence. This is an
offline schema, report and refusal boundary. It is not a game launch, native-call,
fixture/lifetime, observation, restore or capture receipt.

## Delivered boundary

KotorPhasor's scenario parser now accepts an optional `[operation]` table for a
scenario that is intended to use a generated native operation. The table must contain
exactly these fields:

- `id`, a lowercase stable operation ID;
- `operation_contract_sha256`;
- `target_sha256`;
- `deployed_script_sha256`;
- `fixture_sha256`; and
- `runtime_sha256`.

Every digest is required to be exactly 64 lowercase hexadecimal characters. The parser
refuses missing fields, extra fields, malformed TOML values, noncanonical IDs and
invalid digests. It normalizes no paths or build labels into this identity. Parsed
identity is copied into the scenario `report.json` before execution so a future
lifecycle/observation receipt can state the exact intended operation context rather
than infer it from a route name or source path.

Existing non-operation scenarios remain compatible. That compatibility is not an
authorization path for a scenario that declares a generated native operation: a
declaration must satisfy the complete pin schema. `kpharness run` additionally requires
`--operation-contract` and `--hookpack` for that declared scenario before it constructs
`GameSession`. The preflight hashes the contract file, selects exactly one generated
operation, and requires its target/raw-image digest, selected hook-pack binary and
nonempty roles to agree with the scenario pin. It also requires explicit deployed-script,
fixture and runtime-artifact files; each raw file SHA-256 must match its corresponding
scenario pin before boot.

## Evidence

The focused no-game validation used `PYTHONDONTWRITEBYTECODE=1` and
`/usr/bin/python3 tools/kpharness_offline_test.py -v` in terminal batches for
`TestScenario`, `TestStaging` and `TestOperationLease`.

The focused no-game suite completed successfully: **65 tests passed** in six terminal
batches: all 51 `TestScenario` cases, all seven `TestStaging` cases and all seven
`TestOperationLease` cases. It covers the parser/preflight, owned-staging, boot-gate
and durable lease-admission paths. The cases cover
retention into the report; refusal of uppercase digest text, extra fields,
noncanonical operation IDs and malformed digest values; exported-contract/hook-pack
preflight success plus raw-image mismatch refusal; and supplied script/fixture/runtime
artifact acceptance plus runtime-artifact mismatch refusal. `python3 -m py_compile` and
`git diff --check` were also run for the touched Python files.

Tested KotorPhasor source hashes:

- `scripts/harness/kpharness/scenario.py`: `db815d6bc4e990c3de701af5d8b6e757e36b6a247c184eea0b4aac9d6c625731`
- `scripts/harness/kpharness/session.py`: `87e9995c19bcf73533da183144196bc677666f00a45ea868fdc43657e985d1e6`
- `scripts/harness/kpharness/operation_lease.py`: `cfa278ac99b139a4e4ddd531efa2ddc44a37c162f1fa2a339139b7ca558a08cc`
- `scripts/harness/kpharness/cli.py`: `6290f42f0a198efd071f38c88d0d6540abdc3a3b9bcc7fd70f48ee22cce446cd`
- `tools/kpharness_offline_test.py`: `8be56989a5737d91ee028995b3172ac5c59960b0244e26fa220d22041fa16f62`

No AgentDecompile recovery action, 8080 server, real game process, Wine instance, display
or live harness session was started. The tests use disposable synthetic staging under `/tmp`.

## Remaining boundary

This increment gives the scenario layer a complete immutable identity declaration,
makes it durable in the report, and compares its contract/operation/target portion to
an explicitly supplied generated hook pack and three supplied effective artifacts before
a session is constructed. A synthetic owned-staging test proves that explicit
staged-relative locators accept matching staged bytes and reject a changed staged runtime
artifact. A boot-gate test proves a verifier refusal triggers teardown and reaches none
of runtime-ini, display, or launcher setup.

Before any staging copy, INI rewrite, fixture placement, save reset or runtime
installation, an operation session holds a stable `flock` stage lock and atomically records
a `prepared` `kpharness.operation-lease/v1` lease. The record binds the canonical
operation-pin manifest, staged bundle path, PID and process-start identity. A successor may
proceed only after a released record; a live prepared owner, a stale prepared record, a
quarantined record, an unreadable record and a syntactically valid record with malformed
fields are all fail-closed. Duplicate JSON fields are refused. A session does not claim a
pre-existing rejected lease, and rejection cleanup is limited to its acquired locks: it does
not enumerate or signal game processes or remove a foreign `session.json`.

Terminal cleanup binds to the exact lease this session admitted. It publishes `released`
only after a graceful cleanup observes no game or launcher survivor; otherwise it publishes
`quarantined`. Launch cleanup authority is consumed on the first teardown, and the stage
lock remains held until that session's record is removed, so a repeated teardown cannot act
on a successor. These are offline ownership semantics, not corroborated live process
ownership.

Full lease reconciliation against actual game/process ownership and a live mutation
intent/outcome receipt remain G3/G4 work. No game, native call, fixture/lifetime,
independent observation, restore or capture receipt exists; only then may the later
game-thread G5 route be considered for qualified execution.
