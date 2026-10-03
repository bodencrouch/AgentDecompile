# Task 11.3 P1 implementer report

Date: 2026-10-02. Status: READY_TO_COMMIT (source implementation and authored regression source; no behavioral qualification). Editing stopped after the source checks recorded below. Controller owns review, staging, commit and living-plan updates.

## Owned paths

- `src/agentdecompile_recovery/grid_lanes/parity.py`
- `tests/test_grid_parity_binding.py` (new)
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-11-parity-report.md` (this report)

Base inspected: `1f29d91dad54999db2f12e7af9ac8eba51f754bb`. Other owners' existing dashboard/progress changes were not edited. No staging, commit, publication, subagents or live activation was performed.

## Implemented source

`run` and `verify` validate the v1 task before evidence I/O and use one monotonic operation deadline, including proposal authentication, discovery/artifact checks, private input copies, actual checker execution, rereads and publication. Timeout semantics remain null/omitted/nonpositive = 60 seconds, positive capped at 60; malformed/nonfinite/boolean values refuse. Input names, parameter vocabulary, basis type, ID spelling and symbol byte bound are validated without adding a capability requirement or changing the task identity projection.

The local adapter reads through no-follow directory-relative descriptors, checks regular files and declared sizes, bounds unbuffered reads to limit+1 in 64 KiB chunks, and authenticates the stream. Limits are 64 MiB/object, 1 MiB/receipt, 4 MiB/stdout/raw, 1 MiB/stderr, 256 MiB/declared checker artifact. It never calls CAS `get`/`get_path`, quarantine, touch, GC or named-pointer writes on this route. Fresh private temporary directories and exclusive-created copies keep checker writes off CAS inodes. Input and artifact endpoint hashes/sizes are checked before and after execution.

Checker resolution reuses existing registration identities and exact invocation/environment. The optional internal `deadline` branch of `resolve_checker` avoids the public cache-miss path's unbounded registration hashing. Public default discovery remains unchanged. Node executable selection resolves once; Node executable bytes/environment/runtime dependencies remain outside the old Wasm ID. Declared script/js/Wasm order and native identity formulas are unchanged. Resolved Wasm artifact names are checked again to detect persistent symlink retargeting.

The lane-local selector capture drains both pipes under fixed bounds and reserves up to one second (at most a quarter of remaining time) for cleanup within the same deadline. `waitid(WNOWAIT)` retains the owned child PID as the process-group ownership anchor until the final termination signals. There is no `poll`/unbounded `communicate`, no post-reap termination signal, and no reuse of an unchecked PID as termination authority. After reaping, signal-0 existence probes can only refuse completion; a surviving or reused group is conservatively `execution_unavailable`. This also refuses apparent clean completion when a descendant closed its pipes but remains in the group. Hostile session escape and change-and-restore are outside P1 runtime admission, explicitly unqualified.

One normalizer preserves old receipt bytes: current selected parser, dropped `output`, existing kind/version/verifier/sides/symbol/basis/grade fields, message path scrub and portability rule. Publication checks `put` returns the supplied bytes' exact ref, rereads actual retained bytes, and authenticates both outputs. Corrupt preexisting CAS entries cannot pass by returning their expected names.

Proposal authentication requires its own task/basis/status/reason/output set, actual bounded receipt/raw bytes, canonical JSON without duplicate keys or nonfinite numbers, strict integer version/exit/difference fields and parser-shaped grade/exit combinations. Re-normalizing authenticated raw text must reproduce the entire proposed canonical receipt. Unexpected parser failures are unavailable, not evidence against a producer. Independent execution uses the same deadline and output authenticator. Raw refs may differ while separately binding equal normalized receipts.

Verification method is `parity-binding-v1`, with the precise authenticated observation predicate, native-code or Node-symbol-row scope, registered-artifact identity scope, `target_region_complete=false`, `runtime_admission=not_evaluated`, grade, compared receipt and proposal/recomputed output refs. Matched, mismatched and diagnostic-error observations can be reproduced without granting byte-exact source acceptance. Historical method `parity` records are not upgraded during replay.

## Support refinements agreed with controller

Only the exact `LocalDirStore` implementation is supported by this strong route. Subclasses/other transports and platforms without POSIX no-follow descriptor-relative reads plus `waitid/WNOWAIT` refuse `transport_unsupported`.

A `LocalDirStore` with `size_cap_bytes > 0` also refuses `transport_unsupported`: its `put` can invoke GC. The implementation neither invokes that GC nor silently bypasses capacity policy. Other historic store consumers remain untouched. Bounded transport support and a publication contract for capped stores are future extensions.

## Authored but unrun regression source

`tests/test_grid_parity_binding.py` contains 36 test definitions with parameterized cases. Controlled captures/regular-file artifacts are explicitly fixtures, never qualified native/Node receipts. Cases cover:

- Matched/mismatched/error observations; retained historical receipt and task identity; unchanged eight-column view; partial native 100-percent reports retain incomplete scope.
- Foreign task/basis/status/reason; swapped sides; wrong version/grade/exit/difference types; duplicate/nonfinite/noncanonical JSON; unrelated raw; missing/extra/malformed outputs; forged actual digest.
- Task/symbol/timeout validation; timeout default/cap; unsupported remote/get-only store and capped-GC store; missing/corrupt/symlinked/oversized inputs; declared-size contradiction; growing-stream limit+1; over-limit proposal is unavailable.
- Private-copy inode isolation and mutation refusal; corrupt existing put and wrong returned put ref; checker artifact bound; missing checker; stale cached native/js/Wasm bytes; checker mutation during execution; bounded cache-miss resolution.
- Canonical receipt disagreement; one deadline consumed by proposal reads; unexpected parser failure classification; scratch-path raw noise; zero Node display rows remain incomplete; changed runtime/environment remain outside legacy identity.
- Authored actual controlled-child stdout/stderr flood, hang and normal capture cases, plus process seam assertions for ownership-before-signals/reap and refusal of surviving/reused groups. These are capture mechanism tests, not checker qualification.
- Explicitly gated real native/Node acceptance source using supplied actual checker/object paths and required expected grade; it is skipped without `AGENT_DECOMPILE_P1_REAL_ACCEPTANCE=1`. Authorization to execute this gate was not granted or inferred.

No test was run or collected. No RED/GREEN/TDD execution evidence is claimed. No project module was imported for validation.

## Exact source checks performed

1. Read task brief, complete adopted P1/P2/P3 contract, implementer prompt and repository entry-point operational references. Read relevant core/store/parser/target/planner source and public call sites. A quick memory keyword search provided no task-specific implementation authority.
2. `python` standard-library-only `ast.parse(Path(...).read_text(), filename=...)` on the two owned Python files: both **AST OK**. Final source counts: parity.py 811 lines; regression file 512 lines; 36 test definitions. No project imports, bytecode compilation or execution of source definitions.
3. `git diff --check -- src/agentdecompile_recovery/grid_lanes/parity.py tests/test_grid_parity_binding.py`: exit 0, no whitespace diagnostics. The untracked regression file also received AST parsing; Git's ordinary diff does not itself inspect an untracked file.
4. Read base parity.py via `git show 1f29d91dad54999db2f12e7af9ac8eba51f754bb:src/agentdecompile_recovery/grid_lanes/parity.py`, then compared parsed ASTs. Unchanged: `register_native`, `register_node`, `parse_node_report`, `apply_parity_receipt`, `ParityChecker`, `PARITY_RECEIPT_SQL`, `RECEIPT_SCHEMA`, `NATIVE_PREFIX`, `WASM_PREFIX`, and every `ParityCheck` descriptor constant. Output reported each unchanged. This establishes source compatibility, not runtime equivalence.
5. `rg` call-site inspection confirmed parity's strong path uses its deadline-aware resolver and no longer calls generic `run_argv`, `materialize_object` or `verify_by_recompute`. Planner source still supplies v1 target/candidate/verifier_id/symbol without a new parameter.
6. `git diff --numstat -- src/agentdecompile_recovery/grid_lanes/parity.py`: 550 inserted, 51 removed. `git status --short` after other owners' independent work showed only the parity production file and new regression file pending; this ignored report is separately owned.

No tests, suites, builds, typechecks, proof scripts, DB operations, checkers, compilers, runtime/catalog operations, process inspection/control, service/systemctl/restarts, alternate ports or publication were run. The subprocess code was authored, not executed. This checkout is not serving; controller's earlier 8080 corroboration is not activation evidence for these edits.

## Self-review and remaining predicates

Self-review traced validation through actual byte reads, private copies, artifact checks, real invocation source, normalization, publication rereads and proposal/recomputed authentication. Corrections during review: prevent buffered prefetch beyond descriptor read bounds; detect persistent Wasm symlink retargeting; classify unexpected parser failures as verifier unavailability; preserve finite large integer timeout capping; check deadline after scratch cleanup; refuse group survival after pipe EOF; return invalid-spec verification even when malformed inputs make selected task identity uncomputable.

All new behavioral and process-lifecycle cases remain **unrun**. The enlarged single production file is a maintainability cost of the mandated lane-local boundary; no generic infrastructure was changed or duplicated outside this lane. Independent controller review remains required before integration.

Open: real supported native/Node positive/mismatch/diagnostic acceptance; process flood/hang/descendant cleanup timing; unsupported-platform/store refusal behavior; durable historical replay in a real consumer; fixed checker/schema qualification; exhaustive P2 code/data/boundary/fixup/metadata region coverage; P3 current dependency/runtime/key/owner admission; admitted accepted-source adapter; actual dashboard connection/counts; installed/live consumer activation; fresh whole-image acceptance. Neither U11 nor U4 nor complete parity/current acceptance is closed by this source slice.
