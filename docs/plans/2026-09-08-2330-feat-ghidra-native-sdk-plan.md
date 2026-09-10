---
title: Ghidra Native SDK - Plan
type: feat
date: 2026-09-08
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
status: living
---

# Ghidra Native SDK - Plan

**Target repo:** AgentDecompile (`native/`, `src/`, docs) plus an additive branch inside the `vendor/ghidra` submodule.

**Product Contract preservation:** authored in this plan. Recovery ladder plan stays `docs/plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md` and stays the STRATEGY `active_living_plan`. Source RFC and approved plan: `~/.claude/plans/rfc-and-implementation-structured-dongarra.md` (outside the repo).

This is a living plan. Work is in progress on several packages at once. Every box below is unchecked until the named verification has run. The Progress section records what has been verified and when.

## Goal Capsule

- **Objective:** Use Ghidra's own native SLEIGH and decompiler without a JVM in every worker. Export a program once from Ghidra as per-function decompiler savefiles plus a manifest. Re-decompile those savefiles with the native engine for option sweeps, engine-upgrade regression checks, and consumers that cannot host Java. Check native output against the Java decompile of the same program on the same engine version.
- **Authority:** `STRATEGY.md` (priority ladder unchanged), then this plan, then the RFC.
- **Stop when:** The merge gate passes. The differential harness reports 100% `match` on the declared supported set. The JVM-free smoke is green in a container with no JDK. The bench table exists and the plan quotes only what it shows.
- **Do not:** Change the AgentDecompile default decompile path. Move or rename any upstream source file. Claim performance before the bench table exists. Claim concurrency on a single native handle. Treat a Java/native mismatch as tolerance.
- **Execution profile:** Code, in a git worktree on `feat/native-sdk`. No push, no PR.

---

## Product Contract

### Summary

Ghidra ships a native decompiler and a native SLEIGH. No upstream build target links both into one library without libbfd, and the shipped `decompile` binary cannot replay the `<xml_savefile>` that `DecompileDebug` writes. This plan adds a standalone CMake build on an upstream-shaped branch, a small C ABI and process-isolated worker pool in `native/`, a Python exporter that writes one savefile per function, a differential harness that compares native C to Java C, and a bench harness that measures instead of assumes.

### Problem Frame

Facts established by reading the trees (all at tag `Ghidra_12.1.3_build`):

- `vendor/ghidra` was pinned to master (12.2-DEV) and referenced by nothing but `.gitignore`. Tag `Ghidra_12.1.3_build` exists in the module repo. Native work needs Java 21 and no Gradle.
- The hand `Makefile` is the only upstream description of a library with both SLEIGH and the decompiler (`LIBDECOMP_NAMES=$(CORE) $(DECCORE) $(EXTRA) $(SLEIGH)`, `Makefile:138`). It drags libbfd in unconditionally. There is no CMake upstream. Generated bison/flex parsers are committed.
- `DecompileDebug` captures every host query for one function into an `<xml_savefile>` (`xml_arch.cc:20`). Only a Makefile-built console binary can `restore` it (`consolemain.cc:218`). The capture is one-shot per function. `DecompInterface.java` nulls `debug` after each decompile (lines 169 and 822).
- There is no teardown in the native tree: `shutdownDecompilerLibrary()` is empty (`libdecomp.cc:59`), loaded translators live in the process-global `SleighArchitecture::translators` map (`sleigh_arch.cc:36`). XML, bison and flex parsing is not reentrant. Process isolation is the only correct concurrency model at this commit.
- AgentDecompile decompiles through single-threaded `DecompInterface` loops. `ParallelDecompiler` has zero uses in AgentDecompile code. The one measured baseline is 8621 functions in 342 s at 4 threads via `ghidrecomp` (`docs/plans/2026-07-24-perf-recovery-one-shot-living-plan.md`, Baseline table).
- Capability singletons self-register from static initializers (`xml_arch.cc:23` and peers). A plain static archive drops them; the library target must link whole-archive.
- `ghidra_process.cc` installs a `SIGSEGV` handler that calls `_Exit(1)` (`ghidra_process.cc:513-523`). It must never be linked into the SDK.
- At the tag, `ghidra.util.Lock` (`Ghidra/Framework/Project/src/main/java/ghidra/util/Lock.java`) is the exclusive `acquire()/release()` lock. The read/write variant exists only on master.

### Decisions locked (user-confirmed)

1. **Placement: hybrid.** Upstream-shaped additive files on branch `native-sdk/cmake-standalone` inside `vendor/ghidra`. Everything else in a new `native/` tree in AgentDecompile plus Python glue under `src/`.
2. **Engine pin: `Ghidra_12.1.3_build`.** Move the submodule to the tag. Install the Ghidra 12.1.3 release as the Java oracle. PR base is master later; a CMake source-manifest check against the Makefile makes that rebase mechanical.
3. **Scope: P00–P05 and P07 now.** P06 in Python over JPype. P08–P11 and X01 stay unchecked backlog (see Deferred backlog).
4. **Git: PR-sized slices on `feat/native-sdk`** in a git worktree so unrelated dirty files stay untouched, and on `native-sdk/cmake-standalone` inside the submodule. No push, no PR.

Upstream `CONTRIBUTING.md` binds the submodule branch: smallest reasonable change (line 41), no repackaging or renaming without prior authorization (line 44), squash with issue number (line 60), no self-generated binaries (line 64), extra scrutiny for AI-assisted code (line 35). The upstream branch adds files only and never moves a source.

### Honest-cost statements

These hold for v0 and are repeated wherever the feature is described:

- **Export requires one Java decompile per function.** The manifest carries `export_requires_java_decompile: true`. There is no JVM-free export in v0.
- **JVM-free applies to replay.** Replaying savefiles, lifting bytes, and the batch tool run without Java. Loading a program from a binary still needs Ghidra.
- **No performance claim until the bench table exists.** The only measured number is the 8621 / 342 s / 4 threads baseline above. `k_star` (the export break-even) is reported from the table or as `never`, not assumed.
- Savefiles are plain XML. Their size per function is not yet measured; the manifest records `total_bytes` and the plan quotes it only after a run. Compression is v1.

### Requirements

**Upstream subtree (P01)**

- R1. A standalone CMake build produces a library with both SLEIGH and the decompiler, without libbfd by default, from unchanged upstream sources.
- R2. A manifest check compares CMake's source list to the Makefile's and fails on drift, at configure time and as a ctest.
- R3. The subtree configures, builds, and passes its tests in a container with no JDK (R01 in the RFC).

**Session and ABI (P02, P03)**

- R4. A C99 ABI (`gnsdk_*`) exposes init, session create, load image or open snapshot, disassemble, lift, decompile, cancel, diagnostics, and destroy. Every struct is size-tagged. Every status code lives once in `native/conformance/status_codes.json`.
- R5. One live session per process. A second create returns `GNSDK_BUSY`. No concurrency on any handle is claimed.
- R6. Hard errors poison the session, not the process. Signals kill the process; the supervisor handles that.

**Snapshot (P04)**

- R7. The exporter writes `manifest.json`, one `functions/<addr>.xml` per function, and the Java C oracle for the same decompile, using the one shared option configurer (`_configure_decompiler_for_program` in `src/agentdecompile_cli/mcp_utils/decompiler_util.py`).
- R8. The exporter refuses a program with an open transaction and marks `revision.stale` if the modification number changes during export.
- R9. Replay reads only the snapshot directory. Output is canonicalized by whitespace rules only and classified; `mismatch-content` is a bug.
- R10. Engine parity is asserted: manifest `engine.sig_*` equals the native pair, and native `source` starts with `Ghidra_12.1.3_build`.

