---
title: Portable Signatures, Codecaves, and ABI Export — engine-generic
type: feat
date: 2026-09-21
extends: the 2026-09-08 portable-signatures export plan (docs/plans/2026-09-08-0225-*; rename that file to drop its product token under U21)
authority: STRATEGY.md (recovery ordering) · VISION.md (engine-agnostic) · RUNTIME_REUSE.md (integration contract)
status: implementation-ready plan, audits 2, 3 and 4 applied; Step 0, Phase 0 (D1–D7), U5c, U7/U7b, U22, U1–U3/U1b, 3b, D8/D9, R3, hotfixes A1/A2/A3/A5 and the Phase 15 grid skeleton U120–U124 landed on feat/portable-signatures-codecaves-generic (a4e4aca)
---

# Portable Signatures, Codecaves, and ABI Export — engine-generic

## Revision log

- 2026-09-21 — audit 2 (five grill sessions + cross-grill): A1–A31 applied; see
  docs/plans/2026-09-21-plan-audit-2.md
- 2026-09-21 — audit 3 (design vs plan, grill 6): surface ownership, Phase 14 surfaces,
  U28x attestation, no-Start supersession; see docs/plans/2026-09-21-plan-audit-3.md
- 2026-09-22 — audit 4 (round 5, distributed design) + licensing strip + Phase 15
  walking-skeleton order: round-5 amendments A2/A3/A5/A6 applied to the design, every
  licensing passage removed (capability-only access), Phase 15 (`agentdecompile_grid`)
  inserted in the order it was built, register "Distributed compute" section, diagram
  Lane E; see docs/plans/2026-09-21-plan-audit-4.md

Goal (user, 2026-09-21): make the recovery pipeline (1) generate a **portable
signature for every cross-build entity** — functions first, but equally globals,
structures/classes and their fields, vtables, strings, constants, data tables, imports,
dispatch tables, and instruction-level patch points (see "Beyond functions") — so each
is found across *all* builds without absolute addresses, unifying logical entities;
(2) when an entity's surrounding call-graph/CFG/layout is **too different** across
builds, point that out and display it;
(3) **auto-export codecaves + parameters/ABI**, signature-keyed and grouped so they
work on as many builds as possible, implementable in Lua; (4) do this **engine-generic**
— the current corpus now, any other program's builds next: sibling builds of one engine
family, and unrelated engines, formats, and architectures alike. **No product, binary, or
project name appears anywhere in this design; targets are described only by class
(format × architecture × toolchain × engine-adapter).**


### Delta Update (2026-09-22, iteration after audit 4 — U125 and U25 landed; canon on the fast disk)
- **Landed:** U125 integrator `86b9d6d`/`fe9d563` (twelve seams reconciled; the grid-of-one cycle
  publish → work → verify → materialize ran end to end and is recorded in
  `2026-09-21-grid-of-one-walkthrough.md`); 3d U25 `corpus rebaseline` + A3 `ALGORITHM_VERSION` bump
  `2dbd467`/`ca7fdb6` (migration 3 `basis_supersession`; `RestampOnly`/`JsonSitesDiffer`/`LedgerResolver`
  working, `RecomputeDivergence`/`BinaryPackDiffer`/`PackResolver` named slots); audit-4 docs `708683e`;
  R1 in effect — the canonical checkout is now the fast-disk clone (`~/agentdecompile-nvme/AgentDecompile`,
  remotes `codeberg`, `gitlab`, `usb`); the USB copy is a synced mirror. Earlier: grid skeleton U120–U124
  (`d8447f6` … `a4e4aca`), hotfixes A1/A2/A3/A5 `a501e9d`, R3 `40d50ce`, D8/D9 + harness (o)
  `24b3050`/`a4095ba`, Step 0 `0256ca0`, Phase 0 D1–D7 + U5c, U7/U7b `f935db7`, U22 `f5f6a88`,
  U1–U3 + U1b `b271ba6`, U21c `0191303`, 3b `5bf8a11`.
- **Partial:** `corpus rebaseline` on a copy of the real store refuses with "analyzer identity is absent
  for 60 build(s)" — correct under today's rule, and exactly what A4 admission (in flight,
  `unit/a4-admission`) removes by scoping `_identity_rows`/`corpus_manifest_hash` to admitted builds;
  U25's `stored_basis_rows` must take the same scope at integration. An export that refuses *after* a
  re-stamp committed has no enumerated exit code (U25 chose 0 with the refusal under `run.export`) —
  a hindsight item for U28's exit-code table. U125 findings for the adapters: two key-id schemes
  (`log.signing` vs `worker.identity`) need a bridge before offline `Keyring` verification of node-signed
  records; `results/<task_id>.index` is never written on the live path (no GC root for non-enumerating
  stores); the toolchain canary still ends `not-configured` (U163). Round-4 survivors F1–F9/D1–D14 and
  the foundations audit remain pending; the U5c(b) shuffle is not in the gate; `_version.py` local change
  left to its owner.
- **Next:** integrate A4 (`corpus admit`), then attest admit → rebaseline → backfill analyzer_identity →
  verify-determinism → export-hookpack on a copy of the real store; U28x attest verb as a grid task kind
  (U168); U104 admission flags (H5); U21a/U21b; U19a; then the adapters in Phase 15 order (U158, U126,
  U159–U162, U132, U163–U165 first).


## Program thesis (recorded 2026-09-21 from the user's own words; migrates to STRATEGY.md at convergence)

1. **Deterministic, model-free.** The pipeline gives what conventional RE tools give — and far more
   usable — through a deterministic workflow that needs no AI to run; a model may accelerate a
   bounded leftover, never be the mechanism. "Throw a subscription at it" leaves no reusable
   workflow and does not survive a cost bubble; this must.
2. **Compute scales in three steps.** A potato laptop can run it; concurrency everywhere comes next;
   then compute that is not ours — idle-resource donation in the folding-at-home spirit **and** the
   free cloud infrastructure already waiting to be used, so the operator never depends on
   volunteers. The distributed layer is a **modular, reusable package** for other CPU/IO-heavy
   work, not a feature of this pipeline.
3. **Miniature, non-blocking work.** Nothing runs long and independently until a large amount of
   work is done; every step is small enough to hand to another node, checkpoints asynchronously,
   and resumes elsewhere. Large jobs are decomposed, never awaited.
4. **State is never a single stateful device.** A single SQLite file, a spinning disk, and the
   load-balancer workarounds built around them are the permanent bottleneck the industry keeps
   designing around. Storage mediums are archives; working state is concurrently updatable and
   network-capable (content-addressed, log-structured, or a multi-node store); a local database is
   at most a materialized view. I/O bottlenecks are a defect class, not a fact of life.
5. **Small projects, reclaimed.** The program is broken into smaller projects whose results are
   reclaimed into the whole; each is usable alone and none may opt the whole into a bottleneck.

Every unit, design choice, foundations-audit verdict and diagram card is judged against these five.

## The governing principle

Conventional RE tools hand a human *analysis data* — a decompiler listing, a call graph,
a similarity score — and the human is the inference engine that turns it into
understanding and action. **AgentDecompile's recovery pipeline is the inference engine.**
It attempts to reverse as much as is physically possible **itself**, using **deterministic
methodology** of the kind the matching-decompilation community has proven works
(relocation-aware object diffing, masked-pattern signature scanning, compile-gated
propagation, whole-image relink-and-hash), and it records exactly what it could not
determine rather than asking a human to guess. Every unit below is judged by that
standard: (1) does it use a strategy that is widely adopted and *known to work*, (2) are
that strategy's known failure modes addressed up front so they don't surface later, and
(3) is its output a pure, reproducible function of its declared inputs. The "Grounding in
known-working practice" section maps each mechanism to its proven strategy and pitfalls.

**The bar is a level above Ghidra and IDA.** Those tools end at *analysis you still have to
work with*: a database an expert queries, then hand-turns into offsets, hooks, and
bindings. AgentDecompile ends at **usable exports, ready to go**: when analysis finishes,
the memory-mod / code-injection / cross-build workflows already have everything they need
— a pack of every entity with portable locators and coverage, generated Lua bindings so a
mod author writes `player.name` and never touches an offset, per-build headers for native
mods, a readiness report saying exactly what works on which build, and the recovered
source variants with their build manifests. The analysis is not the product. The export
bundle is (see "The export bundle" and Phase 12).

**Universality is pursued exhaustively, not disclaimed.** A single signature will not
resolve on every build — but a single signature is never the whole strategy. Every entity
carries an **exhaustive resolution ladder** (see "Exhaustive resolution ladders" and
Phase 13): its own masked bytes, then anchors, then *every* relationship that can locate it
indirectly (its callers, its callees, the data it touches, the vtable that holds it, the
constructor that initializes it), then structural matching with an embedded runtime
decoder, then a payload-allocation fallback for caves so injected code always has
somewhere to live. "Unresolved" is the **residue after every physically possible
strategy has been tried**, and the corpus **learns every new build it meets**, so the
residue shrinks with each build the pipeline sees. Coverage is recorded per build because
that is how you know what remains — not as a reason to stop early. Runtime reuse never promotes original bytes to
recovered source. This extends the 2026-09-08 portable-signatures plan; it does not
fork STRATEGY's recovery ladder. The former live-recovery operational guards were lifted
by the user on 2026-09-21; what remains is engineering rigor — every change revertable
(Step 0 below), deterministic (the Determinism section), and verified on a temp copy of
the store before it touches the working one.

**Autonomy rule (user, 2026-09-21).** AgentDecompile one-shots all of it — cross-match,
byte-accurate C, codecaves, function and entity signatures, ABI, Lua bindings, headers,
readiness and divergence reports, learn-the-build — **without a human continually
addressing things inside it.** Consequences, binding on every unit: (1) no unit may
require a human action to reach an output; (2) review is an **override applied
afterwards**, never a gate on progress; (3) `ambiguous` and `contested` entities are
still exported, with their evidence and ordered candidates, and **refuse at use time**
rather than wait for triage; (4) therefore the review lane's starvation (risk register
H3) cannot stall coverage — it can only delay overrides. The source-recovery ladder
(STRATEGY stages 1–8) and this plan's substrate both run unattended from one project
open; whole-image byte identity stays program scope (goal), but nothing on the way to it
pauses for a person.

## Source trees and scope — read this first

There are **two source trees**, and which one you read changes conclusions:

| Tree | Git? | Role |
|---|---|---|
| `/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/src/` | Yes (`master`, last commit 2026-09-21 07:27) | **The most comprehensive tree.** A full comparison shows canonical is *newer* on ~78 of the 81 files that differ and carries modules that do not exist on nvme at all: `decode_x86.py` (1193 lines, 2026-09-20), the `exchange/` package (2026-09-10), `corpus/name_precedence.py`, `corpus/db.py`, `corpus/inventory.py`, nine `corpus/materialize_*.py`, `corpus/nds_extract.py`/`nds_import.py`, `corpus/verify_full_image_receipt.py`, `corpus/package_*.py`, `corpus/finish_binary.py`, plus React `exchange-*.ts`, `LogicalNavigator.tsx`, and tests. **This is the implementation base.** |
| `/home/brunner56/agentdecompile-nvme/src/` | **No** (untracked runtime copy) | Behind canonical. Genuinely nvme-only work is **narrow**: `agentdecompile_recovery/containers/{detect,models,nds,registry}.py` (a split of canonical's 364-line `agentdecompile_recovery/containers/__init__.py` — a one-way copy would truncate that to 26 lines), `corpus/dashboard/live_recovery.py`, `corpus/source_parity_synthesize.py`, and three files a few lines newer (`corpus/dashboard/library_identity.py`, two CSS). nvme's root `catalog.py`/`introspect.py` are **stale duplicates** of `corpus/dashboard/actions/{catalog,introspect}.py` that nothing imports. |

> Correction record: an earlier draft of this plan said nvme was "the most comprehensive"
> and canonical "behind." That came from a tree diff that was killed after printing only the
> "only in nvme" lines. The full comparison inverts it. `rtti_recover.py` lives at
> `agentdecompile_recovery/rtti_recover.py` in **both** trees, byte-identical — not under
> `corpus/`, not nvme-only. `match_store.py` differs by one unused import (a lint cleanup
> on canonical). The files Phase 0/1/2 edit — `logical.py`, `propagate.py`,
> `export_hookpack.py`, `features.py` — are byte-identical across trees, so their anchors
> hold; **every other anchor is nvme-relative and must be re-derived on the implementation
> branch** (81 files differ; e.g. `pages.py` 3627 vs 3584 lines, `Surfaces.tsx` 1705 vs
> 1712, `cli.py` 1095 vs 1035). Anchors written as `corpus/introspect.py` are wrong: the
> real files are `agentdecompile_recovery/introspect.py` (stale) and
> `corpus/dashboard/actions/introspect.py`.

Both trees carry `agentdecompile_recovery/` (batch corpus recovery + exporters) **and**
`agentdecompile_cli/mcp_server/providers/` (the interactive Ghidra MCP provider layer:
`getfunction.py`, `_collectors.py`, `callgraph.py`, `dataflow.py`, `decomp_match.py`,
`dissect.py`, `memory.py`, `vtable.py`, `structures.py`, `import_export.py`, …). The
initial audits read only `agentdecompile_recovery/` on nvme; the ABI audit then found the
CLI tree and **reversed one headline conclusion** (per-parameter storage *is* captured and
editable there). Unless a bullet says otherwise, every `file:line` anchor below is from
`src/agentdecompile_recovery/` on the implementation branch where audit 2 re-derived it, and
from the pre-Step-0 runtime copy elsewhere (unverified until order step 2b); anchors from
the CLI tree are marked `[CLI]`.

> **Status (audit 2):** Step 0 is done in `0256ca0` — 119 differing files (not 81); the
> `containers/{detect,models,nds,registry}.py` split was **not** imported (canonical's
> monolith is newer); `source_parity_synthesize.py` was imported at 0 bytes — treat it as
> truncated and re-import before U42. Item 5 (re-anchor) is open: audit 2 re-derived the
> anchors it cites against the implementation branch; the rest stay unverified until order
> step 2b.

**Step 0 (before any code change): branch from canonical, fold in the narrow nvme-only
work by per-file decision, then re-anchor.** The user's standing rule is to resume from
the most comprehensive work and never overwrite effort. Canonical git *is* that work; the
untracked nvme copy holds a small amount of newer material that must not be lost.
**A one-way copy in either direction destroys work** — nvme→canonical would overwrite the
2026-09-21 merge and newer `cli.py`, `pages.py`, `jobs.py`, `router.py`, `ghidra_bulk.py`,
`pipeline.py`, and truncate `containers/__init__.py`. So:
1. Create the implementation branch from canonical `master`.
2. Re-derive the differing-file list on scratch as this step's first action (the earlier
   count was from a diff that timed out), then three-way compare every differing file
   against its last common ancestor (copy both
   `src/` trees to fast scratch first; never diff across the slow external mount). Make an
   explicit per-file ownership decision; **never overwrite a newer canonical file**.
3. Import only the genuinely nvme-only modules (`containers/{detect,models,nds,registry}.py`
   reconciled *with* canonical's `containers/__init__.py`, `live_recovery.py`,
   `source_parity_synthesize.py`) and the three slightly-newer nvme files after inspection.
   Drop nvme's stale root `catalog.py`/`introspect.py`.
4. Record every decision in the commit message. Commit. **That branch is the base for
   every unit below.**
5. **Re-derive every `file:line` anchor in this plan against that branch** before any unit
   starts (only the Phase 0/1/2 core files are byte-identical; treat all other anchors as
   unverified until re-checked). The runtime copy is then refreshed *from* the branch, not
   the reverse.

## The picture from the audit (what already exists)

The substrate is **further along than "greenfield"** — this is *generalize + complete*,
not build-from-scratch. Grounded in a six-part read-only code audit:

- **Signatures:** a rich, mostly arch-agnostic per-function fingerprint set exists
  (`hash_reloc`, `hash_instr`, `hash_mnemonic`, CFG MD-Index, mnemonic-SPP, fuzzy
  SimHash; `corpus/features.py`, `corpus/fingerprint_hashes.py`, `corpus/cfg_signature.py`).
  **But** there is no portable per-`logical_id` signature: `logical_function.best_signature`
  holds the **C prototype string** (`corpus/logical.py:256`), the "signature family" in
  `export_hookpack.py` is a majority-vote over prototypes, `hash_raw` is unmasked exact
  bytes, `unique_window` is per-raw-file (not cross-build, not region-scoped, prologue-
  anchored, no masking, `export_hookpack.py:56`), there is no cross-build `find_unique`
  or coverage record, and BSim is eval-only (`corpus/bsim_eval.py`; `_fuse_bsim` reads an
  optional external table, never writes identity).
- **Hook-pack (`agentdecompile.hookpack/v1`):** emits `binaries[]` (slug/game/platform/
  format — **no image_base, no sha256**) and per-site `logical_id`/`cls`/`method`/
  `signature{kind,value,hits,of}`/`instances[]` where `signature.value` is the opaque
  prototype string the runtime resolver **never reads** (`corpus/export_hookpack.py:120`).
  Missing (confirmed): site-kind, structured ABI, field-extent, `required`, image
  identity, any cave notion. **Key asymmetry:** the runtime host's consumer `registry.cpp`
  already parses image_base/sha256/kind/required/field offset+size — the exporter just
  never writes them.
