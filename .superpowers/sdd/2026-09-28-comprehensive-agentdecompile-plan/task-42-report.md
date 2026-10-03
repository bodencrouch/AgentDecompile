# Task42.1 implementation report — staged additive React publication

Date: 2026-10-02. Assigned base: `c5c191e091e922cedf0d838e20c438f04b30e12b`.

Status: **READY_TO_COMMIT — source implementation and source checks only.** No commit or Git staging was performed; the controller owns both. U13/U42 remain open. The current runtime is a separate source root; this checkout was not activated or published.

## Owned changes

- `src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts`
- `src/agentdecompile_recovery/corpus/dashboard/frontend/package.json`
- `src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.mjs`
- `src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.test.mjs`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-42-report.md`

Other workers' changes and controller documents were preserved. No Python, routing, application root, package-data, dependency or lockfile changes were made.

## Implementation

The existing standard packaged build now orders type checking, Vite staging and publication with `&&`. Vite writes only to `frontend/dist/react-stage`, which is outside the served namespace and already covered by the repository's `dist/` ignore rule. `emptyOutDir` only clears that private staging directory. The publisher receives explicit completed-stage and destination arguments; it does not discover a runtime, execute a build, register an API or start a process.

Vite writes `react-publication.json` after bundle generation. Its schema records every final emitted file's exact byte length and SHA-256. Required references come from Rollup static imports, dynamic imports and referenced files, Vite chunk CSS/asset metadata, and Vite's rendered asset URL hook. A worker plugin captures sub-bundle dependency information before Vite emits those worker outputs as assets. Every emitted file is required even when reachable only lazily, so admission is not limited to entry imports. Missing referenced outputs fail metadata generation. No JavaScript or CSS regex scanner substitutes for bundler dependency metadata.

The metadata code follows [Rollup's output hook and chunk contract](https://rollupjs.org/plugin-development/#generatebundle), [Vite's asset URL handling](https://vite.dev/guide/build#advanced-base-options), and [Vite's worker configuration](https://vite.dev/config/worker-options). Vite's [versioned worker implementation](https://raw.githubusercontent.com/vitejs/vite/v6.0.5/packages/vite/src/node/plugins/worker.ts) was read to corroborate worker output handling. The installed dependency tree was unavailable in this checkout; the lockfile selects Vite 6.4.3, so actual locked-version hook compatibility still requires the unrun build gate.

`publicDir: false` prevents untracked public-directory copies from bypassing the emitted inventory. There is no frontend public directory in the inspected source. Build warnings refuse publication, including unresolved CSS/URL references that Vite would otherwise leave unchanged. The known complete-output chunk-size advisory remains a warning because Monaco can exceed the default size threshold. `/react/`, developer middleware and proxy routing remain unchanged.

The helper validates schema, entry shape, unique versioned asset paths, digests, lengths, complete on-disk inventory and dependency membership. It refuses traversal, non-versioned output assets, symlinks in roots or file paths, nonregular files, extra files, malformed metadata and changed/missing bytes. It snapshots verified bytes into memory before publication, so a later staging rebuild cannot alter the selected generation. Metadata describes a trusted local bundler result, not a signed artifact from an untrusted producer; application runtime/API URLs outside the build dependency graph are not deployment assets.

An exclusive sibling `.DESTINATION.publish.lock` serializes cooperating publishers per destination. Conflicting or abandoned locks are refused and never stolen. A stale lock requires manual ownership corroboration before removal. The existing destination parent must exist. Stage and destination may not overlap.

The publisher preflights all existing asset bytes, refusing same-name/different-content conflicts. New assets are written and fsynced as temporary files, then hard-linked to final names atomically without overwriting any path. Existing byte-identical assets are reused. All prior files, including lazy chunks from older entries, remain untouched. Additive assets left by interruption are safe to retain; no garbage collection or old-file rollback occurs.

Before entry publication, the helper verifies every destination asset against its snapshot, fsyncs reused/new asset files and synchronizes containing directories from leaves upward. It then writes and fsyncs a temporary sibling entry, atomically renames it over `index.html`, and fsyncs the destination directory. This preserves the selected old entry on validation, asset-copy, preparation or pre-commit failure. A failure after successful rename is explicitly `COMMITTED_DURABILITY_UNCERTAIN` with `entryState: committed`; it never claims the old entry is selected. Cleanup failures also preserve the actual entry state in their error result.

## Regression source — NOT EXECUTED

The Node test source contains isolated temporary-directory cases for:

- Complete publication, entry-last observation, retained old lazy bytes and repeated identical publication.
- Missing lazy JS, worker, Wasm and font output; changed bytes; extra files; malformed metadata; absent/traversing references; staged symlinks.
- Same-name/different-byte refusal before adding assets.
- Two overlapping publishers, refusal of the second and completion of the lock owner.
- Asset-link and entry-rename interruption, old-entry preservation and successful retry.
- Directory fsync failure before and after entry rename, checking distinct entry-state results.
- Index preparation fsync failure, destination symlink, overlapping directories and abandoned locks.
- An actual Vite build fixture with a dynamic import, worker, CSS font and Wasm URL, followed by publication into an isolated destination. A missing CSS URL must fail a subsequent build. This case is deliberately separate from synthetic metadata fixtures.

These are authored expectations, not passing behavioral receipts. The real Vite fixture invokes the bundler only if the regression file is separately authorized and executed. No test process was started here.

## Checks performed

All commands below returned exit 0 with no diagnostic output:

```text
node --check src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.mjs
node --check src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.test.mjs
python3 -m json.tool src/agentdecompile_recovery/corpus/dashboard/frontend/package.json >/dev/null
git diff --check -- src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts src/agentdecompile_recovery/corpus/dashboard/frontend/package.json
```

Read-only source/diff inspection corroborated the existing build command/output path, `/react/` base, worker call sites, dependency versions, ignored staging parent and unchanged reader/routing ownership. The allowed Python command only parsed JSON through the standard library; it did not import repository/application modules. No TypeScript check or TypeScript execution occurred.

## Self-review and remaining concerns

Self-review corrected special-file reads to check regular-file status and use nonblocking/no-follow opens; cleanup now attempts every cleanup operation even if an earlier one fails. The publisher holds validated file buffers rather than rereading staging paths while copying. New asset installation uses a non-overwriting hard link rather than rename, which would overwrite existing asset bytes. The committed state is recorded immediately after entry rename and before the final directory fsync.

The helper is deliberately for a local filesystem with hard links, same-directory atomic rename and directory fsync. Unsupported filesystem/platform operations fail; they do not silently downgrade durability. It assumes trusted parent directories and cooperating publishers: Node path-based operations are not protection against a hostile process concurrently replacing ancestor directories. Concurrent builds sharing the private stage can be refused by exclusive metadata creation/inventory or digest mismatches; publication always consumes a complete verified snapshot. There is no build scheduler or generation garbage collector.

The warning policy is conservative and may refuse future otherwise acceptable build warnings; those require examination rather than silent admission. The precise locked Vite plugin ordering, TypeScript compatibility and dependency metadata must still be exercised by the authored real-bundler case. No current build success is claimed.

Still unrun: all regressions; TypeScript checks; builds; package/install manifest comparison; browser scenarios; retrieval through both real asset aliases; an old page triggering a previously unloaded lazy feature across a real rollout; installed/source identity checks; 8080 consumer observations; complete static/React scenario matrices; standalone reloader admission/rejection and unchanged process/state identity observations. No service, catalog, process, systemctl, application import/script, live publication, installation, restart, alternate listener, push or PR operation was performed.

These remaining gates require their own current authorization and ownership corroboration. Source checks do not close installed, live, browser, reloader, recovery or whole-program acceptance.

## Fix round 1 — T42-R1 and T42-R2

Reviewed head: `1cdfe46360bb5d9352d2d9087595bd4aaae34cee`. Both important findings in `task-42-review.md` are addressed in source. Status: **READY_TO_COMMIT**, with controller-owned staging/commit and all behavioral gates still unrun.

**T42-R1:** `publicationMetadata.recordUrl` now removes the first `?` or `#` and its suffix from the disk dependency identity supplied by Vite's URL hook. It does not decode or normalize filesystem paths, modify Rollup's disk-path dependency records, alter emitted URL strings, or bypass emitted-file membership/digest/inventory checks. This matches the locked [Vite 6.4.3 asset implementation](https://raw.githubusercontent.com/vitejs/vite/v6.4.3/packages/vite/src/node/plugins/asset.ts), which supplies a disk filename plus URL postfix to that hook.

