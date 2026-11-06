# Ghidra native SDK

`native/` builds a process-isolated C ABI over Ghidra's native SLEIGH and
decompiler. It is not a JVM replacement for program import or analysis: it
replays raw images and exported decompiler savefiles without Java.

## Build

The linked `vendor/ghidra` worktree must contain the native-SDK standalone
CMake support. In this branch the submodule is a linked git worktree of the
existing Ghidra module repo; `git submodule status` may report it as
uninitialized even when the parent gitlink is valid. Use `git ls-files -s
vendor/ghidra` or `git ls-tree HEAD vendor/ghidra` to check the recorded
pointer.

The GitHub Actions workflow for this branch starts with the same check. It is
manual-only until the native-SDK `vendor/ghidra` gitlink commit is reachable
from the public submodule remote; otherwise CI would fail before checkout can
materialize the linked-worktree-only upstream CMake commit.

Build on a volume with room for compiled SLEIGH definitions:

```sh
cmake --preset relwithdebinfo -S native
cmake --build native/build/relwithdebinfo -j4
ctest --test-dir native/build/relwithdebinfo --output-on-failure
```

Use `--preset asan`, `ubsan`, or `fuzz` for the hardening lanes. TSan is not
built or claimed because the native engine and SDK session model are
process-global and single-threaded after init.

The fuzz lane builds three libFuzzer targets: the production incremental frame
decoder, SLEIGH disassembly over a fixed x86 seed image, and p-code lifting over
the same image. CTest runs each target for 1000 mutations from its checked-in
seed corpus:

```sh
cmake --preset fuzz -S native
cmake --build native/build/fuzz -j4
ctest --test-dir native/build/fuzz -R '^fuzz_smoke_' --output-on-failure
```

To build the shared ABI and its required SLEIGH home together:

```sh
cmake -S native -B native/build/shared -G Ninja -DGNSDK_SHARED=ON
cmake --build native/build/shared --target gnsdk_shared -j4
```

The shared object is `native/build/shared/sdk/libgnsdk.so`; its SLEIGH home is
`native/build/shared/ghidra-decomp/sleigh-home`. Both are needed at runtime.

## Consumers

`native/python` is an independently installable, dependency-free ctypes
package. Set `GNSDK_LIBRARY_PATH` to choose the library explicitly. It never
imports AgentDecompile or PyGhidra.

`native/rust` is a Cargo workspace. `gnsdk-sys` generates bindings from the
frozen `gnsdk.h`; set `GNSDK_LIB_DIR` for linking and `LIBCLANG_PATH` if
libclang is not discoverable. The safe `gnsdk::Session` is intentionally
`!Send + !Sync` because a native session is single-threaded.

## Process model

Ghidra's native engine has process-global state and supports exactly one live
session per process. Use `gnsdk-worker`/the pool for concurrency. Do not use a
shared library session from multiple threads or assume `gnsdk_shutdown()`
frees native registries; it is a logical state transition only.

## Resource limits and cgroups

The worker accepts address-space and CPU `rlimit` values from the pool. They
are the fallback limit on ordinary desktop sessions. A cgroup-v2 memory cap is
only a hard guarantee when the caller owns a delegated writable cgroup; a
typical `/sys/fs/cgroup` root is root-owned and cannot safely be modified by
this SDK. For a delegated user scope, start the caller with:

```sh
systemd-run --user --scope -p Delegate=yes your-batch-command
```

Never report a hard memory cap merely because an RLIMIT was requested. The
worker/pool teardown path remains bounded in either mode.

## Snapshot replay

Export still uses Ghidra and Java once per function. Replay does not: the
checked-in fixture demonstrates the intended two-stage workflow. The native
runtime proof is the `no_jvm_runtime` CTest target, which clears the environment
and runs a SLEIGH smoke binary from the native build tree. For a stronger host
boundary, run the upstream CMake README's Fedora container recipe without a JDK
and then run the same CTest lane inside that container.

```sh
# Java/PyGhidra producer (writes savefiles, options, and Java C oracles)
GHIDRA_INSTALL_DIR=/path/to/ghidra \
  uv run python -m agentdecompile_recovery.native_snapshot export binary \
  --out snapshot --project-location /scratch/project --project-name replay

# JVM-free native validation (requires the native build's SLEIGH home)
uv run python -m agentdecompile_recovery.native_snapshot diff snapshot \
  --console native/build/relwithdebinfo/ghidra-decomp/decomp_console \
  --sleigh-home native/build/relwithdebinfo/ghidra-decomp/sleigh-home

native/build/relwithdebinfo/tools/gnsdk_batch/gnsdk-batch \
  --sleigh-home native/build/relwithdebinfo/ghidra-decomp/sleigh-home \
  --snapshot snapshot --output results.jsonl --timeout 60
```

`diff` is strict: only line-ending and trailing-whitespace normalization may
produce `match`. A layout-only or content mismatch remains a result to
investigate, never a successful replay.
