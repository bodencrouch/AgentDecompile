# Task 25.1 review

## Spec Compliance

- **✅ Spec compliant for the bounded source slice.** The four keyword-only callback seams, blocked default, independent requalification, candidate-content binding, detached evidence/callback input, and fixed container-depth policy match the brief. Evidence: `src/agentdecompile_recovery/corpus/hookpack_v2.py:113`, `:141`, `:186`, `:225`, `:345`, `:373`, `:385`; `src/agentdecompile_recovery/corpus/export_hookpack.py:184`; `src/agentdecompile_recovery/corpus/export_bundle.py:80`; `src/agentdecompile_recovery/corpus/export_validation.py:36`.
- **⚠️ Source approval only.** Tests, builds, project imports, databases, live services, producer qualification, installed consumers and recovery acceptance were not executed or established. The implementation explicitly records these boundaries in `docs/verification/2026-10-02-cave-qualification.md:3` and `:69`. This review does not close U25/U28.
- **⚠️ Production authority remains unavailable.** No real independent whole-image producer is introduced, as required. The unchanged CLI supplies no callback (`src/agentdecompile_recovery/corpus/cli.py:1150`), and bundle listing requires cave qualification without a provider (`src/agentdecompile_recovery/corpus/dashboard/export_listing.py:145`). Their blocked behavior is an intentional documented acceptance tightening, not a missing feature in this seam (`docs/verification/2026-10-02-cave-qualification.md:46`).

## Strengths

- Receipt checks bind exact build/image/architecture/export basis and the canonical sorted candidate content, retaining integer-only actual-count equality. Resealing a substituted candidate list cannot preserve an independently accepted result merely by retaining its count. Both producer and consumer call the shared check: `src/agentdecompile_recovery/corpus/hookpack_v2.py:105`, `:113`, `:373`; `src/agentdecompile_recovery/corpus/export_validation.py:95`, `:104`.
- Evidence is preflighted across the build map before serialization, then hashed and scanned from the same canonical snapshot. The callback receives a separate copy; literal `True` and unchanged input are required. Expected unavailability, false qualification, mutation and unexpected callback failure remain distinct, with unexpected causes retained: `src/agentdecompile_recovery/corpus/hookpack_v2.py:196`, `:225`, `:141`, `:345`, `:386`.
- The iterative walker counts empty/root containers, rejects entry at 65, keeps branch-local cycle detection, and imposes no flat-node cap. V2 full packs receive their own pre-copy guard, and proposed pack wrappers are checked before qualification. Canonical hashing still supports generated tuple fingerprints: `src/agentdecompile_recovery/corpus/hookpack_v2.py:39`, `:48`, `:86`, `:95`, `:385`, `:398`.
- All three required bundle checks receive the callback. The first two precede root/staging creation; the last remains inside the existing savepoint/cleanup boundary. V1 operation export stays independent and callback-free: `src/agentdecompile_recovery/corpus/export_bundle.py:105`, `:115`, `:129`, `:136`, `:155`, `:217`; `src/agentdecompile_recovery/corpus/export_hookpack.py:193`.
- Required validation obtains current authority on serialized reopening and optional validation retains its narrower consistency scope and `runtime_verification=not_run`: `src/agentdecompile_recovery/corpus/export_validation.py:107`, `:143`. The synthetic fixture is plainly labeled and compares a previously captured complete receipt rather than treating a permissive callback as real producer proof: `tests/test_corpus_cave_qualification.py:1`, `:53`, `:71`.

## Issues

### Critical

None found.

### Important

None found.

### Minor

**Q25-1 — Snapshot regression mutates too late to distinguish the protected scanner path.** `tests/test_corpus_cave_qualification.py:222` mutates the original evidence inside the verifier, which runs after `discover_caves`. Consequently, a regression that hashes and scans the original caller object before invoking the callback could still pass this test. The production source does capture and use a detached snapshot (`src/agentdecompile_recovery/corpus/hookpack_v2.py:225`, `:345`), so this is a coverage weakness, not a demonstrated implementation defect. Extend this fixture in a later authorized source edit with a wrapper around the scanner that mutates the caller's original evidence immediately before delegating to the real scanner; assert the scanner argument is detached and the result/hash/decoder still describe the captured state. Keep the test labeled synthetic and do not run it under the current mission restrictions.

