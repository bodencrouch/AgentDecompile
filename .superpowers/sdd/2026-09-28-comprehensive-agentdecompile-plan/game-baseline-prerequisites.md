# Original-game source baseline prerequisite audit

Audited 2026-10-02 against checkout `612e1315`. This is a bounded read-only
prerequisite audit for U33–U39, after retained source reconciliation. No recovery,
catalog/live/process operation, database query/write, import, compiler, build,
test, gameplay or proof execution was performed. Only this report was written.

**Disposition: U33 is not established by the inspected retained evidence.**
There is useful source candidate and static engine-boundary evidence, but no
inspected successful clean semantic C/C++ engine link plus original-game launch
receipt. The concrete retained direct-build receipt is a failure. This finding
does not assert that no additional receipt exists at an uninspected location.

## Accepted scope and prerequisite boundary

[U33](unit-33-requirements.md) consumes U4 and requires a chosen executable,
Ghidra project, toolchain, inventory, sources and receipts bound to hashes;
declarations/data/globals/RTTI/vtables/imports/resources/startup; a clean C/C++
link; and an actual original-game launch. `_emit` and copied PE regions do not
establish semantic recovered source.

[U34](unit-34-requirements.md) consumes that baseline for corrected engine ABI,
transport/lifecycle and original-process queue/dispatch validation. U35–U38 then
require real two-client authoritative gameplay, shared co-op and persistent-world
modes, shared-engine headless `swkotorserver.exe`, public directory and actual
recovered main-menu browser. [U39](unit-39-requirements.md) requires both Windows
executables from a clean source checkout, hashes/toolchain, one headless server
plus two clients and gameplay/browser evidence. Whole-file identity is not
required for newly added multiplayer functionality. This does not remove the
original recovery acceptance policy in [STRATEGY.md](../../../STRATEGY.md:213).

This blocks the dependent game implementation claims, not unrelated native
Ghidra tooling or eligible identity/runtime-reuse work. A demonstration program,
renamed launcher, socket daemon, SDK build or original-byte round trip does not
consume the missing source-built game baseline.

## Exact inspected input and source leads

The retained [research README](../../../docs/research/swkotor-multiplayer/README.md:3)
records import from `0b7305bb6ee1b9dee31311a6dec8623256766627`; its historical
"fresh" statements belong to the original investigation and were not revalidated
during import or this audit. Its [engine evidence](../../../docs/research/swkotor-multiplayer/engine-evidence.md:9)
names these distinct inputs:

