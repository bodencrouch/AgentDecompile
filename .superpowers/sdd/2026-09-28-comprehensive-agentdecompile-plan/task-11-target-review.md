# Task 11.2 source review

Spec compliance: **Issues found**. Code quality: **Needs fixes**.

Severity counts: **Critical 0 / Important 1 / Minor 0**.

Reviewed owned base `2590e25a5926d195f34e88b0675095cf1891e6c2` to head `24d3547fcba59ad2b3b7cd5126ccd1f24d45e360`, using `task-11-target-review.diff`. Full unit U11 remains open.

## Strengths

- `src/agentdecompile_recovery/grid_lanes/target.py:152` and `:222` authenticate bounded copied CAS inputs, derive singleton physical membership from the authenticated immutable snapshot, and recompute the corpus basis. Selection parameters alone do not establish a database association.
- `src/agentdecompile_recovery/grid_lanes/target.py:283` and `:497` derive PE machine/mapping from captured raw bytes and call the retained writer with `reference_free_only=True`; `src/agentdecompile_recovery/corpus/mkobj.py:114` refuses possible references before reaching the decoder. The C7 screening change closes the specified XBEGIN shortcut omission.
- `src/agentdecompile_recovery/grid_lanes/target.py:547` authenticates both advertised outputs, rejects duplicate/noncanonical receipt content, compares the complete expected receipt, and requests exact target plus receipt recomputation at `:590`. A receipt's stated digest does not by itself authenticate the proposed object.
- `tests/test_grid_target_binding.py:88` uses the actual object writer and independent recomputation in authored positive cases; `:256` supplies concrete helper-replacement refusal cases. These are useful regression sources, not observed passing behavior.
- `src/agentdecompile_recovery/grid_lanes/target.py:1` and the implementation report maintain the distinction between implementation consistency, producer output, independent verification, current admission, accepted source, and whole-image recovery. The owned diff does not manufacture a dashboard provider or admission authority.

## Important finding

**I1 — Add the consumed `ObjectRef.hex` accessor to the fixed loaded helper closure.**

Location: `src/agentdecompile_recovery/grid_lanes/target.py:668-669`; affected integrity use at `:164`, image/selection binding in `:222`, and receipt construction at `:439`.

The fixed grid closure fingerprints `ObjectRef.of_bytes` and `ObjectRef.of_value`, but omits `ObjectRef.hex`. The retained accessor at `src/agentdecompile_grid/core.py:60` is executable Python used to obtain the expected digest for actual CAS-byte comparisons and image/receipt bindings. `_implementation` checks that the `ObjectRef` class alias is unchanged, which does not detect replacement of a property on that same class. Replacing `ObjectRef.hex` therefore leaves the captured source hashes, enumerated loaded-function hashes, checked constants, and alias checks unchanged. The changed accessor can inherit the former implementation identity while changing the digest that the lane treats as authoritative. This violates the adopted requirement that the actually consumed byte-affecting helpers cannot inherit an old identity after monkeypatching.

Add `ObjectRef.hex` to the explicit core function list so the existing `_function` property handling fingerprints and pins its `fget`. Prepare a regression that plans first, replaces that property while retaining the same class and disk source, and requires `mkobj_target_loaded_source_mismatch` before materialization or publication. A corresponding source-only edit to the accessor should also be rejected as loaded-source mismatch. Keep this correction within the fixed lane closure; it requires no new trust framework or generic runtime attestation.

## Checks and limits

- Read the task brief, adopted contract, implementer report, and the entire owned diff in bounded sequential chunks. The verification note was reviewed within the diff. Implementer check claims were not treated as runtime evidence.
- Named external check: **fixed loaded dependency coverage**. Read the consumed core canonicalization/reference/task helpers, `determinism_basis` basis-producing functions, and `policy_tables.threshold_params`/`_freeze`. Those calls reach the explicitly listed policy modules/constants and signature-default helpers; the concrete missing core accessor is I1. No general repository crawl was performed.
- Named external check: **actual mapper contract**. Read `verify_recovered_byteexact.file_region_offset`; it enforces whole-region raw backing and overlap/cross-section refusal. The lane derives the machine/magic pair before consuming it.
- Named external check: **recompute outcomes and exception boundary**. Read `_common.verify_by_recompute`; it calls `kind.run`, compares both named refs, makes a recompute refusal UNVERIFIABLE, and leaves other infrastructure exceptions to the lane's outer wrapper.
- Named external check: **bounded local adapter contract**. Read LocalDirStore `path_for`, `size`, `put`, and adjacent integrity behavior. The lane uses its own bounded no-follow copy route rather than the unbounded/quarantining `get` path; publication compares the returned ref to the generated bytes' digest.
- Named external check: **planner admission and partition routing**. Read the retained snapshot/planning chokepoint surrounding the narrow splitter registration. It retains normal basis derivation and snapshot-subject partition assignment; target planning independently rechecks the materialized object's basis.
- Named helper check: **writer output dependencies**. Inspected the retained, unchanged body of `mkobj.build_object` outside the edited hunks to reconcile its consumed constants and `symbol_name_field` against the manifest. No changed implementation hunk was reread from the source file.
- Used a standard-library-only text parser over the supplied diff to produce exact new-side line locators. No project module was imported or executed. No tests, suites, typecheck, builds, proof scripts, database operations, compiler/decoder/runtime/catalog/process operations, Git mutation, service operations, or publication were performed. Only this review report was written.

## Cannot verify from this source review

- Actual import/loaded-source fingerprint compatibility, canonical receipt size, deterministic object/receipt reproduction, local storage behavior, SQLite cancellation, and deadline behavior remain unrun. The total proposal-read plus recomputation duration also needs its authorized runtime budget check: verification starts a deadline at `target.py:557`, while recomputation enters `run` with its own deadline at `:500`.
- The regression functions are authored but unexecuted. In particular, the positive actual-writer/recompute cases and the new accessor-replacement regression must run only in a separately authorized execution phase.
- An actual admitted snapshot/raw-image selection, qualified LocalDirStore runtime, worker/verifier capabilities, independent signing lineage, revocation/current implementation admission, persisted VERIFIED record, and owned 8080 catalog action have not been established here. A matching fixed manifest is consistency evidence only.
- General reference-bearing decoder support, exact candidate source/compile binding, full target-object parity, current accepted-source provider admission, installed consumer behavior, and fresh whole-image recovery acceptance remain separate open predicates. No success claim for any of these follows from this review.

Assessment: **Needs fixes** for I1. The raw-image/corpus/object binding and independent recomputation design otherwise align with the bounded contract visible in this diff; fix the actual loaded helper omission before treating this source slice as compliant. U11 is not complete.
