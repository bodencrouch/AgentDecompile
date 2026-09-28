# Frontend and export implementation — September 28, 2026

The implementation batch is committed as `ef08633` on
`codex/branch-consolidation-20260928` in the NVMe consolidation worktree.
It changes 63 owned files: 3,183 insertions and 187 deletions. This is source
implementation with focused software checks, not live delivery acceptance.
The [product guide](PRODUCT_AND_WORKSPACE_GUIDE.md) explains the intended workflows;
the [43-unit plan](plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md)
still defines the unfinished work.

| Area | Implemented behavior | Remaining acceptance or integration |
| --- | --- | --- |
| Project opening | Explicit open and successful binary registration use the existing admission coordinator without resume/reset. | Live two-project and admission acceptance. |
| Scoped Ghidra reads | Project/program peer state, serialized fallback, explicit queued reads and bounded client retry. | Prove native session isolation before allowing concurrent reads. |
| Matching | BSim persistence, named C++ metadata anchors, K P-code separated from M BinDiff, shadow contract veto and typed match columns. | Admitted BSim query producer, wider metadata recovery and contract-veto qualification. |
| Matching UI | Selection-bound method availability; Vite fleet filters and static method details. | Browser acceptance and complete scheduling receipts. |
| Optional AI | Shared precedence, captured job/child decisions, guarded model boundaries, protected settings endpoint. | Mounted settings and real off/on job verification. |
| Instruction comparison | Shared target/candidate alignment display, register highlighting, mismatch navigation, paged symbols and scratch integration. | Recorded backend receipt and browser workflow acceptance. |
| Expert inspection | Shared-selection assembly, source, references and evidence metadata. | Browser acceptance; no external RzWeb source reused. |
| Format tree | Existing worker parses bounded ELF/PE sections; runtime registers the provider; unsupported formats refuse. | Browser acceptance; archive expansion is unsupported. |
| Dependencies | Actual workstation recovery dock displays recorded prerequisites, independent levels and cycles. | Stage retry is not advertised by the protected workflow catalog and is not fabricated. |
| Exports | V2 packs, generated Lua, header manifests, cave algorithm, readiness/divergence, validation and atomic content-addressed bundle assembly. | Complete image-bound cave evidence and qualified graph producers; native runtime adapters. |
| Export UI | Both surfaces list readiness and verified downloads through a shared scoped reader. | Live route activation and a complete real bundle. |
| Reports | Objdiff-shaped inventory report, weighted consumer, disjoint member accounting, independent extent unions and separate verified/advisory displays. | Independent byte-acceptance provider integration, per-entity matrix counts and publish approval. |

## What the checks establish

Changed Python modules parse. Static JavaScript passes `node --check`; the
static-action ownership checker reports zero violations across all three required
surfaces. A TypeScript program check using the existing NVMe dependency tree
reports zero diagnostics; it emits no files and is not a Vite build.

Focused in-memory checks cover schema migration, matching evidence, policy
capture, header manifests, pack validation, divergence, report weighting,
accounting gaps/double counting and open admission. Generated Lua was exercised
under Lua and LuaJIT with a fake host adapter. Parser checks cover bounded PE
sections, absent ELF section tables, truncated input and unsafe offsets. These
checks do not establish a real Ghidra, compiler, binary, game or browser result.

All eight owner-locked files retain their original SHA-256 values. No tests were
edited, no suite or build ran, and no server was restarted. Parallel workers hit
an account usage limit; local implementation continued. No usage-reset credit
was consumed.

## Activation boundary

The observed 8080 process imports the canonical MyBook source tree despite its
NVMe working directory. Its reloader reported zero watched files. The edited
consolidation worktree is therefore not the mounted consumer. No blind copy,
restart, alternate port, overlapping recovery job or owner-file edit was used to
hide this distinction. Vite source changes also require a separately qualified
bundle before the mounted application can display them.

Current export publication refuses missing required cave/graph prerequisites.
An empty cave list is not a successful discovery receipt. The dashboard's report
projection has no connected independent byte-acceptance provider, so it reports
that limitation and does not promote recorded source to byte-exact acceptance.

## Remaining scope

The source batch does not complete all 43 units. Full provider/project-tab/map
integration (U6–U8), licensed local multi-decompiler comparison (U20), spectator
permissions and mirrored selection (U25), explicit publish approval (U29),
owner-locked test authoring (U30), and report-backed matrix cells (U43) remain.
The partial rows above retain their additional prerequisites. The original
193-unit recovery program and autonomous M0–M7 roadmap remain independently
required; none is closed by this implementation batch.
