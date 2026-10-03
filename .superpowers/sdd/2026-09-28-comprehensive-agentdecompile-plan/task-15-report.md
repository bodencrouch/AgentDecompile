# Task15.1 implementation report

Status: READY_TO_COMMIT — source packet prepared for controller review; behavioral, installed, browser and whole-U15 acceptance remain unverified. No commit or staging performed by this worker.

## Owned paths

- `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`
- `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/StaticSelectionIsolation.test.ts` (new, dedicated regression source)
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-15-report.md`

Base supplied by controller: `cc4524075cacdf25a1ae667ab97c92b1f740656c`. Controller owns Git and integration. No backend, second root/store, API contract, generated assets, React application, grid, service or runtime changes.

## Implemented source behavior

App owns a frozen selection intent with its requested row/address, generation, session, canonical locator/program, requested project/artifact slug, corpus identity and available inventory content hash. UI counters are not presented as artifact revisions. Synchronous target setters and render identity comparison retire old intents. Detail, graph and overview are an admitted keyed packet; primary selection is independently keyed. Render projections mask old packets before effects. The generation is cancellation ownership only.

Workspace, fallback function detail, evidence polling, diagnostic job lookup, timer retries, ensure-program and reload carry their original intent through admission and response processing. A null workspace outcome is ignored and cannot trigger fallback. Response locator/program must agree when supplied. Resolved artifact slug is recorded separately, and a backend function center does not navigate away from an explicit requested address. A program-open intent may adopt an initial function only while current.

Last valid decompile is written only by an admitted evidence commit, with that packet's function label/address, target identity and resolved artifact provenance. It never derives its label from a later selection-only render. Fallback stays within the concrete target and known artifact mapping and is explicitly labeled as the previous function. Listing assembly/preview and graph do not treat a different backend center as evidence for the requested data address.

## Ingress and caller coverage

| Entry/caller | Admission and continuation handling |
|---|---|
| `selectRow` and function table/keyboard/context-menu/graph/listing callers | Old concrete-scope callbacks cannot create a new intent; a current row starts an intent synchronously before selected/page-context updates. All reads inherit it. |
| `selectProgram` | Program and project slug changes retire prior work before one program intent is shared by workspace and ensure. Redundant program-click clears and duplicate double-click ensure were removed because they retired that new intent. |
| `ensureGhidraProgram` | Captured locator/program and original intent checked before admission, after request/body awaits, after retry delay, before first-row/overview/detail commits, after nested workspace, and after inventory fallback. Async callers supply their current captured intent. |
| `reloadProject` | Captures selected row and target before binaries/actions/preview/function-list awaits. Each continuation checks the original token; refresh reads never reselect an obsolete closure row. |
| `resetTabState`, restore, new/close/switch tabs | Synchronous retirement and page-context clearing. Closing an active tab restores its successor before persistence awaits. Preview and session responses cannot restore a retired selection. |
| `setSlug`, `setProgram`, `setActiveSession`, `setDossier` | All App target setters pass through retirement. Inventory/corpus/session-derived identity changes are additionally masked at render. Covers binary tables, siblings, Explorer, project cards, clears, logical/navigation target setters. |
| `openLocator`, pasted-path inspection, initial session restore | Inspection/admission continuations check their original operation generation; only an admitted open establishes its new intent, which is retained through session persistence and ensure. Bootstrap cannot replace a later user selection. |
| registration, project creation, import/create-tab-project, import membership, upload/resolve-drop, remove-program/remove-slug, save/save-as | Original operation generation rejects late UI target changes; validated synchronous target transitions use the same setter boundary. Multi-file import carries the resulting admitted intent before continuing the next file. Existing backend jobs/writers are not cancelled. |
| `loadFuncs` | Inventory results are concrete-target scoped, including render masking, so old rows cannot become selectable functions of a different locator with identical slug/program strings. Existing paging/query/checked-set behavior is retained. |
| `loadPreview`, `loadContext`, persisted session response | Captured generation/token prevents stale target-affecting continuation. Current directory browse remains its independent existing surface. |
| unmount | Existing App cleanup marks selection ownership inactive and retires intent/timer. No server jobs are cancelled. |

## Consumer coverage

| Consumer | Current-only projection |
|---|---|
| Listing label/controls/assembly/preview | Current primary selected row plus admitted detail. A different returned center is metadata, never relabeled instruction/source content at the requested address. |
| `ListingRows` local state | React key includes concrete target and address. Same target/address refresh keeps the key; evidence refresh no longer resets focus index. Its catalog reads additionally carry selection intent, checked before POST and every read/poll continuation. |
| Decompile dock / classic inline decompile | Current matching center or explicitly named previous valid function. Cross-target fallback and known mapped-artifact mismatch are masked. |
| Graph / graph navigation | Graph comes from admitted packet and is hidden when its returned center differs from current address. Navigation enters the same scoped selection handler. |
| `toolContext`, page context, action defaults | Rendered context sees current selected only. Live action/default getter reads current refs, including a click followed by an action before React renders. Address/name/logical-id attributes are blanked on retirement. |
| `AgentDecompileUI.getToolContext/getSiblings` | Context reads current target/primary refs; sibling getter requires the exact admitted current packet, including before the next effect updates the global callback. |
| catalog execution | Current default context is captured at invocation; obsolete implicit-target callbacks are refused. Explicit captured `targetContext`/background jobs remain supported. Post-action refresh may only refresh its originating still-current intent. Existing action allowlisting/confirmation/submission/batch protocol remains. |
| SymbolTree callback boundary | Cache results carry their originating scope solely for callback provenance. Namespace leaves carry sweep scope; paginated flat nodes with mixed scopes become unverifiable. App refuses absent/obsolete scopes. Cache reset/fetch/navigation behavior was not expanded; its independent stale-display/cache obligation remains open. |

## Authored regression coverage (not run)

The dedicated frontend fixture uses the already-existing Vitest, React/htm and `matchReviewHarness` VM hook shim. It evaluates the real static source, instruments only the final App shell return to expose existing closures/projections, and exercises real request readers, evidence commits, decompile consumer output and actual `executeAction` JSON construction. It does not replace the provider or selection implementation with a success stub. Mock endpoint responses are explicit per case; unexpected reads throw.

Authored cases: B-then-A workspace completion and no A follow-on; first B render before any effect; same-event-turn action context; queued/empty/failed fallback refusal; stale evidence while B workspace waits; delayed diagnostic job; requested data address versus resolved center; project-to-artifact slug compatibility; same program/address across locator/session; obsolete tree callback; ensure first-row/nested workspace refusal; reload interrupted before subsequent read; reset retry cancellation and page attribute clearing; current queued-to-complete evidence with stable Listing key.

Harness limitation: existing `matchReviewHarness` is a hook/element-tree shim, not a browser or real React DOM scheduler. This fixture deliberately does not commit background App effects, avoiding unrelated polling/bootstrap fixtures that would obscure reader behavior. It cannot qualify actual unmount scheduling, layout/focus/scroll preservation, rendered DOM Listing remount behavior, keyboard/screen reader/reduced motion, or installed global-consumer timing. Those require the separately authorized real browser/runtime gate. No new test framework, provider, root or source-only string-presence assertion was introduced.

## Verification performed

- Read task brief, adopted selection contract and SDD implementer prompt, plus bounded repository guidance/source/harness reads.
- `node --check src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js` — exit 0, no output, after the final source edit.
- Text/source scans of all App target setters, workspace callers, evidence commits, last-decompile writes and SymbolTree callback provenance. All remaining App workspace calls accept an intent; former unkeyed detail/graph/overview setters and `evidenceSeqRef` are removed.
- No tests executed or collected; no test imports, typecheck, builds, proof scripts, project imports, browser, runtime/process, DB, catalog, services, systemctl, restart, ports, publication, staging or commit. The regression source is authored and unverified.

## Self-review and limits

Self-review corrected program-click post-admission clearing; duplicate double-click ensure; same-address refresh focus reset; stale session-close continuation; pre-render action defaults; mapped artifact preservation on evidence responses that omit slug; explicit data-address versus center labeling; and Listing read continuations retaining an obsolete selection token. Target-derived display packets also mask immediately if available inventory/corpus identity changes during a read; the UI waits for a new current read rather than retaining unverified evidence.

Application remains a large existing file. Controller review should concentrate on operation admission and initial restore ordering as well as the named reader race cases. Source syntax success is not behavioral verification. No end-to-end source/runtime binding, real browser, installed/static bundle or full React proof was collected.

Full React URL/abort masking is reused by source disposition with no change. Broader U15 remains open: logical/build/counterpart navigation, Back/Forward viewport, drafts/conflicts/revision completeness, checked-set admission and confirmation across locator-only changes, SymbolTree cache/display qualification, accessibility/narrow layout and full shell acceptance. No whole-UI selection-safety or U15 completion claim is made.

## Fix round 1 correction receipt — 2026-10-02

Status: **READY_TO_COMMIT**, source-only corrections prepared against the supplied reviewed base `ccd9b63af57d418cf26842584444e2a471d4348f`. This receipt supersedes the original report's claim that project-open/bootstrap ordering and post-action inventory refresh were already complete. Controller review and all behavioral acceptance remain outstanding; no worker Git operations were performed.

Exact owned paths remain:

- `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`
- `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/StaticSelectionIsolation.test.ts`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-15-report.md` (this appended receipt only)

