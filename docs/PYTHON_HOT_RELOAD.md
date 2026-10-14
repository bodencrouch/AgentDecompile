# Update Python without replacing the dashboard

> **Latest restoration (2026-10-10):** PID3286755, started14:22:24 local,
>serves the same canonical NVMe8080/GPR under the existing runtime-owner flock.
>Startup reused32 programs. Playwright confirmed HTTP200 and external corpus
>selection, restoring250 retained assessments and strict hold772e68366608 without
>clearance or dispatch. The jobs.py startup-status/severe-pressure repair reports
>matching source/applied SHA
>`3a4cf8e170565aee7d4cc5d29c1502a8b284207b3c56357a323dcc2ce2d2d6cd`,
>zero in-process restarts. No respawn supervisor was added. The previous death
>cause remains unknown; this does not establish future uptime or recovery proof.

> **Pre-restoration availability check (2026-10-10):** PID2417358 was absent;
>8080 has no listener and Playwright reports connection refused. The bounded
>server log does not establish why it stopped. No replacement or process signal
>was issued during this check. The activation below is historical, not uptime proof.

> **Historical observed activation (2026-10-10):** PID2417358, started09:03:28
> local time, serves the canonical NVMe checkout on8080 in in-process mode
> with zero restarts. Its one-shot launch returned while the server retained
> its independent session and exclusive runtime-owner flock; there is no
> replacement supervisor or automatic respawn loop. Logs are in external
> `corpus_work/dashboard-runtime.tWyFFp/server.log`. Startup reused the existing
> GPR's32 programs. Supported database selection returned200 for the external
> `kotorxid.sqlite`;249 incomplete ownership assessments and the strict
> `772e68366608` holds remain, without historical dispatch or clearance.
> Read-only catalog report `1bf423c82cea` exercised the current-use observer
> in179ms. Its unknown compiler/prefix/output states do not authorize release
> or new compilation. Subsequent Playwright root-button checks preserved all
> six project tabs. This is a runtime observation, not permanent-uptime or
> recovery proof; the cause of earlier exit143 terminations remains unknown.
>
> **Historical activation (2026-10-10, superseded):** PID213100 later
> disappeared; no listener remained on8080, and available bounded journal checks
> did not establish the cause. Under the user's existing restoration authorization,
> the same NVMe Python/root/GPR was launched as PID1615148 at06:53:21 with a
> 1GiB JVM heap cap. Startup loaded32 programs. Playwright confirmed HTTP readiness,
> canonical module paths and zero in-process restarts. The initial empty admission
> view belonged to a checkout-local shadow workspace, not the external corpus.
> Historical receipts were retained, not cleared based on missing PIDs. Job
> `af3c8d56af62` failed the candidate-plus-limit argument guard before compilation.
> The shared preflight repair now rejects that request with HTTP400. Selecting
> the external `db/kotorxid.sqlite` through the supported dashboard API now
> produces its existing sibling `corpus_work` in action defaults; `common.py`
> and catalog changes report applied on the same PID. A transactional JobStore
> scope handoff, root-bound receipt publication/cache and cancellation barrier
> passed independent source review and memory-only checks. All four modules
> report applied without restart. The supported repeat database-selection POST
> safely refused target receipt `772e68366608`: its retained unresolved database
> reservation differs from the current action requirements. Selection was not
> committed and old ownership was retained; historical claims were not cleared.
> Conservative policy-drift import subsequently applied and preserved both the
> original database hold and current Ghidra-project hold; partial release is
> refused. The next supported selection POST refused legacy `193e0253cb0b`,
> which lacks captured database/ownership identity. A complete receipt-set audit
> is underway before further restoration changes. The CLI module's
> in-process reload was rejected (`Ambiguous callable: main.run_it`); fresh job
> subprocesses read current source, but the parent CLI is not claimed updated.
> No fresh compiler or full-image recovery is claimed.
>
> **Earlier activation (2026-10-10, superseded):** the authorized post-boot restoration was
> serving 8080 as PID `213100`, started 04:23:32, using the copied NVMe Python
> 3.14.5 runtime. Playwright confirms canonical module paths, in-process mode
> and zero restarts. The folder-browsing repair reports `applied` and was
> exercised through all five Open-project roots on that unchanged PID.
> `unified_pages.py` subsequently hit a partial merge failure and remains
> quarantined. The obsolete compiler watchdog was retired separately through
> guarded coordinator job `8ae90b94dfd3`; observed thread exit does not recover
> that module. Queued replacements were cancelled and scheduler admission
> resumed through job `682b49316ec2`, with zero active jobs afterward.
>
> **Earlier post-boot revalidation (superseded):** the host booted at 03:58:09; PID
> `1761367` is absent, port 8080 has no listener, and the prior `/tmp` startup log
> is absent. No restart or replacement was performed. The following activation
> receipt is historical, not a claim that hot reload is currently serving.
>
> **Historical activation (2026-10-09):** the authorized bootstrap completed.
> The then-running 8080 process was PID `1761367`, launched through
> `scripts/watch-recovery-server.py` and `inplace_hotreload`. Playwright read
> `/health`: `enabled=true`, `mode=in-process`, `engine=jurigged`,
> `restarts=0`, root `/home/brunner56/agentdecompile-nvme/AgentDecompile/src`,
> 257 watched Python files. The same existing GPR reopened with 32 programs
> loaded; the K1 GOG workstation and function listing returned in Playwright.
> The durable job history remains at 1,443 entries with 0 active jobs. The live
> `corpus.verify-byteexact` action now reports `workers=1` and `offset=0`.

