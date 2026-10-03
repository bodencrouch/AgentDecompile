# Task 11.4 P2 implementation handoff

Status: **READY_TO_COMMIT — source-only, behavioral acceptance unrun**.
Assigned base: `515d3de6c65709a31f538a57bc6ae853d6fcd7e3`.
No staging or commits were performed. No subagents were dispatched. Other owners' changes were preserved.

## Implemented

- Added `ParityRegionCheck` with the separate `parity-region-check` v1 identity and `parity-region-coff-i386-leaf-v1` verification method. The planner takes exactly six explicit immutable envelope/object references and fixed profile/policy parameters; MEDIUM budget and exact capability declarations are validated independently of the task identity projection.
- Added exact canonical task/result envelope decoding, recomputed task IDs, prerequisite task/basis/object/selection joins, canonical target/P1 receipt checks, and strict result/output sets. A serialized verification field is an unknown envelope field and refuses; no recorded VERIFIED lookup is used.
- Added descriptor-relative, no-follow, regular-single-link file reads with actual streamed SHA-256, before/after identity checks, 64-KiB chunks, bounded length checks and one shared 300-second operation deadline. Only exact uncapped Linux x86-64 `LocalDirStore` is admitted. No generic `get`, `get_path`, quarantine/touch, remote fallback or named-pointer mutation is introduced. Nested target/P1 calls require their full 120/60-second reservations.
- Added independent standard-COFF inventory for the exact one-section i386 policy. Accepted objects have exhaustive nonoverlapping file-interval coverage, bounded symbol/auxiliary/string-table walks, exact section/function facts, no relocation/line/dependency content, and only the enumerated legal metadata variants. Optional filename payloads are represented by length/digest, never plaintext. File timestamps are recorded as object metadata; no wall-clock timestamps enter outputs.
- Added a finite byte scanner accepting only the explicit NOP/XOR-EAX/INC-EAX/DEC-EAX/final-RET grammar, requiring a zero-EAX operation and full extent coverage. Every byte is compared independently after both scans; matching decoded operations do not erase encoding differences.
- Added the pinned objdiff 3.8.0 pure parser with exact whole-stdout UTF-8 JSON, duplicate-key/null/depth/default/enum/type/oneof/base64 handling. Both sides' section/symbol identities and every instruction offset/size/operand are checked. Matching counterparts agree on their complete normalized shape, except the specified absent right section percentage. Mismatch diagnostics still require complete per-side coverage.
- The operation directly calls **actual** `MkobjTarget().verify` and **actual** `ParityCheck().verify` in separate owned scratch directories. It binds their returned method/task/result identities and parses both proposed and P1-recomputed authenticated raw reports. Returned outcome summaries are diagnostics in Verification evidence; deterministic receipts carry prerequisite identities/methods without granting authority to serialized outcomes.
- All retained evidence, including the target's image and snapshot under their existing caps, is rehashed before publication. Every P2 `put` checks its returned content address and performs a bounded authenticating reread. Verification authenticates the proposal, repeats the entire operation under its own single deadline, and compares receipt plus both inventory references.
- Implementation source/runtime closure, source binding, runtime admission and linked-image metadata remain `not_evaluated`. No arbitrary provider, checker callback, caller-selected predicate or whole-object equality shortcut was added. P1 and target source/interfaces/receipts remain untouched.

## Owned files

1. `src/agentdecompile_recovery/grid_lanes/parity_region.py` — new kind, finite grammar, COFF inventory, bounded authentication/publication and prerequisite composition.
2. `src/agentdecompile_recovery/grid_lanes/objdiff_v380.py` — new strict pinned parser/profile constants.
3. `src/agentdecompile_recovery/grid_lanes/__init__.py` — narrow import/registration.
4. `src/agentdecompile_recovery/grid_lanes/splitter.py` — narrow planner registration/delegation.
5. `tests/test_grid_parity_region.py` — dedicated regression source, **unrun**.
6. `tests/test_objdiff_v380.py` — dedicated regression source, **unrun**.
7. `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-11-region-report.md` — this handoff.

## Source checks actually performed