All three Important findings were addressed in source:

1. **Pending project open:** reset now installs an explicit pending dossier locator, including an explicit empty locator for a cleared tab. Render uses the dossier's locator property even when empty instead of falling back to the prior session. A different-project open supplies its requested locator before inspection, and tab/bootstrap restoration similarly installs its locator before preview. `currentLocator` and the rendered project locator follow the same target. This keeps pending B consistent across renders without retaining A as the pending target; existing captured-generation checks still refuse an older inspection after a later open/selection.
2. **Bootstrap identity discovery:** a separate navigation generation changes on explicit retirement/target transitions, while render-discovered corpus/content identity changes still retire the immutable evidence intent without advancing navigation ownership. The actual named `bootstrapWorkbench` effect guards saved-session restoration with this navigation generation and mounted state. Identity enrichment therefore masks old evidence without cancelling its own saved-session restore; a subsequent user selection or project open still cancels restoration.
3. **Post-action refresh:** completion of a rename/decompile creates one refreshed intent before starting function inventory and selected detail reads. Both receive that same intent. Function-list completion is no longer made obsolete immediately by the detail refresh. The prior captured action intent must still be current before either refresh begins.

Authored, **unexecuted** regression additions cover A-session to B open with an intervening pending render and saved admission; B inspection losing to a later C open; both corpus-first and inventory-first identity discovery followed by saved sessions; real selection and open intents superseding delayed bootstrap sessions; and completed synchronous rename updating the real function-list projection, with both list-first and detail-first completion ordering. The action cases inspect the actual submitted context and use a completed response without a job or polling fallback. Existing isolation cases remain in place.