**Pool and batch (P05)**

- R11. Workers are separate processes spawned with `posix_spawn`, bounded by rlimits and, when available, a cgroup v2 memory cap. Deadline escalates `SIGUSR1` then `SIGTERM` then `SIGKILL`.
- R12. No orphans: parent death kills workers; the test suite ends with `pgrep -f gnsdk-worker` empty and the tmpdir clean.

**Java-side batch (P06 over PyGhidra)**

- R13. `decompile_functions(...)` drives Ghidra's `DecompilerConcurrentQ` from Python with a private thread pool and disposes every callback. Existing callers are untouched. Never-decompile-twice holds through `pending_addrs()`.

**Bench (P00)**

- R14. Every lane holds the same function list, options hash, and timeout. Rates are computed over the intersection of completed sets. The table is refused on completion drift.

**Consumers and CI (P07, P11 slices)**

- R15. Python `gnsdk` (ctypes) and Rust `gnsdk` (bindgen) consumers share the status table and never import `agentdecompile`.
- R16. CI runs build-test, JVM-free smoke, asan, rust, and differential lanes. The default AgentDecompile test path stays green with no native build present.

### Key Decisions

- Process isolation first. (session-settled: user-directed. Chosen over in-process threads because the parsers are not reentrant and there is no teardown.) Governs R5, R6, R11.
- Whole-archive INTERFACE target for `ghidra::decomp`. (Chosen over a plain archive because capability singletons self-register from static initializers and are dropped otherwise.) Governs R1.
- v0 snapshot is the existing `<xml_savefile>`, one per function. (Chosen over a new schema so the exporter reuses `DecompileDebug` unchanged.) Governs R7, R9.
- Canonicalization is whitespace-only. Any widening is recorded in a `docs/solutions/` entry first. Governs R9.
- ctypes, not nanobind, for the v0 Python binding. (No compiler, no per-interpreter wheel, repo stays pure Python.) Governs R15.
- Never resize Ghidra's shared "Parallel Decompiler" pool; use a private pool. Governs R13.

### Key Flows

- F1. Export: `python -m agentdecompile_recovery.native_snapshot export <binary|project> --out <dir> [--addr ...|--all] [--timeout-s N]`. Writes manifest, savefiles, oracle C. Covered by R7, R8.
- F2. Replay and diff: `python -m agentdecompile_recovery.native_snapshot replay <dir>` then `diff <dir>`. Report at `<dir>/differential/{report.json,report.md,diff/}`. Covered by R9, R10.
- F3. JVM-free batch: `gnsdk-batch --sleigh-home DIR --snapshot <dir> --output results.jsonl`. One JSONL record per `ok` function. Covered by R11, R12.
- F4. Java batch: `python -m agentdecompile_recovery.corpus.cli decompile-batch --threads N`. Writes into the existing `ctext` sqlite. Covered by R13.

### Acceptance Examples

- AE1. Covers R3. Given `registry.fedoraproject.org/fedora:44` with no JDK, when the upstream subtree is configured, built, and tested, then ctest is green and `ldd` on every binary matches no `libjvm|libjava|libjli|libjawt`.
- AE2. Covers R9, R10. Given the committed `tests/fixtures/native_snapshot/test_x86_64` snapshot, when replay and diff run, then `match == ok_count` and zero `native-crash`.
- AE3. Covers R5. Given a live session, when a second `gnsdk_session_create` is called in the same process, then the status is `GNSDK_BUSY`.
- AE4. Covers R12. Given the pool test suite, when it finishes, then `pgrep -f gnsdk-worker` prints nothing.
- AE5. Covers R14. Given two lanes with different completed sets and `--max-completion-drift 0`, when the report runs, then it prints `REFUSED (completion mismatch)` and exits 3.
- AE6. Covers R16. Given no native build, when `uv run pytest -m unit` runs, then it is green.

### Success Criteria

- 100% `match` on the declared supported set (`x86:LE:64:default`, style `decompile`) for `test_x86_64`.
- Agreement on the shipped `sleigh` binary recorded, every non-match classified, none `native-crash`.
- JVM-free smoke green in a JDK-less container.
- Bench table exists under `agentdecompile-native-out/bench/` with `export_requires_java_decompile` and `k_star` stated.
- Default path unchanged: unit tests and ruff green with no native build.

### Scope Boundaries

**In scope:** WP0–WP11 below.

**Deferred:** see Deferred backlog.

**Outside this product's identity:** replacing Ghidra's project format or loaders; a second decompiler; rewriting upstream C++.

---

## Planning Contract

### Assumptions

- The `.venv` pyghidra (3.0.2), the system pyghidra (3.1.0), and the tree's (3.2.0) share the API surface this plan uses (`pyghidra.start()`, `pyghidra.open_program(..., analyze=True)`).
- The 12.1.3 release ships `sleigh` and `decompile` ELF binaries that are redistributable and present on every runner; they serve as real-C++ bench corpora.
- Memory budget on this host is tight: ninja `-j6` while spec compilation runs; never run AARCH64 or x86-64 spec builds concurrently with a JVM lane; `free -g` before each heavy step.
- `/home` is small, so builds, snapshots, and bench outputs go under the MyBook volume (`agentdecompile-native-out/`, gitignored by the existing `agentdecompile*/` rule).

### Layout

```
$REPO (worktree .claude/worktrees/native-sdk, branch feat/native-sdk)
  vendor/ghidra @ Ghidra_12.1.3_build, branch native-sdk/cmake-standalone
    Ghidra/Features/Decompiler/src/decompile/cpp/CMakeLists.txt         (new)
    Ghidra/Features/Decompiler/src/decompile/cpp/cmake/{GhidraDecompSources,CheckMakefileManifest,SleighCompileSpecs,NoJvmCheck}.cmake,
      GhidraDecompilerConfig.cmake.in, README.md, smoke/{sleigh_smoke.cc, expected/*.txt}   (new)
  native/
    CMakeLists.txt, CMakePresets.json, cmake/, README.md
    sdk/{include/gnsdk/gnsdk.h, src/...}      C ABI + session layer (C++20) over unchanged upstream
    worker/                                   gnsdk-worker (framed stdin/stdout protocol)
    pool/                                     gnsdk_pool library (posix_spawn supervisor)
    tools/                                    gnsdk-batch, gnsdk-selftest, fake-worker
    tests/{sdk,worker,pool}, fuzz/, conformance/status_codes.json
    python/gnsdk/                             ctypes + subprocess client, separate package, JVM-free
    rust/{gnsdk-sys,gnsdk}                    bindgen + safe wrapper + two examples
    bench/{fixtures/src, fixtures/build.sh, corpora.json, environment.json}
  src/agentdecompile_recovery/native_snapshot/{__init__,manifest,exporter,cli,canonical,replay,differential,bench,procstat}.py
  src/agentdecompile_cli/mcp_utils/parallel_decompile.py
  scripts/bench_native_sdk.py
  tests/test_native_*.py, tests/test_parallel_decompile_*.py, tests/test_gnsdk_ctypes_errors.py, tests/fixtures/native_snapshot/test_x86_64/
  docs/plans/2026-09-08-2330-feat-ghidra-native-sdk-plan.md (this file), docs/brainstorms/2026-09-08-ghidra-native-sdk-requirements.md
  .github/workflows/native-sdk.yml
  agentdecompile-native-out/                  gitignored: snapshots, bench results, built fixtures
```

