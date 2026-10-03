# HANDOFF — 2026-10-03 17:15

## Goal
Prove the Java-free CMake build for Ghidra's native decompiler is compatible forwards and backwards with zero discrepancies. Then finalize a local v2 review package and a squashed submission branch. **No upstream or fork PR or push without explicit user approval in the current conversation.**

## Done
- Candidate: `eventual-pr/cmake-compat` @ `700c7cb7f6` (8 commits on Ghidra master `a462673d2f`, version 12.3). The tree is clean.
- Matrix on `700c7cb7f6`, all receipts tied to the commit:
  - R4 releases 10.3 to master: the only failures are 11.4's upstream `decomp_datatests`; the skips are real spec changes.
  - Phase B, CMake 3.24.0 to 4.4.3 with `-Werror=dev`: 8 of 8 versions pass 13/13.
  - Phase C, consumers, generators, C++14-23, build types, options: all pass. The apparent failures are harness artifacts (multi-config `-C`, wrapped guard message) or upstream engine bugs:
    - UBSan sites: `semantics.hh:88`, `pcodecompile.cc:776`, `address.hh:605`.
    - LSan leak: `~ProtoModel` never frees `sharedActions`.
  - Phase D, containers so far: Ubuntu 20.04/gcc9, 22.04/gcc11 and 24.04/gcc13 each pass 16/16.
- Receipts: `ghidra-pr-review-package-v2/receipts/{r4-releases,c-phase-findings}-700c7cb7f6.md`.
- Created a test worktree for the review's open test gaps (nothing edited yet): `ghidra-cmake-tests-wt`, branch `eventual-pr/cmake-compat-tests` @ `700c7cb7f6`.

## Next step
Let the queue finish phases D to H (`40-d` to `75-h`). In parallel, add CTest regressions for the four open gaps in `ghidra-cmake-tests-wt`, serially, one subagent per unit:
1. `sleighCompileOptions` parsing, covering `//` and `/* */` comments, in `TestSleighCompileSpecs.cmake`. This means extracting the parse into a helper in `SleighCompileSpecs.cmake`.
2. A positive control for `no_ghidra_process_symbols`, modelled on `TestNoJvmCheck.cmake`.
3. A check that the data-test runner prints `Failures:` on an XML load error.
4. A check that editing the Makefile after configure triggers a reconfigure.

After the queue is done: merge onto `eventual-pr/cmake-compat`, rerun R4 and B, run ce-code-review, squash into a new submission branch, fill the v2 package placeholders, and ask the user for approval.

## Open threads / gotchas
- **Never edit `ghidra-cmake-compat-wt` while the queue runs.** Every phase builds from it (`$CPP`).
- `ctr-ubuntu2404-clang18` sat in `apt-get install` for 31 or more minutes at 17:12. Check it is not hung.
- Another session's `ghidra-pr-runtime/task4-20261003-acceptance/run-native-v3.sh` also builds on this host. It is not ours; do not touch it.
- `git status` on the MyBook worktrees can take minutes. Use timeouts.
- **Do not `source phases/common.sh` interactively.** It appends a `receipt-tree` line to `matrix.status`.
- CTest 4.4 prints "100% tests passed out of N". The `summ` regex in `common.sh` now handles it.
- Gradle, Java and headless receipts come from older bases (`263160cf57`, `4258ca6dfd`, `fab674a1b3`). Say so in the ledger.
- The commits are authored as Copilot; re-author them before submission.
- Untested: macOS, BSD, MSVC, Windows arm64.
- Cursor dispatch is at its usage limit until 2026-10-14, so work runs natively.
- Edits in the shared AgentDecompile checkout are blocked for background sessions, and EnterWorktree failed with "Could not read the repository git config". This file therefore lives on the `handoff/ghidra-cmake-2026-10-03` branch in `AgentDecompile-handoff-wt`.

## Key files
- Matrix: `/run/media/brunner56/MyBook/Workspaces/ai-projects/ghidra-compat-matrix/`
  - `matrix.status`, `logs/`, `queue/`, `phases/common.sh`, `summarize.py <commit>`.
- Runner: `queue-runner.sh`, pid 2023137.
- Candidate worktree: `/run/media/brunner56/MyBook/Workspaces/ai-projects/ghidra-cmake-compat-wt/Ghidra/Features/Decompiler/src/decompile/cpp/{CMakeLists.txt,cmake/}`
- Package: `/run/media/brunner56/MyBook/Workspaces/ai-projects/ghidra-pr-review-package-v2/`
  - `PR-DESCRIPTION.md` and `COMPATIBILITY.md` still hold placeholders.
- Last review: `/tmp/compound-engineering-1000/ce-code-review/20261003-132329-600d47e0/report.md`