The real-bundler regression source now imports one SVG with a fragment and with a query plus fragment. It checks that both emitted URLs retain their suffixes while metadata references use the emitted disk name. It then removes that emitted SVG, expects `STAGE_VALIDATION_FAILED` with the old entry and old lazy chunk intact, restores the exact saved emitted bytes, and requests successful publication. The existing missing CSS URL build refusal remains. These are authored positive/refusal cases; none was executed.

**T42-R2:** the regression imports `test` from the project's existing `vitest` dependency and registers temporary-directory cleanup through its test context's `onTestFinished` hook. It remains discoverable by the standard `vitest run` command, with registration, async completion and cleanup owned by that runner. The [Vitest lifecycle documentation](https://vitest.dev/api/hooks#ontestfinished) was read to confirm the context cleanup API. There is no separate Node runner, exclusion, extra dependency or package-script change. The real-bundler case has an explicit 30-second timeout rather than inheriting the runner's shorter unit-test default. Earlier report references to a Node test runner are superseded by this fix.

Only these paths changed in this round:

- `src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts`
- `src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.test.mjs`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-42-report.md`

Performed checks, both exit 0 with no diagnostics:

```text
node --check src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.test.mjs
git diff --check -- src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.test.mjs
```

Self-review compared the complete owned diff against both findings, confirmed that the existing missing-reference and publication refusal checks remain intact, and changed the regression's SVG restoration to use actual emitted bytes instead of assuming the bundler copied source bytes unchanged. Other owners' source and controller progress edits were preserved. The publisher and package script did not change in this round.

Remaining limits: no tests, build, type check, repository/application import, application execution, service/process/catalog operation, systemctl, installation, publication, staging or commit occurred. Syntax checking parsed the regression module without importing Vitest or running its bodies. Actual locked-version bundling, runner lifecycle behavior, installed/browser/8080/reloader acceptance and the complete U13/U42 gates remain unverified; no additional known implementation finding is outstanding from this review.
