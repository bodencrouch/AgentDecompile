# U13/U42 next asset rollout slice — source discovery

Date: 2026-10-02. Inspected revision: `860731e59e6cb1c20ec8f977d5486872b66dbaad` in `/home/brunner56/.codex/worktrees/6e95/AgentDecompile`.

**Finding: one missing source predicate.** The standard packaged React build must publish a fully staged, validated asset generation additively, retain previously published lazy chunks, then atomically replace `index.html` last. The current build configuration does not implement that publication protocol. This report is a proposed source slice, not implemented rollout, installed-consumer acceptance or U13/U42 completion.

## Exact source evidence

| Source | Current behavior / implication |
| --- | --- |
| `src/agentdecompile_recovery/corpus/dashboard/frontend/package.json:8` | `build` invokes `tsc --noEmit && vite build`; no publication step follows it. |
| `src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts:65` | Vite writes directly to `../static/react` with `emptyOutDir: true`. Deleting the output directory can remove old lazy chunks and the previously served entry before the replacement generation is complete. Disabling deletion alone would still leave non-atomic entry publication. |
| `src/agentdecompile_recovery/corpus/dashboard/react_api.py:26` | `ASSETS` is the same `static/react` directory beneath the serving module. |
| `react_api.py:95–128` | `_missing_entry_asset` checks direct entry `src`/`href` targets; `react_index_response` returns a visible 503/static fallback for a missing entry or its missing direct assets. This is a reader admission guard, not staged publication or lazy-dependency retention. |
| `react_api.py:451–465` | Both `/react/{asset:path}` and `/dashboard/static/react/{asset:path}` read that retained directory, with containment checks, explicit missing-asset 404, and `nosniff`. Existing readers can retrieve old hashed chunks if publication retains their paths and bytes. |
| `task-13-report.md`, “Limits and next concrete missing predicates”, item 3 | The retained reconciliation report explicitly leaves staging, atomic index publication and old lazy-chunk retention open; it does not claim `emptyOutDir` is a safe installed rollout. |

Bounded searches covered frontend configuration/package scripts, repository scripts, Python readers, relevant routing tests and CI source. No retained asset publisher was found in those paths. A different external installation process was not inspected and is not presumed absent; qualifying such a process could supersede this proposed source fix only with its exact implementation/consumer evidence.

## Existing predicates to reuse

- `/dashboard` remains the independent static default; `mode=static` renders the static workbench. Opt-in modes use `react_entry_redirect` (`router.py:104–118`). There is no source reason to change either application root or remount preparation effects.
- `react_entry_redirect` preserves `request.url.query` verbatim and leaves the fragment out of `Location` so a browser can inherit it (`react_api.py:136–141`). That mechanism carries `window=wb-*`, `binary_hash`, `function_id`, `project_id` and repeated query values without a key whitelist. `/dashboard/static/react`, its trailing-slash form, and its `index.html` alias all use it (`react_api.py:413–417`).
- Static browse compatibility redirects keep all query pairs except the intentional `window`/`partial` overrides (`router.py:250–257`). They also omit a replacement fragment. This report does not assert an audit of every historical alias in `unified_pages.py`.
- `_static_fallback_url` keeps repeated selection/query values while setting `mode=static`; the failure page copies `window.location.hash` onto its fallback link (`react_api.py:68–93`, `:131–133`).
- `tests/test_react_canonical_routing.py:18–75` already expresses canonical/deep entry routes; raw/repeated query preservation; fragment-free redirect Locations; retrieval through canonical and legacy asset paths; missing JS/CSS/worker/Wasm refusal; traversal/backslash/escaping-symlink refusal; visible incomplete-build refusal; and selection/fragment-aware static fallback. The query fixture uses `binary`, repeated `program`, and `addr`, so it is not an executed or exhaustive receipt for the specific U13 selection keys.
- `tests/test_dashboard_routes.py:164–205` retains missing/incomplete delivery and security-header assertions. `tests/test_dashboard_actions.py:192–258` retains static workbench/default-window behavior. These are existing regression sources, all **unrun here**; historical expectations do not close current acceptance.
- `task-13-fix-r1-review.md` approves the bounded reconciliation correction and explicitly leaves browser, rollout and installed/reloader gates open. The previously reviewed WorkstationApp root, `/react/` base and package-data declarations require no repeat rewrite for this slice.

## Proposed implementation ownership

An implementation owner should take only:

