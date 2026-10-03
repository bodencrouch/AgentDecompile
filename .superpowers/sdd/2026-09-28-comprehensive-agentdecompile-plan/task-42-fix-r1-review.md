- **T42-R1 — Normalize URL postfixes before matching emitted files — ADDRESSED.** `src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts:23` now records only the substring preceding the first `?` or `#` as the URL-hook dependency identity (`:27`). The emitted URL remains under Vite's control: `renderBuiltUrl` records the filename and returns `undefined` (`:127`), with `/react/` retained (`:124`). Rollup disk-path references remain unchanged (`:15`), and the emitted-file membership refusal remains in place (`:52`). The real-bundler regression supplies fragment and query-plus-fragment SVG imports at `frontend/scripts/publish-react.test.mjs:188`; checks the SVG disk identity and suffix-free references (`:204`), and asserts both original postfixes survive in emitted scripts (`:209`). It then removes the actual emitted SVG, requires `STAGE_VALIDATION_FAILED` and the old entry/lazy bytes (`:211`), restores the saved emitted bytes and requests successful publication (`:215`). The existing missing-CSS-URL build refusal remains (`:218`). These are source assertions, not executed results.
- **T42-R2 — Keep Node regression files out of Vitest discovery or use Vitest consistently — ADDRESSED.** `frontend/scripts/publish-react.test.mjs:3` now imports `test` from `vitest`, matching `frontend/package.json:10`'s standard `vitest run` command and its existing dependency (`:24`). Temporary-directory cleanup is registered through the current test context's `onTestFinished` (`frontend/scripts/publish-react.test.mjs:25`), so registration, async completion and cleanup belong to Vitest. The real-bundler callback and its awaits remain inside the registered test body, with an explicit 30-second timeout (`:180`). The options-before-body overload and context cleanup hook are documented by the primary [Vitest test API](https://vitest.dev/api/test) and [Vitest lifecycle API](https://vitest.dev/api/hooks#ontestfinished). Actual locked-runner execution remains unrun.

### New Breakage in the Fix Diff

- **None found. Counts: 0 Critical, 0 Important, 0 Minor.** The only application-source change is URL-postfix removal from hook-collected dependency identities. Regression changes preserve emitted URL assertions, missing-file refusal, exact emitted-byte restoration and old-generation checks. The package script and publisher are unchanged in this fix round; their broader implementation was not re-reviewed.

### Out-of-Scope Observations

- None.

### Checks and Execution Limits

- Read the task brief, both previous findings, appended fix report and scoped re-review prompt. Read the supplied owned-path diff once, covering base `1cdfe46360bb5d9352d2d9087595bd4aaae34cee` to head `1d468be572b2c8f161ced8527445b49ad352f321`; did not regenerate it or run Git commands.
- Named narrow checks outside the diff: inspected line-numbered URL-hook return/membership context, regression setup/old-entry helper and fixture assertions, the existing package runner/dependency declaration, and primary Vitest documentation for the options overload and context cleanup. No broader publisher, router or repository review occurred.
- The implementer reports successful syntax-only and diff-whitespace checks with no diagnostics. Their report explicitly states that no covering tests ran. These claims were not rerun; they do not provide behavioral evidence.
- Unrun gates remain: all publication regressions, real locked-version Vite bundling and URL assertions, actual Vitest lifecycle/cleanup, TypeScript checks/builds, installed package/source manifests, old-browser lazy loading across rollout, both real asset aliases, static/React workflow matrices, and standalone reloader/live consumer behavior with unchanged process/state identities. U13/U42 acceptance remains open.
- Performed no tests, builds, type checks, project imports, proof/application scripts, syntax reruns, service/process/catalog/runtime operations, systemctl, restart, alternate-port operation, installation, publication, Git mutation or subagent dispatch. Only this review report was written.

### Verdict

- **Fix round 1: All findings addressed, no new Critical/Important breakage.** **2 ADDRESSED, 0 NOT ADDRESSED; no open findings from this scoped re-review.** Source approval does not close the unrun execution, installed, browser or live acceptance gates.
- Path shorthand: `frontend/` is `src/agentdecompile_recovery/corpus/dashboard/frontend/`.
