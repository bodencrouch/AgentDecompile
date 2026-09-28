# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

```mermaid
flowchart LR
  substrate[Substrate] --> corpus[Corpus pipeline]
  substrate --> reconstruct[Single-binary reconstruct]
  corpus --> identity[logical_id]
  identity --> calib[Global calibration]
  calib --> floor[Assembly floor]
  floor --> ghidra[Compiling Ghidra C]
  ghidra --> xmatch[Cross-place]
  xmatch --> leftover[Leftover AI]
  leftover --> bytes[Byte accuracy]
```

## Binary-as-context substrate

### Substrate
The product surface that turns opaque compiled/packaged artifacts into navigable, provenance-anchored evidence agents can compose — distinct from any single recovery pipeline.

### Dismantling
Breaking delivery formats (installers, archives, app trees, binaries) into inspectable layout trees and extracted members without claiming recovered source identity.

### Acquisition bundle
A fingerprint-keyed evidence pack of address-keyed facts and conflicts from acquisition; queryable as advisory context, not as verified recovery.

### Claim boundary
An explicit statement on an artifact or tool response that limits what may be asserted (for example advisory layout vs compile+objdiff verified). Claim tiers are product policy; acceptance gates are caller-chosen.

### Matching recovery (recipe)
An optional operator path that inventorizes, synthesizes candidates, and proves functions with compile+objdiff. Useful when chosen; not the charter of the substrate.

### Corpus pipeline
The named stages preserve prerequisites while identity/calibration refine each other and parity runs continuously. Reconstruct and validate linkable regions early; compile C/C++ candidates, distribute only to compatible recipients, and verify each recipient independently. Terminal recovery still needs a fresh whole-image rebuild, contribution evidence and comparison. Never repeat valid unchanged work; invalidate only affected dependencies. [STRATEGY](STRATEGY.md) owns the contract.

### logical_id
Conceptual entity identity, separate from an implementation variant (behavior/build-specific implementation) and physical instance (standalone, inline, thunk, split or folded occurrence). The same logical ID does not make source interchangeable. One address can represent several logical entities.

### Global calibration
Minimum platform facts followed by incremental compiler, ABI and layout hypotheses at build/library/translation-unit/function scope. Recovery units need not equal compilation or comparison units. Distinct from `corpus calibrate`, which sweeps matcher score and margin.

### Assembly floor
Preserved machine-code regions with required data and metadata, emitted through a supported object or external-assembly backend. Reconstructed fixups and placement need independent validation. Floor bytes do not count as recovered source; successful linking is not image identity.

### Debug donor
The registered binary that still carries STABS or DWARF source paths. It owns the workspace folder layout. Other binaries inherit that layout through identity bindings.

### Skip-if-done
Reuse receipts and analysis whose relevant dependencies are unchanged. Revisit affected work when bytes, types, callees or analysis basis changes, or a documented uncertainty needs another view. Opening an analyzed project is not permission for blanket reanalysis; stale proposals cannot pass acceptance.

### Portable signature
An exported signature family describing a site across builds. The current exporter selects shared/majority stored signature strings and optional PE-derived expected bytes; it does not implement a universal runtime resolver. Corpus identity follows the cascade in [STRATEGY.md](STRATEGY.md), independently of local runtime byte-scan fallback. A prototype string alone proves neither portable resolution nor a safe call.

### Evidence-fusion cascade
Corpus matching that binds `logical_id` by independent channels in failover order (authentic provenance/symbols → unique exact/reloc hashes → rare refs → CFG/call-graph → BSim significance → ABI → optional second opinion → optional emulation), requiring uniqueness and a margin. Auto-accept prefers precision over recall. Structural islands stay `verify`; inlines stay `review`. Candidate generation is not acceptance. A `verify` bind is identity evidence, not objdiff-0 byte proof, and does not by itself authorize copying types or recovered source.

### Cross-build identity
The claim that two code instances occupy the same logical role / descend from the same source function. Distinct from **code equality** (identical bytes or a named normalization) and **behavioral equivalence** (same observable behavior under stated assumptions). Version tracking optimizes for identity; a patched function can change behavior and remain the same `logical_id`.

### Correspondence
A stored relation between code instances (or regions) with evidence, alternatives, status, and assumptions. Must represent ordinary 1↔1 matches, clones, inlines, thunks, split regions, and folded/aliased implementations—not only `src_addr → dst_addr, confidence=0.99`.

### Byte-window search
Copy a short unique instruction run from one image and hunt it in another. That is how a person finds a function by hand. This local scan is distinct from the corpus cascade, where unique exact/relocation-normalized evidence can be an early identity channel. A hook host may use a recorded window (`expected_bytes`) to resolve or verify a site when the VA is missing or stale.

### Leftover
A bound `logical_id` that still has assembly on disk, already tried C or failed compile, and has no `real_c`. Targeted AI and `genproject --leftover-only` only. Not a second pass over recovered source.

### Hook pack
An export from the corpus store (`corpus.export-hookpack`) that a Phasor-shaped host can load: logical site names, the preferred signature family, per-build addresses only as a cache. Game-specific names live in packs/adapters, not generic defaults. Site-key and build-profile compatibility must be checked; export completion is not runtime readiness.

### Runtime reuse
Calling or observing the original executable through a supported adapter after identity and ABI checks. This may precede full recovery. A resolved address, installed hook, successful call and observed behavior are separate claims; none proves recovered source. See [runtime reuse](docs/RUNTIME_REUSE.md).

### Cave, detour, trampoline and native call
A cave is unused executable capacity requiring a bounded patch plan. A detour redirects an instruction site; its trampoline preserves/relocates displaced instructions and returns to original code. Ordinary detours allocate trampolines without static caves. A native call invokes a typed entry with a known ABI, valid object/ownership and execution context. Finding any address does not make these operations interchangeable or safe.

### Reconstruct funnel
The one-shot reconstruct / CRITICAL_PATH stage chain for a single binary. Useful as a recipe; the corpus pipeline is how a set of binaries is recovered together.

## Flagged ambiguities

- "'Recovery' had been used for both the whole product and the matching recipe — prefer Substrate for the product motif and Matching recovery for the recipe track."

Return: [USAGE.md](USAGE.md) · [docs/INDEX.md](docs/INDEX.md)