## Named checks and review method

- **Requirements and change scope:** read `task-25-brief.md` before the implementation report and supplied review package. Reviewed base `6e4b313d740380ea4d7af7389ce5dc0b5312643a` through head `f059c0bb7dc3d7f4412eb8e23764f26d48425dfd`. The initial combined tool output truncated the middle of the diff; bounded reads recovered the missing sections. Used the package for changed source and extracted line locators from its hunks; did not rerun Git or AST checks.
- **Risk: scanner return shape/order or fixture exclusions might conflict with the new candidate digest.** Inspected only the unchanged `discover_caves` body (`src/agentdecompile_recovery/corpus/cave_discovery.py:22`). Its emitted architecture, anchor/capacity/offset/id fields and deterministic order agree with the new sort key. Its instruction, relocation, reference and capacity refusals support the prepared zero-result fixture (`tests/test_corpus_cave_qualification.py:91`). No scanner algorithm was changed.
- **Risk: a late qualification refusal might escape publication cleanup.** The relevant bundle hunk ends before publication/cleanup, so inspected the omitted staging/publication tail (`src/agentdecompile_recovery/corpus/export_bundle.py:129`, `:200`, `:217`). Failed validation propagates through savepoint rollback and staging removal before rename. The fixture's third/fourth callback refusal points correspond to the second/third validator calls (`tests/test_corpus_cave_qualification.py:299`). This was control-flow inspection, not filesystem or transaction execution.
- **Risk: newly written fixture setup could conflict with the store schema.** Read the existing `connect` initialization and narrowly searched store/migration definitions (`src/agentdecompile_recovery/corpus/store.py:162`; `src/agentdecompile_recovery/corpus/migrations.py:192`). The migration-created `ghidra_field` and separately created fixture `ghidra_type` assumptions have no source-visible conflict. No database was created or opened. One attempted standalone `schema.sql` lookup found no such file; the store directs schema ownership to migrations.
- **Risk: tightening could accidentally leave old default consumers claiming qualification.** Read only the default CLI export call and dashboard validation call (`src/agentdecompile_recovery/corpus/cli.py:1150`; `src/agentdecompile_recovery/corpus/dashboard/export_listing.py:145`). Neither supplies authority, so neither bypasses the tightened gate. Initial guessed module paths were absent; focused filename lookup located the corpus-owned modules.
- **Prohibited validation not performed:** no source imports, tests, suites, builds, proofs, AST rerun, database creation, service/catalog calls, process changes, systemctl, source/index/commit changes, or subagents. Only this requested review report was written. Implementer-reported AST/diff checks remain reported evidence, not independently rerun results.

## Remaining verification

- Later authorized execution must exercise the prepared positive/refusal fixtures and capture exact source identity, provider origin and consumer outcome (`tests/test_corpus_cave_qualification.py:71`, `:108`, `:137`, `:172`, `:202`, `:240`, `:299`). No passing result is inferred from readable test source.
- Add or retain explicit future cases for multiple builds with unaffected controls, multiple candidates/reordering, stale anchors, unsupported decoder provenance, and encoder/copy recursion injection. Their absence from executable fixture sources is nonblocking for this source-only slice: ordering/scanner behavior is unchanged, the relevant refusal paths are visible, and no runtime qualification is claimed. The implementer acknowledges these gaps in `task-25-report.md:106`.
- A real acceptance owner must independently resolve producer identity/revision, exclusion completeness, exact candidates, current policy and dependency generation at every consumption point. No synthetic test can establish that external basis (`docs/verification/2026-10-02-cave-qualification.md:24`). Mounted provider integration, runtime allocation/protection/lifetime/reclaim, native adapters, installation/call/restoration and fresh whole-image recovery remain separate acceptance obligations (`docs/verification/2026-10-02-cave-qualification.md:76`).

## Assessment

**Task quality: Approved, with one nonblocking Minor finding (Q25-1).**

The bounded implementation fails closed and keeps serialized consistency separate from independent authority. Source inspection found no blocking defect; approval is limited to the reviewed source slice and does not substitute for deferred execution or production-provider acceptance.