Build dirs: `native/build/<preset>`. Ghidra 12.1.3 runtime: `/home/brunner56/ghidra-install/ghidra_12.1.3_PUBLIC`. `.gitignore` traps: `vendor/*` is ignored with `!vendor/ghidra` negated; anything matching `agentdecompile*/` needs a negation; `native/` and the two `src/` packages are committable as is.

### Contract files (frozen first)

`native/sdk/include/gnsdk/gnsdk.h`, `native/worker/protocol.hpp`, `native/conformance/status_codes.json`, and the manifest schema `agentdecompile.native-snapshot/v0`. Agents on disjoint directories write these before anything that depends on them.

### Sequencing

WP0 before everything. WP1 before WP3 (needs `ghidra::decomp` and `ghidra_specs`). WP4 contract before WP5; WP5 before WP6. WP2 before WP9's console replay. WP8 can start against 12.1.2 until 12.1.3 lands. WP10's Java batch API has no native dependency. WP11 bindings wait for a frozen header and `libgnsdk.so`. Every WP ends with a code-quality review of its diff; WP3 and WP6 also get a security review (process spawning, rlimits, cgroups, file paths from JSON).

---

## Implementation Units

Status legend: a box is checked only after the named verification ran and its output was recorded in Progress.

### WP0. Pin, branches, runtime (P00 part 1)

- [ ] Worktree `.claude/worktrees/native-sdk` on `feat/native-sdk` starts from master.
- [ ] `vendor/ghidra` checked out as a linked worktree of the module repo (no second clone) on branch `native-sdk/cmake-standalone` at `Ghidra_12.1.3_build`; pointer move committed.
- [ ] Ghidra 12.1.3 release installed; SHA-256 checked against the release page.
- [ ] `uv pip install "$GHIDRA_INSTALL_DIR/Ghidra/Features/PyGhidra/pypkg"` into `.venv` (matches `test-headless.yml`).
- [ ] Versions recorded in `native/bench/environment.json`.
- **Verification:** `git -C vendor/ghidra describe --tags --abbrev=0` prints `Ghidra_12.1.3_build` (plain `describe --tags` gains a `-N-g<sha>` suffix once `native-sdk/cmake-standalone` has commits); `grep application.version $GHIDRA_INSTALL_DIR/Ghidra/application.properties` prints `12.1.3`; `pyghidra.start()` against 12.1.3 works.
- **Note:** `git submodule status` in the worktree may report the linked worktree as uninitialized. That is expected and belongs in `native/README.md`.

### WP1. Upstream-facing standalone CMake (P01 core)

Owner: upstream subtree only.

- [ ] `CMakeLists.txt` with `cmake_minimum_required(3.24)`, `project(GhidraDecompiler VERSION <from application.properties>)`, namespace `ghidra::`, options `GHIDRA_DECOMP_*`.
- [ ] Object libraries per Makefile group; archives `sla` (= `LIBSLA_NAMES`) and `decomp_archive` (= `LIBDECOMP_NAMES` minus `bfd_arch loadimage_bfd`); `decomp` as an INTERFACE target linking `decomp_archive` whole-archive plus zlib.
- [ ] Executables `sleigh_compiler`, `decomp_console`, `decomp_test`.
- [ ] Options `LOCAL_ZLIB`, `BFD`, `CONSOLE`, `TERMINAL`, `CPUI_DEBUG`, `SANITIZE`, `BUILD_TOOLS`, `BUILD_TESTS`, `SPEC_PROCESSORS`, `CXX_STANDARD` 11 with Gradle's flags, `INSTALL`. `TERMINAL`, `CPUI_DEBUG`, `LOCAL_ZLIB` are PUBLIC (they change class layout).
- [ ] Install and export `GhidraDecompilerConfig.cmake`; config exports `_SLA_FORMAT_VERSION` (parsed from `slaformat.cc`, `FORMAT_VERSION = 4` at the tag).
- [ ] `CheckMakefileManifest.cmake -P` parses the Makefile groups, computes `EXTRA` like `Makefile:100`, fails with `only-in-Makefile` / `only-in-CMake` lists; runs at configure and as ctest `manifest_matches_makefile`.
- **Verification:** all targets build; `ctest -R 'manifest|unittests'` green; `LOCAL_ZLIB=ON` and `CONSOLE=OFF` variants build; `cmake --install` plus a small `find_package(GhidraDecompiler)` consumer builds; `nm libdecomp_archive.a` shows no `GhidraCapability` symbols.

### WP2. Specs, smoke test, no-JVM proof (P01 completion)

Owner: upstream subtree.

- [ ] `ghidra_sleigh_compile_specs(...)` runs `sleigh_compiler` per `.slaspec` and lays out `<sleigh-home>/Ghidra/Processors/<P>/data/languages/` as `SleighArchitecture::scanForSleighDirectories` (`sleigh_arch.cc:572`) walks it.
- [ ] `sleigh_smoke <sleigh-home> <case>` for x86-64, ARM Thumb, AArch64 with hand-reviewed expected files; `decomp_smoke --check-capabilities`.
- [ ] Datatests: configure-time scan of `datatests/*.xml` selects the subset whose `arch` is covered by the compiled processors; ctest `decomp_datatests` and `decomp_unittests`.
- [ ] R01: ctest `no_jvm_linkage` (`ldd` / `readelf -d` must not match `libjvm|libjava|libjli|libjawt`), `no_jvm_runtime` (`env -i PATH=/usr/bin HOME=/nonexistent LANG=C sleigh_smoke ...`), and a documented podman build plus ctest in `registry.fedoraproject.org/fedora:44` with no JDK.
- **Verification:** `ctest -R 'smoke|capability|datatests|no_jvm'` green; podman run green.

### WP3. Session lifecycle and C ABI (P02, P03)

Owner: `native/sdk`, `native/CMakeLists.txt`, presets, `native/tests/sdk`, `gnsdk-selftest`.

- [ ] `gnsdk.h` frozen (pure C99, `gnsdk_` / `GNSDK_` prefix, size-tagged structs).
- [ ] `gnsdk_init(sleigh_home)` once per process; same home again is a no-op; a different home returns `GNSDK_STALE`. `gnsdk_shutdown` is a state transition, not a teardown.
- [ ] One live session per process; second create returns `GNSDK_BUSY`.
- [ ] States `CREATED`, `CONFIGURED`, `READY`, `BUSY`, `POISONED`, `DESTROYED`. Reset per function mirrors `IfcDecompile::execute`; reset per program is destroy plus create.
- [ ] Error mapping: `LowlevelError` in a request stays `READY`; init or restore failures poison; `bad_alloc` poisons and the worker exits 4 after replying; signals kill the process.
- [ ] Status classes per `native/conformance/status_codes.json`. Version info: abi triple, `sla_format_version`, `ghidra_version`, `source` = `git describe --tags` of the vendor tree at configure (must start with `Ghidra_12.1.3_build`), `build_flags`.
- [ ] Cancel: checkpoints before followFlow, perform, and print; optional in-loop action hook behind cap bit `CANCEL_IN_ACTION_LOOP`. Hard wall-clock is the supervisor's job.
- [ ] Boundary rules: every export `noexcept`; upstream included through one `upstream.hpp` with `-isystem`; never `using namespace ghidra`; `-Werror` only on `gnsdk*` targets.
- [ ] `gnsdk-selftest`: init, list languages, decompile smoke bytes, print version and caps.
- **Verification:** ctest `lifecycle_repeat`, `lifecycle_program_change`, `lifecycle_second_session_busy`, `lifecycle_partial_init`, `lifecycle_exception_paths`, `lifecycle_after_shutdown`, `abi_*` green.
- **Not claimed:** concurrency on any handle, thread-safety after init, TSan.