Harness correction/limits: the new bootstrap cases commit the real named bootstrap effect using the existing hook shim and memoize callbacks through its `useMemo` so explicit renders do not falsely remount bootstrap. Other App effects are deliberately replaced by inert effect callbacks; ordinary reader cases still do not commit effects. The new cases model named deferred response orderings with explicit renders and microtask settlement. They do **not** establish full React scheduling, StrictMode, other background-effect interactions, DOM mounting, focus/scroll, browser behavior, installed delivery, provider/runtime behavior, or whole-U15 acceptance. No test framework or shared harness file was changed. Authored assertions are not passing-test evidence.

Checks performed in this correction round: read the fix brief, original brief, full adopted selection contract, original report/review, repository guidance, the dedicated fixture/shared hook source, and bounded relevant App ingress/reader/consumer source. Text/source inspection checked pending locator propagation, bootstrap dependencies and retirement paths, and the common post-action token. `node --check src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js` exited 0 with no output after the final application source edit. No tests or test collection, builds, typechecks, project/test imports, proof/checker/crypto scripts, database/runtime/process/live/catalog/provisioning/service operations, Git operations, publication, or subagents were used. The added regression source was read but not imported or executed.

Minor M1 (Listing focus-index clamp) remains explicitly deferred to whole-branch review under the fix brief. Captured read/packet/action isolation and the other open U15 gates remain unchanged in scope. These corrections do not claim runtime activation or whole-branch completion.
