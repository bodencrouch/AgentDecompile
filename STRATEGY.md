---
name: AgentDecompile
last_updated: 2026-09-09
charter: VISION.md
active_living_plan: docs/plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md
---

# AgentDecompile Strategy

Charter lives in [VISION.md](VISION.md). Operators start at [README.md](README.md). This file is the investment bet under that charter, not a second north star.

## Target problem

A Ghidra project holds dozens of builds of the same codebase. Each build has its own addresses, but the functions, labels, and types are the same logical objects. Without cross-build identity and a propagation path, every recovery pass repeats work and metadata edits on one binary never reach the others. The crux is telling honest source from a wrapper that only compiles because it still contains the original bytes.

## Our approach

Link the builds, recover on the easiest one, and propagate. Bind every function to a `logical_id` from evidence that survives a rebase, not from a virtual address. Prefer one signature family that hits every registered build: debug/STABS names and compilation unit, then strings/constants/imports and decompiled shape, then BSim, then a unique byte window only when those fail. Copying a nearby instruction blob from one exe into another is the last-resort signal, not the matcher. Do not re-run Ghidra analysis on a program that already has it. Solve compiler, ABI, and global layout once before per-function spend. Scaffold with a linking assembly floor, bulk-replace with compiling Ghidra C, place that C on siblings, spend agent compute only on leftovers, then audit bytes last. Export the identity as a Phasor-shaped hook pack. One catalog on 8080.

## Who it's for

**Primary:** An operator, or an agent acting as one, finishing byte-accurate, assembly-free source for every program in a multi-build Ghidra corpus, with labels and structures kept in sync across builds.

**Secondary:** Someone who only needs citeable facts or a navigable tree and stops before the recovery bar.

## Key metrics

- **Verified readable C:** distinct logical functions with objdiff 0 (coverage or isolated audit receipts). Can regress on audit. Not the same as `real_c`.
- **Compiling Ghidra C share:** functions whose decompiled C is assembly-free and compiles (`ghidra-bulk` tally, `real_c=1`). Leading indicator, not proof.
- **Cross-placed compiling C:** compiling functions placed on sibling builds via `logical_id` (`cross-place` receipts).
- **Identity coverage:** inventoried functions bound to a logical function (`identity` table). Must stay high before propagation claims.
- **Portable resolve:** share of those `logical_id`s that resolve on every registered build from one signature family, not a per-build VA. Can regress when a rebuild changes the window.
- **Loop completion:** catalog jobs from `/dashboard` end with named files on disk, not hang or silence.

## Tracks

### One operator surface (8080)

Workbench + kotorxid corpus pages + Atlas + report + `/api/v1/actions` on the MCP HTTP server. Deprecate leftover dashboard ports when in-tree server runs with corpus env.

_Why it serves the approach:_ Agents and humans must share one catalog and one progress view or they will diverge on what "done" means.

### Corpus recovery pipeline

Extract facts → `logical_id` → global calibration → scaffolding (assembly floor) → readable C (`ghidra-bulk`) → propagation (`cross-place`) → targeted AI on leftovers → parity (objdiff) last. Skip a step when its receipt or Ghidra state already exists. Parallelize analysis, evidence extract, bulk C, and matching. Serialize `logical_id` writes, mutations to one Ghidra project, and isolated compiler/objdiff environments.

_Why it serves the approach:_ Recover once on the easy build and share the win. Do not reverse twenty versions independently.

### Ghidra shared state

One store, BSim, prompt evidence from this tree's venv CLI, session-stable `ensure-program`. Label/type edits flow through identity, not per-address copies. Ghidra Server is RMI over SSL, not HTTP.

_Why it serves the approach:_ Cross-match metadata only works if Ghidra state and recovery receipts share the same program binding.

### Portable identity / hook-pack export

`corpus.export-hookpack` writes a Phasor-shaped pack: logical site names, the preferred signature family, and per-build addrs only as a cache. KotorPhasor (or a clone for another corpus) resolves by unique `expected_bytes` when the recorded VA is missing or stale. Game names stay in data packs, not the resolver.

