## Spec Compliance

- ❌ Issues found: the strict qualification boundary does not reject or implement `SG_HIGHVM`, so whole-region VA-to-file binding can be wrong despite an accepted STABS witness (`src/agentdecompile_recovery/corpus/macho_semantic_witness.py:85–88,148–163`; Important I1 below).
- ✅ The remaining reviewed source implements the bounded thin-image lane: explicit known selected architecture, stored width/format contradiction refusal, same-header CPU subtype/width/endian, raw N_FUN record and bounded declaration, name/VA uniqueness, exact snapshot digest and candidate bytes, distinct recorded scope, and preserved local candidates on semantic refusal (`macho_semantic_witness.py:35–145`; `semantic_identity.py:134–190`).
- ⚠️ Cannot verify behavioral correctness, usable real-image STABS acceptance, installed consumer behavior, activation, live 8080 acceptance, fresh current-source rebuild, whole-image comparison, runtime reuse, or terminal recovery. Authored tests remain unrun. This is source review only.

## Strengths

- `src/agentdecompile_recovery/corpus/macho_semantic_witness.py:109–139` validates every declared symbol/string record before invoking the retained permissive reader. Duplicate roots are preserved for refusal rather than silently deduplicated (`semantic_identity.py:159–170`).
- `src/agentdecompile_recovery/corpus/semantic_identity.py:172–190` verifies positive full region size, exact recorded offset, exact retained bytes, binary IDs, and image digest; attribution and logical identity are not substituted for raw name evidence.
- `src/agentdecompile_recovery/corpus/semantic_identity.py:207–228,292–305` preserves the PE-only reader and adds narrow recorded dispatch. `package_recovered.py:68–107` retains source freshness/readable-C gates and calls its naming claim ingestion-time evidence. `export_run_report.py:42–53,110–117` names the actual witness scope while leaving overall success false and byte comparison unperformed.
- `src/agentdecompile_recovery/corpus/ingest_recovered.py:685–697` keeps PE counts distinct and accounts for accepted STABS. The Task8 seam is unchanged: line263 reloads only for `coverage_index is None`; `tests/test_ingest_target_binding.py:62–74` still distinguishes a pinned observation from explicit empty coverage.

## Issues

### Critical

- None.

### Important

- **I1 — Refuse unsupported high-VM segment mapping.** `src/agentdecompile_recovery/corpus/macho_semantic_witness.py:85–88` reads segment ranges and section count but never reads the segment flags at command offset52 (32-bit) or68 (64-bit). `region_offset()` at lines155–163 always treats `[vmaddr, vmaddr + filesize)` as file-backed and computes `fileoff + address - vmaddr`. Apple's [Mach-O loader header](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/EXTERNAL_HEADERS/mach-o/loader.h#L366-L369) specifies that `SG_HIGHVM` maps file contents into the high end of the VM range, with the low end zero-filled. Consequently, taking the authored fixture's segment (`vmsize=0x800`, `filesize=0x600`) and setting that flag leaves qualification unchanged, yet candidate VA `base+0x200` maps to file offset0 under the flag rather than the accepted offset0x200. A named N_FUN and matching candidate bytes at the incorrect offset can therefore produce `accepted-target-macho-stabs-n-fun`. A lower candidate VA can likewise be incorrectly treated as file-backed. This violates the mandatory exact whole-region mapping and unsupported-layout refusal contract. Read segment flags and explicitly refuse `SG_HIGHVM` for this bounded lane, or implement its mapping consistently across qualification and overlap checks. Add authored 32/64-bit regression cases with `vmsize > filesize`, including a low zero-filled address and the shifted file-backed address. No execution was performed to demonstrate the source counterexample.

### Minor

- **M1 — Seed-edge withdrawal scenario currently deletes an empty table.** `tests/test_macho_semantic_identity.py:262,286` creates `identity` but never inserts an edge before `DELETE FROM identity`. The recorded-consumer assertions are useful, but this operation does not exercise the report's claimed withdrawal scenario. Insert an unrelated seed/family edge, assert that it exists, delete that row, then check the independently witnessed candidate still resolves. Production witness source does not consult those edges; this is a test-strength issue, not an observed production regression. A focused `ingest_recovered.py` identity-write search confirmed ingress reads/deletes existing edges and does not populate this empty fixture table.

## Assessment

- **Task quality: Needs fixes.** Counts: **0 Critical, 1 Important, 1 Minor**. Spec compliance also needs I1 fixed. The core snapshot and recorded-scope separation is coherent, but unchecked mapping-changing flags undermine the central byte-to-VA proof.
- **Reviewed range:** base `2a6f49a2a5a38b016ff8a1bc6b70d28b00ab2e43`, head `000d400a5c83ea38501b5c54f47de1033652c8a5`, scoped package `task-3-review.diff` read once in sequential chunks. No Git commands or source edits were made; only this requested review report was written.
- **Focused outside-diff checks:** (1) permissive producer escaping strict bounds: `machostabs.py:55–129,150–159,198–260`, confirming symbol order, declaration splitting, and segment data retained by the parser; (2) snapshot read/hash mismatch: `targets.py:105–144,162–177`, confirming one retained byte buffer and magic detection; (3) selected metadata fields: `store.py:19–35`, confirming `arch`, `bits`, `format` and no selected CPU-subtype field; (4) Task8 compatibility: `ingest_recovered.py:245–263` and `test_ingest_target_binding.py:62–74`; (5) unsupported segment mapping: targeted source search found no `SG_HIGHVM` handling, and the read-only Apple loader header confirmed that flag's mapping semantics. The initial schema filename probe found no `schema.sql`; the actual schema is in `store.py`.
- **Remaining execution gates:** fix and source-review I1; later, when execution is authorized, run focused STABS admission/consumer cases, existing PE compatibility regressions, and the Task8 explicit-empty regression. Real retained thin-image, installed consumer, activated/live 8080, and requested fresh whole-image acceptance remain separate open predicates. No tests, suites, builds, typecheck, project imports, proof scripts, database operations, runtime/catalog/process/service actions, alternate ports, or publication were performed.