The 8080 runtime uses the standalone `inplace-hotreload` package. It wraps
Jurigged's in-process definition updates with admission checks and observations.
It does not re-execute modules wholesale, replace the server, or restart workers
when source changes. Vite remains responsible for frontend updates.

## Install and launch

Package source: `/home/brunner56/inplace-hotreload`. Install its wheel into the
application's virtualenv with pip. The package has no AgentDecompile dependency
and can be imported with `from inplace_hotreload import start` in other projects.
It has not been published to PyPI.

```sh
pip install /home/brunner56/inplace-hotreload/dist/inplace_hotreload-0.1.0-py3-none-any.whl
inplace-hotreload --root /path/to/project/src --call application.server:main -- --port 8080
```

For this repository, `scripts/watch-recovery-server.py` is now an exec-only
compatibility launcher. It selects the server command's virtualenv Python and
starts watching before importing `agentdecompile_cli.server:main`. It contains
no child supervisor, polling replacement loop, cgroup control or restart fallback.
Old `--work-dir` and `--state-file` arguments remain accepted but do not create
replacement state. Do not launch a second server when 8080 is already owned.

## Edit and inspect

Confirm the live module path before editing; the current runtime source is
`/home/brunner56/agentdecompile-nvme/AgentDecompile/src`. Preserve unrelated
differences between those trees. `/health` reports
`runtime.reload`: process identity, watched roots, applied/rejected/error events
and source/applied hashes. Verify changed behavior through the actual consumer;
an `applied` event alone is not behavior proof.

Compatible function/method bodies, retained callbacks and immutable uppercase
constants can update. Contract changes, mutable module state, effectful defaults,
class layout and initialization changes are rejected. Native atomic-save events
are handled; optional polling is available for filesystems without notifications.
Errors never trigger a restart. Partial merge failures quarantine the affected file.

Existing stack frames, running generators and async tasks finish their existing
code. Later calls use new definitions. Route registration/schema changes, native
extensions, JVM code, already captured values and external worker processes are
not automatically migrated. Updates across uncooperative threads are not atomic;
the package offers a cooperative synchronous guard. These are the current
diminishing-returns boundary, not promises of universal hot replacement.

## Current activation receipt — 2026-10-09

Installed `inplace-hotreload==0.1.0` and its pinned `jurigged==0.6.1` runtime
dependency into the server virtualenv. With the dashboard reporting no queued
or running jobs and no active sessions, the prior PID `1049987` was stopped
gracefully and the same environment, working directory, project path, host and
port were passed to the repository watcher launcher. No `systemctl` command was
used. Startup reopened the existing local Ghidra project at
`/home/brunner56/agentdecompile-nvme/agentdecompile_projects/corpus_work/ghidra-projects/repos.gpr`;
the PyGhidra log reports 32 programs loaded. The selected K1 GOG browser tab
returned its function listing, all 1,443 durable jobs remained available, and
Playwright observed 0 active jobs. The activity panel currently says “No
activity yet” rather than the previous observer-limit error; this verifies the
current surface, not a permanent fix for backend observer saturation.

Startup log: `/tmp/agentdecompile-8080-hotreload-sasx2vhl.log`. Package install,
launch, project reopening and browser checks are operational evidence; they do
not demonstrate source-edit reload behavior for every Python construct. The
compatibility limits below still apply.

## Historical live receipt — 2026-09-20

The user explicitly authorized one bootstrap restart after implementation.
Dashboard job `5766e922d857` was cancelled through 8080; its compiler PID 2993989
was confirmed absent before the old service was stopped through its exact D-Bus
unit. No `systemctl` command was used. The old supervisor/server PIDs 2540883 and
2989049 exited; the old service was subsequently observed inactive.

The new server PID 3578234 started at 02:38:19 America/Chicago. After startup,
editing the existing nested health handler added `reloadPolicy` to its HTTP
response automatically. Server PID/start time and worker PID 3587370 remained
unchanged. `/health` reported `mode=in-process`, `restarts=0`, and applied SHA256
`4516504d14426e7d641bc2db211c802fd650394d45c1811b8bc06b742307468c` for
`agentdecompile_cli/mcp_server/server.py`; the file digest agreed.

Dashboard inspection jobs `3109a9913770` and `f659ec24399e` returned identical
before/after identities:

| Object | Identity |
|---|---:|
| Job store | 140377385207520 |
| MCP executor lock | 140377385288144 |
| Preparation lock | 140374023048800 |
| Lease map | 140374023220672 |
| Session registry | 140381349405296 |

The continuation was submitted through the same dashboard as job `4611016b8e35`,
with original target/database/compiler parameters and one worker. It retained
18,642 existing compiling-C candidates and skipped the 562 failures already
attempted by the interrupted pass. The selected receipt SHA256 was
`ce8656bd289cee37e24519476c20391e8cd8af9005bdca6a90cb8b1f522b8cde`.
The resulting queue had 4,929 candidates; 107 logical-C siblings were also skipped
by the existing reuse policy. Normalization advanced after the live source edit.
These are continuation/compilation observations, not byte-exact recovery proof.

`--resume-failures-sha256` is an explicit same-input/toolchain continuation option,
not automatic provenance detection. It validates the current failure log's exact
bytes and target address membership, then appends to that same log so another
interruption retains prior failures. Use it only after confirming the old owner
has stopped and inputs/toolchain are unchanged. No match or success is inferred
from skipping a previously failed attempt.

The wheel was built and installed into a separate environment; in-memory checks
verified retained callback/class-instance/state behavior on Python 3.14.5 and
admission rejection cases. No filesystem tests or test suites were run or written.
Wheel SHA256: `6e65fbacd1bed118b2118dc6a4a2485049c7175aa12da3b82b55837e5185abca`.