_Why it serves the approach:_ The matcher already refuses raw addresses. A hook host that still keys on `0x005D45D0` per exe repeats the hunt the corpus just finished.

### Native decompiler tier (JVM-free replay)

Export a program once from Ghidra as per-function decompiler savefiles with a manifest. Re-decompile those savefiles with Ghidra's own native engine and no JVM. Use that for option sweeps, engine-upgrade regression checks, and consumers that cannot host Java. The export itself still needs one Java decompile per function. Native output is checked against the Java decompile of the same program on the same engine version. A mismatch is a bug, not a tolerance. The priority ladder below is unchanged. This tier feeds step 4 (readable C) and sits at Tier 1 next to `ghidrecomp` in the tiered-re-analysis skill. Living plan: `docs/plans/2026-09-08-2330-feat-ghidra-native-sdk-plan.md`.

Current scope (2026-10-09): acceptance work covers the optional Ghidra-only CMake build and installed package, not the retained downstream SDK/replay work above. At the candidate's exact upstream source, `DecompInterface` owns and initializes a native process (`DecompInterface.java:134,258-285`) and synchronizes `decompileFunction()` (`:769`); `DecompilerCallback` pools distinct interfaces and releases them in `finally` (`parallel/DecompilerCallback.java:43-78`), while `ParallelDecompiler` dispatches through `DecompilerConcurrentQ` on a shared `GThreadPool` (`parallel/ParallelDecompiler.java:94-120`). Existing one-JVM multi-worker concurrency therefore exists. `DecompilerConcurrentQ` disposes its queue on completion, but it does not dispose the callback; `DecompilerCallback.dispose()` owns that pool cleanup, so callers must manage callback lifetime. Discussion #2903 points to this API and warns about disposal. Issue #2171 concerns multi-file decompilation workflow, not a worker-pool design. The CMake candidate adopts the standalone-consumption rationale of issue #3652 and the external `lifting-bits/sleigh` precedent, not a runtime batching strategy. This candidate adds standalone build/consumption support only: it does not change Ghidra's Java startup path, worker scheduling, or process reuse, and it establishes no measured speedup or new in-process thread safety. Compatibility evidence is bounded to the exact tested source revisions and configurations; no universal forward C++ ABI guarantee is claimed. A separate strict Clang 22 C++11 ASan/UBSan run passes 207/207 native unit cases after isolated fixes to existing undefined behavior; those fixes are not in the CMake candidate, whose strict default C++11 sanitizer gate remains red. This unit result does not certify every sanitizer/CTest gate or runtime path. Candidate receipts do not certify the retained downstream SDK/replay integration.

Acceptance refresh (2026-10-04): Ghidra-only candidate `eventual-pr/cmake-submit-v2` is being rebased/tested against exact official master `a462673d2f1543d153c61d10bcd6c68f85555194`. The current-master CMake 4.3/Ninja build passes CTest 20/20 (205 native unit cases, 87 effective data fixtures); bundled-zlib with console disabled passes 17/17, including installed-consumer checks; Fedora 44 no-Java CTest passes 20/20 with the acceptance count checks. The exact-master Make/CMake wrapper passes bounded initial streams, five `.sla` byte comparisons, and save/restore cross-consumption on concat, forloop1, and bitfields. Java 25/Gradle 9.1 native/IP, jar/spec, distribution (395 native source files), and selected GUI/cache integration tests pass. A custom headless Java post-script did not finish: at 2 GB it hit OOM in Ghidra dev-source compilation; at 4 GB it remained in full source-bundle compilation across validation trees for 30 minutes and was interrupted before the script ran. Do not claim headless/project-reopen or Java/native spec parity. The prior `save <filename>` check was a harness error: both front ends report the same invalid-command result and produce no file; this is not a format mismatch. Strict default C++11 ASan/UBSan remains red on unchanged engine UB, with the engine correction kept separate. This candidate neither fixes the original performance bottleneck nor establishes a speedup. No universal forward compatibility or C++ ABI claim is made.