- Read repository AGENTS/src CLAUDE guidance, the SDD implementer prompt, the assigned brief and adopted full region contract, prerequisite source, core task/result/verification serialization, local object-store layout and target COFF writer.
- Parsed all six owned Python sources with standard-library `ast.parse`; no project imports or bytecode compilation. All parsed successfully.
- Ran `git diff --check` for the two tracked integration files and `git diff --no-index --check /dev/null <file>` for each new source. No whitespace-error output. The no-index commands return the ordinary nonzero diff status for newly added files; this is not behavioral validation.
- Inspected the narrow tracked diff and source call sites for both unavoidable real prerequisite calls, both strict raw-report parses, full nested reservations, and explicit closure exclusions.
- Source search found no direct subprocess/compiler/checker invocation, SQLite operation, generic object `get`, `get_path`, or `verified_result_ref` in the two new implementation modules.
- Read pinned primary upstream `diff.proto`, binding conversion, x86 formatter, object symbol reader/size inference and diff pairing sources. No concrete positive-profile contradiction was found. The native formatter's basic comma/space parts and opcode trailing space are accounted for. This was source inspection, not native-output execution.

Pinned upstream sources used:

- <https://github.com/encounter/objdiff/blob/784a16740a8a67b835b752ab867e76347d8a9691/objdiff-core/protos/diff.proto>
- <https://github.com/encounter/objdiff/blob/784a16740a8a67b835b752ab867e76347d8a9691/objdiff-core/src/bindings/diff.rs>
- <https://github.com/encounter/objdiff/blob/784a16740a8a67b835b752ab867e76347d8a9691/objdiff-core/src/arch/x86.rs>
- <https://github.com/encounter/objdiff/blob/784a16740a8a67b835b752ab867e76347d8a9691/objdiff-core/src/obj/read.rs>
- <https://github.com/encounter/objdiff/blob/784a16740a8a67b835b752ab867e76347d8a9691/objdiff-core/src/diff/mod.rs>
- <https://github.com/encounter/objdiff/blob/784a16740a8a67b835b752ab867e76347d8a9691/objdiff-core/src/diff/code.rs>

## Authored regression coverage — not executed or collected

Pure fixtures cover complete grammar/inventory, legal metadata differences, private filename suppression, absolute-memory/indirect-call/immediate/branch/prefix/tail refusals, x64/extra section/header/relocation/COMDAT declarations, auxiliary overruns and references, string suffix aliases, hidden trailers/nonzero gaps, section-name exclusions, local file links/size limits, capped/unsupported stores, corrupt existing CAS publication, deadline reservations, task ID/types/budget/capabilities and caller overrides.

Parser fixtures cover native omitted defaults/right-section asymmetry, full instruction coverage, missing percentages/sides, reciprocal symbol identity, duplicate functions, present-zero dependencies, invalid numeric/string/enum/boolean/oneof/base64 shapes, unknown/camel-case keys, duplicate JSON keys, UTF-8/depth/trailing content, counterpart opcode/part equality and complete differing reports. These synthetic schema fixtures are not checker evidence.

Opt-in real-native regression source (`ADGRID_P2_QUALIFIED_NATIVE`) uses an owned copy of an independently supplied executable, checks its exact pinned asset digest via the retained native registration, reuses the synthetic physical image/snapshot fixture, and runs the actual target producer and both retained verifiers. Cases cover equal regions with different COFF metadata, byte-different XOR encodings, same-extent differing leaves, forged envelopes/VERIFIED JSON, foreign basis/swapped objects/stale receipts/raw swaps/selection digest, forged inventory, partial recomputed raw evidence after an actual P1 verification, changed actual checker bytes and unchanged legacy P1 scope. Neither positive verifier nor checker is replaced by a fake provider. Execution of these sources requires separate authorization.

## Self-review and remaining evidence

Fixed during source review: canonical envelopes must permit the existing target implementation descriptor's JSON null while native reports reject null; exact ref length closes the historical validator's trailing-newline allowance; native formatted instruction strings include an opcode trailing space; numeric guards reject enormous out-of-range values before float conversion; the real-native fixture modifies only its owned checker copy; prerequisite outcome summaries were removed from deterministic receipt identities.

The larger new composition module remains within the assigned two-module boundary. Failures remain differentiated: unsupported/limits/unavailable local verifier conditions do not become a positive observation; authenticated structural contradictions and differing independently recomputed outputs refute the proposal. Only a reproduced matched grade sets `target_region_complete=true`.

**Not performed:** tests, collection, builds, typechecks, proof scripts, project imports, DB creation/query, compiler/checker/native execution, executable download/install, process/catalog/runtime/Ghidra/service operations, reloads/restarts, alternate listeners, activation or publication. TDD red/green evidence is absent because execution is prohibited by this assignment.

**Still open:** actual native positive/mismatch/refusal execution, actual executable/runtime qualification, installed-consumer evidence, persisted independent signed verification, source/compile contribution joins, P3 implementation closure/current key lineage/revocation/policy/corpus-generation admission, linked-region replacement and fresh whole-image acceptance. This source slice does not close U11/U4/P3 or the overall plan and does not connect the dashboard.
