---
name: AgentDecompile
last_updated: 2026-09-20
charter: VISION.md
active_living_plan: docs/plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md
---

# AgentDecompile Strategy

Charter lives in [VISION.md](VISION.md). Operators start at [README.md](README.md). This file is the investment bet under that charter, not a second north star.

## Target problem

A Ghidra project holds dozens of builds of the same codebase. Each build has its own addresses, but the functions, labels, and types are the same logical objects. Without cross-build identity and a propagation path, every recovery pass repeats work and metadata edits on one binary never reach the others. The crux is telling honest source from a wrapper that only compiles because it still contains the original bytes.

The end state is not per-function byte parity — it is a **whole-image byte-identical rebuild**: a source project that recompiles and *relinks* into a file bit-identical to the shipped executable. Per-function objdiff-0 is necessary but not sufficient. A stock linker assigns its own layout — section order, virtual addresses, padding, the PE/ELF headers, the import table, and base relocations — none of which reproduce the original image unless placement is enforced. This exact-placement gap is a first-class, unsolved part of the problem, not a footnote: the goal is a rebuilt binary whose whole-file hash equals the original's.

## Our approach

Link the builds, recover on the easiest one, and propagate. Treat **cross-build identity**, **code equality**, and **behavioral equivalence** as separate claims—never collapse them into one similarity score. Extract fingerprints once; reuse them. Prefer authoritative debug/provenance and unique exact evidence, then rare refs and neighborhood propagation, then structure/BSim, then optional second-opinion tools and emulation only on the residue. Require uniqueness and a margin; keep ambiguity and alternatives instead of inventing a pair. When inlining or fission breaks one-to-one boundaries, match regions—not forced 1↔1. A `logical_id` bind does not by itself authorize copying types, layouts, or recovered source; those have their own gates. Hook-pack export still picks one portable signature family. Do not re-run Ghidra analysis on a program that already has it. Calibrate compiler/ABI/layout once, scaffold, compile C, cross-place, leftover AI, objdiff, then fresh whole-image acceptance. One catalog on 8080.

## Who it's for

**Primary:** An operator, or an agent acting as one, finishing byte-accurate, assembly-free source for every program in a multi-build Ghidra corpus, with labels and structures kept in sync across builds.

**Secondary:** Someone who only needs citeable facts or a navigable tree and stops before the recovery bar.

## Key metrics

- **Verified readable C:** distinct logical functions with objdiff 0 (coverage or isolated audit receipts). Can regress on audit. Not the same as `real_c`.
- **Compiling Ghidra C share:** functions whose decompiled C is assembly-free and compiles (`ghidra-bulk` tally, `real_c=1`). Leading indicator, not proof.
- **Cross-placed compiling C:** compiling functions placed on sibling builds via `logical_id` (`cross-place` receipts).
- **Identity coverage:** inventoried functions bound to a logical function (`identity` table). Must stay high before propagation claims. Auto-accept precision matters more than forcing 100% paired; unresolved/ambiguous counts should stay visible.
- **Portable resolve:** share of those `logical_id`s that resolve on every registered build from one signature family, not a per-build VA. Can regress when a rebuild changes the window.
- **Loop completion:** catalog jobs from `/dashboard` end with named files on disk, not hang or silence.

## Tracks

### One operator surface (8080)

Workbench + kotorxid corpus pages + Atlas + report + `/api/v1/actions` on the MCP HTTP server. Deprecate leftover dashboard ports when in-tree server runs with corpus env.

_Why it serves the approach:_ Agents and humans must share one catalog and one progress view or they will diverge on what "done" means.

### Corpus recovery pipeline

Extract facts → `logical_id` (evidence-fusion cascade) → global calibration → scaffolding (assembly floor) → readable C (`ghidra-bulk`) → propagation (`cross-place`) → targeted AI on leftovers → parity (objdiff) → fresh whole-image acceptance. Skip a step when its receipt or Ghidra state already exists. Within measured memory/swap and ownership limits, parallelize independent analysis, evidence extract, bulk C, and cheap index queries; run pairwise graph or emulation only on the residue. Serialize `logical_id` writes, mutations to one Ghidra project, and isolated compiler/objdiff environments.

_Why it serves the approach:_ Recover once on the easy build and share the win. Do not reverse twenty versions independently.

**Cross match pipeline** names the compile-gated tier of this: `ghidra-bulk` → compile check → (pass) propagate that `.c` onto every sibling bound to the same `logical_id`, then byte-exact in order verify → permuter → LLM last; (fail) sanitizer/preparse helpers retry compile, then one LLM cleanup pass on that Ghidra body, then retry. Identity binding is a separate, already-run layer — cross match never runs before compile succeeds, and a `logical_id` bind alone never authorizes copying source that hasn't compiled. Elsewhere in this repo, "cross match pipeline" refers to exactly this tier; no further restatement needed.

The point is to reverse each function once and share the result across every build, not to reverse twenty versions independently. Byte parity is proven on the easiest build for a given `logical_id`; recovered source then propagates (compile-gated) to its siblings. Knowledge cross-match runs concurrently with source recovery and is **bidirectional per field**: function labels, user comments, structures/types, and STABS-derived names merge across every build sharing a `logical_id`, with the strongest source for each field winning — a name or struct recovered on one binary flows to the rest, and where another build carries better evidence (richer STABS, authored comments, a fuller type) that flows back the other way. Merge is field-level and precedence-gated (naming precedence in the priority ladder; types and source keep their own gates), never a wholesale copy, so a weaker build never overwrites a stronger one. A build with the most complete metadata for a field becomes the donor for that field, not for everything.