Review refresh (2026-10-04): the complete local review at `/tmp/compound-engineering-1000/ce-code-review/20261004-081529-88b0ffcf/report.md` confirmed two issues, now repaired in the uncommitted candidate diff: detect SLEIGH output write failure before publishing the final `.sla`, and require exact package-version matching because the candidate makes no cross-revision ABI/spec promise. Current-master CMake and installed-consumer suites pass; the exact-master Java IP task caught two omitted CMake-file manifest rows, now repaired and verified. Strict default C++11 ASan/UBSan remains red on valid-input `address.hh` signed-shift UB; keep that engine fix isolated and do not waive the finding. The review's earlier variant gap is closed on both the candidate base and exact-master local-zlib/console-off configuration; empty-environment full decompilation has only native test evidence, not the incomplete headless Java-script probe. The candidate remains an enabler only: it does not remove Java/native-worker initialization latency or prove faster decompilation.

Variant follow-up (2026-10-04): the review's local-zlib/console-off gap is closed on the chosen candidate base and on exact official master. On exact master, CMake 4.3/Ninja with Toy specs, bundled zlib, `GHIDRA_DECOMP_CONSOLE=OFF`, tests and install enabled built both archives and passed 17/17 CTests; the nested installed consumer passed 2/2 and confirmed that console-dependent capability use is rejected. Exact-master CTest log SHA-256 `25619b3b093aa8e3b086725f6687e7b84c5a81a4c06ab6d4b329065f7d491ace` in the `ghidra-pr-master-submit-v2-20261004-localzlib-noconsole-build` output directory. Strict sanitizer, cross-OS runtime, universal forward ABI, and performance evidence remain explicitly unclaimed.

Review gate refresh (2026-10-04): an independent full review of exact-master candidate `bf10714619ab687b482ce0aed8deb4421fccd491` confirmed two fixes are required before calling it ready: preserve the legacy SLEIGH compiler exit status on write failure, and move install serialization outside the DESTDIR payload. The existing `/dev/full` test already exercises that write-failure path, so keep the regression while restoring the old contract. Windows/macOS, CMake 3.24 consumer behavior, and Java headless project-reopen/native parity remain unverified. No push or upstream PR is authorized; obtain explicit current-conversation approval before opening one. This build/package slice remains an enabler only and does not fix Java worker initialization or concurrent decompile latency.

Candidate repair follow-up (2026-10-04; evidence corrected 2026-10-09): the revised uncommitted diff keeps the output-error check private to the CMake-built SLEIGH compiler, validates staged paths against the composed `DESTDIR` destination (so an unrelated host symlink in `/usr/local` does not reject a clean stage), handles a CMake-stripped Windows drive-root prefix locally without mutating the global install prefix, and rejects Windows `DESTDIR` staging explicitly (CMake itself documents that mode as unsupported). Install locks now use a normalized-destination key in fixed per-user temporary storage; Unix verifies the lock directory owner before restricting it to owner-only permissions. The prior full CMake 4.3/Ninja suite passed 20/20 (205 native unit cases, 87 effective data fixtures, installed consumer included), 73.07 seconds, log SHA-256 `f57b3da35457252b8272878e1f2db1cac4f77599c57b887b08a049db5a5d673d`, but predates the latest test-only strengthening. The final trailing-slash regression now uses a unique destination, snapshots lock-directory contents, and asserts exactly one new lock under the canonical key; its focused CTest passed 1/1 on 2026-10-09 (13.53 seconds). A fresh full-suite attempt on that tree stalled at `sleigh_specs_incremental` after six tests, so the current tree has no fresh 20/20 receipt. The final correctness review found no production-code finding; its limits remain advisory same-user locking, string-distinct path aliases, untested Windows/macOS and alias concurrency, and persistent lock metadata under `/tmp`. The test reviewer identified and the strengthened test closes the old assertion's specific blind spot. Windows/macOS runtime, a full CMake 3.24 build/consumer lane, and Java headless project-reopen/native parity remain unverified. The separate local `eventual-pr/ubsan-sign-extend-fix-20261004` branch contains an isolated `address.hh::sign_extend` correction against exact master; independent static review found no correctness issue for defined bit positions 0–63, but called the mismatched/stale harness evidence inadequate. A reproducible independent-oracle regression and full sanitizer target matrix remain required; the strict full gate is not green. Do not call this candidate merge-ready, do not claim a speedup or universal future ABI compatibility, and do not publish a PR without explicit approval in the current conversation.