### WP4. Protocol codec, fake worker, pool test skeleton

Owner: `native/worker/protocol.*`, `native/tools/fake_worker.cpp`, `native/tests/{worker/protocol_roundtrip.cpp,pool}`.

- [ ] `protocol.hpp` frozen: 24-byte LE header (`GNSK`, major 1, minor 0, kind, flags, payload_len, request_id); JSON payload unless RAW; `HELLO` / `HELLO_ACK` negotiate `max_frame` and `max_image_bytes`; equal major required.
- [ ] Kinds: `HELLO, HELLO_ACK, OPEN_RAW, OPEN_SNAPSHOT, DISASM, LIFT, DECOMPILE, CLOSE_SESSION, CANCEL, PING, BYE` and `RESULT, ERROR, PROGRESS, PONG`. In-flight cancel is `SIGUSR1`. stderr is diagnostics only.
- [ ] `fake-worker --misbehave {hang, hang-ignore-term, die-midframe, oversize, bad-magic, garbage-stderr, slow-reply, eat-memory, exit-4, reply-wrong-id, honor-cancel}`.
- [ ] `pool_*` tests written now, `DISABLED` until WP6.
- **Verification:** ctest `protocol_roundtrip` green; fake worker exercises every misbehave mode.

### WP5. `gnsdk-worker` (P05 part 1)

Owner: `native/worker/main.cpp`, `native/tests/worker/worker_e2e.cpp`.

- [ ] `--sleigh-home DIR [--max-frame N] [--rlimit-as BYTES] [--rlimit-cpu SECS]`; `PR_SET_PDEATHSIG` then parent check; self-applied rlimits; `SIGPIPE` ignored; `SIGUSR1` cancels; `SIGTERM` cancels, finishes the reply, exits 0.
- [ ] Exit codes: 0 clean, 2 protocol, 3 poisoned, 4 resource, 5 init, 6 stdout failure.
- **Verification:** `worker_e2e`: HELLO, OPEN_RAW, DECOMPILE, BYE; then SIGUSR1 mid-request yields `cancelled` and the worker serves the next request.

### WP6. `gnsdk_pool` and `gnsdk-batch` (P05 part 2)

Owner: `native/pool`, `native/tools/gnsdk_batch.cpp`.

- [ ] `Supervisor(Config{...})` with `posix_spawn`, one `poll()` thread, `pidfd_open` plus `SIGCHLD` reaper.
- [ ] cgroup v2 hard cap only when `cgroup.subtree_control` is writable; else advisory rlimits and `hard_memory_cap=false`. README documents `systemd-run --user --scope -p Delegate=yes`.
- [ ] Bounds: in-flight equals live workers; queue by count and bytes; results buffered to an outstanding cap then dispatch stalls.
- [ ] Deadline ladder: `SIGUSR1`, then `SIGTERM` after `cancel_grace`, then `SIGKILL` after `term_grace`. Status mapping and retry rules per the RFC (crash once, protocol_error once, resource never, timeout never by default, always on a fresh worker).
- [ ] Orphans: PDEATHSIG, destructor SIGKILL plus reap, startup sweep of dead-pid tmpdirs and cgroup dirs.
- [ ] `gnsdk-batch --sleigh-home DIR [--workers N] [--timeout 60s] [--mem 4G] [--cgroup-mem 4G] [--tmpdir DIR] (--input jobs.jsonl | --snapshot <dir>) --output results.jsonl [--version]`. Exit 0 if all jobs reached a terminal status, 1 supervisor failure, 2 bad input.
- **Verification:** ctest `pool_kill9_worker`, `pool_parent_death`, `pool_slow_consumer`, `pool_truncated_frame`, `pool_oversized_frame`, `pool_enospc`, `pool_fd_exhaustion`, `pool_cancel_ladder`, `pool_stderr_flood`, `pool_cgroup_optional`; behind `GNSDK_HAVE_SPECS`: `pool_real_decompile_x86`, `pool_real_timeout`. After the suite: `pgrep -f gnsdk-worker` empty, tmpdir clean.

### WP7. Sanitizers, fuzzing, presets, native README

Owner: `native/fuzz`, `native/tests/lsan.supp`, `native/README.md`, presets.

- [ ] Presets `debug`, `relwithdebinfo` (default), `asan`, `ubsan`, `fuzz` (clang).
- [ ] Fuzz targets `fuzz_frame_decode.cc`, `fuzz_sleigh_disasm.cc`, `fuzz_pcode_lift_context.cc` with seed corpora; ctest `fuzz_smoke_*` with `-runs=1000`.
- [ ] Shared-lib variant `gnsdk_shared` with hidden visibility; ctest asserts only `gnsdk_` symbols are exported.
- [ ] `native/README.md`: build, presets, R01 proof, cgroup note, the linked-worktree submodule note, what is not claimed.
- **Verification:** `asan` and `ubsan` presets green; `nm -D --defined-only libgnsdk.so | grep -v ' gnsdk_' | wc -l` prints 0. TSan not built, not claimed.

### WP8. Snapshot exporter (P04 producer)

Owner: `src/agentdecompile_recovery/native_snapshot/{__init__,manifest,exporter,cli}.py`, `tests/test_native_snapshot_*.py`, `tests/fixtures/native_snapshot/test_x86_64/`.

- [ ] Layout: `<dir>/manifest.json`, `functions/<addr16>.xml` (overlay: `<space>__<addr16>`), `oracle/<addr16>.c`, `oracle/<addr16>.json`, `options.xml`. Timed-out functions renamed `.partial.xml` and excluded.
- [ ] Per run: refuse if a transaction is open; record `getModificationNumber()` before and after; mark `revision.stale` and exit non-zero on change. Style other than `decompile` refused in v0.
- [ ] Per function: skip `external`, `thunk`, `no_body`, `unsupported_name`; hold the program lock (`ghidra.util.Lock.acquire()/release()`, exclusive at the tag); re-arm `ifc.enableDebug(File)` every time; `decompileFunction` with a `TimeoutTaskMonitor`; classify `ok` / `timed_out` / `error`.
- [ ] Manifest schema `agentdecompile.native-snapshot/v0` with `export_requires_java_decompile: true`, producer, program, engine (`sig_major`, `sig_minor`, `sla_format_version`, `java_sla_sha256`), options (`sha256`, `simplification_style`), capabilities, revision, counts, `total_bytes`.
- [ ] CLI: `python -m agentdecompile_recovery.native_snapshot export <binary|project> --out <dir> [--addr ...|--all] [--timeout-s N]`.
- [ ] Commit the resulting 3-function `test_x86_64` fixture snapshot for JVM-free jobs.
- **Verification:** unit tests (schema round-trip, required keys, stale flag, overlay naming) green; integration with `GHIDRA_INSTALL_DIR`: export `tests/fixtures/test_x86_64`, savefiles start `<binaryimage` then `<coretypes>` / `<specextensions>`, oracle C non-empty.

### WP9. Replay, canonicalization, differential harness (P04 validation)

Owner: `native_snapshot/{canonical,replay,differential}.py`, `tests/test_native_canonicalize.py`, `tests/test_native_differential_*.py`.

