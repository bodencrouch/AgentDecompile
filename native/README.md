# Ghidra native SDK

`native/` builds a process-isolated C ABI over Ghidra's native SLEIGH and
decompiler. It is not a JVM replacement for program import or analysis: it
replays raw images and exported decompiler savefiles without Java.

## Build

The linked `vendor/ghidra` worktree must contain the native-SDK standalone
CMake support. Build on a volume with room for compiled SLEIGH definitions:

```sh
cmake --preset relwithdebinfo -S native
cmake --build native/build/relwithdebinfo -j4
ctest --test-dir native/build/relwithdebinfo --output-on-failure
```

Use `--preset asan`, `ubsan`, or `fuzz` for the hardening lanes. The fuzz
target exercises the production incremental frame decoder:

```sh
cmake --preset fuzz -S native
cmake --build native/build/fuzz --target protocol_fuzzer -j4
native/build/fuzz/fuzz/protocol_fuzzer -runs=10000
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

## Snapshot replay

Export still uses Ghidra and Java once per function. Replay does not: the
checked-in fixture demonstrates the intended two-stage workflow.

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
