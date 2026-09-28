---
title: P1.3 execution actions — run-reccmp-compare and run-reagent-benchmark
type: implementation-plan
date: 2026-09-27
status: design (not implemented)
parent: 2026-09-27-implementation-progress-and-live-track.md
evidence: ~/agentdecompile-deliverables/2026-09-27-p13-reccmp-reagent/ (machine-local)
---

# P1.3 execution actions

P1.3 needs two catalog-owned runs, one reccmp original/rebuild/PDB comparison and one ReAgent
benchmark that consumes a candidate. Each run keeps a raw receipt and a normalized receipt.

The catalog can already read reports (`corpus.normalize-validation-report`) and export
snapshots (`corpus.export-reagent-snapshot`). It cannot yet run either tool. All `jobs.py`
anchors below refer to the dirty working tree (`f312aea1…`), not HEAD.

## Facts that shape the design

**The contract layer is uncommitted.** HEAD has no `_EXTERNAL_ACTION_CONTRACTS`. These files
are untracked: `external_validation.py`, `supervision.py`, `native_verify_contract.py` and
`cross_place_admission.py`.

**Corpus actions come from argparse.** `introspect.py:120-161` builds them; `catalog.py`
needs no insertion. Avoid these field names:

| Field names | Why they are unsafe |
|---|---|
| `--out`, `--out-dir`, `--work-dir` | Bound to the work dir, so an exclusive claim would cover the whole workspace |
| `--binary`, `--input` | Rewritten to the context PE |
| `--path`, `--from`, `--repo`, `--program`, `--id` | Auto-filled from context |
| Bare `--project` | Silently dropped |

Use these names instead: `--report-dir`, `--original`, `--rebuild`, `--pdb`, `--project-dir`
and `--reccmp-target`. Mark both subparsers mutating, long-running and danger.

**Guarded actions are hardcoded in five places** in `jobs.py` (:266-274, :396, :406,
:1077-1083, :1868-1871). Missing one leaks the full server environment into the child.
Replace these with a `_GUARDED_MODULES` registry and a coverage test.

**wineserver daemonizes.** Session-only clearance can report "clear" while the prefix is
still live. Wine-prefix clearance is therefore P0.3 scope. Until it lands, reccmp jobs end
`quarantined`, and each run uses a fresh prefix.

## New module: `corpus/external_execution.py`

This module touches no shared file. It follows the guarded-child pattern of
`cross_place.py` and `native_verify_contract.py`.

**Pins.** `PINS` are code-owned:

| Tool | Version | Commit | Archive sha256 |
|---|---|---|---|
| reccmp | 0.1.7 | `e91a51b…` | `6801afde…` |
| auto-re-agent | 0.4.0 | `d12cea3…` | `65c22a9d…` |

The commits must equal `external_validation.SCHEMA_BASELINES`.

**`freeze_parameters`** runs in the parent before any reservation. It:
- makes all paths absolute and refuses symlinks;
- hashes every input and compares it with the declared sha256;
- verifies the provider;
- canonicalizes the venv.

**`verify_provider`** checks:
- `direct_url.json`: the pinned commit and the archive sha256;
- `RECORD` hashes;
- the entry point;
- the interpreter's realpath and sha256.

**The child launches the provider** as `<venv>/bin/python -I -c <entry-point shim>`. It
uses `-I` without `-S`, avoids console scripts, and runs the provider in the same session.
The environment is an explicit allowlist, and the whole env dict goes into the receipt.

**For reccmp, the child also:**
- runs `pdb_matches_rebuild`, which requires the CodeView RSDS GUID and age to equal those
  in the PDB info stream;
- generates `reccmp-user.yml` and `reccmp-build.yml` inside the report dir, pointing at the
  frozen paths;
- runs `wine_shutdown` afterwards;
- re-hashes the inputs before and after the run.

## Actions

### `corpus.run-reccmp-compare`

Fields:
- `project-dir`, `reccmp-target`;
- `original`, `rebuild` and `pdb`, each with its sha256;
- `db` (from context) and `binary-slug` (from context `slug`, used only to cross-check md5);
- `report-dir`, which must not exist;
- `provider-venv`, `wine`, `wineprefix` (dedicated and initialized; `~/.wine` is refused)
  and optionally `cvdump`;
- `timeout`, default 1800 and maximum 7200.

Argv: `reccmp-reccmp --target <id> --json <report-dir>/report.json --silent`, with cwd set
to `<report-dir>/reccmp`.

### `corpus.run-reagent-benchmark`

Fields:
- `manifest` and `manifest-sha256`;
- `inputs-dir`, copied into `<report-dir>/work`;
- `candidate` and `candidate-sha256`;
- optionally `candidate-receipt`;
- `report-dir`, `provider-venv`, `timeout`.

The manifest is validated:
- rows need an argv-array `reference` and `candidate`;
- shell strings and `sh`/`bash`/`env` are refused as argv[0];
- argv[0] must be absolute and is hashed;
- the candidate must actually be consumed.

## Receipts