- [ ] Path A `ConsoleReplayer(decomp_console, sleigh_home)`: per function `restore <xml>; load function <load_name>; decompile; print C; quit` with begin/end markers; one process reused for up to `--per-process 200` functions.
- [ ] Path B `BatchReplayer(gnsdk_batch --snapshot)` parses WP6 JSONL.
- [ ] `canonicalize(text)`: CRLF to LF, strip trailing whitespace per line, drop trailing blank lines, one final newline. Nothing else. `layout_collapsed()` only labels `mismatch-layout-only`; it never produces a match.
- [ ] Classes: `match`, `mismatch-layout-only`, `mismatch-content` (with `diff/<addr>.diff`), `native-missing-dependency`, `native-error`, `native-timeout`, `native-crash`, `oracle-absent`.
- [ ] Parity asserted: `manifest.engine.sig_*` equals native's pair (hard error); producer `ghidra_version` 12.1.3 and native `source` starts with `Ghidra_12.1.3_build` (hard error); `.sla` hash difference is a warning unless that language has any `mismatch-content`.
- [ ] CLI subcommands `replay` and `diff`; report at `<dir>/differential/{report.json,report.md,diff/}`.
- **Verification:** unit tests green; integration with `GHIDRA_INSTALL_DIR` and `GNSDK_BUILD_DIR`: `test_x86_64` export, replay, `match == ok_count`, zero crashes; slow: the shipped `sleigh` binary, all functions, agreement recorded and pinned as `expected_agreement`.

### WP10. Batch decompile over PyGhidra (P06) and bench harness (P00 part 2)

Owner: `src/agentdecompile_cli/mcp_utils/parallel_decompile.py`, `decompile-batch` subcommand in `corpus/cli.py`, `native_snapshot/{bench,procstat}.py`, `scripts/bench_native_sdk.py`, `native/bench/**`, related tests.

- [ ] `decompile_functions(program, functions, *, threads, timeout_s=60, options_configurer=None, on_result=None, monitor=None) -> BatchSummary` over `DecompilerConcurrentQ` with a private `GThreadPool` and `@JImplements` of `QCallback` and `BasicFactory` into a `CachingPool`. Results drained on the caller's thread through a bounded queue. `try/finally` disposes queue, pool, and thread pool.
- [ ] Read-only: refuse if a transaction is open; `stale` if the modification number changed; no lock held across the batch.
- [ ] `python -m agentdecompile_recovery.corpus.cli decompile-batch --threads N` writes into the existing `ctext` sqlite via `decompile_text.persist_text` and `pending_addrs()` so never-decompile-twice holds. MCP tool deferred.
- [ ] Bench lanes, one fresh JVM per lane: `serial`, `parallel` (N in 4, 8, 11), `ghidrecomp` (own row, `includes_analysis: true`), `export`, `native-console`, `native-batch`.
- [ ] Corpora in `native/bench/corpora.json`: `tiny` (`tests/fixtures/test_x86_64`, `tests/fixtures/elf/tiny_i386.elf`), `fixtures` (built by `native/bench/fixtures/build.sh`, `SHA256SUMS` committed), `sleigh` and `decompile` (the shipped 12.1.3 ELF binaries), `arm64-slice` (`tests/fixtures/test_arm64`; no aarch64 cross compiler on this host).
- [ ] Held constant: function list, options hash, timeout. Rates over the intersection of completed sets. `REFUSED (completion mismatch)` with exit 3 on drift beyond `--max-completion-drift` (default 0).
- [ ] Metrics: `wall_s`, `fn_per_s`, `cpu_s` (JVM plus descendants), `p50/p95/p99_ms`, `rss_hwm_mb`, `jvm_heap_max_mb`, child count high-water. `k_star = T_export / (T_java_parallel_best - T_native_best)` or `never`.
- [ ] Output `agentdecompile-native-out/bench/<ts>-<corpus>/{bench.json,bench.md}` with a "held constant" block.
- **Verification:** `tests/test_parallel_decompile_unit.py` (dispose on exception, backpressure, stale), `tests/test_parallel_decompile_integration.py` (threads=2; C text byte-equal to serial; JVM child `decompile` process count returns to baseline), `tests/test_native_bench_report.py` (intersection rule, refusal exit code, `k_star never`).

### WP11. Native Python and Rust consumers, conformance, CI, docs

Owner: `native/python/gnsdk`, `native/rust`, `native/conformance`, `.github/workflows/native-sdk.yml`, docs, `tests/test_gnsdk_ctypes_errors.py`.

- [ ] Python `gnsdk` package (ctypes, no deps, py >= 3.10): `_lib.py` loader (`GNSDK_LIBRARY_PATH`, then alongside package, then `find_library("gnsdk")`; error lists paths tried), `_abi.py`, `errors.py` generated from `status_codes.json`, `session.py` (context manager, not thread-safe, refuses `api_major` mismatch), `batch.py` (subprocess client for `gnsdk-batch`, no shared lib needed, never imports `agentdecompile`).
- [ ] Rust workspace: `gnsdk-sys` (bindgen on `gnsdk.h`, `GNSDK_LIB_DIR`), `gnsdk` safe wrapper (`Session` is `!Send + !Sync`; `Drop` destroys), examples `lift_bytes.rs`, `consume_batch.rs`.
- [ ] Conformance: `status_codes.json` single source; C ctest, `test_status_table.py`, `status_table.rs`; version negotiation tests assert `source` starts with `Ghidra_12.1.3_build`.
- [ ] CI `native-sdk.yml`: `build-test`, `jvm-free-smoke` (`debian:bookworm-slim`, `! command -v java`, replay the committed fixture snapshot), `asan`, `rust`, `differential` (Ghidra install steps copied from `test-headless.yml` with `version: "12.1.3"`), `macos` (`workflow_dispatch` only). `native/python/gnsdk` added to the ruff path in `test-unit.yml`. `tests/conftest.py` gains a `gnsdk_build_dir` fixture that skips without `GNSDK_BUILD_DIR`.
- [ ] Docs: this plan and its row in `docs/plans/README.md`; `docs/brainstorms/2026-09-08-ghidra-native-sdk-requirements.md`; STRATEGY track "Native decompiler tier (JVM-free replay)". Still to write by the owning agents: one short README/USAGE subsection with the `export` and `diff` commands; a Tier 1 line in `src/agentdecompile_cli/CLAUDE.md` section 20 and `skills/tiered-re-analysis/SKILL.md`; `native/README.md`; upstream `cpp/cmake/README.md`. `docs/solutions/tooling-decisions/native-decompiler-replay-differential.md` only after the first passing differential run.
- **Verification:** `tests/test_gnsdk_ctypes_errors.py` green; `cargo test` green; all CI lanes green on the branch; `python3 scripts/validate-frontmatter.py` passes on each new doc.

---

## Merge gate (end-to-end verification)

1. `cmake --preset relwithdebinfo && cmake --build --preset relwithdebinfo && ctest --preset relwithdebinfo` green; `asan` and `ubsan` presets green.
2. Upstream subtree alone: configure, build, ctest green here and inside `registry.fedoraproject.org/fedora:44` with no JDK (R01). `manifest_matches_makefile` also run once against master's Makefile to record the delta for the eventual rebase.
3. `gnsdk-selftest`, `gnsdk-batch --snapshot`, and the Python `gnsdk.batch` client run under `env -i`; `strace -f -e execve` shows no `java`.
4. Differential: 100% `match` on the declared supported set (`x86:LE:64:default`, style `decompile`) for `test_x86_64`; agreement on the `sleigh` binary recorded; every non-match classified; none `native-crash`.
5. Pool fault matrix green; `pgrep -f gnsdk-worker` empty and tmpdir clean after the suite.
6. Bench report under `agentdecompile-native-out/bench/`; completion-equality checks passed; this plan quotes only what the table shows and states `export_requires_java_decompile` and `k_star`.
7. AgentDecompile default path unchanged: `uv run pytest -m unit` and `uv run ruff check --no-fix src/ tests/` green with no native build present; `uv run pytest -m integration tests/test_parallel_decompile_integration.py` shows the child process count back to baseline.

