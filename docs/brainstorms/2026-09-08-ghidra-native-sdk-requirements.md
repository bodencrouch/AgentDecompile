---
date: 2026-09-08
topic: ghidra-native-sdk
---

# Ghidra Native SDK: export once, replay without a JVM

## Summary

Use Ghidra's own native SLEIGH and decompiler without a JVM in every worker. Export a program once from Ghidra as one decompiler savefile per function plus a manifest. Re-decompile those savefiles with the native engine for option sweeps, engine-upgrade regression checks, and consumers that cannot host Java. Compare native output to the Java decompile of the same program on the same engine version. This remains a research proposal; prioritize and sequence implementation through `STRATEGY.md` and the comprehensive delivery plan.

## Problem Frame

AgentDecompile decompiles through single-threaded `DecompInterface` loops. Every decompile pass, and every option or engine change, pays for a JVM and for Ghidra's process-per-decompiler model again. A historical benchmark recorded 8,621 functions in 342 s at 4 threads via `ghidrecomp`; treat it as an old observation, not a current throughput guarantee.

Ghidra already ships a native decompiler and a native SLEIGH. Three things stand in the way of using them on their own:

- No upstream build target links both into one library without libbfd. The hand `Makefile` is the only description of that library. There is no CMake upstream.
- `DecompileDebug` can capture every host query for one function into an `<xml_savefile>`, but only a Makefile-built console binary can `restore` it. The capture is one-shot per function.
- The native tree has no teardown and its XML, bison, and flex parsers are not reentrant. Threads in one process are not a safe option at the pinned commit.

## Who it serves

- **Operators running bulk C on a corpus** (STRATEGY ladder step 4, readable C). They can re-run a decompile with different options, or on a new engine build, without re-opening the Ghidra project.
- **Agents at Tier 1** of the tiered-re-analysis skill, next to `ghidrecomp` (`src/agentdecompile_cli/CLAUDE.md`, section on tiers). A snapshot plus the native batch tool gives them C text with no JVM.
- **Consumers that cannot host Java:** a CI job in a slim container, a Rust or Python tool, a fuzz target.
- **Maintainers checking an engine upgrade.** Replay the same snapshot on two engine versions and diff.

## Requirements

Detailed requirements R1 to R16 live in the plan. In short:

- R-A. A standalone CMake build on an upstream-shaped branch inside `vendor/ghidra` produces a library with both SLEIGH and the decompiler from unchanged sources. A manifest check fails on drift from the Makefile.
- R-B. A small C ABI and a process-isolated worker pool under `native/`. One live session per process. Hard errors poison the session, not the process.
- R-C. A Python exporter writes `manifest.json`, one savefile per function, and the Java C oracle for the same decompile.
- R-D. A differential harness replays the snapshot natively, canonicalizes whitespace only, and classifies every function.
- R-E. A bench harness that measures. Every lane holds the same function list, options, and timeout.

## Scope Boundaries

**In scope (v0)**

- Per-function `<xml_savefile>` snapshots, plain XML, one file per function.
- Replay through the console binary and through the native batch tool.
- Languages on the declared supported set only: `x86:LE:64:default` with simplification style `decompile`.
- A Java-side batch API over PyGhidra (`decompile_functions`) so the corpus pipeline can use Ghidra's own thread pool. It writes into the existing `ctext` store through `pending_addrs()`.
- Python (ctypes) and Rust (bindgen) consumers that never import `agentdecompile`.

**Out of scope (deferred backlog in the plan)**

- Binary snapshot schema v1: compression, multi-function archives.
- In-process concurrency (P09). Blocked on the non-reentrant parser audit and a real teardown upstream.
- JVM-free loaders and ingestion (P10). v0 export still needs Ghidra to load and analyze the program.
- Java-side changes to `DecompilerCallback` or `ParallelDecompiler` (P06 Java side).
- Release and ABI stability graduation (P11), GraalVM (X01), a nanobind binding, an MCP batch tool, and the upstream PR itself.

## Success Criteria

- 100% `match` on the declared supported set for `tests/fixtures/test_x86_64`. Agreement on the shipped `sleigh` binary is recorded, every non-match is classified, and none is `native-crash`.
- The JVM-free smoke is green in a container with no JDK.
- The bench table exists. `k_star` (the export break-even) is reported from the table or as `never`. It is not assumed.
- `uv run pytest -m unit` and `uv run ruff check --no-fix src/ tests/` stay green with no native build present.

## Constraints

- Upstream `CONTRIBUTING.md` binds the submodule branch: smallest reasonable change, no renaming or repackaging without prior authorization, extra scrutiny for AI-assisted code. The branch adds files only and never moves a source.
- No default-path change. Existing `DecompInterface` callers stay as they are. `DecompilerLease` is untouched.
- Never decompile the same logical function twice. The Java batch path goes through `pending_addrs()` and `persist_text` in `src/agentdecompile_recovery/corpus/decompile_text.py`.
- Export requires one Java decompile per function. The manifest says so (`export_requires_java_decompile: true`).
- Engine parity is asserted, not assumed. The manifest's engine pair must equal the native pair, and the native `source` string must start with `Ghidra_12.1.3_build`.
- Canonicalization is whitespace only. Any widening is recorded in `docs/solutions/` first.
- No performance claim before the bench table exists.

## Dependencies / Assumptions

- `vendor/ghidra` is pinned to `Ghidra_12.1.3_build` as a linked worktree of the module repo. Ghidra 12.1.3 is installed at `/home/brunner56/ghidra-install/ghidra_12.1.3_PUBLIC` as the Java oracle.
- The pyghidra versions in play (3.0.2 in `.venv`, 3.1.0 on the system, 3.2.0 in the tree) share the API surface the exporter uses.
- Host memory is tight. Spec compilation and JVM lanes do not run at the same time.

## Outstanding Questions

**Deferred to Planning**

- Savefile size per function is not measured. The manifest records `total_bytes`; the plan quotes it only after a run. Whether v1 needs compression depends on that number.
- Java `getC()` and native `print C` may differ in layout on some functions. The harness labels that `mismatch-layout-only` and never normalizes it. Whether the label is common enough to need a fix upstream is unknown until the first differential run.
- The cancel hook inside the action loop may drift upstream. The capability bit lets the pool test pass either way; whether to carry the hook at all is open.
- Whether the exclusive `ghidra.util.Lock` at the tag (no read/write variant until master) blocks any real export workflow. It serializes export with any mutator, which is fine for a quiescent program.