| Retained target | Recorded SHA-256 / role |
|---|---|
| `/home/brunner56/agentdecompile-nvme/agentdecompile_projects/extract/raw/K1__k1_win_gog_swkotor.exe` | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`; 4,042,752-byte corpus input |
| `/home/brunner56/agentdecompile-nvme/k1gog-target/swkotor.exe` | `34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88`; distinct 4,395,008-byte wrapper/build |
| `/home/brunner56/agentdecompile-nvme/workspace/Workspace.gpr`, program `/K1/k1_win_gog_swkotor.exe` | Existing analyzed-project lead; `.gpr` existence corroborated, current project/program hash binding not established |
| `/home/brunner56/agentdecompile-nvme/agentdecompile_projects/corpus_work/k1_win_gog_swkotor.exe/` | Existing mixed source-candidate/substrate directory, corroborated directly |

Executable hashes above are retained recorded identities, not freshly recomputed
binary proof. The different inputs cannot borrow each other's receipts without a
transformation/binding record. Filenames `k1_gog_from_source.exe` and
`k1_win_gog_swkotor_BUILT.exe` are not source-build provenance.

The source-directory top-level name inventory contains no shared `.h`/`.hpp`,
`CMakeLists.txt`, `Makefile`, `meson.build`, `.sln`, `.vcxproj`, `.vcproj` or `.mak`.
This is a scoped directory observation, not a claim about surrounding projects.
Directly inspected `SendMessageToPlayer_005d4cb0.c` labels its 763 original bytes
"NOT recovered source" and emits `_emit` instructions. `ProcessReceivedFrames_005d57d0.c`
labels itself not byte-verified and declares/calls zero-argument `ghidra_call()`
(lines 128/179), leaving real application dispatch unresolved.
`CNetLayer_005d54a0.c` is not byte-verified and contains surrogate `GhidraBlob`
types. Current `CreateServer_00401380.c` is a **compile-only C candidate**, with
layout/ABI placeholders possible; the older research's substrate description
does not describe this current file. Neither classification establishes a link.

## Retained receipt paths and content identities

All paths in this table are relative to
`/home/brunner56/agentdecompile-nvme/agentdecompile_projects/corpus_work/`.
Counts are observed manifest assertions, **not newly verified recovery counts**.
Digests identify the bytes read on 2026-10-02; file immutability is not established.

| Inspected file | Observed scope/result | SHA-256 of read content |
|---|---|---|
| `k1_win_gog_swkotor.exe.matching.json` (mtime Sep 20) | `binary_id=8`, 24,242 functions; 1,609 byte_exact, 17,038 compiles_not_exact, 5,593 asm_floor, 2 absent; `receiptsPartial=true` | `7d52807e1b870896518bd571b22a5435d5384cf1937a130d24207c49dea509e2` |
| `k1_win_gog_swkotor.exe.variants.json` (mtime Sep 20) | Same counts; byte-accurate 1,609 C + 22,633 shim; max-C 18,647 C + 5,595 shim. Both `byte_identical=false`; byte-accurate `exact_placement_hash_equal=true` is explicitly diagnostic | `34e21e93cd3978b8347a1f4845ada539f706fd35a9aa53ae3d527ba1b13a970b` |
| `k1_win_gog_swkotor.exe.byteexact.json` (mtime Sep 18) | 1,302 `byteExact` / 24,276; per-function result collection | `57d0e4d632bcbcddd6cec119dc3059412aac7d0046ce0523fb78c7804c0064d0` |
| `k1gog_matching_manifest.json` (mtime Sep 15) | 98 byte_exact / 24,242; separate historical snapshot | `6274f861d26a4bc0253b4b55a1e3176c7be6d63dd14f2b1c195d2b7260effe39` |
| `compile-receipt.json` (mtime Sep 20) | `program=k1_win_gog_swkotor.exe`, 199 entries in `ok`; no full-link/toolchain/launch assertion | `cf23369820a67f521e373af15ad82f2357b285afb9a562311eace6f48439affe` |
| `k1_win_gog_swkotor.direct-receipt-20260917T0115/receipt.json` | Direct compiler/full-image receipt: no candidate, no objdiff, `compilerProducedWholeImage=false`, `wholeFileByteIdentical=false`, `verified=false`; compiler timeout and missing candidate/comparison | `150b735bf4e19a7b59d471ecc47af845830b6eac786ee32e8ad1f659d4088279` |

The direct receipt's `startedNs=1789716287211438318` denotes
`2026-09-18T07:24:47.211438Z`; the directory name's `20260917T0115` is a locator,
not the recorded execution timestamp. The receipt binds target
`/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`
to the corpus hash `9c10…1435`. It records failed use of
`/home/brunner56/agentdecompile-nvme/agentdecompile_projects/scripts/compile-msvc71.sh`
on a temporary object input; it contains no successful toolchain/source/output
hash bundle. The target and compiler script were not executed or independently
inspected. Adjacent dated directories `…direct-receipt-20260919T0000/` and
`…direct-receipt-20260919T0010/` contain an `objects/` directory but no top-level
`receipt.json`; their object trees were not traversed.

Adjacent `k1gog_byteexact_receipts.json` asserts 198/2,100 with `partial=true`;
`k1gog_maxc_receipts.json` asserts 121/1,100 with `partial=true`. These are separate
result collections, not a whole-engine acceptance manifest. Historical research
counts (1,956 exact / 18,882 max-C / 2,169 separate byteexact / 18,094 compiled)
therefore remain historical; merging them with the current files would fabricate
a completion claim. No successful immutable whole-game baseline receipt was
identified in the exact research links, referenced manifest family and three
adjacent dated direct-receipt directories inspected here.

The retained [binary-binding receipt](../../../docs/research/swkotor-multiplayer/evidence/binary-binding.json)
compares 150 sender instructions to the corpus input, marks disassembly truncated,
and expressly excludes source compilation, objdiff and full-function proof.
The retained callback/queue/identity analysis is useful U34 input, including
four explicit sender/callback stack arguments, shared player record, unchecked
frame lengths and local execution context. It is static evidence, not an original
process validation receipt or remote gameplay proof.

## Real remaining gate and next discovery step

The missing complete U33 input is a hash-bound semantic engine **source project**
with compilation/link context (toolchain, headers/libraries, startup, data,
resources, imports and placement), a successful clean-link receipt demonstrating
compiled replacement contribution, and an actual original-game launch receipt
for the same chosen build. Existing project names and partial function manifests
do not supply these predicates. U34 additionally needs typed dispatch and
original-process lifecycle/queue/player validation; U35–U39 remain dependent on
their named game, directory, UI and release predicates.

**One next authorized discovery step:** inspect `GET /api/v1/actions` on the
existing 8080 workbench, then describe the returned action relevant to opening or
resuming the exact corpus build with its retained source/receipt prerequisites.
Use the corpus hash above, existing `Workspace.gpr` program and `binary_id=8` as
leads to corroborate; do not treat the ID or locator as current identity proof.
Require the action's actual parameter schema to identify a source-project and
successful link/launch evidence bundle, or name the exact missing input. The
source routes [list and describe actions](../../../src/agentdecompile_recovery/corpus/dashboard/actions/openapi.py:66)
support this discovery; no guessed action ID or direct recovery CLI is proposed.
This audit did not call that endpoint. Before any subsequent admitted work,
AGENTS requires catalog/process ownership corroboration and reuse of valid
analysis/receipts; no blanket fresh decompilation follows from the older research
recipe.

`native/README.md` and `native/CMakeLists.txt` identify `native/` as `gnsdk`, the
SLEIGH/decompiler SDK consuming `vendor/ghidra`, with SDK/worker/pool/tools/tests
targets. The inspected native build definitions do not supply recovered KotOR
engine/client/server targets. Source presence or historical SDK receipts cannot
close U33 or U39. No builds/tests were run to reach this disposition.

Memory was used for brief navigation and the historical max-C proof-boundary
reminder (`MEMORY.md:461–462`); current conclusions above come from directly read
repository documents, retained sources and manifests.

## Controller catalog discovery follow-through

The controller subsequently read the existing 8080 `/api/v1/actions` successfully: 233 actions, retained in `live-actions-continuation.json`; selected schemas are in `catalog-game-prerequisites.json`. No action was submitted. `workbench.prepare` accepts locator/program/slug plus `resume`; `mcp.open` accepts the existing project path and has `analyzeAfterImport=true` by default, which is not permission to regenerate retained analysis. `corpus.genproject` requires queue/out/db/raw/repo-path and may take a base-project. `corpus.build-project` requires an existing project-dir and optionally a compiler. None of those inspected schemas establishes a successful hash-bound semantic engine link/launch receipt. The missing complete source project and successful receipt bundle therefore remain the exact prerequisite; parameter availability is not evidence of those inputs. Current DB/program hash binding and process ownership must still be corroborated before any admission.