Milestones: M1 upstream subtree builds and its ctest is green in the JDK-less image; M2 differential passes on `test_x86_64`; M3 pool fault matrix green with no orphans; M4 bench table with all lanes on the `sleigh` binary; M5 bindings and JVM-free smoke green.

Commit slices on `feat/native-sdk`, each message carrying the test command and result: (1) pin and worktree, (2) upstream CMake core, (3) specs, smoke, no-JVM, (4) sdk and lifecycle, (5) protocol and worker, (6) pool and batch, (7) sanitizers, fuzz, presets, (8) exporter and fixture snapshot, (9) replay and differential, (10) PyGhidra batch API and corpus stage, (11) bench and results, (12) Python and Rust consumers and conformance, (13) CI, docs, STRATEGY track.

---

## Risks & Dependencies

- **gcc 16 warnings from `-std=c++11` upstream sources.** Never `-w` upstream; `-isystem` on our side.
- **ODR:** `__TERMINAL__`, `CPUI_DEBUG`, `LOCAL_ZLIB` must stay PUBLIC. Static init order is safe only with static linking (one copy of each registry).
- **Spec compile time and memory.** x86-64 and AARCH64 each take minutes and a lot of RAM on this host. Keep the default processor set small; cache `sleigh-home` in CI by vendor commit.
- **Cancel hook may drift upstream.** Capability bit plus `pool_real_timeout` pass either way.
- **Java `getC()` vs native `print C` layout may differ systematically.** Reported as `mismatch-layout-only`, never silently normalized.
- **Savefile completeness is per decompile.** JVM and Dalvik are marked unsupported.
- **Exclusive `Lock` at the tag serializes export with any mutator.** Acceptable for a quiescent program; documented.
- **pyghidra API surface** limited to what 3.0.2, 3.1.0, and 3.2.0 share.
- **Host memory.** A prior `git submodule update --init` clone was SIGKILLed on this host. Do not clone the submodule again; the linked worktree avoids it.

---

## Progress

Dated deltas. Newest first. A delta names what was verified and how; it does not check boxes above unless the named verification ran.

### 2026-09-10 (benchmark report safety core)

- **Default native verification baseline:** after the worker parent-identity change, `ctest --test-dir native/build/relwithdebinfo --output-on-failure` passed 31/31. The receipt is retained under `agentdecompile-native-out/test-receipts/`; this does not complete any partial work package whose named acceptance cases are still absent.
- **WP7 toolchain repair in progress:** GCC 16's installed ASan linker script points at the absent `/usr/lib64/libasan.so.8.0.0`, so the old ASan build could not link `sleigh_compiler`. The ASan preset now selects the installed Clang 22 toolchain, whose `libclang_rt.asan` runtime is present; fresh configuration succeeded. The old incomplete GCC build was moved under gitignored `agentdecompile-native-out/abandoned-builds/`, and the Clang ASan build/test receipt remains required.
- **WP10 partial landed locally:** `3c1e54b` adds the native benchmark report builder. It consumes observed lane addresses and timings, refuses any non-identical completion set before calculating rates, percentiles, or `k_star`, and writes a JSON plus Markdown table. `tests/test_native_bench_report.py` passed 3/3, including refusal and `k_star = never` cases. This is deliberately not a performance result: lane collectors, the required corpora, and a real report under `agentdecompile-native-out/bench/` remain open.
- **Native-only collector evidence:** `f077e47` adds `scripts/bench_native_sdk.py`. A real fixture run wrote `agentdecompile-native-out/bench/20260910T034933Z-test_x86_64/{bench.json,bench.md,native-batch.jsonl}`. Both console and batch lanes completed exactly the same three addresses. The table explicitly records `export_requires_java_decompile: true` and `k_star: never`; it is not a serial/parallel/export comparison and therefore cannot satisfy the full benchmark gate yet.
- **WP6 fault cleanup strengthened locally:** `978240e` retires/reaps a worker immediately when a write, poll, framing, EOF, or wrong-ID fault occurs instead of leaving it alive until `stop()`. `132c7b6` adds a crash-mid-frame regression. The focused pool fault set passed 5/5, with explicit zero-live-worker assertions after wrong-ID and truncated-response faults. Respawn/retry policy, queue accounting, cgroups, and the remaining plan fault cases are still open.
- **WP11 Rust consumer has a real lifecycle test:** `b751226` adds a raw x86 image test for the safe `Session` wrapper. With the shared SDK and its compiled SLEIGH home, `cargo test --manifest-path native/rust/Cargo.toml --workspace` now runs one actual init/create/load/decompile/drop test successfully (rather than a zero-test workspace). Publish/install policy and CI remain open.
- **WP5 real cancellation evidence landed locally:** `e5b4b61` adds a test-hook-only delay to the test build of `gnsdk-worker`. The real worker e2e sends SIGUSR1 during an active decompile, receives a cancelled reply, then proves the same worker serves the next request. `worker_e2e` passed with the hook compiled under `GNSDK_ENABLE_TEST_HOOKS`; production workers do not contain the hook.
- **WP5 parent identity and production-shaped test coverage strengthened locally:** `59c448e` keeps the cancellation probe conditional on `GNSDK_ENABLE_TEST_HOOKS`, so the ordinary HELLO/open/decompile/BYE path remains valid when test hooks are absent. The pending worker change makes the real worker verify `GNSDK_EXPECTED_PPID` after `PR_SET_PDEATHSIG`, while the supervisor supplies a fresh value instead of inheriting one from its environment. Focused hooked and hook-free `worker_e2e` runs passed, as did the hooked supervisor spawn test. The full default-suite receipt must be rerun cleanly after this change; restart/retry, queue accounting, cgroups, and the remaining pool matrix remain open.

### 2026-09-10 (checked-in three-function native replay fixture)

- **WP8/WP9 evidence added locally:** the official PyGhidra exporter created `tests/fixtures/native_snapshot/test_x86_64` from the existing x86-64 fixture on the installed Ghidra 12.1.3 runtime. Its manifest validates and contains exactly three successful savefiles and Java oracles (`_add`, `_multiply`, `entry`). `tests/test_native_replay_integration.py` is opt-in through `GNSDK_BUILD_DIR` so ordinary Python runs remain native-build-free; against `native/build/relwithdebinfo`, the replay unit, differential unit, and three-function real console lane passed 5/5 with every classification exactly `match`. The fixture is a reproducible exporter product, not a hand-authored C baseline.
- **WP6 JVM-free evidence added locally:** `tests/test_native_batch_integration.py` feeds that same fixture through `gnsdk-batch` and strictly classifies all emitted C against the Java oracles. The real batch and console tests passed 2/2. Separately, `env -i PATH=/usr/bin HOME=/nonexistent LANG=C gnsdk-batch --snapshot ...` completed all three functions, so this replay path does not need a Java runtime. `native/bench/environment.json` records the host/tool versions for forthcoming measurements.

### 2026-09-10 (first end-to-end native snapshot batch result)

