# Task 8.1 implementation report

Status: READY_TO_COMMIT. No staging or commits performed; controller owns Git mutations. This implements the bounded explicit-input and faithful local-observation selection slice. It does not close U8 or U21.

## Basis and authorization

Implemented against controller-provided base `d966fefcaeef5cc185de4ac6bdaa371a5ab28301` in `/home/brunner56/.codex/worktrees/6e95/AgentDecompile`. Read Task 8 brief first and the requested implementer template. The brief's concurrent execution refinement and current mission constraints override template test/commit instructions. Read repository entrypoint, usage, plans, runtime reuse and documented-solution guidance. A lightweight memory lookup supplied only source-versus-consumer evidence discipline; current brief and repository source govern this implementation.

Controller corroboration, not independently rechecked by this worker: healthy existing 8080 PID `2697197`, start time `1790595674.5226107`, start ticks `68973313`, cwd NVMe, restarts 0; loaded module source remains under MyBook revision `753d7fce`. These isolated source changes are not activated and provide no live receipt. No runtime, catalog, service, process, systemctl, recovery CLI, project import, DB query/creation, test, compiler, build or proof action was performed.

## Owned changes

- `src/agentdecompile_recovery/corpus/package_authoritative.py`: exact requested public build signature, required explicit module input flags, workspace-relative default output/ASM/database/programs layout, optional explicit config passed to existing environment-aware loader. No `__file__` or cwd-derived corpus basis remains. Existing output, including dangling output symlinks, refuses before mutation.
- Same package: opens an existing database with SQLite `mode=ro`, checks the columns it consumes and closes the reader on both success and refusal. No schema DDL, input creation or shared `db.connect()` path remains. Required input directories, canonical programs and every admitted non-DRM assembler tree are checked before output creation. Empty admitted coverage is an explicit zero-local-C selection.
- Same package: loads/deep-copies one coverage index and passes it into parsing, so source admission and manifest provenance use the same pinned historical observation basis. Current disk ledger changes after capture do not substitute a different observation by label. Candidate source/target digests, checked address, region offset/size and comparison bytes must agree with that observation.
- Same package: retains a single package-local source byte read, checks the producer-recorded digest and the existing readable-C classifier against those exact bytes, and exports those bytes directly. Parser-classified emitter shims refuse. Source edits after parsing invalidate package admission; edits after snapshot cannot alter exported bytes or recorded digest. No hashing upgrades historical unbound evidence.
- Same package: uses only the parser's checked target-region address. Conflicting source header or coverage symbol hints refuse even when the alternative is a canonical function. Legacy unique-byte placement fallback is removed from this local-observation lane. Duplicate selected addresses remain explicit refusals. Selection is restricted to listed non-DRM canonical binaries so counts cannot include unmapped/nonexported candidates.
- Same package: preserves parser diagnostics, adding the pinned historical observation when present; package refusals include source/target provenance. Metadata and generated README qualify compatibility names `verified_c`/`verified_c_count` as local readable-C selection only, describe canonical placement, keep ASM representation separate and state unavailable independent semantic/address/contribution/whole-image acceptance. No accepted ledger, recovered-byte coverage or whole-image percentage was added.
- `src/agentdecompile_recovery/corpus/ingest_recovered.py`: only an optional keyword `coverage_index` and its docstring/load branch. Existing calls retain the existing loader behavior; `None` reloads, supplied `{}` stays empty. No additional parser classification/schema changes.
- `tests/test_package_authoritative_binding.py`: new focused regression source, 14 named test functions and parameterized positive/refusal cases.
- `tests/test_ingest_target_binding.py`: one focused snapshot/empty-index-versus-absent regression source.
- This report. Controller progress/master/living/todo/briefs, cave worker edits and all unrelated changes were preserved.

## Specified regressions (unrun)

