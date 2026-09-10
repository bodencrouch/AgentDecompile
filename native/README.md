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