- **WP6 partial landed locally:** `0586fdf` adds `gnsdk-batch` for `--snapshot` and explicit snapshot-job JSONL. It opens each savefile in the real worker and emits a JSONL decompile result. `d1b9804` makes the standalone Python batch consumer use this actual file-based input/output contract. A real export of `test_x86_64` ran through Python client -> `gnsdk-batch` -> worker and returned `_add` C; `pool_supervisor_smoke` and `gnsdk_batch_version` passed 2/2. This intentionally uses one worker because session affinity and pool-wide routing are not implemented. Queue bounds, multi-worker scheduling, retries, cgroups, resource classifications, and the required fault matrix remain open.

### 2026-09-10 (first real native console replay match)

- **WP9 partial landed locally:** `e0aaabc` adds `ConsoleReplayer`, which runs the real upstream console with `SLEIGHHOME` set to the compiled home, restores a savefile, loads its recorded function name, decompiles, and extracts C between standalone console markers without discarding leading source layout. A fresh real PyGhidra export of `test_x86_64` then replayed `_add` through `decomp_console`; strict canonical differential classification was `match`. The focused replay plus classifier suite passed 3/3. The report CLI, committed fixture snapshot, multi-function run, and full differential lane remain required.

### 2026-09-09 (native Python/Rust consumers and usable shared target)

- **WP11 partial landed locally:** `af8cde6` adds the dependency-free Python ctypes package and a real shared-library raw-image decompile test. It also fixes the CMake target graph: `gnsdk` and `gnsdk_shared` now depend on compiled SLEIGH definitions, so a direct shared-target build creates a usable SLEIGH home instead of an empty directory. The Python suite passed 3/3 against `libgnsdk.so`; `abi_shared_exports` passed 1/1. `e9afc08` adds the Rust workspace: bindgen reads frozen `gnsdk.h`, the safe Session wrapper is `!Send + !Sync`, and its x86-64 example produced real decompiled C. CI cannot yet truthfully build this lane from a normal checkout because the standalone upstream-CMake submodule commit is local-only; no deceptive workflow was added.
- **Still required:** the Rust consumer needs a publish/install policy, the JSONL batch executable is not implemented, and CI can only be enabled after the gitlink target is fetchable by GitHub Actions.

### 2026-09-09 (export/batch verified; pool and fuzz foundations added)

- **WP8 landed locally:** `71c749b` exports a read-only PyGhidra program into a manifest plus one savefile/XML/options bundle per selected function. The transaction guard permits only the proven empty PyGhidra bootstrap transaction and rejects real caller mutations. `tests/test_native_snapshot_export_integration.py` passed 9/9 against the installed Ghidra 12.1.3 runtime, and `tests/test_native_snapshot_manifest.py` passed 30/30.
- **WP10 landed locally:** `b9f7ded` adds bounded private-pool PyGhidra decompilation and preserves existing corpus persistence behavior. Its unit suite passed 12/12 and the real serial-versus-two-thread integration test passed with byte-identical C text.
- **WP6 remains incomplete, but its tested foundation landed locally:** `28a9dfa` adds a `posix_spawn` supervisor with dedicated stdin/stdout protocol pipes, HELLO negotiation, pidfds when supported, and a SIGUSR1 -> SIGTERM -> SIGKILL deadline ladder. `ctest --test-dir native/build/relwithdebinfo -R '^pool_supervisor_smoke$' --output-on-failure` passed 1/1 against two fake workers. The full fault matrix, respawn policy, JSONL batch CLI, cgroups, and real pool tests remain required.
- **WP7 partial landed locally:** `27828fb` adds Debug/RelWithDebInfo/ASan/UBSan/libFuzzer presets and a chunk-boundary fuzzer for the production protocol decoder. `cmake --preset fuzz -S native`, build of `protocol_fuzzer`, and `protocol_fuzzer -runs=1000 -seed=12345` passed. Sanitizer CTest lanes and a checked-in corpus remain required.
- **Next:** implement the batch/replay runners and their report artifacts, then finish pool fault handling, bindings, CI, benchmarks, and all merge-gate lanes. No package described as partial above is a completed work package.

### 2026-09-09 (real worker e2e and narrow differential core)

- **Landed:** `13e3729` adds `gnsdk-worker` over the frozen protocol and C ABI: HELLO negotiation, raw/snapshot sessions, DISASM/LIFT/DECOMPILE, SIGUSR1 cancellation, parent-death signal, and self-applied address-space/CPU rlimits. Its real-worker test ran HELLO -> OPEN_RAW -> DECOMPILE -> BYE against compiled x86-64 SLEIGH specs and passed: `ctest --test-dir native/build/relwithdebinfo -R '^worker_e2e$' --output-on-failure -j1` (1/1). `gnsdk-selftest`, protocol roundtrip, fake-worker smoke, and its full misbehavior matrix also passed from the CTest log. `c5d77a9` and `8eda04f` add the intentionally narrow canonicalization and the strict `match` / `mismatch-layout-only` / `mismatch-content` / `native-crash` classifier; their focused pytest suites passed.
- **Partial:** WP8 remains uncommitted. The real PyGhidra export test still reaches an unresolved transaction-lifecycle condition after `open_program(..., analyze=True)`; no snapshot manifest was created and the export suite is not green. The implementation must preserve the read-only transaction requirement while repairing the fixture/program lifecycle.
- **Next:** finish console/batch replay and report writing; then repair and re-run the real exporter before committing WP8. Pool supervision, fuzzing, bindings, CI, and benchmark work are still absent and remain required by the merge gate.

### 2026-09-09 (upstream CMake repaired; downstream audit)

- **WP3/WP4, green and committed locally:** `fdca4b6` adds the public C ABI, session lifecycle implementation, and direct lifecycle tests; `d2180d8` registers the protocol round-trip and fake-worker misbehavior matrix; `14c6963` adds `gnsdk-selftest`. `ctest --test-dir native/build/relwithdebinfo --output-on-failure -j1` passed 22/22 before the selftest was added. `ctest --test-dir native/build/relwithdebinfo -R '^gnsdk_selftest$' --output-on-failure` then passed 1/1 and the executable printed real x86-64 SLEIGH disassembly (`PUSH RBP`, `MOV RBP,RSP`, `XOR EAX,EAX`, `POP RBP`, `RET`) plus Ghidra `12.1.3` provenance. The post-analysis PyGhidra export integration remains open: `getCurrentTransactionInfo()` can retain a stale record after analysis, so the exporter now consults the current transaction id where available; the real export suite still requires a clean captured result before WP8 is committed.

