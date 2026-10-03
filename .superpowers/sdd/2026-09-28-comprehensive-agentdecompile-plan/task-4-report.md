# Task 4.1 implementation report

Status: **READY_TO_COMMIT**. The bounded source correction is complete; editing
stopped. No commit or staging was performed. Controller-supplied source base:
`bb41404123636d456862aac7c0850427b4a111af`. Controller owns Git, plan, progress,
briefs and integration; concurrent parity/matrix work was preserved.

## Scope and consumed authority

Read `task-4-brief.md` first, then the adopted
`next-linked-contribution-contract.md`, its consumed
`next-reconstruction-prerequisite.md`, `unit-4-requirements.md`,
`unit-33-requirements.md` and STRATEGY's whole-image requirements. Followed the
SDD implementer prompt template with the explicit source-only/no-commit rules
overriding its generic test and commit recipes. Memory registry guidance was
used only for the source/live distinction; current source established these
findings. No prior receipt was promoted to fresh evidence.

## Exact owned changed paths

- `src/agentdecompile_recovery/corpus/verify_direct_full_image.py`: module/parser
  diagnostic wording and receipt/terminal decision only. Preserved CLI arguments,
  generic compiler/link and local verifier calls, local diagnostic counts,
  full-file size/SHA-256 equality, fresh-work refusal, candidate/objdiff freshness
  checks, errors and negative receipt persistence. Added diagnostic `claimScope`
  and `linkedContribution`; acceptance always refuses the unavailable producer.
- `src/agentdecompile_recovery/corpus/cli.py`: only the existing vdfi parser
  block; `vdfi.mutating = True` and `vdfi.long_running = True`.
- `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py`: only
  `_active_duplicate` and `_external_pipeline_owner` action-specific work-key
  lookup/canonicalization hunks. Exact ID `corpus.verify-direct-full-image`
  reads `work-dir`. New lookup uses `(live_root() or Path.cwd()).resolve()`;
  existing rows use recorded `execution_root` with the existing root fallback.
  Direct external exclusion hints resolve db/work paths with
  `_canonical_resource_path` against that same current execution-root selection.
  Other actions keep their previous keys and resolution behavior.
- `tests/test_direct_full_image_boundary.py`: new focused regression source,
  **unrun**. Nine test functions cover the cases below with parameterization.
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-4-report.md`:
  this requested report only.

No changes to compile_link's generic `ok`, source_contribution, finish_binary,
byte_parity, parity lanes, matrix, introspection, generic job policy,
`_EXTERNAL_ACTION_CONTRACTS`, resource/release/reconciliation authority, service
or runtime state. No callback, trust flag, imported-proof input or adapter seam
was added.

## Refusal boundary

The receipt exports exactly:

```json
{
  "status": "unsupported",
  "reason": "same_build_linked_contribution_unavailable",
  "missingBindings": [
    "source_inventory_capture",
    "effective_toolchain_identity",
    "same_build_object_image_provenance",
    "linked_region_fixups",
    "final_compiled_replacement_ownership",
    "variant_binding"
  ]
}
```

This diagnostic is derived internally, never consumed as caller authority. The
exact reason is appended to errors, terminal `verified` and
`compilerProducedWholeImage` are false and the return code is nonzero.
`wholeFileByteIdentical` remains independently measured and can still be true.
Partial compilation and stub-main details remain in `build.compileLink`.

## Authored regression specifications, not execution evidence

- Otherwise successful generic link, all matching local counts and exact file
  equality still refuse terminal acceptance and retain equality/counts.
- Successful partial compilation or stub-main-only diagnostics remain visible.
- Forged success fields in link/local JSON cannot grant direct authority; the
  direct parser rejects a proposed imported-contribution argument.
- Missing candidate, differing candidate, stale candidate/local receipt,
  nonmatching local results, failed link and pre-existing work retain refusals.
- Exact catalog ID/hyphenated fields and mutating/long-running metadata remain;
  the action gains no external qualification allowlist or Ghidra writer key.
- Duplicate lookup covers both incoming/existing `work-dir`, all three active
  statuses, relative/absolute/symlink aliases and execution-root versus cwd.
  Completed, unrelated and nonoverlapping jobs remain independent; unrelated
  legacy `workDir`/`work_dir` behavior is retained.
- The external exclusion hint covers direct relative/absolute/symlink aliases
  using a synthetic proc fixture; unrelated `out-dir` behavior remains and the
  new hyphenated key is not recognized for unrelated actions.

Mocked build output and fixture process text specify refusal/hint behavior only.
They cannot establish real compilation, safe ownership or positive recovery.

## Checks actually performed

1. Read-only source/diff/call-site inspection, including introspection's
   field/metadata derivation, JobRecord.execution_root, canonical path helper,
   existing qualification allowlist and `_resource_keys` Ghidra condition.
2. An inline `python -` script imported only standard-library `ast`, `json` and
   `pathlib`, read the four owned Python sources, and called `ast.parse`.
   **All four parsed.** No project imports or source execution occurred.
3. The same source-only script used `ast.literal_eval` plus a JSON round trip on
   the literal diagnostic to check the exact status/reason/six-binding order.
   It inspected assignments for both false terminal flags, independent equality,
   exact vdfi attributes and absence from the qualification allowlist. **All
   static assertions passed.** Nine regression functions were parsed, unrun.
4. `git diff --check -- src/agentdecompile_recovery/corpus/verify_direct_full_image.py src/agentdecompile_recovery/corpus/cli.py src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py`
   returned exit 0 without whitespace errors. The owned production diff was
   read in full for self-review.
5. `git diff --no-index --check -- /dev/null tests/test_direct_full_image_boundary.py`
   returned exit 1 for the new-file difference with no whitespace diagnostics.
   The same check on this new report returned exit 1 with no diagnostics.

No tests, imports of project code, builds, typechecking, proof scripts, DB
queries, compiler, Ghidra, catalog/runtime/process/service/systemctl operations,
restarts, alternate ports or publication occurred. No executable test pass,
fresh compiler proof, live consumer activation or runtime acceptance is claimed.

## Self-review and remaining gates

Reviewed exact contract values and every changed production hunk; the change
stays within the owned direct runner/parser/action lookup boundaries. The
regression source's proc isolation uses Path.iterdir patching only, preserving
the Path class used by canonicalization. Unrelated action branches retain their
prior behavior. Source-only checks support reviewability, not executable proof.

The refusal-only correction and narrow metadata/work-key correction are ready
for controller review. **U4/U33 remain open.** A positive producer still needs
complete actual source/startup/inventory capture, admitted effective
compiler/linker/header/library/options closure, same-build object/image
provenance, verified linked placement/fixups and final compiled replacement
ownership, separately bound C+floor/max-C variants and a fresh whole-image
acceptance run. The bounded ReconstructionObservation is not direct-link
evidence. Producer-backed terminal dashboard consumption and U33 original-game
launch also remain open.

**Current safe direct action admission is unsupported/unqualified.** Work-key
canonicalization improves duplicate/exclusion hints only. No compiler/Wine
closure, source-staging write boundary, escaped/shared writer lifetime or
actual-process ownership was established. No allowlist-derived release or
reconciliation authority was granted. Those premises require a separately
owned action-local qualification/admission slice and authorized real evidence.