- **Codecaves:** **zero discovery in AgentDecompile.** The runtime host has the concept
  (`docs/user/codecaves.md`), a 4.1 MB one-off `data/codecaves.toml` (16,184 caves / 9
  builds), and a raw-write primitive — but **no committed generator** and no capacity/
  relocation/restoration bookkeeping (a raw memory write through the Lua host's memory API is unrestorable). Since the Lua
  host exposes **no allocation primitive** (its memory API is 23 read/write/`findsig` functions),
  writing a stub into a `findsig`-located cave is the **only** route to executable space.
- **ABI/params:** recovered at extraction (`corpus/features.py:130-138`: convention,
  return/param *type names*, counts, stack sizes, varargs) but **per-parameter storage is
  dropped** — `features.py:131` records type names and never calls `getVariableStorage()`.
  `varargs`/`no_return` recovered but not persisted. `thiscall`/`fastcall` collapsed to one
  `ecx` class (`corpus/propagate_conventions.py:13`). Vtable info built (`agentdecompile_recovery/rtti_recover.py`, present in both trees)
  but never exported. The exporter drops all structure, emitting only the prototype text.
- **Divergence:** relation vocabulary exists (`one_to_one/clone/inline/split/fold/unroll`,
  `corpus/correspondence.py:13`) but its split/inline/fold detector is inert: per-block
  hashes **are** stored (`features.py:218,246,270` → `extract.py` → `store.py:70,211`) —
  the "not stored" docstring at `block_inline.py:6` is stale — but they are mnemonic-class
  hashes over Ghidra's `BasicBlockModel` partition, i.e. analysis-derived (see U6b);
  **a persisted per-`logical_id` neighborhood/CFG divergence signal is missing** — the only
  cross-build neighborhood comparison anywhere is an unpersisted tiebreaker in the CLI
  `match-function` tool (U17b); CFG/call-graph only ever *boost* a match, never flag "too
  different,"
  so divergent matches are silently forced or hidden; the review UI shows only accept/reject/
  score (`Surfaces.tsx:1286`) and the API doesn't even SELECT `relation` (`pages.py:768`).
- **Genericity:** the `binary` schema (`arch/bits/format/image_base/language_id`), format
  detection (`targets.py`), container registry, source-language registry, and the
  `compiler_for` profile seam are already genuine adapters. Breakage clusters in three
  places: **no signature masking** (breaks x64/PIE/ARM — the #1 blocker), **MSVC-x86 ABI
  duplicated in 4 files**, **PE32-only VA→offset** — closed in `f935db7`: `_file_offset`
  (`export_hookpack.py:82-90`) now goes through `mapper_for(image, load_base)`. Plus a few hardcoded product-specific *paths* to move to data-packs.

## Design spine

### 1. Two orderings — do not conflate them
- **Identity resolution (matcher, corpus-side):** decides two functions are the same
  logical entity. Bytes stay **last-resort** here (STRATEGY's crux: an honest source vs a
  wrapper that only compiles because it still holds original bytes). Unchanged.
- **Runtime resolution (locator, in the exported pack):** finds an *already-bound* site in
  a live image without a VA. A relocation-masked byte window is a legitimate **primary**
  member here, because identity was already settled upstream. A runtime byte-match is
  **never** an identity edge. Runtime resolutions go to
  `runtime_claim(build_sha256, entity_key, addr, member, evidence, observed_status)`, a claim
  beside `match`, never a row in `identity`. Only `bind_identities` promotes a claim, and only
  when a non-byte channel confirms it; rejection writes a receipt and deletes it. Nothing
  exports, diffs or counts `runtime_claim` as identity; the harness lists it under
  `FIXTURE_TABLES`, never `OUTPUT_TABLES`.

### 2. Signature is a *family*, split by where it runs
- **Identity-time evidence** (produces `logical_id`): symbols → exact/reloc-normalized →
  rare refs/C++ metadata → neighborhood → CFG/SPP → BSim → byte-window last. Unchanged.
- **Runtime locator family** (shipped in the pack for the Lua host, which has only a byte
  scanner (`findsig`); its C++ length-disassembler is not exposed to Lua and there is no BSim): (a) **relocation-masked byte
  window — primary**; (b) **anchor-relative** descriptor (resolve a unique nearby import/
  string/symbol, then relative offset); (c) content/region hashes for verification. CFG/BSim
  are the *producers* of these, not runtime resolvers. **The pack must carry the corpus-
  computed uniqueness/margin proof** — `findsig` cannot recompute `find_unique`. Record
  **per-build coverage** when no single family member hits every build.

### 3. Codecave = a signature-anchored *plan template*, not a fixed VA+bytes
Exportable (in the pack): anchor signature, relative offset to the cave, capacity
*requirement*, payload + relocation *rules*, expected original bytes, restoration plan,
arch tag, provenance. **Irreducibly resolve-time (never exported), left to the runtime:**
resolved absolute VA, actual free capacity/availability, live relocation fixups, quiescence,
and actual-byte verification. Detours ≠ caves: ordinary detours self-allocate trampolines;
the cave template is only for the resident-payload subset. Never claim "works on all builds";
group by `logical_id` and record per-build resolvability/capacity coverage.

### 4. The generic seam is three layers
- **L1 — generic core** (any PE/ELF + Ghidra, zero engine knowledge): reloc-masked byte
  windows, CFG-structural signatures, call-graph neighborhood hashes, cross-build
  uniqueness/margin, **cave candidate discovery** from section padding/alignment, and the
  **divergence delta**.
- **L2 — architecture adapter** (per-arch, shared by every engine on that arch): detour
  width (x86-32 five-byte), relocation model, relative-branch reach, register call
  mechanics, signature mask policy/opcode set. *Detour width is per-arch, not per-engine* —
  a 64-bit target and a 32-bit target differ here while sharing L1, regardless of engine.
- **L3 — engine adapter + build profile**: VM/script-API name→key mapping (one map per
  engine's script system), this-kind/typed-call semantics, build slug→profile, image
  base/hash, overlays, semantic aliases, hook-intent/site-kind policy.
A new engine plugs in by adding an L3 adapter and *selecting* an existing L2; L1 never
changes. **L3 adapters and build profiles are external data packs, never code or docs in
the core.** Data packs are declared inputs: root path from config, `pack.json
{schema_version, engine_class, arch_class, entries}`, sorted discovery, content hash in the
basis, one loader (U19a: a fixture pack loads; removing it yields `missing_adapter`, never a
default).

### 5. Divergence is a first-class L1 signal, not a display afterthought
It is the same epistemic requirement the identity model already mandates (region-match, not
forced 1↔1; keep one-to-many/split/inlined representable). Compute a neighborhood/CFG delta;
when it exceeds region-match confidence, surface a **"diverged — counterpart structurally
different, possibly inlined/split"** state instead of a silent forced match.

### 6. Beyond functions: the cross-build entity model

A memory mod or injected code never needs *only* functions. It needs to **locate**
things, **understand their shape**, and **act** on them — across every build. The
function-only framing under-delivers the goal. So the pipeline treats **every entity kind
below identically**: cross-build identity (a logical id), a portable locator (signature /
anchor-relative / xref-derived — never a VA), shape/type info, and per-build coverage +
divergence. Pack v2's `sites[]` generalizes to `entities[]` keyed by `kind`. Anything that
exists in the binary and that a mod could reasonably want is an entity.

**How non-function entities get identity and location.** Functions are the anchor
substrate: once a function is identified and located by signature, everything it
*references* inherits a deterministic locator — "the global read by the instruction at
offset N of logical function F", "the vtable written by F's constructor", "the string at
the 3rd data reference in F". Cross-build identity for data flows through the **xref
graph from identified code** plus symbols/debug info where present, plus content
(strings, constants) and structure (field-access fingerprints). This is the same
cheap-first cascade, extended to data.

| Entity kind | Cross-build identity from | Portable locator | Shape carried | What it enables (mod / injection) | Divergence to surface |
|---|---|---|---|---|---|
| **Function** (existing) | cascade (symbols → reloc-normalized bytes → refs → neighborhood → CFG → BSim) | masked window / anchor-relative | ABI, CFG, size | entry hooks, typed calls, detours | split/inlined/diverged |
| **Mid-function instruction site / patch point** | parent function identity + decode-stable instruction index | function locator + instruction offset from a masked interior anchor | instruction bytes, operand layout, live register/stack contract at that point | mid-function hooks, reading locals at a hook, nop-outs, redirects | instruction absent / moved / reordered |
| **Immediate / constant in code** | patch point + operand slot | patch-point locator + operand offset & width | width, signedness, inferred semantic (multiplier, limit, flag) | constant patching (speed, damage, caps) | operand width/value changed, folded away |
| **Call site** | caller identity + callee logical id + ordinal within caller | caller locator + instruction offset | target logical id, arg setup pattern | per-call-site redirects (vs hooking every caller) | call inlined / removed / re-targeted |
| **Global / static variable** | xref from identified functions (data-ref channel), symbols/STABS, content | anchor-relative from a code reference (instruction at F+N → operand → address) or data-section masked adjacency | type, size, alignment, r/w usage | read/write game state; anchors for other data | moved / resized / retyped / merged |
| **Singleton / manager pointer** | global holding a pointer, deref pattern from accessors | as global + deref chain | pointee class, deref depth | reach live object graphs from a known root | pointer indirection changed |
| **Structure / class** | name (symbols/STABS/RTTI), **field-access fingerprint** (set of (offset,size,kind) accesses from decompiled refs), constructor identity | (shape entity — located via its instances/ctor) | **per-build field map** (offset/size/type per field) + a cross-build **field-level correspondence** | read/write fields *by name* portably; typed pointer args; safe object walking | **fields shift/added/removed/resized/reordered** — must be first-class, since layouts change between builds |
| **Class size + constructor/destructor + allocator** | allocation-site arg (`new`/`malloc` size) + ctor identity | ctor locator; allocator locator | `sizeof`, ctor ABI, dtor, allocator kind | **spawn / free objects from injected code** | size changed, ctor split |
| **VTable** | RTTI, constructor vtable-writes, xref | anchor-relative from ctor store, or data masked window | **slot → logical method map per build**, slot count | virtual hooking (slot replacement), virtual calls, class identification of an object | **slot reorder / insert / remove** — must be tracked per slot |
| **RTTI / class hierarchy** | type descriptors, complete-object locators, base-class arrays | data locators | class name, bases, offsets | dynamic-cast-style checks, hierarchy-aware hooks | base added/removed |
| **String literal** | content hash + referencing functions | content + xref anchor | encoding, length, refs | text patching, anchoring locators, localization | text changed / moved |
| **Static data table / array of structs** | referencing function + element layout fingerprint + stride | code-ref anchor + element index | element struct, count, stride, index semantics | edit items/stats/tables; enumerate content | element layout or count changed |
| **Enum / flag set** | switch tables, comparisons, symbols/STABS | (semantic entity) | value → name map per build | semantic constants for patches and calls | value renumbered |
| **Jump / switch table** | indirect-jump site in parent function | patch-point locator | case → target map | hook/redirect one case; dispatch understanding | cases reordered |
| **Import / IAT entry** | API name (or ordinal + library) | import thunk / IAT slot | name, library, ordinal | **IAT hooking**, API-call anchoring; trivially cross-build by name | name-only vs ordinal-only builds |
| **Export** | name / ordinal | export table | prototype/ABI | DLL-side hooking, calling exports | ordinal changed |
| **Function-pointer / dispatch / callback table** (incl. script-VM routine tables, event-handler tables) | table identity + index; the L3 script-API map | data locator + index | entry layout, index → logical function | **hook one script command / event**; register new entries | entries reordered / added |
| **Script VM interpreter: opcode handlers / dispatch loop** | interpreter function + handler table | function + table locators | opcode → handler map | bytecode-level interception | opcodes renumbered |
| **Thunk / import stub** | resolve-through to target | — | target | identity only (never a hook target itself) | — |
| **TLS slot** | TLS index global + accessors | as global | slot index, type | per-thread state access | index changed |
| **Exception / unwind table** (x64 `.pdata`/`.xdata`, SEH) | per-function | per-function | unwind codes, handler | keep unwinding **valid for injected code**; whole-image rebuild | — |
| **Relocation table** | format | format | entries | masking input; exact placement | — |
| **Sections / segments** | format | format | geometry, permissions | whole-image, cave scoping, W^X handling | layout changed |
| **Resources** (version info, dialogs, embedded assets) | resource type + id | resource directory | type, id, size | resource mods; version identification | id changed |
| **Global initializers / static constructors** (`.init_array`, `.CRT$XC*`) | init table | table locator | order | earliest-possible init hooks | order changed |
| **Entry point / main loop / frame tick** | entry + loop structure (back-edge dominating everything) | function locator | — | the canonical "per-frame" hook anchor | loop restructured |
| **Stack frame / locals at a site** | parent function + decompiler dataflow | patch point | stack offsets of named locals per build | reading/writing locals at mid-function hooks | offsets shifted |
| **Register state contract at a site** | decompiler dataflow at the instruction | patch point | which registers hold which values, clobbers | **safe** mid-function hooking (what to preserve) | allocation changed |
| **Serializers / save & network structures** | functions + the structs they walk | derived (function + struct entities) | wire/save layout | save-game and packet mods | layout changed |
| **Allocator / memory-management functions** | library-signature DB + usage | function locators | kind (heap/pool), size arg | spawn/free; **must be library-excluded from identity matching** | — |
| **Compiler-generated / CRT / library functions** | library-signature DB (FLIRT/FunctionID-style) | function locators | — | hookable (e.g. I/O) but **excluded** from cross-build identity to stop false positives | — |
| **Inlined region** | region correspondence (existing relation) | parent function + range | — | represent "this logic is inlined here" | (is itself divergence) |
| **Debug / symbol info** (STABS, PDB, map files) when a build has it | — | — | names, types, layouts | **donor** of names/types/layouts to builds without it | — |
| **Integrity / anti-tamper / checksum routines** | identify by behavior (self-hash of text, CRC loops) | function locators | region checked | **must be known** — patches break them; surface, never silently trip | — |

**Actions the entity model makes possible (what "we should be able to do"):**
- **Hook:** function entry · mid-function · vtable slot · IAT/import · export · call site ·
  dispatch/script-command entry · event callback · per-frame loop · static initializer.
- **Patch:** bytes/immediates at portable patch points; nop; jump redirect; table entry;
  string — every patch carries expected originals and is verified and restorable.
- **Read / write:** globals, singletons, struct fields **by name**, table entries, strings,
  TLS, locals at a hook site — by portable locator, never by VA.
- **Call:** typed native calls (ABI descriptor), virtual calls (vtable slot map), script-VM
  calls (dispatch table).
- **Spawn / free:** objects via allocator + constructor + `sizeof`.
- **Inject:** code into signature-located caves; register new dispatch/callback entries.
- **Observe:** trace calls/args/returns/field changes at any site (runtime-reuse evidence).
- **Verify first, always:** expected bytes / hash / capacity / unwind validity before any
  write; refuse on mismatch.
- **Migrate:** a mod written against one build resolves on every covered build through the
  pack — the whole point.
- **Diff:** a per-entity divergence report between any two builds (field moved, slot
  reordered, function split, table resized, constant folded).

### 7. Data acquisition: portable roots, ordered fallbacks, idempotent resolution

**The anti-pattern this replaces** (the user's reference script for another program): a
*static offset registry* — two builds told apart by a string compare, every data root
(`stats_header`, `gametype_base`, the player table, the object table) a hardcoded absolute
address per build, no fallbacks, no caching, no verification, and **silent zeros when a
read fails**. Everything about it breaks the moment a third build appears. Yet the
*structs* in that script (a player record with a name at `+0x4` and a team at `+0x20`; a
unit record with weapon slots; a biped with fixed-stride body-part blocks; bitfield flags;
wide-string names; `getplayer(index)` / `getobject(id)` table accessors) are exactly what
**does** persist across builds. The pipeline keeps the structs and replaces the addresses.

**Every data root gets an ordered locator family** — not one strategy, a ranked list,
each member with per-build coverage, so a build that cannot support one lookup still
resolves through another. Cheap-first and deterministic, mirroring the identity cascade:

1. **Symbol / debug info** (export table, STABS, PDB, map file) — when the build has it.
2. **Xref from an identified function** — `(function logical id, decode-stable instruction
   index, operand slot)` → the referenced address. The strongest *generic* strategy:
   functions are already located by signature, and every global/table/string a function
   touches inherits that location for free. Most roots resolve here.
3. **Anchor-relative to a format-table entry** — an import/IAT slot, an export, or
   string-table *content* (never a Ghidra reference) plus a signed offset.
4. **Data-section masked adjacency** — a masked window over the bytes *around* the root
   (a neighboring constant or string that the build preserves), same total-order selection
   as code windows.
5. **Pointer chain from another resolved root** — a deref path `root → +off → * → +off`,
   each hop verified; lets one well-anchored singleton reach a whole object graph.
6. **VTable / RTTI-derived** — identify an object's type from its vptr, then its fields.
7. **Module-relative RVA / section+offset** — the floor. An entity resolved only here is
   `pinned(member)`, `portable:false`, never `resolved`; present only so a build with
   nothing else still has a recorded answer instead of a silent failure.

**The resolver contract** (the runtime-host side, driven by the pack; every rule is what
the reference script lacked):
- Try members **in order**; stop at the first that resolves *and verifies*.
- **Verify before trusting**: expected original bytes / masked-window match, pointer
  sanity (inside a mapped region), type-shape check (e.g. a wide-string root actually
  holds a terminated UTF-16 run), value-range plausibility where the shape declares one.
- **Memoize per `(build image hash, root id)`** — idempotent: the second call returns the
  cached, already-verified address; never recomputed per frame.
- **Report which member resolved** (and which failed, with reasons) into the pack's
  per-build coverage — so the corpus learns which strategies each build supports.
- **Refuse, never zero**: total failure raises a named, structured error
  (`root unresolved on this build; members tried: …`). A mod must not proceed on garbage.
- **Builds are identified by image hash / code hash**, never by a string literal. An
  **unknown build is admitted in signature-only mode**: no profile, no RVA fallback, full
  locator families, coverage recorded — it works as far as its signatures resolve, and
  says exactly how far.

**Structs are first-class and per-build.** A `logical_struct` carries, for every build, its
field map (name → offset/size/type/encoding) plus the cross-build field correspondence
(`same / shifted / resized / retyped / added / removed / reordered`). The mod reads
`field(player, "name")`; the resolver returns the right offset for the running build.

**Accessors are generated, not hand-written.** Recovered descriptors for: array-of-struct
**tables** (root + stride + count/capacity + element struct + index semantics); **handle /
id → pointer** lookups (index/salt bit layout + backing table); **bitfields** (byte offset
+ bit index + width); **strings** (encoding, terminator or length rule); **nested repeated
sub-struct blocks** (base + stride + count — the body-part pattern); **enums** (value →
name). The Lua API exposes them build-agnostically: `resolve(root)`, `field(struct, name)`,
`entry(table, i)`, `handle(table, id)`, `bit(addr, i)`, `str(addr)`, `wstr(addr)`.

**A mod script contains no absolute address.** A lint over mod scripts rejects any literal
address; the only way to reach memory is through a root, a struct field, or an accessor.
That single rule is what makes a mod portable to every covered build — and to builds that
did not exist when it was written.

## Determinism — a hard requirement, and what it takes

The user's bar: **same inputs → byte-identical signatures, caves, matches, and pack**, every
run. Most RE tools can't; we can, because the core signals are pure functions of the binary
and the nondeterminism lives in *how we serialize, order, and tie-break* — which we control.

**"Deterministic" is only meaningful relative to a declared basis.** Every pack records a
**determinism basis**. This object is normative (U54 lands it; U5c emits it):

```
basis = {
  basis_version;
  decoder{name, version}                        -- from binary.decoder_revision
  analyzer{version, processor_spec_hash, compiler_spec_ids, options_hash,
           timeout_policy, loader_revision}     -- from binary
  algorithm_version                             -- incl. the tie-break key version
  masking_rule_version                          -- ≠ "none" once U4 lands
  threshold_params                              -- live serialization of PAIR_POLICY,
      CONTENT_FLOOR(S), channel_confidence.BASE and penalties, cfg slack,
      BSim {trusted_significance, margin, tiny_n_instr, tiny_sim},
      window {min_n, max_n}, divergence {d, u, s}; empty is a gate failure
  filler_set;
  external_channels{bsim_generator_revision};
  data_packs[{id, schema_version, sha256}]      -- sorted
  seeds; toolchain_identity_hash; corpus_manifest_hash
}
```

Enforcement: every field derives from store-recorded values or pinned package constants,
never from the process environment at export; each `binary` row carries
`basis_hash = sha256(basis minus corpus_manifest_hash)` written at ingest (migration 2);
export, the harness and `export-bundle` refuse when any field is absent, "unknown" or
empty, or when the store holds more than one distinct `binary.basis_hash`, naming the field
and both bases. `schema_migration.basis_hash` uses the same object. Any field change → U25.
Acceptance = re-run under an identical basis, byte-diff the pack, expect zero.

### What the code does today (determinism audit, nvme tree)
- **No format relocation table is consulted anywhere.** The fingerprint family is
  decode-derived, but function extents (`f.getBody()`), block partitioning
  (`BasicBlockModel`, `features.py:222`), and every reference channel (`strings`,
  `ext_calls`, `callees`, `data_refs` via `getReferencesFrom`, `features.py:193-213`) are
  **Ghidra-analysis-derived** and drift when auto-analysis runs differently. → **A
  canonicalization layer is mandatory.**
- `hash_raw` is unmasked exact bytes (`features.py:179`); `hash_reloc` is a *magnitude
  filter* on constants (`0x100 ≤ |v| < 0x7FFFFFFF`, `features.py:191`), **not** relocation
  masking — 32-bit absolute VAs pass it. Neither is reloc-tolerant.
- Already deterministic (do not touch): `fingerprint_hashes.py` (sorted + sha256),
  `cfg_signature.py` (fixed-seed mix, sorted RPO), `mnemonic_spp.py`, `fuzzy_fingerprint.py`
  (sorted tokens, blake2b), `store.j()` compact JSON, `dedupe_identity_addrs` total ORDER BY,
  `ghidra_bulk` uses `ThreadPoolExecutor.map` (submission order — safe to widen).
- No `hash()`-on-persisted-values, no random/uuid/time/pid in the signature/export path.

### Binding design decisions (RE-analysis review)
1. **Mask = decode-identified address operands ∪ format relocation-table entries**, computed
   over the **raw file image**, never from Ghidra's analysis references. Reloc-table-only
   under-masks: relative `call/jmp rel32`, x64 RIP-relative `disp32`, and jump-table-relative
   operands are position-relative and absent from `.reloc`. Leave non-address immediates
   literal (struct sizes/constants carry the discriminative signal). Mask scope is
   determined by decode semantics — it is **not** a tunable knob.
   **1b. Candidate-address class.** When the format carries no relocation table
   (`reloc_table_present=false`), an immediate whose value falls inside any mapped section's
   VA range is classed candidate-address and masked; this class is part of
   `masking_rule_version`. The window selector adds criterion (iii): zero candidate-address
   bytes, preferring such windows before applying the total order. A window that cannot
   avoid them is recorded with coverage `degraded(candidate_address)` for that build.
2. **Window selection uses a provably total order**: among windows meeting (i) a minimum
   literal-byte floor and (ii) uniqueness-with-margin against the *declared* corpus, choose
   by **(literal-content length asc, section-relative offset asc, full masked-pattern
   lexicographic)**. Mask-density is dropped as a criterion (preferring more-masked selects
   *less* discriminative content). Scan order pinned to (section index, offset asc); margin
   definition is part of the algorithm version. Uniqueness is per build over its executable
   region; `margin` = min over covered builds; consensus = intersection; both stored.
3. **Coverage is keyed by build slug, stored as sorted lists, and the corpus manifest hash
   is in the pack** — uniqueness is evaluated against the current build set, so adding a
   build legitimately changes the canonical window; determinism is "pure function of (sorted
   build-image hashes + decoder revision + algorithm version)." D1/D2/D3 tie-breaks and every
   "best" pick use `binary.content_sha256`, never rowid or slug; NULL refuses; changing the
   key is a versioned change.
4. **Cave anchor = the nearest-*preceding* function with a unique tail** (the *maximum*
   function-start offset below the cave in the same section), walking backward only if the
   nearest lacks a unique tail. Not the lowest-offset one — distance maximizes drift. The
   tail goes through the same mask/total-order/uniqueness machinery; the cave offset is
   stored **anchor-relative**, capacity as a *requirement* verified live, and the cave's
   per-build resolvability inherits the anchor's coverage.
5. **Divergence = integer components + cross-multiplied rational thresholds, never a float,
   never a division** (`a/b > t ⇔ a·t_den > t_num·b`). Store `nodes_only_in_A/B`,
   `edge_symdiff`, `neighborhood_symdiff`, `size_A/B`. CFG node identity across builds is a
   **build-invariant key** (position in deterministic reverse-postorder from entry, successor
   tie-break by decode order, plus masked-content hash) — never a VA. Symmetric differences
   run over **sorted** invariant keys / sorted `logical_id`s. Thresholds are **named,
   versioned parameters recorded in the basis**, not code constants. Output is a 3-way
   deterministic classification — **`1↔1 structural match` / `1↔N split-or-inlined
   candidate` / `diverged, no confident counterpart`** — not one boolean; a single
   `too_different` flag would collapse the split/inlined case STRATEGY and F07 require.

### Phase 0 — the minimal ordering fix set (makes the hookpack byte-reproducible today)
**D1–D7 landed** (`16f0823`, `a0db224`, `5225722`, `559dc46`); D8 and D9 below remain.
These are prerequisites for everything above, and for **divergence determinism, which
inherits the `logical_id` cascade's determinism**. Gate wording everywhere: "canonical
sorted row-set equality including `match.id`", never "byte-for-byte":
- **D1 `logical.py:39-64`** — the driving SELECT has no `ORDER BY` — and there are **two**
  SELECT branches (the `canon.DRM_EXCLUDED`-gated one and the ungated one); both need it.
  (`DRM_EXCLUDED` is an empty `set()` — a DRM mechanism with no data, which is also why the
  packed/DRM target class has no representation yet; see the matrix.) `logical_function.id`,
  `best_name`, `best_signature` and identity confidence are assigned in row order, and every
  downstream `logical_id` inherits it. Fix: `ORDER BY f.canon_key, f.binary_id, f.addr`;
  total tie-break in `rank` `(len, pri, bid)`; `:152` key `(-n_instr, binary_id, addr)`.
- **D2 `export_hookpack.py:71,74,85`** — three unordered SELECTs → pack array/object order;
  `:119` site-key **last-wins collision** when two logicals share `best_name`; `:26`
  `Counter.most_common` count-ties by insertion order. Fix: `ORDER BY id` / `ORDER BY
  i.binary_id, i.addr`; stable `max(items, key=(count, value))`; disambiguate collisions
  as `f"{key}__{lid}"`; `json.dumps(sort_keys=True)`.
- **D3 `propagate.py:157-209` `bind_identities`** — candidate SELECT unordered; sort on
  `conf` only; first-wins decides winner/loser and persists both to `identity` and `match`.
  **Ties are the common case, not the edge case:** `callgraph_propagate.py:18`
  `PROPAGATION_SCORE = 1.0` gives every propagated pair identical confidence, so large tie
  groups resolve by *query-plan order* into the first-wins race. Also `:167-170`
  `logical_members` is built from an unordered `SELECT` keyed `(logical_id, binary_id)`
  last-write-wins, and the schema's unique index is only `(binary_id, addr)`
  (`store.py:117`), so two addrs in one binary can share a `logical_id` and seed the
  conflict decision non-reproducibly. Fix: `ORDER BY m.dst_binary, m.dst_addr,
  i.logical_id, m.src_binary, m.src_addr` (and `ORDER BY logical_id, binary_id, addr` on
  `:169`); total sort key `(-conf, dst_binary, dst_addr, logical_id, src_binary, src_addr)`.
  **Recorded choice — dst-major, not src-major.** Either key is a total order and either
  makes the result reproducible, but they select *different winners* in the first-wins race
  and therefore produce different `identity` tables and different
  `logical_id_binary_conflict` demotions. Dst-major makes "which source claims this
  destination" the decided question — the thing the race actually resolves — rather than a
  side effect of scan order. This ordering is part of the **algorithm version** in the
  determinism basis; changing it is a versioned change, not a refactor. **Verdict (landed):** D1–D7 are in; the remaining risk is rowid-keyed tie-breaks (D8)
  and the rowid backfill (D9). (Int-keyed sets/dicts were never the issue — CPython doesn't
  randomize int hashing; the instability was SQL plan order + stable-sort ties.)
- **D4 `match_store.py:60-68,666,703`** — func SELECT unordered feeds the greedy cascade;
  `for b in cands` iterates a set; `scored.sort` ties on `(score, margin)` keep row order.
  Fix: `ORDER BY addr`; `sorted(cands)`; sort key `(-score, -margin, a, b)`; round persisted
  score/margin to 4 dp (`match_engine` already does; `match_store` doesn't — a last-ULP
  difference can flip the 0.62/0.70 verify gate).
- **D5 `match_engine.py:73-78` `cosine()`** — sums over a `set` of **string** keys →
  float accumulation order is `PYTHONHASHSEED`-dependent; `na`/`nb` also sum over
  `a.values()` in dict-insertion order. Fix: `for k in sorted(keys)` and sort both value
  sums.
- **D6 `callgraph_propagate.py:131`** — `dependencies` evidence list in `mapping` insertion
  order, persisted into `match.evidence`. Fix: `sorted(parents)`.
- Smaller: `_fuse_bsim` unordered SELECT + first-src-wins (`match_store.py:273-309`);
  `next(iter(set))` for the quarantine dst (`:466` → `min`); unsorted `glob` in
  `cross_place.py:167,194`; `run_pair` insert order → `match.id` (`propagate.py:71`);
  receipt `ok` array order (`ghidra_bulk.py:851` → `sorted`).
- **D7. Audit-and-fix the surfaces the determinism audit did not reach**, so no unaudited
  path can leak order into a persisted value: `ghidra_bulk.py` compile-queue row selection
  (the `rows` that feed the `ThreadPoolExecutor.map`) and `raw_image_path` resolution;
  `block_inline.inline_hits`; `correspondence.enrich_evidence`; `channel_confidence.py`;
  `canon.canonicalize`; `symbol_provenance.authentic_named_index` (returns a dict of lists
  in `funcs` order — inherits D4); and `store.py` `ensure_binary_columns`, whose
  `recovery_family='unclassified:' || id` backfill persists a value derived from row-id
  assignment order, written by whichever connection wins the lock, with failures swallowed. Same rule everywhere: any SELECT feeding a persisted or
  first-wins decision gets a total `ORDER BY`; any set/dict that reaches a hash or artifact
  is sorted first; any "best/preferred" pick has a total key ending in the actual bytes.
- **D8. Rowid tie-breaks.** `logical.py:48,60`, `propagate.py:168,209` and
  `export_hookpack.py:138,150,165` order and tie-break on `binary_id`/`id` (rowids); the
  harness pins `binary.id`, so build-ingest order is never perturbed. Fix per design
  decision 3: key on `binary.content_sha256`, never rowid or slug; NULL refuses.
- **D9. `store.py:293` backfills `recovery_family='unclassified:' || id`** — a value
  derived from rowid assignment order (the `:288-290` comment calls it safe; false once
  build order moves). Derive it from `content_sha256`; add `recovery_family` to the harness
  dump.

## Grounding in known-working practice

Every mechanism here stands on a strategy the RE / matching-decompilation community has
proven in the field, with that strategy's *documented* failure modes addressed as units
(Phase 10). Sources are primary docs and source code, fetched 2026-09-21; the community
consensus for portable signatures, reconstructed from them, is: **decode-derived operand
masks + module-wide uniqueness check + a size floor + a secondary discriminator for
identical bodies + library exclusion.**

| Mechanism | Proven strategy (how it actually works) | Documented failure modes | Plan units |
|---|---|---|---|
| **Portable function signatures** | *FLIRT*: first 32 bytes with relocated bytes wildcarded, then CRC16 past the first variant byte, then referenced names, then curation; drops functions under 4 bytes. *Ghidra FunctionID*: full/specific 64-bit body hashes (mnemonics + addressing modes, constants only when heuristically non-address), parent/child hashes to split identical bodies, an instruction-count threshold. *BSim*: data/control-flow feature vectors, constants/registers/types deliberately excluded, cosine similarity × a "meatiness" confidence. *BinDiff*: raw-byte hash → name hash → MD-index → prime signature → call-graph MD-index → string refs → address sequence. *Community sigscanning* (`makesig`, AlliedMods): wildcard every address/`DYNAMIC` operand and every `call/jmp rel32`, grow the pattern until `findBytes` over the **whole module** returns < 2 hits, else "could not find unique signature". | Prologue-only signatures collide (FLIRT needs CRC + names + humans on top). Small/generic/**library** functions collide across unrelated binaries — FLIRT, Lumina, BinDiff and BSim all exclude or de-weight them. Unmasked relocations break hashes (Ghidra #2792: same function, two ELF relocations, two FunctionID hashes). Uniqueness must be checked module-wide. Identical bodies with different names (templates, ICF) are a leaf collision resolvable only by neighbours. Packed images scan to nothing. | Decision 1–3, U4–U7b, U5b, U6, U6b; **gaps → U48 library exclusion, U49 identical-body rule, U50 packed gate, U51 anchor definition, U52 reloc-table flag** |
| **Cross-build matching + divergence** | *BinDiff*: global match then iterative expansion through callers/callees; similarity (25% edges, 15% blocks, 10% instructions, 50% MD-index) **× confidence** of the producing algorithm; output = matched + two *unmatched* lists; "only non-library functions are considered" for counts. *Diaphora*: dozens of heuristics incl. pseudo-code; best/partial/unreliable tiers; symbol porting. | The 1-to-1 assumption ("functions can be inlined, or split" — QBinDiff); library/CRT false positives; compiler-optimization drift wrecks diffing (BinTuner); imported-function anchoring fails on altered binaries; symbol porting is **destructive by default** (BinDiff's own warning). | U14–U17b, U39 (stronger than BinDiff's model — it has no split/inlined class); **gaps → U48 in `neighborhood_symdiff`, U53 producing-channel weight, toolchain identity in U54** |
| **Matching decompilation** | *objdiff*: target vs base relocatable objects, Patience-diff instruction alignment, relocations compared by symbol+addend never VA, penalties insert/delete 100 · reg 5 · imm 1, `match% = 1 − score/max`; report distinguishes fuzzy vs fully-matched vs linked. *decomp.me*: "the same compiler, assembler, and flags" — compilers are frozen exact ids. *decomp-permuter*: best when only regalloc remains. *dtk*: `Matching / NonMatching / Equivalent` per object, per-object exact `mw_version` + cflags. *reccmp*: annotation-driven PE/MSVC comparison, "effective match" normalizes addresses to symbols. | Exact toolchain per **object** is non-negotiable; regalloc/UB-dependent codegen; three match grades must never be collapsed (progress metrics corrupt); a score is a ranking heuristic, not byte-identity of the placed image; stochastic helpers (permuter seeds, m2c var naming) must be pinned. | STRATEGY stages 4–7 (program scope); **seam gap → U54 toolchain identity in the basis, U62 seam contract** |
| **Whole-image byte identity** | *dtk*: control-flow analysis + relocation rebuild → "fully shiftable objects", topological link order, whole-file `build.sha1` gate, `dol diff` localizes the first mismatch. *reccmp-roadmap*: symbol-location comparison to recover PE link order. *Ghidra delinker*: synthesized relocation tables ("relies on the accuracy of the Ghidra database"). *reproducible-builds*: stable inputs/outputs, `SOURCE_DATE_EPOCH`. PE spec: `TimeDateStamp`, `CheckSum`, alignment rules, lexically-sorted export names, `.reloc` unless `RELOCS_STRIPPED`. MSVC/lld `/Brepro`: timestamp = hash of the binary. | Linker version + link order dominate placement; padding/filler byte is toolchain-specific and must match; non-reproducible header fields (timestamp, checksum, debug directory); a missed relocation still links at original addresses and only a *shifted* rebuild exposes it; IAT order follows linker input order. | STRATEGY stage 8 (program scope); **seam gaps → U62: `binaries[].sha256` is the stage-8 identity; U58 filler/padding provenance shared with rebuild; U52 reloc-stripped images** |
| **Codecaves, detours, patching** | *Detours*: replace ≥5 bytes with a jump, copy whole instructions to a trampoline, `DetourUpdateThread` fixes IPs of threads inside the rewritten range; x64 trampolines within ±2 GiB. *MinHook* (source): length disassembler; rel8→rel32 widening; RIP-relative disp32 recomputation; refuses "can't alter instruction length in a branch", `ret` inside the width, loop-family branches; hot-patch only on **uniform** 0x00/0x90/0xCC runs on executable pages; `VirtualProtect(RWX)` → write → restore → `FlushInstructionCache`; freeze = suspend all other threads + IP fixup; `MH_ERROR_ALREADY_CREATED` per target. *safetyhook*: stops threads, fixes IPs, Zydis decoder. *Control Flow Guard*: gates **indirect** calls; failure terminates the process; `VirtualProtect`'d executable pages are valid targets by default unless `PAGE_TARGETS_NO_UPDATE`. | Target shorter than the jump; prologue instructions with relative operands; branches *into* the patch window; a thread executing inside the patched bytes; x64 reach; CFG-instrumented targets reached indirectly (vtable slots, cave stubs); mixed/non-executable "padding" is not a cave; anti-tamper scans detect resident payloads; second hook on one target; raw writes without saved originals are unrestorable. | §3, U12, U13, U13b, U23, U24; **gaps → U55 thread quiescence, U56 CFG, U57 cave ownership, U58 filler policy, U59 anti-tamper, U60 export-time detourability** |
| **ABI / parameter storage** | *Ghidra cspec*: prototype models assign the first fitting `<pentry>`; `extrapop`, `stackshift`, `killedbycall`, hidden-return when no entry fits ("extra hidden input parameter… pointer to where the function will store the return value"); the doc itself cautions inverse inference "may not be unique". *Function API*: `hasCustomVariableStorage()`, `getAutoParameterCount()` ("always 0 when custom parameter storage is used"), `getStackPurgeSize()`, `hasVarArgs()`. *MS x64*: RCX/RDX/R8/R9 + XMM0–3, 32-byte shadow, aggregates ≤64 bits by value in RAX else caller-allocated pointer as first arg **shifting the rest right**, varargs duplicated in int + float regs. *MS x86 `__thiscall`*: `this` in ECX, callee cleans; **varargs member functions are `__cdecl` with `this` pushed last**. Verification in the community = recompile and diff the call site. | Analyzer options change the recovered prototype (Ghidra #5531: headless `__fastcall` vs GUI `__stdcall`); custom storage hides the `this` auto-parameter; the thiscall/varargs collapse; hidden sret shifts argument positions; ≤64-bit aggregates by value; inference not unique → confidence required. | U8–U11, U18, U23; **gaps → U61 `this`/custom-storage normalization, U63 sret triple + x64 rules, U64 recompile-and-diff ABI verification, analyzer options in U54** |
| **Pipeline determinism** | *reproducible-builds*: file ordering, timestamps, randomness, paths, locale, archive metadata; `SOURCE_DATE_EPOCH`. *objdiff*: closed-form diff, no time/random/thread inputs. *Bazel*: content-addressed action cache keyed by input hashes. *dtk*: per-object toolchain pin + whole-artifact hash as the gate. | Ghidra decompiler export non-deterministic (#4332, reproduced by maintainers); headless vs GUI differ by analyzer defaults (#5531/#2639); the Decompiler-Parameter-ID analyzer has a **wall-clock timeout** — load-dependent prototypes; loader/relocation handling changes hashes (#2792); stochastic helpers. | Phase 0, U5c, U25, U28, U29, U6b; **gaps → U54 basis += analyzer option set, cspec/processor-spec/loader ids, timeout policy, toolchain identity, filler set, seeds; U65 timeout policy; U66 content-addressed receipts** |

Contradictions in the sources, and how the plan resolves them: (1) *Anchor on the
prologue* (AlliedMods, FLIRT) vs U6's interior preference — FLIRT only survives prologue
anchoring by layering CRC + names + humans; for an unattended pipeline the interior
window plus a uniqueness proof is the consistent choice, so the contradiction validates
U6. (2) *Unmasked hashing works* (Lumina's `md5` of function bytes) — only as a
same-build knowledge share; it is the counterexample to `hash_raw` as a cross-build
locator, consistent with decision 1. (3) *`TimeDateStamp` is a timestamp* (PE spec) vs a
hash (`/Brepro`; lld reverted the default because it "breaks AppCompat") — treat the field
as toolchain-policy-derived, never as recovered. (4) *CFG blocks caves* — narrower in the
doc: `VirtualProtect`'d executable pages are valid targets by default; the hazard is
`PAGE_TARGETS_NO_UPDATE` or an indirect call into a page never re-protected — U56
encodes the doc's version.

## Target artifact: `agentdecompile.hookpack/v2`

v1 cannot carry this. `agentdecompile.hookpack/v2` root: `format`, `basis` (the normative
object in the Determinism section), `pack_sha256` (U24), `corpus_manifest_hash`.
- **binaries[]**: `slug, content_sha256, image_base, arch, bits, format, endian, pointer_size,
  wchar_width, compiler_spec, this_kind, reloc_table_present, unpack_state, cfg_instrumented,
  basis_hash, toolchain`.
- **`entities[]` replaces `sites[]`** (kept only under `--format v1`), each with a `kind` from
  the entity catalog
  (`function | patch_point | immediate | call_site | global | singleton | struct | class_ctor
  | vtable | rtti | string | table | enum | jump_table | import | export | dispatch_table |
  vm_opcode_table | tls | unwind | section | resource | initializer | entry_loop | site_frame
  | site_regs | allocator | library_fn | inlined_region | integrity_check`) + `required`:
  ```
  { key: stable_key, previous_keys[], kind, required,
    shape{per kind},
    abi{convention, this_kind, args[{type,width,storage}],
        ret{type,width,storage,sret{allocator,ptr_storage,returned_in}},
        stack_cleanup, varargs, confidence, provenance},
    locators[] ordered, each {
      kind ∈ symbol | masked_window | anchor_rel | xref_from_function | data_xref |
             caller_callsite | callee_order | vtable_slot | pointer_chain |
             neighbour_position | structural | region | module_rva | section_offset,
      portable (false only for module_rva/section_offset), value, mask, region,
      uniqueness{scope: per_build_exec_region, hits, margin_min_over_builds},
      verify{expected_bytes | region_hash | shape},
      coverage[{build, status, reason}] },
    structural{mnemonic_seq_hash, cfg_mdindex, spp, margin},
    callers[{key, callsite_index}], callees[key…], neighbours{prev, next},
    instances[{build, addr, expected_bytes, resolved_by, status, detourable, reason}],
    status{build → rollup}, divergence{per kind} }
  ```
  Every ladder member names the locator kind it consumes (see the kind tags on Ladders A
  and C). The per-kind **shape** block is as before (struct → per-build field map + field
  correspondence; vtable → per-build slot map; table → element layout/count/stride;
  patch_point → operand layout + register/stack contract). Function-only consumers ignore
  unknown kinds.
- **Closed status set**, per member and per entity × build:
  `resolved(member) | pinned(member) | degraded(member, reason) | ambiguous | unresolved |
  contested`, rolled up by U30's rule; `observed_status` is separate.
- **caves[]**: `{ id, claim{pack_sha, cave_id, build_sha256}, anchor: locator, offset,
  capacity, arch, original_bytes, relocation_rules, restoration, candidates[] (U100),
  coverage[{build, status, capacity}] }` — U12 is the only producer.
- **Format bump:** `FORMAT` (`export_hookpack.py:32`) becomes v2 in the first unit emitting
  a v2-only key; until U23's refuse-on-unknown lands, v2 is emitted only behind
  `--format v2` (default v1; `RH/src/hooks/registry.cpp:336` matches v1 exactly, else the
  legacy parser). Consumers ignore unknown kinds and refuse unknown formats.

### Surface ownership (FI §2 rule)

Both frontends read one backend. The static 8080 workbench is the required surface for
every artifact this plan produces; the 5174 app renders the same objects with richer
drawing and is never the only place a field exists. Ownership: **review lane + U17
fields** → 8080 `wb-review` (`ReviewReact`, `workbench-app.js:907`) now; 5174 after a
Compare tab exists (REC N3) — not `Surfaces.tsx`, which is unmounted. **U90 readiness +
coverage-per-build** → the entity × build matrix inside the corpus-first view (8080
`wb-logical`; 5174 `Logical`), keyed by `stable_key`, not a separate report page.
**Ladder residue** (members tried, per-member reason, `contested` evidence pairs) → the
evidence rail for the selected entity on both surfaces. **Divergence report** → the same
Compare surface, per pair. Status glyphs: identity-edge state
(candidate/accepted/rejected/unresolved) and U30 locator state are two axes and are
never rolled into one badge; `observed_status` is a third. **Starvation is drawn, not
inferred:** the age of the oldest unreviewed review row, the oldest waiting lane and the
longest-running job against its deadline appear on both surfaces (risk register H1–H6;
U111). **Control (user, 2026-09-21; supersedes "one start/pause/resume control"):**
there is no Start button. Admission of eligible missing work begins on its own when a
project is opened, binaries are added, or prior work is resumed — reopening known
material still admits nothing that already has a receipt — and the single control is
pause/resume plus its scope, never start. Phase 14 holds the units.

## Implementation units (phased, ranked)

### Phase 1 — Close the exporter↔consumer asymmetry (exporter side; the consumer half is U23)
- **U1. Emit `image_base` + `sha256` + `arch`/`bits` per binary.** `export_hookpack.py:133`;
  data already in the `binary` row. Consumer already reads them (`registry.cpp:346,398`).
- **U2. Always carry per-instance `expected_bytes`** and a per-site instance-window list the
  resolver can try in turn; relax the all-builds-agree gate (`export_hookpack.py:113`).
- **U3. Emit site-`kind` + `required` + field `offset/size`.** Exporter change
  (`export_hookpack.py:120`); the *kind classification* input is engine policy → an L3
  data-pack/adapter, not core (R6). Consumer reads them (`registry.cpp:312,364,417`).
- **U1b. Adapter-key mapping + semantic-alias/overlay merge on the exporter side.**
  RUNTIME_REUSE names the gap: export keys (`best_name`/`canon_key`) "need explicit mapping
  to adapter keys (e.g. a script-VM run-script adapter key); overlay merging matches literal names, not
  semantic aliases," and today merging lives only in the runtime host (`registry.cpp:467-493`
  `merge_overlay` over a hand-authored per-build overlay file). Add an L3
  data-pack-driven `site_key → adapter_key` map and an alias table to the exporter so a
  site carries its adapter key and known aliases in the pack; make the merge deterministic
  (sorted alias lists, collision → explicit `__{lid}` disambiguation, never last-wins).

### Phase 2 — Portable signature core (the "find it across all builds" ask) — L1/L2
- **U4. Reloc/immediate-masked byte pattern** per function, computed over the **raw file
  image** by a **named, versioned decoder** — not from Ghidra's analysis references. There
  is no decoder revision to record today (`pyproject.toml` pins `pyghidra>=3.0.2` floating;
  no capstone/iced dependency; canonical's `decode_x86.py` is pattern matchers, not a
  length-disassembler). Decoder = one pure length-and-operand decoder library with Python and C++ bindings,
  pinned by version; U91 embeds the same library and revision. The analyzer's disassembler
  is evidence, never a mask input. Mask = decode-identified address operands ∪
  format relocation entries (design decision 1). The `features.py:185-192` operand loop is the
  integration point, but its *inputs* change to the decoder; store `func.mask_pattern`.
- **U5. `logical_signature` table** keyed by `logical_id`: consensus masked pattern +
  structural hash + **cross-build `find_unique` + coverage**; build beside `logical.py`
  (a new `corpus/signatures.py`), consume in `export_hookpack._preferred_signature`.
  Uniqueness per design decision 2; uncovered builds recompute hits==1 in the executable
  region live; packed margin advisory; coverage `uncovered`.
- **U6. Region-scoped, interior-anchored windows** (executable section only; prefer
  distinctive interior bytes over the prologue frame-size immediate). `export_hookpack.py:56`.
  Add a section-scoped, tail-anchored window primitive beside `unique_window` (`:56` is
  whole-file, entry-anchored).
- **U7. Rewire VA→offset to the correct mapper that already exists (one-import fix).**
  **Landed (`f935db7`):** `_file_offset` (`export_hookpack.py:82-90`) calls
  `mapper_for(image, load_base)`; the PE32-only duplicates are retired; remaining:
  `exact_corpus.py:121` still calls `pe_mapper` directly. Original finding, for the record:
  Three VA→offset implementations exist: the correct `exact_universal.mapper_for`
  (`:116-117`, dispatching `pe_mapper`/`elf_mapper`/`macho_mapper`; `pe_mapper:41-44` reads
  the optional-header magic and uses `<Q` ImageBase when `0x20B` — **PE32+ handled
  correctly**) and two broken PE32-only duplicates (`genproject.py:37-57`,
  `exact_corpus.py:24`, both reading a 4-byte ImageBase). `export_hookpack._file_offset:61-67`
  imports the broken one, so x64 windows are silently garbage. Fix: swap the import in
  `export_hookpack` (and retire the duplicates in `genproject`/`exact_corpus`,
  `recover_named_ghidra.py:513`). **The highest-leverage single edit in the plan — but
  necessary, not sufficient:** `pe_mapper` subtracts the *file-header* ImageBase, while
  `func.addr` is Ghidra's *loaded* address and `binary.image_base` (`store.py:31`) is stored
  but never consulted (`exact_universal.py:251` calls `va2off(addr)` directly). For PIE
  ELF, Mach-O, or any rebased import the swap alone still yields wrong offsets. The mapper
  must accept the load base and compute `off = va2off(addr - binary.image_base +
  format_base)`; add PIE ELF to the target matrix.
  **Coverage caveat (closed):** XBE landed with U7b (`exact_universal.py:174`; `mapper_for`
  `:200`).
- **U7b. XBE mapper + container detection (any `.xbe` build).** **Landed (`f935db7`)** —
  `xbe_mapper` at `exact_universal.py:174`; container detection remains open. Add `xbe_mapper`
  to `exact_universal.mapper_for` and XBE detection to `agentdecompile_recovery/containers/detect.py` /
  `registry.py` (the registry already hosts NDS, so the plug-in shape exists). XBE layout
  (all little-endian, header at file offset 0): magic `"XBEH"` @`0x000`; **base address**
  @`0x104`; size of headers @`0x108`; size of image @`0x10C`; **number of sections**
  @`0x11C`; **section-headers pointer (VA)** @`0x120`; entry point @`0x128` and kernel-thunk
  @`0x158` are **XOR-obfuscated** (retail vs debug keys — decode both, pick the one that
  lands inside the image; record which). Each 56-byte section header: flags @`+0x00`,
  **virtual address** @`+0x04`, virtual size @`+0x08`, **raw address** (file offset) @`+0x0C`,
  raw size @`+0x10`, name-pointer @`+0x14`, plus digest. `va2off(va)`: find the section
  with `vaddr ≤ va < vaddr + max(vsize, rsize)`, return `raw + (va − vaddr)` — the same
  contract as `pe_mapper`. Section flags give `r/w/x`, so the executable-region scope for
  U6/U12 comes for free. Mark the XOR-decoded entry/thunk as *derived*, never as a
  signature input. Add an XBE row to `targets.inspect_magic` (`"XBEH"` → format `xbe`,
  arch `x86`, bits `32`). Detour width for XBE is x86-32 — it selects the existing L2
  adapter; the engine adapter is the current engine's existing L3.
- **U5b. Anchor-relative locators + verification hashes (runtime locator family members
  b/c).** For each `logical_signature`, also emit (b) an **anchor-relative** descriptor —
  resolve a unique nearby **format-table** entry — import thunk / IAT slot, export, or
  string-table content — chosen by the same total order as U6, then a signed relative
  offset — for sites whose own bytes are not unique. Never a Ghidra-derived reference
  (`getReferencesFrom`). When a build has no exports and its imports are resolved only
  through a packed IAT, member (b) records *degraded* coverage for that build rather than
  falling back to analysis data; and (c) a **region content hash** over the masked window for post-resolve
  verification (the runtime refuses on mismatch). Coverage per member, sorted by slug.
- **U5c. Determinism basis in every pack + two-level verification (ships in order step 1,
  not Phase 2).** Emit the basis object (decoder revision + processor-spec hash, algorithm
  version, masking-rule version, threshold parameter set, sorted corpus-manifest hash) at
  the pack root. Then two gates, because one is blind to most defects:
  (a) **Export byte-diff** (`corpus.verify-determinism`): re-run the export on a temp copy
  of the store and byte-diff the packs. Cheap — but it only detects D2, since D1/D3–D6 run
  *upstream* of the store contents.
  (b) **Cascade determinism harness** (landed, `e47d387`; this wording is the gate): snapshot
  one extraction's fixture tables and run the cascade from the snapshot under three
  layouts: (i) canonical insert; (ii) fresh DB, rows inserted in a seeded shuffled order
  with fresh rowids, **and `binary` rows inserted in shuffled order so `binary.id`
  differs**; (iii) layout (ii) followed by `VACUUM; ANALYZE`. Compare `identity`, `match`
  (including `id`), `logical_function` and `recovery_family` as sorted canonical JSON
  row-sets against (i). Both (ii) and (iii) are required: with `ANALYZE` statistics the
  planner tends to serve unordered SELECTs from `ix_func_bin_addr`, which hides
  insertion-order defects; (ii) exposes them. Removing either layout is a versioned change
  to the gate. `FIXTURE_TABLES` gains the BSim vector table (U5d) and `runtime_claim`
  (U99); a missing-table skip fails the harness; `generate_fixture` emits a synthetic
  `content_sha256` per `binary` row (the fixture has no raw images, so `backfill.py:35-43`
  cannot). Needs no Ghidra re-run, so it does not collide with STRATEGY's never-re-analyze
  rule. A non-empty diff fails and names the first differing row.
- **U5d. Persist BSim vectors as a first-class identity channel (gap 6).** `bsim_eval.py`
  is eval-only and `_fuse_bsim` reads an optional external `bsim_hit` table; the CLI tree's
  `batch_bsim.py` only collects XML paths on disk. Persist the LSH vectors produced by
  `bsim_ops.generatesigs` into the store (a `func_bsim` table keyed `(binary_id, addr)`),
  and consume them in `match_store` as a cascade channel (still *behind* the cheaper
  channels per STRATEGY) with deterministic ordering (`ORDER BY src_addr, dst_addr`,
  sorted `by_src`). Vectors are identity-time evidence — they are producers of the
  locator family, never runtime resolvers.
- **U6b. Canonicalization layer for extents and blocks.** The audit found extents come
  from `f.getBody()` and blocks from `BasicBlockModel` (analysis-derived). Define every
  signature window as a **byte range over the raw file image anchored at a decode-stable
  point** (function entry from the symbol/export/reloc-derived entry set, or the
  identity-time accepted entry), with the window's extent bounded by decode + the format
  section table — never by Ghidra's function-body model. For CFG-structural signatures,
  derive block boundaries from a deterministic decode-driven flow walk (branch targets +
  fall-through) so the MD-index/RPO keys don't move when auto-analysis re-partitions.
  Keep Ghidra's model as *evidence* for identity; keep it out of the hash inputs.

### Phase 3 — ABI/param export for Lua (the "params/codecaves in Lua" ask) — L1 + L3
- **U8. Bridge the CLI tree's structured storage collector into the batch path.** The
  per-parameter storage collector is `[CLI] guide_function.py:7-18` (`storage_pieces` →
  `{size, register | stackOffset}`) and `:31-38` (`function_properties`: `customStorage`,
  `returnStorage`, per-parameter storage). `[CLI] _collectors.py:486-506` carries
  `{name,type,ordinal}` only and `:236` stringifies a local-symbol representative; neither
  is an ABI source (`[CLI] getfunction.py:185-227` is only the `set_storage` JSON schema). The batch recovery tree drops it at extraction (`features.py:131`
  records type names only) and the exporter drops it again (`export_hookpack.py:120`).
  Fix: persist the `storage_pieces` output in `func_param(binary_id, addr, ordinal, name,
  type, pieces_json)` plus `func.return_storage`, and reuse the `function_properties`-shaped
  output as the exporter's ABI source. **Architecture-agnostic — carries
  x64 register storage for free**, bypassing the 32-bit `ret imm` / `@N` heuristics.
- **U9. Persist `varargs`/`no_return`** (recovered at `features.py:135`, add columns).
- **U10. Stop collapsing thiscall/fastcall** (`propagate_conventions.py:13`); keep raw
  convention; surface `class_source`/`n_source` confidence.
- **U11. Structured ABI block in the pack** from U8/U9 data (`export_hookpack.py:120`,
  reusing `canon.split_signature`); **export vtable/inheritance** from `rtti_recover.py`
  (present in both trees at `agentdecompile_recovery/rtti_recover.py`) via the `vtable` table **whose DDL U33 owns** (U11 emits only what U33 defines, recording
  `abi_walk=format-derived` in provenance until U79 lands) and
  `sites[].kind = vtable` entries with slot index.
- **U11b. Typed struct fields for marshalling.** `export_types.py:71-89` renders every
  pointer as `void *` and every nested composite as a byte array — byte-accurate offsets,
  lossy semantics, useless for typed field access from Lua. Emit the real pointee type and
  nested composite reference (with a stable name) alongside the offset/size, keeping the
  existing `_sizecheck_` assertion as the determinism guard on layout.

### Phase 4 — Codecave discovery + Lua patch path (greenfield top gap) — L1 core + L2/L3 + the runtime host
- **U12. Cave discovery writes into `hookpack/v2` `caves[]` — no separate artifact, no
  second verb** (the one exporter verb is `export-hookpack`, `cli.py:195`; advertise via
  `corpus/dashboard/actions/introspect.py` — not the stale root `introspect.py`). Enumerate
  ≥N-byte uniform-filler runs in executable sections from the raw image. **Cave candidacy is
  validated, not assumed** (a run of filler bytes is not proof of unused space): a candidate
  must be (i) not covered by any instruction range from the **U4 decoder** — never the
  analyzer's function-body model (the prior pass recorded corpus function ends "a few bytes
  short", which reports a false cave inside the previous function's tail); (ii) not a
  relocation target, data-reference target, or PC-relative load target (the literal-pool
  case; ARM stays refused until a per-arch guard (iv) exists); (iii) bounded by two
  U4-decoded function ends. **One anchor rule, decode-derived, never a Ghidra naming predicate**
  (`non-FUN_` is analysis-derived and empty on a stripped image): anchor = the function with
  the greatest decoded entry offset below the cave in the same section whose tail passes the
  U6 uniqueness-with-margin test, walking backward only if the nearest fails; stripped
  images use the identity-time accepted entry set. Emit the cave-plan template; group across
  builds by the `logical_entity` machinery; record per-build capacity coverage.
- **U13. A cave helper in the runtime host's Lua API** — capacity-checked writes + restoration bookkeeping,
  reusing the detour engine's length-disassembler/relocation/restore (`trampoline.hpp:71,147`).
  the runtime host is a separate repo (the sibling runtime-host repo);
  land it there as its own change. Depends on U23's mask-aware `find_unique(value, mask)`:
  the cave anchor is a masked tail window (design decision 4) and
  `RH/src/api/memory.cpp:697-706` is all-`0xFF` today, so it cannot evaluate it — U23/U46
  land before this unit (see the order).
- **U13b. Arch-gate the the runtime host runtime so it can consume 64-bit / non-x86 packs.**
  `thiscall.hpp:75` `#error x86-32 only` and `trampoline.hpp:46` `static_assert(sizeof(void*)
  == 4)` hard-block any 64-bit target (any 64-bit target). Replace with the L2
  architecture adapter: detour width, relocation model and relative-branch reach selected
  by the pack's `arch`/`bits`, with the x86-32 five-byte detour as the first adapter and an
  x86-64 adapter (14-byte absolute jump or RIP-relative + trampoline within ±2 GiB) as the
  second. Refuse packs whose `arch` has no adapter, loudly. ARM stays refused until a cave
  policy handles literal pools in `.text` (`codecaves.md:45`). x86-64 L2 rule: in the
  displaced window, `disp32` RIP-relative memory operands are recomputed iff the trampoline
  is within ±2 GiB of the original (U101 near-alloc); `jmp/call [rip+disp32]` are rewritten
  to an absolute island; any other RIP-relative form, or a trampoline out of reach, is
  `Unrelocatable`.

### Phase 5 — Cross-build divergence (the "too different, display it" ask) — L1
- **U14. `corpus/divergence.py`** — a pure, deterministic metric. **Hard dependency:
  U4 + U6b** (node keys are masked block hashes over U6b's decode-driven partition). Node
  key `k(n) = masked_block_hash(n)`; `(in_deg, out_deg)` is only a pairing tie-break among
  equal hashes; RPO position (successor tie-break by decode order) orders equal keys within
  one build only and never enters cross-build equality. Let `K_A, K_B` be the sorted
  **multisets** of keys and `E_X = {(k(u), k(v))}` the edge multisets; `size_A=|K_A|`,
  `size_B=|K_B|`, `nodes_only_in_A=|K_A∖K_B|`, `nodes_only_in_B=|K_B∖K_A|`,
  `edge_symdiff=|E_A△E_B|` (multiset differences). Neighbourhood `N(f)` = depth-1
  `{(key(g), caller)} ∪ {(key(g), callee)}` over `stable_key`, excluding U48 library
  entities; unbound neighbours are counted in `nbr_unbound_A/B` and stay out of the
  symdiff; `neighborhood_symdiff=|N_A△N_B|`, `nbr_A=|N_A|`, `nbr_B=|N_B|`. Emits **integer
  components** only (generalizing the callee-jaccard at `match_engine.py:211`) — no float,
  no division. Classification with versioned rationals `d=(d_num,d_den)`, `u`, `s`: `1↔1`
  iff `(nodes_only_in_A+nodes_only_in_B)·d_den ≤ d_num·(size_A+size_B)` and
  `neighborhood_symdiff·u_den ≤ u_num·(nbr_A+nbr_B)`; `split-or-inlined` iff not `1↔1`
  and (`block_inline` yields a containment hit for the pair or
  `min(nodes_only_in_A,nodes_only_in_B)·s_den ≤ s_num·min(size_A,size_B)`), direction
  recorded as a field; `diverged` otherwise. Swapping A/B swaps the `_A/_B` components and
  the direction field; the class is unchanged. Thresholds are per pair class, like
  `PAIR_POLICY`.
- **U15. Classify + store + gate:** evaluate thresholds by cross-multiplication against
  **recorded, versioned parameters** into a 3-way classification — `1↔1 structural match` /
  `1↔N split-or-inlined candidate` / `diverged, no confident counterpart` — and persist the
  components on `match`. **Do not add a parallel taxonomy:** map the class onto the
  *existing* `match.relation` vocabulary (`correspondence.py:13` `RELATION_KINDS` = eight
  kinds: `one_to_one, clone, inline, thunk, split, fold, region, unroll`) — `1↔1` →
  `one_to_one`; `split-or-inlined` → `inline`/`split`/`fold`/`unroll`; `diverged` →
  `region` (the kind STRATEGY mandates: "match regions—not forced 1↔1"), which today has no
  producer. `bind_identities` already admits only `relation='one_to_one'`
  (`propagate.py:163`), so the gate is mostly "populate `relation` truthfully". In `match_store.py:707` a pass that
  classifies as split/inlined or diverged emits `status="review"` with the class as the
  reason (never a silent `auto`); `propagate.persist_status` bars those classes from `auto`. Admit `region` to
  `OPERATIONAL_RELATION_KINDS` (`correspondence.py:17`; `enrich_evidence` raises on it today)
  with a producer note; add `split, fold, unroll, clone` to `PINNED_KINDS` (`propagate.py:11`);
  identity binding stays gated on `relation == 'one_to_one'` (`:118`).
  Depends on the **Phase 0 cascade-determinism fixes (D1, D3, D4)** — neighborhood symdiff
  over `logical_id` inherits `bind_identities`' determinism.
- **U16. Per-`logical_id` rollup** at `bind_identities` (`propagate.py:215`) — "structural
  spread across N builds."
- **U17. Display.** `review_queue_json` (`pages.py:771-772` today: no `relation`, names
  hard-coded `""`, `ORDER BY score DESC LIMIT ?` with no tie-break) returns per row:
  `match_id, run, src_binary_slug, src_addr, src_name, dst_binary_slug, dst_addr, dst_name,
  score, status, relation, divergence_class, components{nodes_only_in_A, nodes_only_in_B,
  edge_symdiff, neighborhood_symdiff, size_A, size_B, nbr_A, nbr_B}, thresholds_version,
  producing_channel, channel_weight, reason`; total order `status, relation, score DESC,
  src_binary_slug, src_addr, dst_binary_slug, dst_addr`. A **Divergence** column in 8080
  `ReviewReact` (`workbench-app.js:907-929`); the 5174 shell gains the same columns when
  REC N3 lands (U109). `Surfaces.tsx` is unmounted and is not the target (U106).
- **(U0 withdrawn.)** `func.block_hashes` is already computed and persisted; what is wrong
  is its *basis* (Ghidra `BasicBlockModel` blocks). U6b re-derives block hashes from the
  decode-driven flow walk; U22's backfill repopulates the column under the new basis, which
  is what actually lights up the split/inline/fold detector deterministically.
- **U17b. Gate the CLI `match-function` tool with the same classification.** The only
  cross-build neighborhood comparison in either tree is `[CLI] getfunction.py:1212-1231`
  `_call_graph_overlap` — source-normalized recall (`shared/(source_callers+callees)`),
  name-keyed, ephemeral, and used **only as a tiebreaker** (`:1333`); the sole filter is the
  name/signature score (`:1329`). A name-matched candidate with `callGraphOverlap == 0.0` is
  accepted at `similarityScore: 1.0`, then **propagated (rename/prototype/comments) and
  checked in to the shared Ghidra project** (`:1306-1320, 1373+`). That is the forced-match
  failure in the tree that *writes*. Symmetrize it (missing/extra, not recall), route it
  through U14/U15's classification, and refuse to propagate `split-or-inlined`/`diverged`
  candidates without review. `_call_graph_overlap` is the starting point to reuse, not a
  second implementation — but reuse only its caller/callee collection (it divides at
  `:1230` and is first-wins on strict `>` at `:1333`); compute U14's integer components
  over names as keys — no ratio, no float; candidate order `(score desc, class rank, name)`.

### Phase 6 — Genericity hardening (the "any game" ask) — L2/L3 adapters
- **U18. One ABI adapter** consolidating the 4 MSVC-x86 copies (`ghidra_bulk.fix_thiscall`,
  `high_emit._thiscall_to_fastcall`, `ctxtypes.py:98`, `genproject.symbol_for/write_prompt`);
  selected by target profile. Highest-leverage 64-bit unlock.
- **U19. Compiler/toolchain profile** as a target-selected object (promote `TOOLCHAIN_SCRIPTS`
  + `COMPILER_PROFILES`; add GCC/clang/x64/ARM; drop the Wine/MSVC-only default in
  `ghidra_bulk._find_compiler`).
- **U19a. Data-pack registry.** One loader for L3 packs: root path from config, `pack.json`
  (`schema_version, engine_class, arch_class, entries`), sorted discovery, content hash
  recorded in the basis (`data_packs[]`). An unknown engine plugs in by dropping a pack;
  core never enumerates engines. Acceptance: a fixture pack loads; removing it yields
  `missing_adapter`, never a default.
- **U20. Remove `arch='x86' AND bits=32` SQL gates** (`recover_named_ghidra.py:99`,
  `permuter_harness.py:786`) → profile-driven filters. Relax `elf_target.is_elf_i386` to
  accept x86_64 ELF (a one-check win for any 64-bit ELF sibling build).
- **U21. Purge every product, binary, and project name from AgentDecompile — code, docs,
  comments, labels, defaults, and data — and enforce it.** Known code offenders: module-level
  hardcoded corpus paths at `text_permuter_watch.py:33-40`, `dashboard/byte_parity.py:20`,
  `dashboard/panels/crossmatch.py:112` (a product-named signature-DB path),
  `dashboard/workflow.py:228` (a product-named data-pack filename); cosmetic labels in
  `corpus_report.py`, `dashboard/panels/binaries.py:94` (`GAME_LABEL`), and docstrings in
  `recovery_orchestrator.py`, `consolidate_corpus.py`, `kx_cli.py`, `whole_image_relink.py`;
  legacy product-prefixed marker aliases in `source_claims.py:22-25` / `verify_packages.py:27`.
  Everything product-specific moves to an external L3 data pack keyed by build profile.
  **Docs are in scope too:** the canonical `STRATEGY.md`, `FRONTEND_INTENT.md`,
  `RUNTIME_REUSE.md`, `CONCEPTS.md` and the 2026-09-20 dashboard-design docs name specific
  products, binaries, and the runtime repo — rewrite them by class. **Enforcement:** extend
  `scripts/check-anonymization.sh` (already the CI step at `test-unit.yml:39-40`; fails
  today on 34 files): pattern moved to an env-pointed file outside the repo, `docs/` added
  to the scan set, the `docs/plans/**` exclusion dropped, token class widened to
  product/binary/project names — so the rule cannot be satisfied by hiding the names in the
  linter. Split into three units, in this order:
- **U21c. Gate.** The extended script ratchets against a recorded baseline, then zero.
- **U21a. Scrub `src/`.** 57 files; 8 file renames with import shims; the `db.py` default
  path; the exporter docstring.
- **U21b. Rewrite docs by class.** 49 files. Acceptance for the three: the gate returns 0
  over `src/` and `docs/`.

### Phase 7 — Lifecycle, safety, and verification (gap pass)
Units that earlier phases implied but never named. Without these the plan is not honestly
implementation-ready.
- **U22. Schema migration, versioning, and backfill.** New tables/columns (`func_param`,
  `logical_signature`, `func_bsim`, `vtable`, `match.divergence` + components,
  `func.mask_pattern`, re-based `func.block_hashes`). **Landed at `f5f6a88`:** `PRAGMA user_version` + a `schema_migration` ledger, strict
  migrations (any error raises), lock-tolerant data backfill (`store.py:291-298` keeps the
  lock/readonly tolerance for the concurrent-watcher case), and the `corpus.backfill` frame.
  **Remaining:** the ledger owns every DDL site (`store.py`, `db.py` until U82,
  `export_types.py`, `propagate_types.py`, `stabs_link.py`, `decompile.py`); a per-table
  per-binary delete registry so `remove_binary` (`store.py:209`) removes every per-binary
  row; migration 2 adds `binary.basis_hash`, `decoder_revision`, `analyzer_version` and
  makes `content_sha256` a cascade precondition. **Backfill is a raw-image re-extraction pass, and it must be scheduled and
  costed:** masked patterns, decode-based block hashes, and storage are computable from
  *existing* Ghidra state + the raw image in a read-only pass (no re-analysis — STRATEGY
  holds), but over the full corpus it is a real job: a cataloged, resumable, receipted verb
  (`corpus.backfill-signatures`). **Pre-fix identity data is not grandfathered silently:**
  `identity`/`logical_function` rows produced under the pre-D1/D3 nondeterministic cascade
  are, by this plan's own verdict, not reproducible — re-baseline them via U25 on the first
  run under the new basis and record the supersession.
- **U23. Runtime-host consumption of pack v2 + version negotiation (this is real C++).**
  Today `registry.cpp:336` accepts only the exact string `agentdecompile.hookpack/v1`; any
  other `format` **silently falls through to the legacy address-table parser** (`:398`),
  and nothing parses locator families, ABI blocks, caves, coverage, or the basis. Also the
  resolver's `find_unique` (`memory.cpp:697-706`) uses an all-`0xFF` mask — **it cannot
  evaluate a masked window at all**; only the Lua-facing `findsig` parses wildcards. So the
  plan's *primary* runtime locator is unusable by the pack loader until this unit lands. Add:
  a **mask-aware `find_unique(value, mask)`** with the uniqueness check; a v2 loader that
  refuses unknown formats loudly (never falls through); v2 detection by `format`; signature-family **try-in-turn**
  resolution (masked window → anchor-relative → verify hash; refuse if the verify hash
  mismatches); cave-plan resolution (locate anchor, apply relative offset, **verify actual
  capacity and expected original bytes live**, refuse on shortfall); ABI-descriptor-driven
  marshalling replacing hand-written per-site adapters, gated by `abi.confidence` (refuse
  low-confidence/derived ABIs for writes). v1 packs keep loading unchanged, and the exporter
  gains a `--format v1|v2` switch so existing consumers keep working through the
  transition. This is the other half of the contract; the exporter side alone delivers
  nothing runnable.
- **U24. Pack integrity.** Packs drive code patching, so a tampered or stale pack is a
  code-execution hazard. Emit a pack-level sha256 over canonical bytes, per-site expected
  originals (already partly there), and the basis object; the consumer refuses a pack whose
  hash mismatches its manifest, whose basis it does not recognize, or whose target
  `sha256` does not match the loaded image. Optional detached signature; never optional
  hash check.
- **U25. Re-baseline procedure when the determinism basis changes.** A decoder/Ghidra
  upgrade or a masking-rule/threshold change legitimately changes every signature. Rule:
  never silently mix bases in one store. On basis change, run a full deterministic
  re-export into a *new* pack version, byte-diff against the prior pack, record the
  supersession (old basis → new basis, per-site changes) as a receipt, and keep the prior
  pack loadable. Divergence classifications are re-evaluated against the recorded threshold
  parameters of the *new* basis and the delta reported, not overwritten.
- **U26. Signature ⇄ identity conflict rule.** When a runtime-resolved site (by locator)
  disagrees with the identity-bound `logical_id` for that build/address, or two logical
  functions' locators resolve to the same site, **never auto-rebind** (bytes are not
  identity — STRATEGY). Emit `identity_locator_conflict` with both claims and their
  evidence into the review queue; the pack marks the site `contested` for that build. Intra-entity rule: two members of one
  entity resolving to different addresses on one build → `contested` with both members'
  evidence; no member outranks another by ladder position. Members after the first hit run
  in verify mode and may confirm or contest, never replace.
- **U27. Stripped and symbol-poor builds.** Name/symbol-keyed pieces (canon keys, the CLI
  `match-function` overlap, anchor-by-symbol) degrade to empty on stripped images. The
  locator family must still resolve from masked bytes and import/string anchors; coverage
  records *which member* resolved per build; identity-time evidence for stripped builds
  leans on the byte/structural channels by design. No unit may assume names exist.
- **U28. Verification and test plan** (the no-tests guard is lifted). (a) **Determinism
  CI:** export twice from a temp copy of a fixture store under an identical basis and
  byte-diff (U5c's verb, wired into CI). (b) **Mapper round-trips** on synthetic headers
  for every format the matrix claims (PE32, PE32+, ELF32/64, Mach-O, XBE): known
  VA → expected offset, including section-boundary and out-of-image cases. (c) **Masking
  property tests:** two synthetic images differing only in relocated/relative operands
  yield identical masked patterns; differing in a literal immediate yield different ones.
  (d) **Divergence metric tests:** symmetric, integer-only, order-independent under node
  relabeling; the 3-way classification is stable under `PYTHONHASHSEED` sweeps. (e)
  **Cascade determinism:** the U5c(b) harness under all three layouts, including the
  build-order shuffle (o), comparing `identity`, `match` (incl. `id`), `logical_function`
  and `recovery_family` as sorted canonical row-sets — the D1/D3/D4/D8 acceptance.
  (f) **Cave discovery:** on a fixture image, discovered caves are identical across runs
  and every anchor's uniqueness claim holds against the whole executable region.
  (g) **ABI (Phase 3):** ABI-block schema validation + U64 recompile-and-diff on a fixture.
  (h) **Entities (Phase 8):** entity pack round-trip and `logical_entity` migration
  idempotence. (i) **Data locators (Phase 9):** a synthetic image with known roots; each
  family member disabled in turn; the expected member resolves and total failure yields
  a structured `unresolved`. (j) **Host (U23):** v1/v2 negotiation and refuse-on-unknown-
  format. (k) **Write journal (U73/U80):** rollback round-trip. (l) **Bundle (Phase 12):**
  U88's generated module passes U47's lint and resolves every fixture entity; U90's JSON
  validates against `readiness/v1`. (m) **Ladders (Phase 13):** on a fixture pair, disable
  the masked window and confirm each ladder member resolves in order.
  (n) **Divergence fixtures:** an injected inlined pair, split pair and diverged pair each
  classify to their class, land as `status='review'`, and `match-function` refuses to
  propagate them. (o) **Build-order shuffle** in (e): `binary` rows inserted in shuffled
  order with fresh ids. (p) **Key-stability run:** fixture + one added build, then
  remove/re-add; every `stable_key` unchanged. (q) **Name gate:**
  `scripts/check-anonymization.sh` returns 0 over `src/` and `docs/`. (r) **Attestation:**
  receipts from the real corpus (U28x) are compared each loop iteration; a regression in
  any verb blocks the wave. **U28 holds cross-cutting gates only; every other unit names
  its acceptance test in its own bullet.**
- **U28x. Inline-CLI attestation against the real corpus** (`corpus attest`, cataloged
  read-only). Runs a declared set of corpus verbs against a **copy-on-write temp copy** of
  a real store — never the live file — each under a **per-verb deadline**: a verb that
  overruns is reported as `hang` with the verb name and elapsed time, never waited on
  (risk register H2/H4). Emits sorted JSON receipts, one per verb, with build slugs
  **hashed** so no product token can reach a receipt, into a receipts directory outside
  the repo; diffs against the previous attestation. Exit codes: 0 same, 3 changed, 4 hang
  or failure. Acceptance: on a synthetic two-build store the verb produces byte-identical
  receipts twice and reports a change (exit 3) after one row is edited; a verb that
  sleeps past its deadline is reported as `hang` (exit 4).
- **U29. Concurrency × determinism.** The companion recommendations doc widens
  parallelism (per-environment compile pools, laned worker cap, parallel pairwise
  compare). Every such change must keep persisted outputs independent of thread timing:
  collect results by **submission index** (`ThreadPoolExecutor.map`, already the pattern —
  never `as_completed` into a persisted order), and serialize all persisted writes through
  the single deterministic commit path with the total orders from Phase 0. Add this as an
  acceptance check on each concurrency change. **Specifically:** the companion doc's C4
  (parallelize `run_pair` inside `bind_store_cascade`) would make `match.id` race-dependent
  — the very defect Phase 0 names (`propagate.py:71`). C4 is **barred** until it collects
  results and inserts in a sorted total order (or assigns deterministic ids).
  **Catalog flags (grill 6):** `backfill` → `mutating`, `long_running`,
  `identity_scope="database"` (it rewrites the D8 tie-break key); `export-bundle` /
  `export-hookpack` → output-tree scoped; `verify-determinism` → read-only on temp
  copies; `attest` (U28x) → read-only temp copy. The dashboard's admission loop
  (`jobs.py:363-386`) must see these before the design's pause-drain can be truthful —
  risk register H5 (admission cannot drain what it cannot see) and H6 (lane starvation
  at the acceptance point). U104 lands the flags.
- **Note on the design mockup.** The interactive frontend mockup produced in this session
  uses illustrative example build and function names. It lives outside the repo; if any
  part of it is ever brought into AgentDecompile, genericize its sample data first — the
  no-product-names rule (U21) applies to it too.

### Phase 8 — Entity coverage beyond functions (the memory-mod / injection substrate)
One unit per entity family from the catalog. All reuse the function machinery
(cascade, locator family, coverage, divergence, determinism basis); none introduce a
second identity system.
- **U30. `entities[]` in pack v2 + `logical_entity` store — THE single identity schema.**
  Ownership rule for every later unit: `logical_entity(kind, …)` is the one logical table
  and `identity` gains a `kind` column; U41's `logical_data`/`data_identity` and U32's
  `logical_struct`/`struct_instance` are **`kind` partitions (or views) of these two
  tables, never parallel tables**. Generalize `logical_function`
  → a `logical_entity(kind, …)` table (functions remain a kind) with per-kind shape and
  per-build instances; the exporter emits `entities[]`; `kind` is the dispatch key for the
  consumer. Deterministic ids per Phase 0 rules. `identity` PK → `(binary_id, kind, addr)`;
  `ux_identity_bin_addr` → `ux_identity_bin_kind_addr` (`store.py:117,120`; a `patch_point`
  at instruction 0 shares its function's address). `logical.build()` (`logical.py:32-33`
  wipes all of `identity` today) and every deleter scope to `WHERE kind='function'`; each
  kind has its own builder. `logical_entity.stable_key TEXT UNIQUE NOT NULL` is a pure
  function of the entity's own members: function → authentic `canon_key`, else sha256 of the
  sorted multiset of members' U4 masked-body hashes; struct → donor name else
  this-fingerprint hash; vtable → owning struct key; global/string → content hash else
  `(function key, instr_index, operand_slot)`; slot → `(vtable key, method key)`. Ordinal
  ids never leave the store; pack keys are `stable_key`, never `__{lid}`; a key changed by a
  joining build is kept in `previous_keys[]`. **U30 owns the closed status set and its
  rollup** — one function every emitter and report calls. Per entity × build: (i) two
  verified members disagree, or locator vs identity → `contested`; (ii) else nothing
  resolved-and-verified → `ambiguous` if any member returned an indistinguishable candidate
  set, else `unresolved`; (iii) else the first member in family order that resolved and
  verified → `resolved(member)`, `degraded(member, reason)` under a weaker precondition,
  `pinned(member)` for `module_rva`/`section_offset` (`portable:false`). Display order only,
  never a rollup: contested, unresolved, ambiguous, pinned, degraded, resolved. Runtime
  observations (U68/U99) go to a separate `observed_status` and never overwrite pack status.
- **U31. Data-entity identity via the xref-from-identified-code cascade** (globals,
  singletons, strings, constants, tables). Cheap-first: symbols/debug info → **xref from
  an identified function** (function logical id + decode-stable instruction index + operand
  slot → a deterministic data locator) → content hash (strings, constant pools) → data-
  section masked adjacency. Persist `logical_data` instances with the referencing-site
  provenance. Uniqueness/margin and coverage exactly as for code.
- **Where structs stand today (struct audit).** Types are **per-binary only**:
  `ghidra_type` is keyed `(binary_id, name, kind)` with one packed-C text blob, no field
  rows (`export_types.py:15-23`). STRATEGY's "structures/types merge across builds per
  field" is **unimplemented for structs** — `propagate.py` never references
  `ghidra_type`/`stabs_type`; `cross_place.py` moves `.c` files only. The sole cross-build
  type mechanism, `propagate_types.py`, is name-keyed, whole-definition, **fill-empty-only
  and unidirectional** (`:58-77`, `already_native; continue` at `:68-70`) — useless on
  stripped builds and never improves an existing layout. `export_types.emit_struct` renders
  pointers as `void *` (`:77-78`), nested composites/arrays as byte arrays (`:87-88,123`),
  enums as `int` regardless of width, **collapses unions** (`:107`) and **silently drops
  bitfields** (`if off < cursor: continue`, `:113`); `#pragma pack(1)` erases real
  alignment. Vtable slot addresses, base-class offsets and inheritance are not persisted
  (`rtti_recover.py:20-33` dataclasses → JSON receipts only). STABS `=s` field bodies
  **with bit offsets** are stored verbatim and unparsed in `stabs_type.stab`
  (`stabs_link.py:81-115`). No structured field-access evidence exists:
  `high_emit.TokenFact.field_offset` is declared (`:37`) but **never populated**
  (`_clang_token_fact:381-420`), `_fields_from_program` (`:466-478`) flattens every struct
  into one colliding `offset → name` dict, and `decompile.py:75-110` keeps only
  `n_field/n_deref/n_index` counts — but the raw material is there: decompiled C is
  persisted (`decompile_text.py`, `ingest_ghidra_knowledge.py`) and `ghidra_bulk.py`
  already regex-parses field-ref shapes (`FIELD_NAME_RE` `:297`, `fix_field_names`
  `:308-320`, `->`/`.` chains `:378-390,513-530`). **Correction:** `[CLI] getfunction.py`
  has no field refs (only a `stackOffset` schema string, `:226`); the evidence path is
  `high_emit.py` + stored C, not the get-function tool.
- **U32a. Field rows, not C blobs (prerequisite for every struct unit).** Add
  `ghidra_field(binary_id, type_name, ordinal, offset, size, name, dt_kind, pointee_type,
  element_type, array_count, bit_offset, bit_size, comment)` beside `ghidra_type`; extend
  `export_types.export` (`:186-208`) to emit rows from `dt.getComponents()` including
  `BitFieldDataType`, `Pointer.getDataType()`, `Array.getElementType()/getNumElements()`
  and union members. Fix the `:113` bitfield drop and `:107` union collapse; record real
  alignment. Keep `emit_struct` + `_sizecheck_` as the layout guard.
- **U32b. Parse STABS field bodies** (new `corpus/stabs_fields.py`, fed from
  `stabs_type.stab`) — the cheapest *true* per-field map including bit offsets/sizes for
  any build that carries debug info; those builds become the **name/layout donors**.
- **U32c. Field-access fingerprint extractor.** Two paths, both deterministic: (a)
  **offline** over stored decompiled C using the `ghidra_bulk.py` shapes plus
  `readability_rewrite.py:183-191` `_N_M_` (offset,size) sub-access views — no Ghidra
  boot; (b) **live** — extend `high_emit._pcode_from_high` (`:425-463`) to keep
  `PTRSUB/PTRADD/LOAD/STORE` with `(base HighVariable type, offset, size, r/w)`, populate
  `TokenFact.field_offset` from `ClangFieldToken.getOffset()`, and replace
  `_fields_from_program` with a per-struct map. Persist
  `field_access(binary_id, func_addr, struct_name|null, offset, size, kind)`; aggregate per
  struct per build into the sorted multiset. Join through `identity.logical_id` so the
  **same logical function's accesses on two builds yield field pairs even with no names**.
- **U32. `logical_struct` + per-build field map + correspondence (U30 applied to structs).**
  Tables `logical_struct(id, canon_name, …)`, `struct_instance(logical_id, binary_id,
  type_name, size)`, `field_corr(logical_id, field_key, binary_id, offset, size, type,
  state)` with states `same / shifted / resized / retyped / added / removed / reordered /
  ambiguous`. Build beside `logical.py:31 build()`; seed identity from (a) exact/canon
  name (`canon.strip_templates`, `canon.py:35`), (b) `propagate_types.plan_adoptions`
  donors (`:54-63`) reinterpreted as *instances*, not copies, (c) STABS/RTTI names, (d)
  **name-free seed:** cluster identity-bound functions by this/param-0 access multiset
  (U32c); a cluster present on ≥2 builds seeds a `logical_struct` with `canon_name=null`.
  `field_corr.field_key` = donor field name when any build has one, else `f@0x<offset>` on
  the recorded reference build (`logical_struct.ref_binary_id`).
  Replace `apply_adoptions`' fill-empty with a **per-field precedence merge** (the
  bidirectional fusion STRATEGY specifies but code never implemented). Reading a field
  "by name" on any build resolves through this map. Extends U11b.
- **U32d. Stripped-build struct matching.** Candidates for logical struct S on build B:
  the functions bound to S's accessor functions via `identity` (`propagate.py:142
  bind_identities`) → their `this`/param-0 access sets; score by fingerprint overlap +
  size + constructor identity; report through `correspondence.enrich_evidence`
  (`correspondence.py:34`) status bands, never a bare float. Same-size same-type field
  swaps stay `ambiguous` — recorded, not guessed.
- **U33. VTable slot correspondence + inheritance.** Persist only address-resolved slot
  targets from the `[CLI] vtable.py:144-177` slot walk into `vtable(binary_id, class, addr,
  slot, func_addr)`; retire `rtti_recover.align_vtable_methods` (`:198-233` zips corpus
  methods positionally — the index fallacy this unit forbids); `vtable` gains
  `logical_method_id` via `identity.logical_id` and slots match across builds on that
  column; add base-class/offset parsing
  (Itanium `__class_type_info` arrays / MSVC `RTTIBaseClassArray`) — today only names
  (`rtti_recover.py:81-119`). Build a per-build `slot → logical method` map; match slots
  across builds by **method identity, not index**; surface `reordered / inserted /
  removed`. Pack `kind=vtable` carries the map, so virtual hooking targets a *method* and
  the consumer resolves the slot per build.
- **U34a. Accessor descriptor recovery (all missing today).** `grep stride|bitfield` hits
  nothing relevant; `wchar16` is only a primitive name (`ctxtypes.py:20`); the sole
  accessor-ish recovery is the live vtable slot walk. Recover deterministically: **table
  stride** from `INT_MULT`-by-constant feeding `PTRADD` in the U32c live path (plus
  `shl`/`imul`-by-constant indexing at decode level) and **count/capacity** from loop
  bounds and compare-immediates; **handle/id → pointer** formats from mask/shift on an id
  feeding a table index; **bitfields** from `BitFieldDataType` (U32a) and mask/shift
  patterns; **string** encoding/length rule from the reader routine's element width and
  terminator; **repeated sub-struct blocks** from fixed-stride offset series inside one
  struct; **enums** from switch tables and STABS `=e`. Emit
  `array_table(root, stride, count, elem_struct)`, `handle(table, index_bits, salt_bits)`,
  `bitfield(byte_off, mask, shift)`, `string(off, encoding, len_kind)`,
  `sub_block(base, stride, count)`, `enum(values)` per build; the Lua API exposes them
  (`entry`, `handle`, `bit`, `str`, `wstr`).
- **U34. Instruction-level entities: patch points, call sites, immediates.** Decode-stable
  instruction indexing within a function (index in decode order from the entry, never a
  VA); an **interior masked anchor** for each site (same total-order selection as U6);
  operand offset/width for immediates; the **live register/stack contract** at the site
  from decompiler dataflow (`[CLI] dataflow.py`) so a mid-function hook knows what to
  preserve and where locals live (`site_frame`, `site_regs`). Divergence: `present /
  moved / absent / operand-changed`.
- **U35. Object lifecycle descriptors + library-signature DB.** `sizeof` from
  allocation-site arguments, constructor/destructor identity, allocator kind → a `spawn`
  descriptor per class. **Consume U48's library-signature database** (U48 owns it and
  `func.is_library`; source per toolchain: Ghidra's shipped `.fidb` where one exists, else
  import-adjacent heuristics with `is_library` marked `heuristic`) so
  CRT/library/compiler-generated functions are **excluded from cross-build identity
  matching** (the classic false-positive source) while remaining locatable as hook targets
  (`kind=library_fn`, `allocator`).
- **U36. Imports, exports, dispatch/callback and script-VM tables.** Imports/exports by
  name (ordinal-only imports resolved through the library's export table); `dispatch_table`
  / `vm_opcode_table` entities with `index → logical function` maps, populated for the
  engine's script/event system by the L3 data pack (this is where the script-API name→key
  map lives — never in core). Enables hooking one script command or event portably.
- **U37. Format/structural entities.** Sections, relocation table, exception/unwind tables,
  TLS, resources, static initializers, entry point / main loop — extracted deterministically
  from the format via the container registry. Includes an **unwind-validity check** for any
  injected code on x64 (injected regions must register unwind info or be unwindable), and
  section permissions feeding W^X handling for caves.
- **U38. Integrity / anti-tamper routine identification.** Behavioral signature (self-
  hashing loops over `.text`, CRC tables over image ranges) → `integrity_check` entities
  with the ranges they cover, so a patch inside a checked range is flagged *before* it
  silently trips the check. Surfaced, never auto-disabled.
- **U39. Per-kind divergence + display.** Extend U14–U17 so the divergence signal and the
  review/compare UI are per entity kind: field-map delta, slot delta, table delta, patch-
  point absence, constant folded — each rendered in the shared-entity workspace, not only
  for functions.

### Phase 9 — Data roots, accessors, and the runtime resolver (the memory-mod substrate)
This phase implements design §7. It is the largest gap in the codebase.

**Where data stands today (data-lookup + accessor audits).** The corpus schema has
**no table for a data item** (`store.py:19-155`: `binary, func, calledge,
logical_function, identity, stabs_type, match, eval`). `features.py:204-205` does
`data_refs += 1` and **discards the target address**; string content is kept but the
string's *address* is dropped (`:206-211`); STABS statics/globals are parsed **with
addresses** (`machostabs.py:274-279` `N_STSYM/N_LCSYM`) and then discarded
(`stabs_link.py:202` extends only functions); ELF `STT_OBJECT` reaches only an inventory
JSON (`inventory.py:651-691`). PE exports/imports are parsed (`inventory.py:440-546`,
`address_util.resolve_iat_to_thunk`) but no "export/IAT + offset" anchor form exists.
There is **no masked/wildcard byte scanner** at all (`unique_window` is exact, entry-only;
no `findBytes` wrapper). Pointer deref is single-level, live-only (`vtable.py:144-168`);
`n_deref` is a count. `features.py:191`'s `0x100 ≤ |v| < 0x7FFFFFFF` filter **leaks
absolute data addresses into `consts`** (an accidental same-build anchor that breaks
cross-build) **and drops every realistic stride and mask** (4, 8, 0x18, 0x3c, 0xb0).
Accessor recovery is **absent**: `grep PTRADD|INT_MULT|INT_LEFT|INT_AND|INT_RIGHT` → zero
hits; `high_emit._pcode_from_high:439` filters to exactly the ops that *don't* carry
stride/mask semantics. The function side already has what data needs: an ordered anchor
cascade (`match_store.anchor_sets:449-455` I → H → X(string) → X(const), quarantine on
conflict), an ordered fallback resolver with provenance, score and **tie refusal**
(`agentdecompile_recovery/module_resolver.py:35-48` — package root, not `corpus/`), byte-verified placement with
`conflict|unplaced` statuses (`context_pack.py:396-420,479-493`), a hash-keyed cache shape
(`match_cache.cache_key:26`), and a refuse-on-mismatch precedent
(`acquisition_bundle.validate_bundle_target:231-250` raises). **Clone those for data.**
The runtime host already has the *consumer* schema the accessors need
(`structs.hpp:123-162` `Field{offset,size,elem_size,count,kind,elem,confidence}`,
`Layout{how_to_obtain}`).

- **U40. Capture data-reference targets (one new column, many readers).** Touch set:
  `features.py`, `extract.py`, `store.py`+`db.py` (until U82), `match_store.py`,
  `prompt_evidence.py`, `genproject.py`; `determinism_harness.generate_fixture` emits
  `data_ref_targets` (today `snapshot()` picks columns from `PRAGMA table_info`, so a new
  column rides along as NULL and the harness is blind to it). `instr_index` = U34's
  decode-order-from-entry definition in every producer, recorded in `algorithm_version`.
  `features.py:204-213`: replace the count with a list of `{to, instr_index, operand_slot,
  ref_type, is_write, string_at_to?}` persisted as `func.data_ref_targets` (keep the count
  for compatibility); emit string **addresses** beside content at `:206-211`. Split
  `:191` into a **typed operand-position channel** (immediates by role: index stride,
  mask, shift, compare bound, absolute address) instead of one magnitude filter — and do
  **not** un-mask `hash_reloc` (`fingerprint_hashes.py:26` masks absolute addresses on
  purpose so function identity survives data relocation); add a parallel channel.
- **U41. Data-item persistence (`kind=global|string|table|…` partitions of U30's
  `logical_entity`/`identity` — not new tables).** Mirror the row shape of
  `logical_function`/`identity` (`store.py:95-120`, same `ux_*_bin_addr` uniqueness):
  `data_item(binary_id, addr, size, section, kind, name, name_origin, type_hint,
  initial_bytes_sha)`, `logical_data(id, canon_key, kind, best_name)`,
  `data_identity(logical_id, binary_id, addr, confidence, method, evidence)`. Populate
  from U40 targets, STABS statics (new `stabs_link.py` branch beside `:202`), ELF
  `STT_OBJECT`, PE exports, Ghidra labels/defined data (`[CLI] memory.py:309`), and
  acquisition-bundle `global` entities (`acquisition_bundle.py:89-101`) — today the only
  root registry, recipe-less and absolute.
- **U42. `corpus/data_locator.py` — the locator family + resolver contract.** Per root, the
  ordered descriptor from §7: `symbol` → `xref_from_function {logical_id, instr_index,
  operand_slot}` (decode the operand from `expected_bytes`/decode, generalizing the
  hardcoded shapes in `source_parity_synthesize.py:618-630`) → `anchor_relative {anchor:
  export|import_iat|string_addr, delta}` → `masked_scan {section, pattern, mask,
  hit_offset}` (**a new scanner** — generalize `unique_window` to a mask; region-scoped) →
  `pointer_chain` (U43) → `vtable_rtti` → `module_rva {rva}` last — an entity resolved only
  by `module_rva` is `pinned(member)`, `portable:false`, and that flag propagates to U44
  instances, U47 port, U88 `describe` and U90 rows. Contract modeled on
  `ModuleResolver.resolve` + `context_pack` semantics: try in order; **verify** (byte
  compare at the data offset + declared size/type/alignment/section-permission + shape
  check); memoize by `(content_sha256, logical_data.id)`; return `{addr, member,
  channel_index, verified_by}`; statuses come from U30's closed set and rollup; on total failure `status: unresolved`
  with per-member reasons — never `0`/`None`.
- **U43. Pointer-chain / deref-path descriptors** (greenfield). `{base: <root id>,
  steps: [{deref, offset, size}], expect: {kind, align}}`; single-step primitive from the
  `vtable.py` walk; chains are discovered **offline from stored p-code** (U32c(a)) once U45 widens the op
  set — never from a timed live decompile (`collect_function_data_flow`,
  `[CLI] _collectors.py:188-336`, runs under `timeout_s=30`); canonical chain per root =
  min by `(hops, base member rank, offsets)`; offline validation verifies hops only through
  initialized image data, else `unverified_offline`, verified at runtime.
- **U44. Per-root recipes + coverage in the pack.** Extend `export_hookpack.export:158`
  with `entities[kind=global|singleton|table|string|…]`: the ordered family, per-build
  `instances[]` with `resolved_by`, `expected_bytes` at the data offset (`unique_window`
  is already `(image, offset, size)`-agnostic), and a coverage matrix `{member: hits/of}`
  (like `:113-120`). Add the CLI verb beside `export-hookpack` (`cli.py:194-200`). Fix the
  `_preferred_signature:114` `most_common` tie while there.
- **U45. Accessor recovery (all blockers named).** (a) **Lossless type export** — same
  fix as U32a: `render_field_type` returns `""` for `Structure|Union|Array`
  (`export_types.py:87-89`) so element type, stride and count die before reaching the
  DB; keep `Array(elem,count)/Pointer(target)/Enum(members)` as structured JSON.
  (b) **Stride/count pass** — widen `high_emit._pcode_from_high:439` to keep
  `INT_MULT/INT_LEFT/PTRADD/PTRSUB/LOAD/STORE`; stride = constant input to
  `INT_MULT`/`INT_LEFT` feeding `PTRADD`; count = the `INT_LESS/INT_SLESS` bound (a loaded
  count field or immediate); lift the `0x100` floor (U40). (c) **Bitfield pass** —
  `INT_AND`/`INT_RIGHT` with constant mask on a `LOAD` of `base+off` → `{byte_off, bit,
  width}`. (d) **Handle format** — on the id-resolver-shaped function, recover the index
  mask (`INT_AND`), salt shift (`INT_RIGHT`) and the backing table root. (e) **String
  rule** — from the `Data` type (`TerminatedCString` vs `TerminatedUnicode` vs a
  `{ptr,len}` string struct) emit `{encoding, length_rule}`. (f) **Descriptor emitter**
  into pack v2 `entities[]` (table/handle/bitfield/string/sub_block/enum), shaped to the
  runtime host's `Field`/`Layout` consumer schema.
- **U46. Runtime host: make the resolver real (this is C++ + Lua; pairs with U23).**
  Findings and fixes, each anchored in the runtime host repo:
  - **Admission is by slug filename only.** The pack's `expected_sha256()` is parsed
    (`registry.cpp:401-403`) but **never compared to the live image**; three identity keys
    exist (file sha256 `load.cpp:328`, slug `:330-334`, deciphered-text sha256 `:444`) and
    **Lua receives only the slug** (`compat.cpp:632`). Fix: compare `expected_sha256` to the
    live image at admission (`runtime.cpp:412`); expose `runtime_base`, `image_sha256`,
    `text_sha256` to Lua beside `build`; admit **unknown builds in signature-only mode**.
  - **Memo keyed by module base, not image hash** (`memory.cpp:50-53,620` key =
    `scan_base|len|sig`) — two builds at the same base share a cache, and misses are cached
    too. Fix: key on `text_sha256`/`image_sha256`.
  - **Field sites are never verified** (`registry.cpp:511` skips them); globals are never
    shape-probed. Fix: verify every entity kind per U42's contract.
  - **Object-id → pointer resolver is declared but never wired** (`structs.hpp:194-196`
    `set_address_resolver`; sole caller is a test fake in the host's `tools/` struct-test harness), so
    `struct.view(id)` is inert in the shipped runtime. Fix: wire it from the pack's handle
    descriptor (U45(d)).
  - **Struct field maps are compiled in** (`structs.cpp:25` reads a generated
    `structs_<product>.inc`; the generator accepts one product flag). Fix: move field maps
    into the pack (the parser already handles `kind=field` with `offset/size`,
    `registry.cpp:311-319`) so `field(struct, name)` is per-build data, not code.
  - **Missing locator families in the host:** no export lookup (`GetProcAddress`/`dlsym`
    — none in `src/platform/*.cpp`), and scan regions are **executable-only by design**
    (`memory.hpp:50-57`) so no data/rdata string or adjacency scan. Fix: add both, plus a
    data-section region set. `find_unique` needs the mask overload (U23). Expose
    `at_index` (`fields.hpp:138-144`, C++-only today) and a `resolve(site) → {addr,
    family, verified} | structured-failure` to Lua; keep `readbit` (LSB-0), string readers,
    and RVA-delta as-is.
  - **Pack vs host split:** host keeps scan/probe/memo/region bounds/`at_index`/verify;
    pack carries locator families, per-build field maps, handle formats, expected bytes,
    string rules, coverage. The pack format string is the seam (`registry.cpp:336`).
- **U47. Mod-script lint + port-a-mod tooling.** A lint that rejects any literal address
  in a mod script (the only memory access is `resolve`/`field`/`entry`/`handle`); a
  `port` verb that takes a mod authored against one build and reports, per target build,
  which roots/fields/accessors resolve and which are `unresolved`/`ambiguous`; a per-build
  coverage report and a diff-two-builds report built from the same coverage data.

### Phase 10 — Practice-derived units (every documented failure mode, addressed)
Derived mechanically from the "Grounding" table. None is optional; each closes a failure
mode a primary source documents.
- **U48. Library / CRT exclusion set** (L1 + L3 data pack). Identify library functions
  (a FunctionID/FLIRT-style DB plus import-adjacent heuristics); persist `func.is_library`;
  **exclude** them from `find_unique` candidates (U5), cave anchors (U12), and
  `neighborhood_symdiff` counts (U14) — BinDiff's "only non-library functions are
  considered". They stay locatable as hook targets (`kind=library_fn`). Without this, CRT
  bodies identical across unrelated binaries become "unique" anchors.
- **U49. Identical-body collision rule.** When two `logical_id`s share a masked body
  (templates, ICF), the masked-window member is marked `ambiguous` for those builds and
  the family is forced to the anchor-relative / callee-identity member — FLIRT's
  leaf-collision behaviour, made explicit rather than implicit in U5.
- **U50. Packed / compressed-image gate.** Detect (entropy, section-name, entry-in-last-
  section heuristics, or an explicit profile flag); **refuse to sign or cave a packed
  image**; require the unpacked image and record the *unpacked* hash in the basis and
  `binaries[].sha256`; `binary.unpack_state` becomes a first-class attribute (the
  `DRM_EXCLUDED` set is empty today).
- **U51. Anchor definition for U5b.** An anchor is the **reference site** or the **import
  name / IAT slot** or **string bytes** — never an import-thunk's bytes (`FF 25 <abs>`
  masks to nothing). Specify the exact byte range hashed per anchor kind.
- **U52. Record `reloc_table_present` per build.** Old 32-bit images commonly set
  `IMAGE_FILE_RELOCS_STRIPPED`; then decision 1's reloc half is empty and decode-only
  masking carries the whole load. Coverage and the masking-rule version must say so;
  never let "decode ∪ reloc" silently mean "decode only".
- **U53. Producing-channel weight on divergence classes.** Record which cascade channel
  produced a match and its weight (BinDiff's similarity × algorithm-confidence), so a
  `1↔1 structural match` from a weak channel is not treated like one from symbols.
- **U54. Land the full determinism basis** — absorbed into the normative basis object in
  the Determinism section: the full analyzer option set (Ghidra #5531 is exactly this
  drift), compiler-spec id, processor-spec/loader revision (#2792), timeout policy (U65),
  toolchain identity per build (decomp.me/dtk style — what objdiff/permuter receipts cite),
  filler set (U58), data-pack hashes (U19a), seeds. Every field store-derived or a pinned
  constant; per-binary `basis_hash`; refuse on unknown/empty/mixed. U25's re-baseline
  triggers on any change.
- **U55. Thread quiescence is mandatory in the C++ helper (U13/U23).** Suspend all other
  threads, fix any IP inside the patched or trampoline ranges (`SetThreadContext`), resume
  — Detours/MinHook/safetyhook all do this. The Lua host cannot; **refuse any patch from
  Lua that bypasses the quiescing helper.**
- **U56. Control Flow Guard handling.** Per-site `cfg_target_required` for anything
  reached by an *indirect* call (vtable-slot sites, cave stubs); consumer reads the image's
  load-config `GuardFlags`; use default-valid `VirtualProtect` semantics (never
  `PAGE_TARGETS_NO_UPDATE`) or `SetProcessValidCallTargets`; direct `jmp rel32` detours are
  not gated. Record per build whether the image is CFG-instrumented.
- **U57. Cave ownership / claim tokens.** Claim identity = `(pack_sha, cave_id,
  build_sha256)`; the ownership table maps claim → resolved range; the consumer refuses a
  cave already claimed (MinHook's `ALREADY_CREATED` semantics extended
  to byte ranges); collisions across packs or with third-party patches are recorded, never
  silently overwritten.
- **U58. Filler and padding provenance in U12.** The allowed filler set is a toolchain
  parameter (`0x00/0x90/0xCC`), recorded in the basis, not a constant; require a
  **uniform** run on an **executable** page (MinHook's hot-patch rule); record section
  `FileAlignment`/function-alignment origin — cave "free space" and stage-8 rebuild
  "padding" are the same bytes, so the rebuild can regenerate them.
- **U59. Anti-tamper / integrity policy.** Build-profile flag `self_integrity_checks:
  unknown | none | present` fed by U38's detection; when `present`, refuse resident cave
  payloads (detours-only mode) unless the check's range is known and excluded; surface,
  never auto-disable.
- **U60. Export-time detourability validation.** Run the MinHook-class length-disassembler
  checks at export: ≥ jump-width bytes before any `ret`, no branch *into* the patch window
  from elsewhere, no loop-family or unfixable RIP-relative instruction in the moved
  prologue. Emit `detourable: false` + reason per site per build, so a site fails at
  export, not at install. Uses the U4 decoder; the export-time verdict is advisory: the host
  re-runs its own decoder at install (`RH/src/hooks/trampoline.hpp:71`) and refuses
  independently; U62 records both decoder revisions.
- **U61. `this` / custom-storage normalization in U8.** Persist `hasCustomVariableStorage`
  and `getAutoParameterCount` per function (auto-param count is always 0 under custom
  storage, so `this` becomes indistinguishable from an explicit first parameter); emit
  `this` in **one canonical form** regardless of mode, or `args[]` is inconsistent between
  CLI-edited and untouched functions. **New capture, not persistence:**
  `getAutoParameterCount()` and `isAutoParameter()` are read nowhere in the tree today; add
  them to the U8 collector before emitting the canonical form.
- **U62. The C/D seam contract (one paragraph, binding).** `binaries[].sha256` **is** the
  stage-8 whole-file identity (the `build.sha1`-style gate) — one hash for the runtime
  target check (U24) and the rebuild check; the basis's toolchain identity (U54) is the one
  objdiff/permuter receipts cite; cave/padding bytes are shared data with the rebuild
  (U58). Per-function objdiff is a gate; whole-file hash equality is the claim.
- **U63. sret triple + x64 rules.** Replace `ret.by_ref` with `ret.sret = {allocator,
  ptr_storage, returned_in}`; encode the x64 argument-right-shift when sret is present, the
  ≤64-bit aggregate-by-value rule, and the x64 varargs int+float register duplication in
  the L2 adapter (U13b/U18) — never inferred per site. **New capture:**
  `getReturn().isForcedIndirect()` is read nowhere today; `ret.sret` has no producer until
  the U8 collector reads it.
- **U64. Recompile-and-diff ABI verification** (added to U28). From the exported ABI
  block, compile a synthetic caller and compare its call-site codegen against the original
  call sites (objdiff/reccmp style); a wrong convention shows as stack-adjust/register-move
  diffs. This is the community's only real check of a recovered prototype.
- **U65. Analyzer timeout policy.** Run extraction with an effectively unbounded
  decompiler timeout, or persist per-function `timed_out` as data under the basis —
  never let a wall-clock cutoff silently shape a persisted prototype.
- **U66. Content-addressed receipts** (required — grill 6: the draw-the-work replay has
  nothing to replay without it). Key every receipt by `hash(inputs + basis)` — `basis`
  read as the kind's declared basis projection (design §2.8; U158), so an identical-basis
  re-run is a cache hit, not a recompute (Bazel action-cache model), and a change to a
  basis field the kind does not consume is a cache hit too; the receipt still carries the
  full `basis_hash`. This is also the cheapest possible determinism check. Receipts carry
  `{stable_key, build, operation, member, outcome}` so both surfaces can replay them
  (CDP §6.1; U110). Acceptance: a recorded backfill replays identically on both surfaces.

### Phase 11 — Unify the machine the mod runs on (cross-platform sweep)
Verdict of the sweep: earlier phases unify *what* is located; this phase unifies *the
machine*: calling shape, pointer width, endianness, wide-char width, image relocation,
module, thread, and the write/rollback discipline — today either compile-time constants in
the runtime host or free-text/absent in the corpus. **Endianness appeared nowhere in the
plan before this phase.** Anchors: `AD/` = corpus tree, `RH/` = runtime host.
- **U67. Per-site calling shape from the pack, never from `#if _WIN32`.**
  `RH/src/runtime/hook_bodies.cpp:154-171` selects thiscall vs cdecl by platform macro
  with a self-documented live bug ("server-loop body above still assumes __thiscall on
  both"); `RH/src/api/enginestruct.cpp:29-37` binds every accessor as an unconditional
  thiscall; the per-build sites file carries **126 `convention =` entries that nothing
  parses**. Fix: the U11 ABI block carries `this_kind ∈ {ecx, stack, rdi, r0, …}`; the
  loader parses it; every call goes through the descriptor-driven layer (U13c), which replaces the one
  existing `CallShape` switch (`RH/src/harness/fields.hpp:60-70`). Delete the dead column or
  make it load-bearing.
- **U13c. Descriptor-driven native call layer in the host.** Every native call is a
  compile-time template today (`RH/src/harness/fields.hpp:60-71` two-value `CallShape`;
  `RH/src/api/enginestruct.cpp:29-37`); Lua reaches natives only through the fixed
  VM-dispatch bridge. Add a runtime thunk layer — per-ABI generated thunks in `alloc_exec`
  memory (default) or an embedded FFI — driven by the U11 ABI block (`this_kind`, per-arg
  `{register|stack, width}`, `ret.sret`, `stack_cleanup`, `varargs`); expose
  `call(entity, …)` to Lua. U88 emits a call stub only for ABIs this layer expresses, else
  `call_stub: refused, reason`. U67's one `CallShape` switch becomes this layer. U101 `near`
  is new platform work (both `alloc_exec` take `nullptr` today). Acceptance: a fixture
  entity with sret + this + varargs is called through its descriptor on x86-32 and x86-64
  fixtures; an inexpressible ABI yields the refusal, never a wrong call.
- **U68. Unknown-build admission (signature-only mode) — the plan asserts it in §7; this
  unit owns it.** `RH/src/image/load.cpp:381-385` returns `UnrecognisedBuild`;
  `runtime.cpp:331-337` treats any non-Ok as failure; `resolve()` bails on an empty build
  (`:363-366`); a *known* build is refused if its `.text` hash isn't listed (`load.cpp:446-
  451`); signature scan runs only *after* identity succeeds (`:412`). Add a `degraded`
  path: derive scan regions from the live image, resolve every entity by locator family,
  record coverage, refuse only `required` misses. Corpus side: `add-binary --admit-
  unknown` (`AD/corpus/cli.py:94-106` requires only `--id --path` today).
- **U69. Typed per-build platform/ABI descriptor.** New `binary` columns: `endian,
  compiler_spec, os, pointer_size, wchar_width, bool_size, enum_size, default_packing,
  this_kind`. `AD/corpus/inventory.py:102-106` already computes `endian` and
  `compiler_spec` and **discards them** (`upsert_binary` never passes them; no column).
  Fix `AD/targets.py:130-131`, which maps `EI_CLASS` not `e_machine` — **a 32-bit ARM ELF
  is recorded as `x86`**; read `e_machine` + `EI_DATA`. Consumers: `export_types.py:27-59,
  85-86` (real `wchar16/32`, enum width — today `"int" if len==4 else "int"`, `bool` forced
  to `unsigned char`), and the host's scalar readers (`RH/src/api/memory.cpp:280-307`
  host-native `memcpy`; `:364-383` wide strings hardcode 2-byte LE and narrow to Latin-1;
  `wchar_t` is 4 bytes on POSIX builds; no `readptr` — `readdword` is the pointer reader;
  `normalise_bit:314-318` truncates to 32 bits). Emit the descriptor in `binaries[]`.
- **U70. Platform-gate every cross-build donor.** `AD/corpus/propagate_conventions.py:44-
  58,94-95` pools donors by *product* only and sniffs x86 `ret imm16` on any binary, so a
  POSIX row inherits `ecx` from a Windows sibling; `propagate_types.py:76-86` adopts a
  32-bit MSVC layout verbatim into a 64-bit or GCC sibling. Donor pool must match `(arch,
  bits, endian, compiler_spec)`; otherwise record `skipped_cross_abi`. Gate
  `match_engine.classify_pair:98-108` on the U69 descriptor, not just `(arch, bits)`.
- **U71. Per-build, per-platform struct layouts loaded from the pack** (extends U32/U46).
  Replace the compiled-in single-product layout include (`RH/src/api/structs.cpp:25`; the
  generator accepts one product flag; `Kind::Ptr → uint32_t` at `:750`; research JSON
  embeds absolute VAs in prose) with pack layouts keyed `(logical_struct, build)`; pointer
  width from U69. Add a **`scaled`** correspondence state (offset = f(pointer width)) that
  U32's vocabulary lacks — the 32→64-bit layout case.
- **U72. Rebase every site consumer; support PIE.** Three rebase paths exist
  (`RH/src/hooks/registry.cpp:503-531,572-574`, the harness adapter), one is **missing**:
  `hook_bodies.cpp:248,293,300,306` and `runtime.cpp:590-604` call through raw
  `site->addr` — masked only because every current image shares one base. `load.cpp:47-74`
  assumes ELF is `EXEC` not `PIE` and a rebased image is *refused* (`:452-462`). Make
  `AddressTable::find` return rebased addresses so raw `->addr` cannot be used; support
  PIE ELF / Mach-O / shared-object live base (pairs with U7's load-base fix).
- **U73. Protect and journal every write, with before-bytes.** `RH/src/api/structs.cpp:
  735-756` struct-field writes do `is_readable` then a bare `memcpy` — **a W^X hole**;
  `memory.cpp:146-151` restores non-exec pages to `ReadWrite` unconditionally (no
  protection query), leaving read-only data writable forever; `WriteRecord{address,
  width, kind, value, where}` (`memory.hpp:96-102`) keeps **no before-image**;
  `set_write_observer` (`memory.cpp:708`) has zero production callers. Fix: route every
  write through the `memory.cpp:122-168` funnel; extend the record with `before, build,
  pack_sha, entity_id`; wire the observer to a persistent journal; restore the *prior*
  protection from a page-permission map.
- **U74. Site/cave ownership registry + cross-mod collision refusal** (merges with U57).
  `HookSet::install` refuses only its *own* re-install (`registry.cpp:558-561`); nothing
  stops a script writing into an installed trampoline or another script's cave; the host
  API doc claims such writes "are refused" and self-flags it as **"Spec only"**. Ownership
  table keyed by claim `(pack_sha, cave_id, build_sha256)` → resolved range (one identity
  with U57); `store()` refuses writes into ranges owned by another
  script, a detour, or a trampoline; `cave.claim(id, size)` in the Lua API.
- **U75. Multi-module entity axis.** A build is a *set of modules* (exe + DLLs/.so/dylib,
  container overlays). Today `repo_path UNIQUE` = one file per build (`store.py:21`);
  container overlays never become `binary` rows (`AD/containers/__init__.py:318-349`);
  the host targets only `self_module_path()` (`runtime.cpp:201-211`), every
  `module_base(name)` caller passes `nullptr`, scan regions are main-image-only
  (`memory.hpp:69-70`). Add `entities[].module`, `binary.program_id + module_name`,
  per-module scan regions and base resolution.
- **U76. Endian-aware signature/decoder path.** Add `endian` to the determinism basis;
  big-endian variants through `features.py` mnemonic classes (no PPC classes today,
  `:20-46`), the decoder gating, and the `exact_universal` mappers; stop raising on
  big-endian ELF (`AD/inventory.py:553-554`). Without this the matrix's console-build
  class has no representation at all.
- **U77. Unpack state + code-section hash as first-class build identity; one build
  registry.** Persist `unpack_state ∈ {plain, packed, dumped}`, `unpacked_of`, and
  `code_sha256` on `binary` (writers: `unpack.py:93-139` returns a recovery family nobody
  stores; `runtime_dump.py`; the dashboard writes filesystem receipts only); match on
  `code_sha256` in `identical_image.py:74-90` so a DRM-wrapped image with identical code
  short-circuits. **Unify the three unsynchronized build registries** (the host's Python
  `BUILDS` dict, its per-build JSON files, the corpus `binary` row — one profile is in the
  dict but recognisable nowhere at runtime) into one exported profile, and **delete the
  hardcoded per-build receipt in C++** (`runtime.cpp:444-451` string-compares a build slug
  and hardcodes field offsets — the exact anti-pattern §7 names). Extends U50.
- **U78. Cross-build compatibility keys for save/network.** Network compatibility today
  = *exact image sha256* (`runtime.cpp:456-468`, `transport.cpp:126-127`) — it refuses
  byte-identical sibling builds. Replace with a hash of the **logical layout set the
  transport touches**; give the serialized situation blob a build/basis header
  (`events/situation.cpp:8-22` has none).
- **U79. ABI-correct RTTI walk** (prerequisite for U33's slot maps on non-MSVC builds).
  `AD/rtti_recover.py:312-322` picks the ABI by *file format* (PE→MSVC, ELF→Itanium —
  wrong for MinGW-PE and Mach-O) and `:209-210` skips `slot_count − 2` "meta" entries
  regardless of ABI (MSVC meta is at index −1). Dispatch on the recorded `compiler_spec`
  (U69); walk MSVC COL/TypeDescriptor/BaseClassArray vs Itanium `_ZTV/_ZTI`; handle vptr
  position, multiple-inheritance thunks, vbase offsets.
- **U80. Pack hot-reload + rollback-on-reload.** Script reload exists (`RH/src/lua/
  host.cpp:384-420`, mtime-driven) but the address table and hook set are set once
  (`runtime.cpp:818-823`) and reload does not undo the departing script's writes. Revert
  journaled **data** writes (U73) in reverse journal order on reload; code patches (detours,
  cave payloads) are reverted only through the U55 quiescing helper, otherwise reload
  refuses to unload a script that owns a code claim; allow table replacement.
- **U81. Workflow verbs** (merges with U47): `corpus.diff-builds A B` (per-entity
  divergence from U14/U39), `corpus.coverage-by-entity` ("entity X: resolved on {…},
  member used; unresolved on {…}" — today every report is a per-binary aggregate, the
  closest thing is prose), and `corpus.port-mod --from A --to B` (re-resolve every
  entity a script references; per-site status). Nothing today operates on a Lua script or
  a hook set.
- **U82. Schema unification** (prerequisite for every new `binary` column). Two `binary`
  DDLs exist (`AD/corpus/store.py:19-36` vs `AD/corpus/db.py:19-34`); `db.py` has a
  product-named default path and one importer (`name_precedence.py:45`). `db.py` is deleted
  and the importer repointed to `store.connect`; existing stores need no DDL change; the
  `role` column keeps one documented vocabulary in `store.py`.
- **U83. Corpus-side unwind / TLS / SEH parsers** so U37's `unwind`/`tls` entities have
  producers: `.pdata/.xdata` (today only section allowlists), SEH scope tables, the TLS
  directory/index, Mach-O compact unwind; `.eh_frame` is parsed for ELF only. Pairs with
  the host registering unwind info for x64 trampolines (none today).
- **U84. Allocator identity per build** (feeds U35's `spawn`). Only name-based exclusion
  exists (`AD/corpus/canon.py:29-32`); map `operator new` / `malloc` / `HeapAlloc` /
  mangled variants per build with the size-argument signature.
- **U85. Localization / string-table entities.** Per-function string features exist
  (`features.py:206-212`); no string-table / localized-resource identity and the host has
  no string-table site. Add `kind=string_table` with per-build lookup (index → content
  hash), so text mods port across languages and builds.
- **U86. Integrity-check range awareness at runtime** (completes U38/U59). U38 identifies
  checkers; nothing models "this write lands in a checked range" at runtime. The ownership
  registry (U74) gains checked ranges from the pack; writes into them are refused unless
  the profile's anti-tamper policy allows.

## The export bundle — what analysis produces, ready to use

One deterministic verb produces everything below from the store; nothing in it requires
a human to finish it before a workflow can use it. Every artifact is a pure function of
(store + basis) and carries the basis and the corpus-manifest hash.

| Artifact | For | Contents | Produced by |
|---|---|---|---|
| **`hookpack/v2`** | the runtime host, any consumer | every entity kind with locator family, per-build instances + coverage, ABI blocks, struct field maps + correspondence, accessors, caves with plan templates and claims, integrity ranges, adapter-key map, determinism basis, pack hash | U1–U3, U5–U5d, U11, U30, U44, U45, U24, U54 |
| **Generated Lua bindings** | mod authors | a `require`-able module per corpus: named roots (`roots.player_table`), per-struct typed accessor tables (`Player.name(ptr)` / `Player.set_health(ptr, v)`), table/handle/bitfield/string helpers bound to descriptors, typed call stubs per function from the ABI block, hook helpers per site kind, a `describe()` that reports resolution status — all through `resolve/field/entry/handle`, **no literal address anywhere** | **U88** |
| **Per-build C/C++ headers + build manifest** | native mods, recompilation, the matching-decomp loop | structs with exact per-build layouts (bitfields, unions, real pointee types), prototypes with conventions/storage, vtable slot enums, constants/enums, a manifest naming the build hash, toolchain identity, and basis | U11b, U32a, U33, **U89** |
| **Readiness report** | everyone | per entity × per build: U30's closed set `resolved(member) / pinned(member) / degraded(member, reason) / ambiguous / unresolved / contested` (plus `observed_status`); per build: unpack state, CFG, integrity checks, missing adapters; what a mod can and cannot do on that build, in plain language | U81, **U90** |
| **Divergence report** | reviewers, mod authors porting | per-entity cross-build classification (`1↔1 / split-or-inlined / diverged`), field-map deltas, slot deltas, table deltas | U14–U17b, U39 |
| **Recovered source variants + manifests** (optional) | byte-accurate rebuild | byte-accurate C + assembly-floor, and max-C, each with build instructions, toolchain identity, exact verification status; absent with a `not_in_scope` receipt within this plan | STRATEGY stages 3–8 (program scope) |
| **Receipts** | determinism, audit | content-addressed receipts for every artifact keyed by `hash(inputs + basis)` | U5c, U66 |

### Phase 12 — The export bundle as a first-class deliverable
- **U87. `corpus.export-bundle` — one deterministic verb, one output tree.** Runs every
  exporter in a fixed order into a content-addressed directory, writes a top-level
  `bundle.json` (basis, corpus manifest hash, artifact list with hashes), and refuses to
  emit if any artifact fails its own verify gate — the gate applies only to rows this plan's
  units produce; the recovered-source row is optional and absent with a `not_in_scope`
  receipt. Re-running under an identical basis
  yields a byte-identical tree (this is the acceptance test, per U5c/U28). Cataloged on
  the same action surface as `export-hookpack` (`cli.py`, `actions/catalog.py`).
- **U88. Generated Lua binding module from the pack** (new `corpus/export_lua_bindings.py`,
  consuming `hookpack/v2` only — never the store — so it is reproducible from the pack
  alone; cataloged as `corpus.export-lua-bindings`). A generator that turns pack v2 into
  a `require`-able Lua module: roots by name; one accessor table per `logical_struct`
  with typed getters/setters derived from the field map and per-field encoding (widths,
  bitfields, strings via the string rule); `entry(table, i)` / `handle(table, id)` bound
  to the accessor descriptors; typed call stubs per function generated from the ABI
  block (refusing to generate for low-confidence ABIs); hook helpers per site kind;
  `describe(entity)` returning the resolution status from the readiness data. The
  generated module contains **no literal address** and passes U47's lint by
  construction. Determinism: sorted emission, no timestamps. Every generated
  getter/setter/entry/handle raises `error({status, entity, members_tried})` on any
  non-`resolved` status; only `describe()` returns without raising; call stubs depend on
  U13c; a generated module that can return `nil` for a resolved-looking read fails the U28
  lint.
- **U89. Per-build C/C++ headers + build manifest.** From U32a's field rows and U11's
  ABI blocks: per-build headers with exact layouts (`_sizecheck_` asserts retained),
  prototypes with conventions and storage attributes, vtable slot enums, constants and
  enums with correct widths; a manifest naming build hash, toolchain identity (U54), and
  basis. Extends `build_types_header.py` rather than adding a second header path.
- **U90. Readiness report** (new `corpus/readiness_report.py` + a versioned JSON schema,
  `readiness/v1`, consuming the pack's coverage matrices; cataloged as
  `corpus.readiness-report`). A generated, human-readable report (and its JSON) from the
  coverage matrices: per entity × build status, per-build environment facts (unpack
  state, CFG, integrity checks, endianness, pointer width, missing L2/L3 adapters), and
  a plain-language "what you can do on this build" summary. This is what a user reads
  first; it is the honest counterpart of "ready to go".

## Exhaustive resolution ladders — pushing coverage as far as physically possible

The principle: **a locator failing is a signal to try the next relationship, not to stop.**
Every entity in a binary is connected to other entities — by calls, by data references, by
vtables, by constructors, by relocations, by strings, by its position in the image. If the
entity's own bytes changed, one of those connections almost always survived. The ladder
walks them all, deterministically, in a fixed cheap-first order, and only then records a
residue. Two facts make this stronger than any single RE tool: (1) for a **known build** the
whole ladder runs **offline** in the corpus, where every channel of the identity cascade is
available, so runtime resolution is just reading a precomputed instance; (2) for an
**unknown build** the runtime host gets an embedded decoder (U91) so the *same* structural
strategies run live, and the results are fed back to make it a known build (U99).

### Ladder A — a function whose masked window does not match on build B
Each member names the v2 locator kind it consumes (in brackets).
1. **Anchor-relative** [`anchor_rel`] to an import/export/string-table entry (U5b) —
   survives any change inside the body.
2. **Via a resolved caller** [`caller_callsite`] — resolve any caller G (by *its* ladder), decode G's call
   instruction at the recorded call-site index, follow `rel32`/RIP-relative/indirect target
   → F's address. Exact, deterministic; a `call rel32` decode is trivial even without a full
   decoder. (U92)
3. **Via a resolved callee** [`callee_order`] — scan F's expected callers' neighbourhood: the function that
   calls resolved callees {C1, C2, C3} in F's recorded order is F. (U92)
4. **Via data it references** [`data_xref`] — resolve any global/string F is known to touch (Ladder C),
   then find the instruction(s) that reference that address (relocation-aware scan) and take
   the enclosing function. (U93)
5. **Via its vtable slot** [`vtable_slot`] — resolve the class's vtable (Ladder D), read slot k. (U94)
6. **Via a resolved neighbour by position** [`neighbour_position`] — in the same section, functions keep relative
   order far more often than bytes: the function between resolved F−1 and F+1 whose
   structural fingerprint (Ladder A-7) matches is F. (U95)
7. **Structural match with the embedded decoder** [`structural`] — decode candidate regions, compute the
   mnemonic-class sequence / CFG MD-index / SPP (the same fingerprints the corpus uses,
   `fingerprint_hashes.py`, `cfg_signature.py`, `mnemonic_spp.py`), and match against F's
   recorded structural signature with the recorded margin. Runs offline always; at runtime
   on unknown builds via U91. (U96)
8. **Region match for inlined/split code** [`region`] — search the bodies of F's likely hosts (its
   callers, or the functions that took over its callees) for F's masked-window fragments;
   emit a `region` site (host function + range) so a hook can target the logic where it now
   lives. (U97)
9. **Symbol / debug info at runtime** [`symbol`] — export table, PDB/map file if present beside the
   image (many builds ship them). (U68/U5b)
10. **Offline only, for the residue:** emulation-based behavioural fingerprint (the corpus
    already has an emulation path, `unpack_emulate.py`) and BSim over the full corpus. Never
    at runtime. (U5d, U98)
11. **Annotation with provenance** — a human or model proposes; recorded as a
    `runtime_claim`-style annotation claim outside the closed set, never as resolved; the
    entity's status stays `unresolved` until a deterministic member confirms it. (U26)
Only after all eleven: `unresolved`, with the per-member reasons.

### Ladder B — a cave that is missing or too small on build B
1. **Multiple candidate caves per anchor** — ship the N largest validated caves near each
   anchor, not one; the resolver takes the first that fits. (U100)
2. **Live cave discovery** — the host already has the detour engine's length-disassembler;
   with U91 it can run the U12 validation rules (uniform filler, executable page, not
   covered by a decoded instruction, not a reloc/data target, between two function ends)
   over the whole section at resolve time. (U100)
3. **Section slack** — the space between a section's raw size and its virtual size is
   mapped, executable (for code sections), and unused by the loader: the classic large cave.
   Deterministic from the headers. (U100)
4. **Header / stub space** — DOS stub and header padding for tiny payloads. (U100)
5. **Executable allocation** — `mem.alloc_exec(size, near_addr)` in the host (x64: within
   ±2 GiB of the site; x86: anywhere): payload space is **always** available; caves become
   an optimisation for the cases that require in-image residency (anti-tamper constraints,
   on-disk patches). This is what makes injected code universally placeable. (U101)
6. **Image extension for on-disk mods** — append a new section to the file when the target
   is a disk patch rather than a live process. (U101)
Only after all six: `no_placement`, with reasons — in practice only when the process
forbids executable allocation *and* the image has no slack, which the readiness report
(U90) names per build.

### Ladder C — a data root that does not resolve on build B
1. Symbol / debug info [`symbol`]. 2. **Xref from any identified function**
[`xref_from_function`] (the strongest; U42).
3. **Inverse xref scan** [`data_xref`] — the masked *access instruction* (`mov eax,[abs]`, `lea`,
   RIP-relative) is itself a signature: scan the section for it (relocation-aware) and take
   its operand → the root, even when the referencing function's own ladder failed. (U93)
4. Anchor-relative to import/export/string-table content [`anchor_rel`]. 5. Data-section
   masked adjacency [`masked_window`]. 6. **Pointer chain from any resolved root**
   [`pointer_chain`] (U43). 7. **Via the
   constructor / initializer** — static initializers and constructors write roots with
   constants in a fixed order; decode the resolved initializer to recover the store
   targets. (U102) 8. VTable/RTTI-derived [`vtable_slot`]. 9. **Value-shape probe** — for roots with a
   declared shape (a UTF-16 run, a pointer into a known table, a magic constant), scan the
   data sections for the shape and confirm with a second member. (U102) 10. Module-relative
   RVA [`module_rva`, `pinned`], last. Then `unresolved`.

### Ladder D — a struct field that moved, or a struct on a stripped build
1. Name / debug-info donor (STABS/PDB, U32b). 2. **Accessor decode** — resolve any
   identity-bound accessor function (getter/setter/ctor) by Ladder A, decode its
   `[base+off]` access → the field's offset **on this build**, exactly. Works on fully
   stripped images. Offline via U32c; at runtime via U91. (U103) 3. **Constructor initializer
   sequence** — ctors write fields in declaration order with recognisable constants; decode
   the resolved ctor → offsets and sizes. (U103) 4. **Field-access fingerprint match**
   (U32c/d) with size/type/usage — `ambiguous` only for true same-size same-type swaps.
   5. **Sibling-field anchoring** — if fields {a, c} resolved and b sits between them on
   every other build, b's offset is bounded; confirm with an access decode. (U103)
   6. **Scaled inference** for pointer-width changes (U71). Then `unresolved` per field.

### Ladder E — vtable slots and dispatch tables
1. RTTI (U33/U79). 2. **Constructor vtable-store decode** — the resolved ctor stores the
   vtable pointer; read it. (U94) 3. **Slot matching by method identity** — each slot's
   target is resolved by Ladder A; slots are matched by *which method* they point to, so
   reordering is detected exactly, not guessed. (U33) 4. **Dispatch tables by handler
   identity** — same rule for script-VM / event tables: entries are matched by the logical
   handler they point to. (U36) Then per-slot `unresolved`.

### Ladder F — an unknown build
1. Admit in signature-only mode (U68). 2. Run every ladder above live, with U91's decoder
   for the structural members. 3. **Record everything the build taught** — every resolved
   instance with its member, every residue — and **ingest the build into the corpus** (its
   image hash, its resolved instances as `runtime_claim` rows per §1 — never `identity` — pending
   `bind_identities`' confirmation). Next time it is a known build with full
   offline coverage; the residue is re-attacked offline with the members that need the
   whole corpus (BSim, emulation). (U99) This is how residue shrinks with every build seen.

### Phase 13 — Exhaustive-ladder units
- **U91. Embedded decoder in the runtime host** — the **same** pure decoder library and revision U4 pins (a
  mismatch → the host refuses structural members with `decoder_mismatch`), exposing
  decode-to-mnemonic-class, operand extraction (`rel32`, RIP-relative, `[base+off]`), and a
  flow walk sufficient for CFG MD-index / SPP. Scope: operand decode + live structural
  members on unknown builds only; masks are produced offline by U4 and the runtime never
  re-masks; masked compare needs no decoder (U23). The trampoline length-disassembler stays
  for install-time safety (U60 advisory; U62 records both revisions). Results land in
  `runtime_claim`. This single unit converts the runtime from
  "byte scanner" to "structural matcher" and unlocks Ladders A-2..A-8, B-2, C-3, D-2..D-3.
- **U92. Via-caller / via-callee resolution** — pack carries, per function, its call-site
  indices in each caller and its ordered callee list; resolver implements A-2/A-3.
- **U93. Inverse data-reference scan** — masked access-instruction signatures per root
  (C-3) and per function (A-4); relocation-aware section scan with uniqueness check.
- **U94. Constructor-derived resolution** — vtable pointer from the resolved ctor (E-2),
  method from slot (A-5).
- **U95. Positional neighbour resolution** — order-preserving placement between resolved
  neighbours in the same section, confirmed structurally (A-6).
- **U96. Runtime structural matching** — corpus fingerprints (mnemonic class sequence,
  CFG MD-index, SPP) shipped per function with margin; matched live via U91 (A-7).
- **U97. Region sites for inlined/split logic** — locate a function's fragments inside its
  host bodies; emit `region` entities a hook can target (A-8).
- **U98. Offline residue attack** — a cataloged verb that re-runs BSim + emulation-based
  fingerprinting over the current residue after each corpus change (A-10).
- **U99. Learn-the-build loop** — runtime resolution results (per member, per entity) are
  exported as a build report the corpus ingests as `runtime_claim` rows (§1) — never
  `identity`; `bind_identities` confirms (promotes) or rejects (receipt + delete); the build becomes known (Ladder F). Deterministic: the
  report is a pure function of the image + pack + basis.
- **U100. Cave candidates, live discovery, section slack, header space** (B-1..B-4) —
  N candidates per anchor in the pack; live discovery with the U12 validation rules via
  U91; slack and header caves computed from headers.
- **U101. Executable allocation + image extension** — `mem.alloc_exec(size, near)` in the
  host with the platform's W^X sequence and (x64) near-allocation within ±2 GiB (B-5);
  append-section for on-disk patches (B-6). Payload placement becomes universal; in-image
  caves remain for residency-constrained cases.
- **U102. Initializer- and shape-derived data roots** (C-7, C-9) — decode resolved static
  initializers/constructors for store targets; value-shape probes over data sections with
  second-member confirmation.
- **U103. Accessor-decode and constructor-derived field offsets** (D-2, D-3, D-5) — the
  stripped-build struct answer: exact per-build offsets from decoded accesses, offline
  (U32c) and live (U91).

### Phase 14 — Surfaces (both frontends draw what Phases 1–13 produce)
Ownership rule: "Surface ownership" above — 8080 required, 5174 richer, no field on only
one surface. Hangs and starvation are the top risk class (register H1–H6), so U104 lands
first and U111 before any drawing unit. The Autonomy rule (governing principle) applies:
every surface draws outputs that already exist; no surface is a gate, and the review lane
is an override, so its starvation (H3) delays overrides and never coverage.
- **U104. Verb admission flags** (`corpus/cli.py`, `dashboard/actions/introspect.py`,
  `dashboard/actions/jobs.py`). `backfill` → `mutating`, `long_running`,
  `identity_scope="database"`; `export-bundle` / `export-hookpack` → output-tree scope;
  `verify-determinism` → read-only on temp copies; `attest` (U28x) → read-only temp
  copy. The admission loop (`jobs.py:363-386`) reads them (H5/H6). Acceptance: pause
  drains a running backfill; the catalog JSON shows the flags on all four verbs.
- **U105. Autonomous start + single admission-scoped control.** Remove the per-stage
  Run buttons (`workbench-app.js:948-951`, `panels/steps.py:282-299`) and the "Run
  pipeline" / "Stages" controls (`workbench-app.js:4791`); the three renderers of
  `workbench.workflow-control` (`PreparationActivity.tsx:45`,
  `ExplorerProjectActions.tsx:35`, `StageTrace.tsx:117-119`) collapse to one
  admission-scoped pause/resume with its scope named. Opening a project, adding binaries
  or resuming prior work admits eligible missing work without a click; reopening known
  material admits nothing that already has a receipt. Expert verbs stay in Commands,
  never as ladder Run buttons; the review lane is an override applied afterwards, never a
  gate the pipeline waits on (Autonomy rule). Acceptance: no `Run` control in the required 8080
  surface; a fixture project auto-admits on open and a re-open admits zero jobs; pause
  stops admission within one tick and resume continues from receipts.
- **U106. Review lane U17 fields on 8080** (`ReviewReact`, `workbench-app.js:907-929`):
  `relation`, `divergence_class`, `components`, `thresholds_version`,
  `producing_channel`, `reason`; U17's total ORDER BY. Acceptance: the queue JSON and the
  rendered rows carry every U17 field, in U17's order.
- **U107. Readiness × coverage matrix inside the corpus-first Logical view** (8080
  `wb-logical`, 5174 `Logical`), keyed by `stable_key`; the six U30 statuses and
  `observed_status` are separate glyph axes; `pinned` is drawn as a non-portable pin
  labelled `module_rva` / `section_offset`; never merged with identity-edge state.
  Acceptance: matrix rows equal U90's JSON row for row.
- **U108. Evidence rail: ladder residue and contested pairs.** For the selected entity:
  members tried in family order, per-member reason, and for `contested` two locator
  arrows landing on different addresses in one build lane, both with evidence, no
  winner. Acceptance: a fixture `contested` entity renders both members' evidence.
- **U109. 5174 Compare tab (REC N3)** rendering the same U17 object per pair;
  `Surfaces.tsx` stays unmounted and is not the target. Acceptance: one U17 object,
  identical on both surfaces for the same pair.
- **U110. Draw the work from receipts.** U66 is required; receipts carry
  `{stable_key, build, operation, member, outcome}`; the fifth design verb
  **Derive/backfill** draws build row → derived column → receipt; replay over the
  existing poll (CDP §6.1), never a progress bar. Acceptance: a recorded backfill replays
  identically on both surfaces.
- **U111. Starvation and hang metrics** (H1–H6). Age of the oldest unreviewed review
  row, oldest waiting lane, longest-running job against its deadline — drawn on both
  surfaces and emitted in receipts; a job past its deadline is drawn through the failover
  rule as a named failure, never a spinner. Acceptance: a fixture with a stale review row
  shows its age; a fixture job past its deadline is drawn as a named failover.
- **U112. Product vocabulary in the surfaces.** The `game` column/field and the fixture
  names under `frontend/src` and `static/` (grill 6: 7 files / 19 hits; schema-level at
  `AtlasApp.tsx:579` and `workbench-app.js:989`) are renamed under U21a/U21b rules.
  Acceptance: the name gate returns 0 in `--strict` mode over those two trees.

### Phase 15 — Distributed compute (`agentdecompile_grid`; design: docs/plans/2026-09-21-distributed-compute-design.md)
Walking-skeleton order (charter §6c): a thin end-to-end path through every layer landed
first — one working implementation per layer, every other adapter declared by name with a
named refusal — and each unit after U125 turns one declared adapter, canary, provider or
lane into a working one behind the interface the skeleton fixed. Effort is agent-hours; the
design's former 170-engineer-day figure is a human-team estimate, not the plan. Access is
by capability only: a node that proves a capability by canary is offered the lanes that
capability serves and fetches the input objects those tasks name; a role decides what a
node mirrors and whether its key may sign invites, run verifiers or run appliers — nothing
else. Every result from every node is a proposal until an independent key verifies it; the
corpus SQLite store and the similarity index are materialized views of verified records;
no worker ever holds their write lock (H1 by construction). Every task has a kill deadline
(H2) and a task id `sha256(canonical(kind, kind_version, inputs, params, basis projection))`.
Acceptance tests are named, never written (charter §6b). The design's §8 keeps its own unit
ids as the detailed specification; read them through this map:

| Design §8 id | This phase | Note |
|---|---|---|
| U120 slim distribution + skeleton | U120 | same |
| U121 object store adapters | U121; U159/U160/U161 for the declared adapters | local working; s3, static mirror, peer, layered declared |
| U122 logs, heads, frontier, outbox | U122 | same |
| U123 compaction snapshots | U122; U170 for pruning policies | absorbed |
| U124 worker runtime | U124; U166 container sandbox; U158 basis projection | absorbed |
| U125 join, attach-first, canaries | U124; U163/U164/U165 for the canaries | **U125 here is the integrator pass** |
| U126 roles, keys, invites, revocation, rate limits | U126 | same content |
| U127 verifier loop, independent keys, caps | U124 | absorbed; its named tests stay with U124/U156 |
| U128 view materialisation, appliers | U123; U169 similarity applier | absorbed |
| U129 fleet bootstrap | U129 | same content; `manual`/`ssh` already in U124 |
| U130–U157 | same ids | U143 and U150 retitled as delta binders |
| — | U158, U162, U167, U168, U169, U170 | new here (no design id) |

**15.0 Skeleton — landed by parallel builders (2026-09-22)**
- **U120. Contract ✔** (`d8447f6`). `src/agentdecompile_grid/{core,__init__}.py`, packaging
  (second distribution `agentdecompile-grid`, `adgrid` entry point, no analyzer bindings, no
  dashboard): Protocols for every layer (object store, log, heads, signer, transport,
  provider, canary, task kind, view applier), records, task ids, registries with declared
  slots, named errors. Acceptance (named): `test_grid_never_imports_recovery`,
  `test_cli_no_recovery_import`, `test_cli_describe_lists_every_registry`,
  `test_cli_every_error_is_named_and_coded`.
- **U121. Objects + tasks + config ✔** (`b147f99`; `7cc0b63`, `c575411`).
  `objects/{base,local,s3,static,peer,layered,gc}.py` (local working; s3, static-mirror,
  peer, layered declared or working as their docstrings state), GC with pin-then-verify and
  a named refusal at the cap (R2), `config.py` (`GridConfig`, TOML then env),
  `tasks/{spec,registry,results,budget,builtin}.py` (canonical specs, per-producer result
  pointers `results/<task_id>/<producer>` + `results/<task_id>.index`, kinds `hash-object`,
  `python-canary`, `subprocess-verb`). Acceptance (named):
  `test_local_put_get_roundtrip_and_idempotent_put`, `test_store_full_named_error_at_cap`,
  `test_gc_never_evicts_named_referents_or_their_outputs`,
  `test_task_id_stable_across_param_key_order_and_input_order`,
  `test_proposal_cap_refuses_fifth_producer_by_name_and_same_producer_rewrites`,
  `test_subprocess_verb_timeout_is_status_timeout_and_kills_process_group`,
  `test_config_rejects_unknown_key_by_name`.
- **U122. Log + heads + frontier + signing + compaction ✔** (`95e8428`; `515fd47`).
  `log/{records,local,heads,backoff,intents,frontier,compaction,signing,outbox,s3,http}.py`:
  hash-chained signed records, `LocalFileLog`, `LocalFileHeads` CAS with sub-partitions,
  seeded backoff with rotation, advisory fenced intents, pure `frontier.derive`, bounded
  checkpoints and prune, signers null/hmac/ed25519 (ed25519 declared), `Appender`/`Outbox`.
  Acceptance (named in `log/README.md`): U122 (a)–(e), heads-cas, heads-fork,
  backoff-rotation, outbox-batch, frontier-cap, frontier-order, intents-fence,
  compaction-idempotent, compaction-prune-guard, signing-roundtrip.
- **U123. View + pipeline lanes + CLI ✔** (`95e8428`; content at `eecfcaf`, `85784cc`).
  `view/{applier,similarity}.py` (`SQLiteViewApplier` replays verified records only into
  `grid_*` tables with position tracking and `materialize`; similarity applier declared),
  `src/agentdecompile_recovery/grid_lanes/{verbs,compile,parity,cascade,analysis,splitter}.py`
  (corpus verbs via `subprocess-verb`, `compile-attempt`, `parity-check`,
  `match-score-shard`, declared analysis kinds, `splitter.plan_tasks` with the
  never-awaited rule), `cli.py` (`adgrid` with named exit codes). Acceptance (named):
  `test_view_materialize_twice_identical_dump`, `test_view_no_worker_opens_view_for_writing`,
  `test_view_stale_under_foreign_lock` (H1), `test_match_shard_equals_monolithic_scores`,
  `test_compile_masked_coff_equal_across_timestamps`, `test_parity_sides_named`,
  `test_plan_no_slug_in_any_spec`, `test_cli_publish_refuses_foreign_basis`.
- **U124. Worker + verify + fleet + transport ✔** (`8eb5202`, `a4e4aca`; the audit-4 brief
  listed it in flight — the branch carries it; the builder's report is reconciled in U125).
  `worker/{agent,loop,canaries,identity,outbox,records,sandbox}.py` (attach-first join,
  `EADDRINUSE` = already owned; canaries incl. `python-canary`; work loop with kill
  deadlines; outbox), `verify/{loop,methods,policy}.py` (independent-key verifier,
  hash-lookup and recompute methods, proposal caps), `fleet/{cloudinit,manifest,providers}.py`
  (`manual`, `ssh` working; `oci`, `hetzner`, `aws`, `gcp` declared; cloud-init rendering),
  `transport/{local,https,peer}.py` (`LocalTransport` working; https and peer declared).
  Acceptance (named): `test_join_attaches_to_running_agent`,
  `test_eaddrinuse_is_already_owned`, `test_sleep_forever_is_killed_at_deadline`,
  `test_three_independent_timeouts_poison`, `test_killed_child_leaves_no_partial_result`,
  `test_never_self_verifies`, `test_byte_emitter_refuted`, `test_two_lineages_asserted`,
  `test_user_data_single_step`, `test_outbox_survives_restart`, `test_idle_only_admission`.
- **U125. Integrator pass ✔ (`86b9d6d`, `fe9d563`; walkthrough `docs/plans/2026-09-21-grid-of-one-walkthrough.md`).** Reconcile the names each slice assumed against what landed:
  `objects.open_store`; `tasks.registry.execute`/`stamp`; `tasks.results.*` and
  `results/<task_id>.index`; `PythonCanary` registration in `core.CANARIES`;
  `log.frontier.derive` as used by `publish`; the VERIFIED body = `Verification` field names;
  `put_path`/`get_path` streaming on every store; the lane entry-point group (`grid_lanes`
  assumed `agentdecompile_grid.lanes`, `tasks.registry` discovers
  `agentdecompile_grid.task_kinds`); the object tag vocabulary (the lane classes tag outputs
  `public`/`restricted` — the tag is a mirror class `record`/`image`/`toolchain` and no code
  path may read it as a permission; rename). Then one end-to-end "grid of one" cycle on a
  laptop: `adgrid publish` from a store snapshot → `adgrid join` (attach-first) works the
  frontier → a verifier under a second key verifies → `adgrid view materialize` reproduces
  the rows; a documented walkthrough under `docs/` (generic names only). Acceptance (named):
  `test_grid_of_one_cycle_publish_work_verify_materialize`,
  `test_every_assumed_name_resolves` (one import per reconciled name),
  `test_cli_join_attaches_never_starts`.

**15.1 Adapters — each unit turns a declared adapter into a working one (listed in the order
of the interfaces they unblock; interleaved with Phases 2–14 per the Recommended order)**
- **U158. Basis projection per kind** (`tasks/registry.py`, `core.py`): `basis_fields(kind)`
  declared per kind as basis field paths (the basis object above is the vocabulary),
  `basis_projection(kind)` inside the task id, the full `basis_hash` on every record;
  publish, verify and consume refuse on a projection mismatch by name (design §2.8 table;
  never redo completed work). Acceptance: `test_basis_projection_declared_for_every_kind`,
  `test_pin_policy_change_leaves_compile_ids`,
  `test_toolchain_change_rekeys_only_compile_kinds`.
- **U126. Ed25519 as the default signer; invites, revocation, rate limits**
  (`log/signing.py` ed25519 working; `worker/identity.py`): invites signed by operator or
  fleet keys, a revocation-list object any fleet key may extend, per-key rate limits, 7-day
  key lifetime renewed after a canary re-run, the two-lineage invariant asserted.
  Acceptance: `test_ed25519_default_signer_roundtrip`, `test_invite_roles`,
  `test_revoked_key_ignored`, `test_rate_limit_65th_record`, `test_key_lifetime`.
- **U159. S3-compatible objects, log and heads with conditional PUT** (`objects/s3.py`,
  `log/s3.py`; heads by `If-Match`; design Q1, register R13). Acceptance:
  `test_s3_conditional_put_is_noop_on_existing`, `test_s3_heads_cas_conflict_named`,
  `test_heads_rebuilt_by_chain_scan_equal_live`.
- **U160. Static mirror index + rsync** (`objects/static.py`; index publication; refresh).
  Acceptance: `test_mirror_list_reads_published_index_and_names_missing_index`,
  `test_mirror_put_is_read_only_by_name`.
- **U161. Peer HTTP read endpoint** (`objects/peer.py`, `transport/peer.py`; fleet nodes as
  mirrors, design §6.1). Acceptance: `test_peer_reads_verify_and_list_uses_json_endpoint`,
  `test_peer_put_refused_unless_allow_put`, `test_peer_token_never_in_describe`.
- **U162. HTTPS outbound-only transport with presigned write-once PUT** (`transport/https.py`;
  size-capped, scoped to the expected output hash; the head CAS is the only live RPC; no
  inbound port on any node). Acceptance: `test_https_presigned_put_is_write_once`,
  `test_https_no_inbound_port_required`, `test_cas_contention_backoff`.
- **U132. Toolchain manifest identity** (`grid_lanes/toolchain.py`,
  `source_parity_synthesize.py:21705-21722`, `source_plugin_runner.py:369-394`):
  `toolchain_identity_hash` = sha256 of the sorted (relative path, content hash) pairs of a
  declared manifest — no host state, no install path, no file times; the canary fingerprint
  stays outside the identity. Acceptance: `test_toolchain_identity_path_and_mtime_free`,
  `test_toolchain_identity_ignores_files_outside_manifest`,
  `test_toolchain_identity_changes_on_one_manifest_byte`.
- **U163. Toolchain canary** (`worker/canaries.py`, `grid_lanes/compile.py`): declared
  manifest hash + probe TU compiled and masked-COFF-hashed against the pinned value;
  persistent wineserver probe; per-node concurrency cap measured; a fetched toolchain
  object passes the same canary as an owned install. Acceptance:
  `test_toolchain_canary_pins_masked_coff`,
  `test_toolchain_canary_mismatch_refuses_lane_by_name`.
- **U164. Analyzer canary**: a fixture packed program opened headless, function-inventory
  hash equal to the pinned value; owned install or fetched bundle. Acceptance:
  `test_analyzer_canary_pins_inventory_hash`, `test_capability_only_after_pin`.
- **U165. Parity canary**: hash-pinned checker binary + fixture pair yielding the pinned
  receipt; `objdump` a declared capability with a named refusal (`mkobj-target`).
  Acceptance: `test_parity_canary_pins_receipt`, `test_parity_checker_missing_refuses_by_name`.
- **U129. Cloud providers with `fleet up/down/status/replace`** (`fleet/providers.py`:
  `oci`, `hetzner`, `aws`, `gcp` working; credentials via the secret-session path, never a
  prompt; the fleet manifest as objects; lane placement by canary, never by tier).
  Acceptance: `test_fleet_up_records`, `test_down_recorded`, `test_fleet_status_reads_pointer`,
  `test_arm_node_fails_toolchain_canary_offered_no_toolchain_task`.
- **U166. Container sandbox** (`worker/sandbox.py`: a container as one packaging of the
  same toolchain object, never a requirement). Acceptance: `test_process_group_killed`,
  `test_container_sandbox_declared_or_working_by_name`.
- **U167. Idle policies** (`--idle-only`: battery, user-activity and load adapters; a
  declared policy idles by name). Acceptance: `test_idle_only_admission`,
  `test_idle_policy_battery_declared`.
- **U130. Observer-path fixes** (design U130; prerequisite for the browser lane).
  Acceptance: `test_200_browser_connections_one_snapshot_201st_refused`.
- **U154. Browser lane** (design U154: module worker, wasm parity, rewrite proposals under
  the contributor's own key; never offered a toolchain or analyzer task because its canaries
  cannot prove those capabilities). Acceptance: `test_browser_parity_receipt_matches_native`,
  `test_browser_one_click_stop`.
- **U131. Measurements** (design U131 (a)–(h): R12 headless open and pack size, O2
  masked-COFF equality over ≥ 500 TUs, `/P` equivalence, link wall, per-scan window cost,
  one real search, native vs wasm parity, attempts per function). Acceptance:
  `test_measurement_receipts_exist_for_a_to_h`.
- **Toolchain lanes — U133 compile-attempt adapter (persistent wineserver, per-node cap),
  U134 repair chain as a derived graph, U135 content caches + link task, U136 parity lane**
  (design 15.1). Acceptance: `test_compile_same_tu_same_task_id_two_nodes`,
  `test_compile_infra_writes_nothing`, `test_repair_chain_replays_identical_tu_hashes`,
  `test_link_cache_hit_spawns_no_linker`,
  `test_parity_stub_never_returns_yields_timeout_within_budget`.
- **Analyzer lanes — U137 import + analysis slices + deterministic two-key pin (the A2.2
  spike first), U138 JVM-free facts + References reader, U139 decompile chunks with affinity
  + knowledge view, U140 H2 closure + object tags, U141 similarity signatures and queries**
  (design 15.2). Acceptance: `test_analysis_slice_checkpoint_is_packed_program`,
  `test_sliced_vs_monolithic_inventory_hash_recorded`,
  `test_pin_divergence_lexmin_deterministic`,
  `test_decompile_chunk_partial_plus_continuation_equals_full`,
  `test_bsim_sigs_without_template_refused`.
- **Identity lanes — U142 match cascade decomposed (per-round checkpoint first), U143 delta
  binders (logical shards + identity merge emit verified delta objects that the view applier
  binds into `identity`/`logical_function`; never a direct identity write), U144 cross-place
  as placement objects** (design 15.3). Acceptance: `test_match_shard_equals_monolithic_scores`,
  `test_match_shard_two_outputs_refute_never_merge`, `test_logical_rows_deterministic`,
  `test_identity_delta_applied_only_from_verified_records`,
  `test_placement_body_hash_identical_across_recipients`.
- **Residue lanes — U145 permuter cases + search shards, U146 rewrite adapter + win
  verifier, U147 text permuter generate/score split** (design 15.4). Acceptance:
  `test_search_shard_p99_under_35s`, `test_rewrite_two_bases_two_task_ids`,
  `test_text_permute_generate_needs_no_toolchain`.
- **Export and relink lanes — U148 export slices/shards/merge, U149 window index + shards,
  U150 backfill as records (delta binder: `image-registered`/`basis-stamped` records bound by
  the view applier, never a direct store write), U151 verify-determinism as a receipt gate +
  the anonymisation grep, U152 place-check/splice/join, U153 closure-based terminal receipt**
  (design 15.5). Acceptance: `test_export_merge_byte_identical_to_single_process`,
  `test_window_results_equal_unique_window`,
  `test_backfill_replays_identically_on_both_surfaces`,
  `test_object_store_has_no_slug_or_repo_path`, `test_image_join_reproduces_legacy_rebuild`,
  `test_terminal_receipt_from_cache_hits_accepted`.
- **U168. `corpus-attest` lane** (after U28x): the attest verb as a `subprocess-verb` kind
  over a copy-on-write snapshot, receipts as objects, a hang = a named timeout record.
  Acceptance: `test_attest_declared`, `test_attest_lane_hang_is_timeout_record`.
- **U169. Similarity applier** (`view/similarity.py` working: verified `bsim-merge` objects
  reach the index through the commit verb; the index is a view). Acceptance:
  `test_similarity_view_rebuild_lists_same_programs`.
- **U170. Compaction pruning policies** (`log/compaction.py`: retention policies, prior-basis
  archive snapshots, the 1 GB-node resident-set target). Acceptance:
  `test_snapshot_plus_tail_frontier_equals_full_replay`,
  `test_prune_refuses_uncovered_records`.
- **U155. Bundle manifest stub; U156. Grid determinism and chaos harness** (named only:
  lease expiry mid-task, duplicate delivery, head loss, disconnected outbox, single-field
  basis change mid-run, CAS starvation, verifier livelock — the frontier stays consistent
  and no verified record is ever written by a producing key); **U157. Retire the
  coordinator** (design 15.6). Acceptance: `test_bundle_tree_byte_identical_under_one_basis`,
  `test_chaos_frontier_consistent_never_verified_by_producer`,
  `test_workbench_prepare_draws_receipts_starts_nothing`.
Prerequisites from earlier phases (design §8): 3b/U54 basis and per-binary `basis_hash`,
U65, U66 (projection reading), A4 real-corpus admission, R1.

## Feasibility determination

| Capability | Feasibility | Deciding factor |
|---|---|---|
| Portable function resolution on **known** builds | **High** | The full identity cascade runs offline over the whole corpus; the runtime reads precomputed instances. Coverage = cascade coverage, which the existing matcher already achieves for most functions and Ladder A raises further. |
| Portable function resolution on **unknown** builds | **High with U91**, Medium without | The runtime needs a decoder for structural members; embedding one is routine (safetyhook ships Zydis; the detour engine already has a length-disassembler). Without it, only byte/anchor/caller members run. |
| Inlined / split functions | **High (as regions)** | Region sites are locatable by fragment search; they cannot be hooked *as the original function*, only as the region — which is the physically correct answer. |
| Universal payload placement (caves) | **High** | Executable allocation (U101) makes placement always possible where the process allows exec allocation; in-image caves via candidates + slack + live discovery cover the residency-constrained cases. The only true failure: no exec allocation *and* no slack, which is rare and named per build. |
| Struct fields on stripped builds | **High** | Accessor decode gives exact per-build offsets from any resolved accessor; constructors give ordered offsets; ambiguity remains only for same-size same-type field swaps with no accessor evidence — a genuine tie, recorded as such. |
| Data roots | **High** | Xref-from-function plus the inverse access-instruction scan resolve nearly everything a function touches; initializer decode and pointer chains cover the rest; RVA is the floor. |
| VTable / dispatch slots | **High** | Slots matched by method identity, not index — exact under reordering. |
| Cross-platform correctness (endian, widths, calling shape) | **High** | All are format/compiler facts recorded per build (U69) and consumed by adapters; nothing here is inference. |
| Determinism (byte-identical re-runs) | **High under a declared basis** | Ordering fixes (Phase 0) + decode-derived hashing (U6b) + basis recording (U54). Invariance *across* basis changes is impossible for any tool and is handled by re-baseline (U25). |
| Learn-the-build loop | **High** | Runtime report → corpus ingest is plumbing; determinism holds because the report is a pure function of image + pack + basis. |
| Byte-identical whole-image rebuild | **Medium** | Real for many targets (dtk/reccmp-class projects prove it); linker-layout reproduction is the open engineering problem STRATEGY names. Program scope, not this plan's. |
| Semantic *meaning* labels ("this is max health") | **Low as derivation, High as evidence** | Shape, location, identity and *usage context* are deterministic; the label is an annotation with provenance (U26). The pipeline gives the mod author the exact evidence to name it, deterministically. |
| Packed / anti-tamper-protected images | **Medium** | Post-unpack scanning works where an unpacked image is obtainable (the corpus has the unpack path); resident payloads under active integrity checks require the check's range to be known (U38/U86) — refused otherwise, by policy. |

**Net:** every workflow the user described is feasible to a high degree with the units in
this plan; the residue after the ladders is small, named per build, and shrinks as the
corpus learns. The two genuinely open problems — exact whole-image placement and semantic
naming — are program-scope and annotation-scope respectively, and the plan does not
pretend otherwise.

## Genericity: cost by target class (no product names — classes only)

| Target class (format × arch × toolchain × engine) | Cost | What it needs |
|---|---|---|
| **Sibling builds of the current engine family; 32-bit PE; MSVC** | near-free | Reuses the existing path end-to-end. |
| **Same family; 64-bit ELF x86_64** | one-check | `is_elf_i386` → `is_elf_binary` (U20); the `roundtrip` triple already exists. |
| **Same family; XBE (x86-32)** | moderate, format-only | XBE mapper + container detection + XOR-decoded entry/thunk (U7b); kernel-import naming lives in the L3 data pack. Same x86-32 code, so signatures/ABI/L2 reuse. XBE mapper landed (`exact_universal.py:174`); container detection remains. |
| **Different engine; 32-bit PE; possibly non-MSVC / non-thiscall** | moderate | ABI adapter (U18) + masked signatures (U4) + an L3 data pack for its script/VM API map. |
| **Different engine; PE32+ / x86-64** | real adapter work | Exercises every hardwired assumption at once: mapper rewire (U7), x64 ABI (U8+U18), x64 masked signatures (U4/L2), x64 compiler profile (U19), cave policy (U12), and the runtime host's arch gating (U13b). |
| **Same family; Mach-O (x86/arm64)** | moderate | `macho_mapper` + `machostabs` already exist; needs the load-base fix (U7) and an L2 for arm64 detours. |
| **Any family; PIE ELF / rebased image** | moderate | Load-base reconciliation (U7): file-header base ≠ loaded address. Masked signatures are position-independent by design; anchor-relative locators must be base-relative. |
| **Any family; packed / DRM-protected image** | real work | Signatures and caves are computed **post-unpack only** (scan the deciphered executable region, never ciphertext); `DRM_EXCLUDED` is empty today, so the class has no representation — add unpack-state as a first-class binary attribute and refuse to sign/cave a packed image. |
| **Any family; section overlays / multi-image containers** | moderate | The container registry already models overlays for one handheld format (`containers/nds.py`, ARM9/ARM7 + overlays); generalize overlay-aware VA→offset and per-overlay coverage. |
| **Any family; fat / multi-arch binaries** | moderate | Per-slice entities keyed by (arch, slice); one pack, per-slice coverage. |
| **Managed / IL (.NET, JVM, bytecode)** | separate track | VISION names managed/IL lifters in scope; signatures here are IL-level, not native — an L1 variant, not the native masking pipeline. Out of scope for this plan; do not fake coverage. |
| **ARM / other native ISA** | refused until | The handheld container already decodes ARM9/ARM7 images, so "refused" applies to *signing and caving*, not loading: needs an L2 adapter plus the U12 unreferenced-data validation (literal pools in `.text`); refuse loudly, never silently drop. Today a 32-bit ARM ELF is mislabeled x86 (`targets.py:131` maps `EI_CLASS`); U20 reads `e_machine`, then refuses. |

`roundtrip.py` (whole-image byte substrate) already works for any arch Ghidra handles.

## Honest limits
- The runtime substrate (RUNTIME_REUSE.md, dated 2026-09-20) is an **integration contract,
  not a proven pipeline** — no fresh export→resolve→call run is established. Treat pack v2 as
  the contract to fill, and validate resolve/install/observe as separately authorized runtime
  work.
- A universal signature/cave is not guaranteed. Ship **coverage, not universality**; mark a
  site/cave `resolvable on {A,B,C}, ambiguous on D, absent on E`.
- Runtime observations refine names/types/behavior with provenance; they never promote source
  parity or count original bytes as recovered C.

## Recommended order of first units
0. **Step 0 ✔** (`0256ca0`; 119 differing files). Open: the
   `containers/{detect,models,nds,registry}.py` split was not imported (canonical's monolith
   is newer — decide whether to re-import); `source_parity_synthesize.py` is 0 bytes — treat
   as truncated and re-import before U42.
1. **Phase 0 (D1–D7) + U5c (both gates) ✔** (`16f0823`, `a0db224`, `ce5e8d4`, `e47d387`,
   `5225722`, `559dc46`, `0c50f69`). Gate wording: canonical sorted row-set equality
   including `match.id`.
2. **U7 + U7b ✔** (`f935db7`). Remaining: `exact_corpus.py:121` still calls `pe_mapper`
   directly.
   - **2b. Re-anchor the plan** (Step 0 item 5) against the implementation branch.
   - **2c. U21c → U21a → U21b** — the name gate is clean before any further doc or code
     lands.
3. **U22 ✔** (`f5f6a88`). Remaining per U22's bullet (DDL ownership, delete registry,
   migration 2).
   - **3b. Basis hardening** — the normative basis object (Determinism section) and
     migration 2 (`basis_hash`, `decoder_revision`, `analyzer_version`) **✔** (`5bf8a11`);
     D8, D9 and harness (o) ⏳ (`unit/d8d9-harness`); harness (p) waits for U30's `stable_key`.
   - **3d. U25 re-baseline verb ✔ (`2dbd467`, `ca7fdb6`)** — `corpus rebaseline` records the supersession in `basis_supersession` (migration 3) and re-stamps in one transaction; divergence re-evaluation stays the U14 slot `RecomputeDivergence`; `ALGORITHM_VERSION` is now `phase0.3+key:content_sha256+dep:content_sha256_16` (A3). Attested on a copy of the real store: refuses (exit 2, hashed identities) until A4 admission scopes identity rows to admitted builds — the 60 placeholders block it today. Load-bearing since 3b: any package-constant change or a
     `PENDING_FIELDS` removal makes every stamped store refuse with "re-baseline", and the
     backfill fills NULLs only, so the verb that re-stamps under a recorded supersession must
     exist before the first such change (hindsight, charter §4).
   - **3c. U28x inline-CLI attestation** — `corpus attest` against a copy-on-write temp
     copy of the real store, wired into the loop; every later wave compares its receipts
     (U28 (r)) and a hang is a named failure, never a wait.
4. **U1–U3 + U1b ✔** (`b58a2e1`, `b271ba6`) — v1-shaped; `--format v2` stays off until U23
   (the v1 loader matches the format string exactly and any other pack falls through to
   the legacy parser).
   - **4b. U19a data-pack registry** + pack hashes in the basis.
5. **U82 + U69 + U20 (`e_machine`) + U70** — before any further `binary` column lands and
   before any cross-build donor runs (U70 gates on U69).
6. **U18 + U8/U11 + U61/U63** — donors now platform-gated; the CLI tree's structured
   storage collector, architecture-agnostic, unblocks x64 ABI.
7. **U28 (a)–(f) only**, wired into CI; every later unit lands the acceptance test named in
   its own bullet.
8. Then, in dependency order: Phase 2 (U4 decoder pin first, then U6b, U48, U50, U52) →
   **U30** (`logical_entity`; status-set owner) → Phase 9 (U40–U45) → Phase 5 (U14–U17b,
   U39, U53) → **U79** → Phase 8 (U30–U38 incl. U32a–d; U33 now valid after U79) →
   **U23/U46** (mask-aware `find_unique`, refuse-on-unknown format) → Phase 4 (U12 into
   `caves[]`, U13, U13b) + U24 + U55–U60 → Phase 11 rest (U67–U86, incl. **U13c** beside
   U67) → Phase 6 rest (U19) → U25–U27, U62–U66 → **Phase 13** (U91–U103) → **Phase 12**
   (U87–U90; U88 after U13c) — the terminal deliverable; `export-bundle` byte-identical
   across two runs under one basis is the whole plan's acceptance.
9. **Phase 14 surfaces** — U104 first (H5), then U105, U110, U111, U106–U109, U112. Both
   surfaces draw the bundle's readiness matrix, residue and receipts; "surfaces phase
   landed" is part of the goal's done definition.
10. **Phase 15 distributed compute** — grid skeleton (U120–U125) then adapters interleaved
   with the remaining phases. U120–U124 ✔ landed as a walking skeleton (charter §6c;
   `d8447f6` … `a4e4aca`, hindsight: built out of order because the skeleton costs hours
   and unblocks every lane); **U125** (integrator, the grid-of-one cycle) follows U104/H5
   directly. The adapters land as units beside the phase whose interface they serve: U158,
   U126, U159–U162, U132, U163–U165, U129, U166–U167 with steps 5–7; U131 and the compile
   lanes U133–U136 with U62–U66; the analyzer lanes U137–U141 with Phase 2/U25; the
   identity lanes U142–U144 with Phase 8/U30; the residue lanes U145–U147 after U136; the
   export and relink lanes U148–U153 with Phase 12; U168 `corpus-attest` right after 3c
   U28x; U130/U154 with Phase 14; U169, U170, U155–U157 last. "The grid skeleton runs a
   grid-of-one cycle; adapters landed" is part of the goal's done definition.
All of 1–7 are additive and testable on a temp copy of the store; nothing touches the
working store until its determinism and migration receipts are green. Every unit is
built by subagent-driven development against this plan, one bounded file scope at a
time, with the acceptance test named in its own bullet (U28 for the cross-cutting gates).
