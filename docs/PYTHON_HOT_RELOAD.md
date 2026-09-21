# Update Python without replacing the dashboard

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
`/home/brunner56/agentdecompile-nvme/src`, not the canonical Git checkout.
Preserve unrelated differences between those trees. `/health` reports
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

## Live receipt — 2026-09-20

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