The new package regression source describes explicit synthetic basis selection, retained exact bytes/producer digests and original observations, checked anonymous address, relative ASM reference, count-to-set equality, unchanged input DB/ledger and honest scopes. Refusal cases include missing required Python arguments, `--out`-only module invocation, absent database/programs/ASM/recovered/coverage, incompatible DB, shims, unbound legacy observations, stale sources, later withdrawal, changed target, conflicting header/symbol hints, duplicate selected address, mismatched candidate observation, existing output and dangling output symlinks. Mutation cases distinguish parser-to-snapshot edits from snapshot-to-export edits and replace the ledger after its capture. Legacy unique bytes are present in the refusal fixture and cannot rescue unaccepted source. Empty supplied coverage yields explicit zero local C without recovery dispatch. Parser regression distinguishes preloaded snapshot, absent snapshot and explicit empty snapshot.

No RED/GREEN or passing-test claim exists. The sources are deliberately unexecuted under the mission restriction; future authorized execution can expose runtime/platform assumptions that static inspection cannot settle.

## Source checks performed

1. Ran `python3` with an inline standard-library-only `ast.parse` inspection of the four edited Python sources. All four parsed successfully. No project module was imported or executed and no bytecode/test/build artifacts were generated. The inspection printed package build positional `['out']`, keyword-only `['workspace', 'recovered_dir', 'coverage_dir', 'config_dir']`; parser keywords `['rejected', 'coverage_index']`; and no package call to `copyfile`, `executescript` or `commit`. It counted 14 focused package test function definitions and 5 existing parser test function definitions (including the new case).
2. Ran `git diff --check`; exit 0, no whitespace errors.
3. Ran owned-path `git diff --stat`, `git diff` and `git status --short`, reviewed the package diff and the minimal shared parser/test diff. Existing concurrent controller/cave changes were already present and untouched. New regression source is untracked for the controller to stage.
4. Ran bounded `rg` searches over package/parser/test sources and `rg -n 'parse_recovered\(' src tests scripts` for call sites. Existing production ingestion still passes both directories and diagnostics with no snapshot keyword; packaging passes explicit directories, diagnostics and the pinned snapshot. No residual installation-root constants, legacy unique-byte fallback, shared DB mutation helper or source-copy reread remain in the package.
5. Read the existing readable-source validator implementation to ensure the new gate uses the shared classifier and the specified shim fixture contains a rejected `_emit` construct. This is source inspection only.

## Self-review

Confirmed exact input API values and backwards-compatible parser keyword; removed accidental implicit-root basis and post-check copy reads. C counts are derived from the selected sets actually written. Producer observations remain unchanged, while independent acceptance is explicitly unavailable. Source-address conflicts never replace checked placement. Input DB cannot be accidentally created or schema-upgraded. Found and fixed an output-refusal edge case during self-review: resolve of a dangling output symlink could bypass checking the caller's original path, so the original destination is now checked before resolution as well as afterward. Added a matching unrun regression.

No independent reviewer was spawned. No serving-root synchronization or Git index mutation was attempted.

## Remaining gates and limits

- Full U8 deterministic portable hookpack/Lua/headers/readiness/divergence/receipt bundle and clean-host recipe resolution remain open. This slice keeps direct output writes and external relative ASM symlinks; it supplies no stage/validate/flush/rename interruption proof.
- Independent accepted-source provider, semantic target identity, VA-to-file mapping, linked-source contribution, disjoint recovered-byte accounting and current-source fresh whole-image rebuild/comparison remain open. ASM representation and selected readable C receive no new accepted-source credit.
- Tests, package execution, real consumer integration and live 8080 verification were not performed. Source parser/diff checks cannot establish those outcomes. Controller review is required before controller-owned commit; no publication is authorized.
- The invocation pins a historical ledger observation basis and parser target snapshot, rather than promising freshness after package capture. Mutations after capture do not upgrade or silently replace that observation. Physical input provenance remains in metadata, so full author-machine-path-free portability is not claimed.
- The package now refuses any missing listed assembler tree before creating output; this prevents a claimed selection whose files are omitted. Existing admitted empty ledgers remain supported and visible.