### Ghidra shared state

One store, BSim, prompt evidence from this tree's venv CLI, session-stable `ensure-program`. Label/type edits flow through identity, not per-address copies. Ghidra Server is RMI over SSL, not HTTP.

_Why it serves the approach:_ Cross-match metadata only works if Ghidra state and recovery receipts share the same program binding.

### Portable identity / hook-pack export

The implemented `corpus.export-hookpack` is advertised through the 8080 catalog. It exports identities, signature strings and per-build instances; it does not prove a ready-to-call adapter. KotorPhasor already loads v1 packs and overlays, admits known builds and can fall back from a stale address hint to a unique executable-region byte scan. Matching hints and instances without expected bytes retain weaker checks. Export site names/build slugs must map to native adapter keys/profiles; raw export is not automatically drop-in.

Runtime reuse is a parallel branch after sufficient identity/ABI evidence, not a mandatory stage after full recovery. Shared corpus → runtime pack and target bindings → supported typed adapter or cave plan → preflight → controlled install/call → independently observed behavior → provenance feedback. KotorPhasor consumes original binaries; it does not replace recovery or turn original bytes into recovered C. Feed names, types, fields and behavioral observations back through the same field-level evidence gates.

[Runtime reuse](docs/RUNTIME_REUSE.md) records source pointers, architecture/ABI limits and missing readiness proof. Keep the core generic with target adapters and build profiles: all BioWare corpus builds remain in scope, with future other-game support requiring adapter work. A resolved address is not a universal C-call interface.

## Priority ladder (do not reorder)

1. **Identity:** extract facts once; short-circuit identical images; then bind `logical_id` by independent channels (authentic symbols/provenance → unique exact/reloc hashes → rare refs / C++ metadata → neighborhood propagation → CFG/SPP → BSim significance → ABI → optional BinDiff/BinExport → optional emulation). Candidate generation is not acceptance. Preserve ambiguity; quarantine bad seeds. Do not re-analyze a program that already has Ghidra analysis unless incomplete or corrupted.
2. **Global calibration:** compiler versions, flags, ABIs, and global struct layouts before per-function recovery.
3. **Scaffolding:** donor workspace: one file per function, exact inline asm if no C, must link.
4. **Readable C:** `ghidra-bulk` replaces asm when C compiles; keep asm on failure.
5. **Propagation:** only after compile succeeds; sibling `.c` via `logical_id`. Identity match does not auto-copy ABI-sensitive types or unrevalidated source.
6. **Targeted AI:** leftovers only, leaves before callers; not before tiers 4–5 for functions Ghidra C already compiles. LLM output never creates a trusted identity edge alone.
7. **Parity:** objdiff 0 per function when claiming verified readable C; isolated toolchain; rebuild-validation stage—not a cross-architecture identity oracle.
8. **Whole-image byte identity (exact placement):** the terminal goal. After every function is objdiff-0, relink into a file bit-identical to the shipped image. Requires exact placement — pin each function and data object to its original VA, reproduce section order/sizes/padding, headers, import/IAT layout, and base relocations — then verify by whole-file hash, not per-function diff. Per-function parity that does not survive a whole-image relink is not done. This tier is an open engineering problem (a stock linker will not reproduce the original layout); treat it as core scope, not a stretch.

## Whole-image byte identity (dedicated track)

Per-function objdiff-0 and a whole-image byte-identical rebuild are **separate claims** — the second is the project's terminal deliverable and the harder one. A source project can have every function compile byte-exact and still relink to a different file, because the linker owns layout: virtual addresses, section order and padding, the PE/ELF header fields, the import table / IAT, TLS, resources, and the base-relocation table. Closing this needs an exact-placement link: a layout spec derived from the original image (per-symbol VA, section geometry, header bytes, reloc sites) that the link honors, plus a rebuild-validation stage that compares whole-file hashes and localizes any residual byte delta back to the owning function/section. Assembly-floor bodies preserve original instruction bytes and let the image link early; placement and relocation still require verification. Each is then replaced by real C that must still pass both the per-function gate and the whole-image relink. Until a build produces a file whose hash equals the shipped binary, whole-image recovery is unproven — say so plainly and keep the exact-placement work visible on the ladder.

_Why it serves the approach:_ "Decompiled" means rebuildable to the original artifact, not just readable per function. Without this tier the corpus can look 100% recovered while no build reproduces the shipped file — the exact gap the mission audit flagged as never proven.

Maintain two separately measured variants: **byte-accurate C+assembly-floor**, with every assembly/original-byte contribution explicitly counted, and **max-C**, maximizing readable assembly-free C. Never count floor bytes toward recovered-C coverage or borrow one variant's receipt for the other. Final acceptance needs a fresh compiler/toolchain run on the complete current source, per-function relocation-aware objdiff and an exact-placement whole-image relink/hash comparison for each claimed build. Cached receipts guide reuse; they do not substitute for this terminal fresh rebuild. Cheap deterministic compile/repair/verification comes first; permuter next where applicable; LLM/Mizuchi last on measured residue.

## Marketing

**Key message:** Identity first—and identity is not an address, not byte equality, and not a single score. Extract once. Fuse independent evidence. Keep ambiguity. Separate gates for types, source, and byte audit. One catalog.