1. `src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts`: change packaged build output to a private staging directory outside `../static/react`; keep `/react/` as the emitted URL base and keep current routing/dev middleware intact. `emptyOutDir` may clear only this staging area.
2. `src/agentdecompile_recovery/corpus/dashboard/frontend/package.json`: route the existing packaged `build` through the publisher after successful type-check/build validation. The standard command must not bypass staging.
3. One new publication helper, `src/agentdecompile_recovery/corpus/dashboard/frontend/scripts/publish-react.mjs`: expose a narrow local-file interface receiving a completed staged directory and the existing served `../static/react` destination. It must not import application Python, register a backend API, start a server, infer the serving source root or deploy automatically.
4. Corresponding focused publication regression source, only during a separately authorized implementation/verification run. Existing routing tests are reused; no new router, package root, frontend root or backend is needed.

The helper is an implementation/build reference. Adding it would not authorize executing the build or copying assets into the active runtime under the current mission. The helper location/API above is proposed, not an existing executable interface. A Vite publication hook implementing the same contract can be substituted only if the owner keeps equivalent staging, validation and failure boundaries; changing `emptyOutDir` alone is insufficient.

## Compatible publication and refusal contract

- Validate the complete staged emitted asset set and its local references before mutating the served entry. Include lazy imports, CSS assets, workers, Wasm and fonts; the current reader's direct entry checks are insufficient as a publisher validator. Reject missing or escaping references, traversal/escaping symlinks, malformed output and incomplete staging with a named error.
- Publish new content-named assets under their existing `/react/assets/...` paths first. For a destination path already present, accept byte-identical content and refuse differing content rather than overwrite bytes an open browser may still require. Preserve all prior hashed files, including old lazy chunks; garbage collection is a separate future policy.
- Write the new entry to a temporary sibling on the destination filesystem and atomically replace only `index.html` after every required asset is available. A failed build, validation, asset copy or index preparation must leave the old entry usable. Additive new assets left after an interrupted attempt are safe to retain; do not roll back by deleting old files.
- Keep one publisher per destination. Refuse conflicting publication rather than interleave generations. Keep staging outside the served namespace and destination-path checks inside the helper; do not make caller-supplied paths a route surface.
- Preserve existing URLs, static fallback, redirect query/fragment behavior, security/cache headers and package-data contracts. No Python reader edit is required for the smallest slice: retained files remain reachable through the existing handlers.
- Review pre-switch interruption, failed validation, same-name/different-bytes refusal, racing publication refusal and repeated identical publication against old/new entry and chunk bytes. Source assertions must not be presented as installed/browser proof.

## Real-consumer acceptance still unrun

After separately authorized packaging/installation and current runtime ownership corroboration, record the exact source/build/install manifest and the serving module `__file__`, selected revision, PID/start time, state identities and asset hashes. The historical source-root text in `docs/PYTHON_HOT_RELOAD.md` is orientation, not a current observation. This checkout was not activated.

On the existing 8080 consumer, keep an old React page open, publish a validated new generation, then trigger a previously unloaded old lazy feature and retrieve its original chunk through both asset aliases. Observe the entry switch serving complete old/new generations, capture refused incomplete/conflicting publication while the previous entry remains usable, and verify installed files match the selected source/build manifest.

Capture real browser receipts for `/dashboard` static usefulness without Node; `/react/` completeness; opt-in/legacy redirects with `window=wb-*`, `binary_hash`, `function_id`, `project_id`, repeated query values and fragments; and the affected scenario matrices in both complete interfaces. Fragment assertions in an HTTP client are not a browser inheritance receipt.

Standalone in-process reloader admission/rejection and real-handler observations on unchanged process/state identities remain the separate U42 consumer gate. Asset-file publication itself is not a Python reload, and a rejected Python edit never authorizes a restart. `docs/PYTHON_HOT_RELOAD.md` and root `AGENTS.md` continue to govern activation; no restart, alternate port or `systemctl` is implied.

## Checks and scope

Performed: bounded read-only source/diff-history-report inspection and line lookup; read U13/U42 requirements, root instructions, README/USAGE/plans hub/runtime reuse orientation and the hot-reload contract. Only this report was written. Parent-owned progress changes and other owners' application edits were preserved.

Not performed: builds, type checks, test execution, repository imports, application scripts, service/process/catalog queries, browser actions, package installation, asset rollout, serving activation, recovery admission, restart, source/index mutation, commits, pushes or publication. U13 and U42 remain open.