**Raw receipt:** `execution.json`, schema `agentdecompile.external-execution/v1`. It records:
- the provider pin and interpreter;
- input identities at freeze, before the run and after the run;
- argv, cwd and env;
- Wine tool hashes;
- the process result;
- the stream digests and the raw report digest;
- `execution_state` and the refusal, if any.

**Binding:** add `external_validation.bind_execution(normalized, execution)`. Leave
`normalize_report` and `read_report` byte-for-byte unchanged. `bind_execution` wraps the
unchanged normalized output and sets:
- `provenance_verified=true` only when the pin is verified, the three-phase hashes are
  equal, and the raw sha256 matches;
- `proposal_only=true` and `recovery_accepted=false`, always.

**States:** `completed`, `crashed`, `timed_out`, `unavailable`, `unsupported` and
`invalid_output`.

## Refusal codes

| Area | Codes |
|---|---|
| Wine | `wine_unavailable`, `winepath_unavailable`, `wineserver_unavailable`, `cvdump_unavailable`, `wineprefix_uninitialized`, `wineprefix_default_refused` |
| Provider | `provider_unpinned`, `provider_record_mismatch`, `provider_entry_point_missing`, `provider_interpreter_unavailable`, `provider_implementation_changed` |
| Inputs | `input_hash_mismatch:<name>`, `input_changed_during_run:<name>`, `project_hash_mismatch`, `reccmp_target_unknown`, `pdb_rebuild_mismatch`, `slug_md5_mismatch` |
| Paths | `report_dir_exists`, `report_dir_parent_missing`, `symlink_external_resource`, `output_aliases_input` |
| Manifest | `manifest_invalid`, `manifest_shell_command`, `candidate_not_consumed`, `manifest_timeout_exceeds_action` |

## `jobs.py` delta (single writer only)

1. Add the `_GUARDED_MODULES` registry and a registry-coverage test.
2. Add contracts:
   - reccmp: output `report-dir`, wineprefix `wineprefix`, input `project-dir`;
   - reagent: output `report-dir`, input `inputs-dir`.
3. Derive `provider` and `input` claims from the frozen params only. Admission and restore
   must share one derivation function.
4. Add the `provider` and `input` kinds, both shared. Add `_claims_conflict`: a conflict
   needs an overlap where at least one side is exclusive.
5. Set the job timeout to the frozen timeout plus 60 s.
6. P0.3 owns `wineprefix_clearance`, likely implemented as a non-blocking lock probe on
   `/tmp/.wine-<uid>/server-*/lock`.
7. The existing Wine callers (`compile-link` and `verify-direct-full-image --wineprefix`)
   take no claims. This is a P0.3 follow-up.

## Timeout and kill

- **Child:** SIGTERM, then SIGKILL after 5 s, then `wine_shutdown`. It writes `timed_out`
  and exits 124.
- **Parent:** the existing `_default_executor` is unchanged. A session that is not clear,
  or a prefix that is still live, ends the job `quarantined`.

## Tests (specified)

- **Unit:**
  - every refusal code;
  - fake dist-info pin failures;
  - symlink refusal;
  - PE/PDB GUID mismatch;
  - generated yml;
  - the env allowlist;
  - the `guarded_command`/`command_matches` round trip;
  - `bind_execution` leaves the normalized output unchanged;
  - the state mapping.
- **Resources:**
  - shared and exclusive claim semantics;
  - restore round trip;
  - restore after the venv is reinstalled;
  - registry coverage.
- **Synthetic E2E** through the real `_default_executor`, using a fake venv, fake tools and
  a fake Wine:
  - success;
  - timeout;
  - a detached grandchild;
  - an input rewritten mid-run;
  - an unpinned provider;
  - cancel before spawn;
  - the ReAgent candidate is consumed;
  - a shell manifest is refused.
- **OpenAPI catalog:** both actions are listed with their flags, and no trap field names
  are used.

## Acceptance

**Lane A (actions delivered):** code, then tests in a lock-held window, then `/health`
module identity, then `GET /api/v1/actions`, then the expected `dryRun` argv. This lane is
not P1.3 itself.

**Lane B (P1.3 live) prerequisites:**
- pinned tools reinstalled;
- Wine, cvdump and a dedicated prefix;
- an MSVC 7.1 rebuild with its PDB and a reccmp project;
- a ReAgent reference executor and a real candidate.

**Per job, retain:**
- the job receipt;
- `execution.json`, `report.json` and `normalized.json`;
- the streams;
- matching input hashes;
- a provider revision equal to the pin;
- the owner check (from `/proc` start ticks and cwd);
- an independent re-normalization through the catalog.

Neither run counts as recovery acceptance or whole-image equality.

**Order:**
1. `external_execution.py`, `bind_execution` and tests. No shared files.
2. The `cli.py` and `introspect.py` insertions.
3. The `jobs.py` delta, through its writer.
4. The P0.3 prefix probe.
5. Lane B.

## Addendum
- USAGE.md documents the existing actions. Update it in the same change as the cli.py insertion.
- Test precedents to copy:
  - `tests/test_job_resource_quarantine.py:427` builds a catalog action from the real corpus CLI and checks its resource contract.
  - `tests/test_reagent_snapshot_export.py:80-94` makes the same check at catalog level.