_Why it serves the approach:_ Bulk C is the step the corpus repeats most. Decompiling from a saved snapshot lets a worker run without Ghidra and lets an engine change be checked before it touches the corpus.

## Priority ladder (do not reorder)

1. **Identity:** extract facts, then bind `logical_id` (debug names, compilation unit, strings/constants/imports and decompiled shape, BSim, then unique byte window). Do not re-analyze a program that already has Ghidra analysis unless the previous analysis is incomplete or corrupted.
2. **Global calibration:** compiler versions, flags, ABIs, and global struct layouts before per-function recovery.
3. **Scaffolding:** donor workspace: one file per function, exact inline asm if no C, must link.
4. **Readable C:** `ghidra-bulk` replaces asm when C compiles; keep asm on failure.
5. **Propagation:** only after compile succeeds; sibling `.c` via `logical_id`.
6. **Targeted AI:** leftovers only, leaves before callers; not before tiers 4–5 for functions Ghidra C already compiles.
7. **Parity:** objdiff 0 per function when claiming verified; isolated toolchain; separate from "compiles."

## Marketing

**Key message:** Identity first, and identity is not an address. Skip work that is already done. Calibrate once. Recover on the easy build. Propagate. Export the hook pack. Byte-exactness is a last audit, not a compile receipt.

Acceptance correction (2026-10-09, later rerun): the exact-master CMake 4.3/Ninja suite passed 20/20 in 45.07 seconds after the legacy SLEIGH error-path repair; `LastTest.log` SHA-256 `1938e2373b1c89d21a39ec69b073d6f18be9603a9afdb9acfcad42261fd9c8df` (205 native units, 87 effective data fixtures, installed consumer included). A macro-less Makefile `sleigh_dbg` probe confirmed failed `/dev/full` output still reports the write error and exits 2. The generated `cmake --install` + `DESTDIR` sequence staged 259 files, including 58 `.sla` files, on Linux. A clean CMake 3.24.4/Ninja/GCC 16.2.1 build completed 265 steps and passed CTest 20/20 including the installed consumer in 51.95 seconds; log SHA-256 `bb49044c62e5d958099440aa180d20ea0e0e346e25feac3b6460a3d4a5cbf637`. Its bundled-zlib ON / console OFF / Toy variant also passed 17/17 in 51.38 seconds after 130 build steps; log SHA-256 `b2e79629654b81a5ba919f0b17ed851e1c93c52b471894f6789528d766661cec`. The nine-file repair diff received a focused Compound Engineering review with no actionable correctness finding; its residual limits include same-user-only install coordination. The reviewed repair is committed locally as `b893d808b2`. The overall compatibility/sanitizer gate remains open: Windows/macOS, Java headless reopen/spec parity, and strict ASan/UBSan remain unverified or failing. Keep the unrelated `address.hh::sign_extend` correction separate and the full sanitizer finding explicit. This remains build/consumption support, not the concurrency or decompile-performance fix; no speedup or universal forward compatibility is established. No push or upstream PR without explicit approval in the current conversation.

The full staged install also passed using CMake 3.24.4 itself: 259 files and 58 `.sla` files under a fresh DESTDIR root, no lock metadata staged. This is Linux-only evidence.

Package-version contract note: the initial WP1 text said `SameMajorVersion`, but this candidate uses exact Ghidra version matching because internal native headers and C++ ABI are not promised stable across releases. That is a deliberate conservative plan deviation, not forward-compatibility evidence; surface it for maintainer review.
