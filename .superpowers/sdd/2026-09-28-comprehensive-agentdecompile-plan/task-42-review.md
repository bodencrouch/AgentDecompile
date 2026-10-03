# Spec Compliance

- **Issues found.** The bounded staging/publication protocol is implemented, but valid Vite asset URL postfixes are misidentified as missing files (T42-R1). The new regression source also collides with the existing test runner (T42-R2). Counts: **0 Critical, 2 Important, 0 Minor**.
- **Cannot verify from source:** locked-dependency build/type compatibility, executed regression outcomes, installed files, browser lazy loading across rollout, both asset aliases, and unchanged live consumer/reloader identities. These intentionally unrun gates remain open; their absence is not an additional implementation finding.
- Scope: owned-path package from `c5c191e091e922cedf0d838e20c438f04b30e12b` to `1cdfe46360bb5d9352d2d9087595bd4aaae34cee`. Python readers/routes and other owners' source are outside the diff and unchanged by this slice.

# Strengths

- `frontend/package.json:8` and `frontend/vite.config.ts:144` put the standard build through private staging and then publication; `/react/` remains the base. No backend API or runtime discovery was added.
- `frontend/vite.config.ts:10` collects Rollup import/dynamic-import/referenced-file metadata and Vite CSS/assets; `:124` installs the worker collector. `:34` inventories final output bytes. Vite **6.4.3** worker source corroborates the worker-generated outputs being emitted into the main bundle, including worker assets. [Versioned primary source](https://raw.githubusercontent.com/vitejs/vite/v6.4.3/packages/vite/src/node/plugins/worker.ts)
- `frontend/scripts/publish-react.mjs:71` verifies file digests, sizes, inventory and reference membership and snapshots buffers before mutation. The explicit trusted-local-bundler/cooperating-publisher assumption is appropriate; this is not an untrusted artifact or hostile ancestor-directory defense.
- `frontend/scripts/publish-react.mjs:139` uses an exclusive destination sibling lock, `:151` preflights same-name conflicts, and `:166` installs complete assets with non-overwriting hard links. Old chunks are retained and no rollback deletes prior assets.
- `frontend/scripts/publish-react.mjs:195` switches the entry only after asset verification and fsync; `:196` records commitment immediately. `:202` distinguishes post-rename uncertainty, and `:208` attempts all cleanup actions while preserving the actual entry state.
- `frontend/scripts/publish-react.test.mjs:122` expresses pre/post-commit fsync refusal semantics; `:180` includes a real Vite fixture for lazy JS, worker, CSS/font and Wasm emission. These are useful regression sources, not executed receipts.

# Issues

## Critical

- None.

## Important

- **T42-R1 — Normalize URL postfixes before matching emitted files.** `frontend/vite.config.ts:23`, `:49`, `:122`: `renderBuiltUrl` records its filename verbatim, but Vite can pass a file plus URL query/fragment. In locked Vite **6.4.3**, `asset.ts:87–96` constructs `filename = file + postfix` before calling the output URL hook; `build.ts:1335–1341` forwards that value unchanged. Thus a valid emitted `assets/icon-<hash>.svg` referenced as `./icon.svg?url#symbol` is also recorded as `assets/icon-<hash>.svg#symbol`, and line 49 refuses the complete generation. Preserve the URL in emitted code, but normalize only the dependency identity to its disk path before membership checks. Add positive real-bundler coverage for fragment/query-bearing asset URLs and preserve missing-file refusal. This is a conditional valid-input bug; the focused source check found no current application call site using such an emitted URL, so no current standard-build failure is claimed. [Vite 6.4.3 asset implementation](https://raw.githubusercontent.com/vitejs/vite/v6.4.3/packages/vite/src/node/plugins/asset.ts), [Vite 6.4.3 output URL hook](https://raw.githubusercontent.com/vitejs/vite/v6.4.3/packages/vite/src/node/build.ts)

- **T42-R2 — Keep Node regression files out of Vitest discovery or use Vitest consistently.** `frontend/scripts/publish-react.test.mjs:3` imports `node:test`, while `frontend/package.json:10` runs `vitest run`. No Vitest-specific config or exclusion is present in the frontend inventory, and the changed Vite config adds none. The file matches locked Vitest **5.0.1**'s default `**/*.{test,spec}.?(c|m)[jt]s?(x)` include and is not excluded. Consequently the standard frontend test command discovers a file whose tests register with Node's runner, outside Vitest's suite/lifecycle; it can also start the nested bundler fixture during collection. Either use the project's Vitest API/lifecycle or give the standalone Node suite a non-Vitest-discovered filename plus an explicit Node invocation. Do not run either under the current mission; first correct the source integration. [Vitest 5.0.1 defaults](https://raw.githubusercontent.com/vitest-dev/vitest/v5.0.1/packages/vitest/src/defaults.ts), [maintainer explanation of distinct runner contexts](https://github.com/vitest-dev/vitest/discussions/6482)

## Minor

- None.

# Assessment

- **Task quality: Needs fixes.** The local-filesystem publication protocol has clear ownership, additive retention, entry-last atomicity and honest post-commit error semantics. Correct the two bounded integration defects before approving this source slice; execution and live acceptance remain independently open.
- Checked: brief, implementer report and supplied owned-path diff. The initial tool output truncated the helper/package hunks; only those missing hunks were fetched again. A subsequent diff scan extracted line numbers only.
- Named external checks: (1) metadata hook compatibility and URL identity — inspected the lockfile selecting Vite **6.4.3** / Rollup **4.63.1**, then official Vite **6.4.3** worker, asset and output-hook source; (2) regression runner discovery — inventoried frontend config filenames, checked lockfile Vitest **5.0.1**, and read its official versioned default include/exclude definitions and maintainer runner guidance. A requested versioned runner source URL returned 404 and supplies no evidence. No broader codebase crawl occurred.
- Performed no tests, builds, type checks, syntax reruns, project imports, application scripts, live publication, service/process/catalog operations, commits or subagent dispatch. Only this report was written.
- Path shorthand above: `frontend/` is `src/agentdecompile_recovery/corpus/dashboard/frontend/`.