- **WP1/WP2, green and committed locally:** `vendor/ghidra` commit `7309d92206` adds the standalone CMake entrypoint and the three reviewed SLEIGH smoke fixtures; parent commit `496a366` advances the gitlink. `cmake --build native/build/upstream -j4 && ctest --test-dir native/build/upstream --output-on-failure` passed all 10 tests, including `decomp_unittests` (204/204), every smoke fixture, `no_jvm_runtime`, and `no_ghidra_process_symbols`. Unit coverage required compiling the Toy, PowerPC, and MIPS processor definitions in addition to x86, ARM, and AARCH64. Smoke output had process-address instability in LOAD/STORE space IDs; the smoke printer now emits the semantic `spaceid[ram]` token, and repeated x86-64 runs hash identically.
- **WP3 is not commit-ready:** `cmake -S native -B native/build/relwithdebinfo ...` fails at generation because `native/sdk/CMakeLists.txt` declares `src/abi.cpp`, but that implementation is absent. The C ABI header and session internals remain uncommitted work until a complete boundary implementation and lifecycle tests exist.
- **WP4 is not commit-ready:** fake-worker/protocol test sources exist, but `native/tests/` has no `CMakeLists.txt`, so these tests are not part of any build or ctest target.
- **WP8 unit schema is green; real export is blocked by the fixture:** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -q tests/test_native_snapshot_manifest.py tests/test_parallel_decompile_unit.py` passed 40 checks. `tests/test_native_snapshot_export_integration.py` then failed because its `pyghidra.open_program(..., analyze=True)` fixture retains a current analysis transaction. The exporter correctly rejects that state before exporting; do not weaken its transaction precondition. Repair the fixture/program lifecycle and rerun the real export suite before committing WP8.

### 2026-09-09 (first run interrupted; packages restarted)

- **WP0, verified on disk:** worktree HEAD is `2db9f47` "wip: native SDK contracts and protocol codec snapshot" on `feat/native-sdk`, on top of `85e0238` (the pointer move) and master `22cbd8a`. `vendor/ghidra` is a linked worktree on `native-sdk/cmake-standalone`; `git describe --tags --abbrev=0` prints `Ghidra_12.1.3_build`, plain `describe --tags` prints `Ghidra_12.1.3_build-1-gf323dec82f` because the branch now carries one commit (`f323dec82f` "wip: standalone CMake helper modules"). HEAD records that commit as the gitlink. `/home/brunner56/ghidra-install/ghidra_12.1.3_PUBLIC/Ghidra/application.properties` has `application.version=12.1.3`. `.venv` still reports pyghidra 3.0.2. `native/bench/environment.json` does not exist. WP0 boxes stay open until the `pypkg` install and the environment file are verified.
- **First agent run interrupted.** WP1, WP2, WP3, WP4, WP8, and WP10 were restarted on 2026-09-09 and are in progress. No box in those packages is checked; no verification command from those packages has been recorded here.
- **On disk at the time of this delta (unverified, not built):** upstream subtree has `cpp/cmake/{CheckMakefileManifest,GhidraDecompSources,NoJvmCheck,SleighCompileSpecs}.cmake`, `GhidraDecompilerConfig.cmake.in`, and `cmake/smoke/`; no `cpp/CMakeLists.txt` yet. AgentDecompile side has `native/conformance/status_codes.json`, `native/sdk/include/gnsdk/gnsdk.h`, `native/worker/{protocol.hpp,protocol.cpp,json_min.hpp,json_min.cpp,CMakeLists.txt}`. Missing: `native/CMakeLists.txt`, `src/agentdecompile_recovery/native_snapshot/`, `src/agentdecompile_cli/mcp_utils/parallel_decompile.py`, `scripts/bench_native_sdk.py`, `.github/workflows/native-sdk.yml`, and every `tests/test_native_*` and `tests/test_parallel_decompile_*` file.
- **Docs landed in this delta:** the row for this plan in `docs/plans/README.md`, `docs/brainstorms/2026-09-08-ghidra-native-sdk-requirements.md`, and the STRATEGY track "Native decompiler tier (JVM-free replay)". The priority ladder is unchanged and the ladder plan stays the `active_living_plan`. Still owed by the owning agents: README/USAGE subsection, the Tier 1 line in `src/agentdecompile_cli/CLAUDE.md` section 20 and the tiered-re-analysis skill, `native/README.md`, upstream `cpp/cmake/README.md`.

### 2026-09-08 (plan opened)

- **WP0, verified on disk:** worktree `.claude/worktrees/native-sdk` is on `feat/native-sdk`; HEAD `85e0238` "chore: pin vendor/ghidra to Ghidra_12.1.3_build for the native SDK series" on top of master `22cbd8a`. `vendor/ghidra/.git` is a file (linked worktree of the module repo, no second clone), branch `native-sdk/cmake-standalone`, `git describe --tags` prints `Ghidra_12.1.3_build` (`8b4c91d4d5`). Ghidra 12.1.3 is installed at `/home/brunner56/ghidra-install/ghidra_12.1.3_PUBLIC` (`application.version=12.1.3`, build date 2026-Aug-17).
- **WP0, not yet verified:** `.venv` still reports pyghidra 3.0.2 (the 12.1.3 `pypkg` install has not been confirmed); `native/bench/environment.json` does not exist yet. Boxes stay open.
- **In progress by parallel agents:** WP1, WP2 (upstream subtree), WP3 (sdk), WP4 (protocol), WP8 (exporter), WP10 (Java batch and bench). At the time of this delta the only file under `native/` in the worktree is `native/.gitignore`; no `CMakeLists.txt` exists yet in the upstream subtree and `src/agentdecompile_recovery/native_snapshot/` does not exist yet.
- **Docs in this delta:** this plan was opened. The row in `docs/plans/README.md`, `docs/brainstorms/2026-09-08-ghidra-native-sdk-requirements.md`, and the STRATEGY track had not landed when the first agent run was interrupted; see the 2026-09-09 delta.
- **Host recorded for the bench environment file (to be written by WP0/WP10):** cmake 4.3.0, ninja 1.13.2, gcc 16.2.1, clang 22.1.8, OpenJDK 21.0.11, podman 5.8.4, 12 CPUs, 31 GB RAM, system pyghidra 3.1.0, `.venv` pyghidra 3.0.2.

---

## Deferred backlog

Unchecked. Each item names the RFC id it comes from. None of these is in progress.

- [ ] **P06 (Java side).** Java additions to `DecompilerCallback` or `ParallelDecompiler`. Needs a Gradle/JDK toolchain and maintainer agreement. The Python-over-JPype batch API (WP10) is the v0 answer.
- [ ] **P08.** Database and cache optimization for repeated decompiles.
- [ ] **P09.** In-process concurrency. Blocked on an audit of the non-reentrant XML, bison, and flex parsers and on a real teardown upstream.
- [ ] **P10.** JVM-free ingestion and loaders. v0 export still needs Ghidra to load and analyze the program.
- [ ] **P11.** Release and compatibility graduation: an ABI stability declaration needs two independent consumers over time.
- [ ] **X01.** GraalVM.
- [ ] Binary snapshot schema v1: compression, multi-function archive.
- [ ] nanobind binding behind the same `session.py` surface.
- [ ] MCP `decompile-functions-batch` tool over WP10's API.
- [ ] The upstream PR itself: needs a fork remote and maintainer contact per `CONTRIBUTING.md`; content is WP1 and WP2 files only, squashed, manifest check re-run against master.

---

## Sources & Research

- `~/.claude/plans/rfc-and-implementation-structured-dongarra.md` (approved plan; outside the repo).
- `STRATEGY.md` (priority ladder, tracks). `docs/plans/README.md` (living vs frozen).
- `docs/plans/2026-07-24-perf-recovery-one-shot-living-plan.md` Baseline table (the one measured number).
- `src/agentdecompile_cli/mcp_utils/decompiler_util.py` `_configure_decompiler_for_program` (shared option source).
- `src/agentdecompile_recovery/corpus/decompile_text.py` `persist_text`, `pending_addrs`.
- `vendor/ghidra` at `Ghidra_12.1.3_build`: `Ghidra/Features/Decompiler/src/decompile/cpp/{Makefile,libdecomp.cc,sleigh_arch.cc,xml_arch.cc,consolemain.cc,ghidra_process.cc,slaformat.cc,signature_ghidra.cc}`, `Ghidra/Features/Decompiler/src/main/java/ghidra/app/decompiler/DecompInterface.java`, `Ghidra/Framework/Project/src/main/java/ghidra/util/Lock.java`, `CONTRIBUTING.md`.
- `.github/workflows/test-headless.yml` (Ghidra install and `pypkg` steps to copy).
