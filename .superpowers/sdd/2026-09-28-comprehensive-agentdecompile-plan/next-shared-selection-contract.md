# U15 first implementation packet: static selection-response isolation

Status: **implementation-ready source contract; implementation and acceptance remain open**. Investigation dated 2026-10-02. This report owns no application source. It is based on bounded source/document reads, not a running application, test result, database observation, installed bundle, or browser receipt.

## Predicate and disposition

Implement the missing predicate: **once the static workbench selects B, a read begun for A cannot restore A as selected, merge A evidence into B, or expose A as B through Listing, Decompile, graph, the page context, or action defaults.** This includes the first render while B is loading and a project change whose program/address strings happen to equal A's.

Authority: `unit-15-requirements.md`; `unit-15-selection-extract.md` F08/F09/F11/F12 and workstation Task 3; `docs/FRONTEND_INTENT.md:123–145`. This is the first asynchronous-selection child of U15, not closure of logical navigation, revisions, drafts, batch admission, history, accessibility, or U15 overall. The consumed U13 source integration can be reused; unrelated U13 acceptance does not block this disjoint source packet.

## Actual retained surfaces and ownership

Source locators use these abbreviations: `dashboard/` is `src/agentdecompile_recovery/corpus/dashboard/`; `static/`, `frontend/`, `react_api.py`, `workbench.py`, and `router.py` are beneath that dashboard directory; bare React filenames and `workstation/` are beneath `dashboard/frontend/src/`. Line numbers are investigation locators; another owner may move them.

| Surface | Existing root/state/navigation | Disposition |
|---|---|---|
| Static8080 | `dashboard/router.py:104–119` serves `/dashboard` in default/static mode via `render_workbench(static_mode=True)`. `dashboard/workbench.py:2488–2492` loads React/htm and `static/workbench-app.js`; that file's `App` starts at 3342 and mounts into `wb-root` at its end. | Keep this root. The selection owner is already `App`: slug, program, selected, detail, graph, overview, checkedAddrs, activeSession/currentSession/dossier. No replacement universal store. |
| Static persistence/links | `workbench-app.js:3819–3884` persists server sessions through `/dashboard/api/workbench/sessions`. `currentLocator` at 4652 prefers dossier locator, then session locator. Initial URL reads occur at 3343–3400; `bootAddrRef` at 4165–4175 applies a deep-linked address once. Layout preferences use `readUiPref`/`writeUiPref` at 2097–2109. | Reuse session and URL contracts. This root does not implement the full React Back/Forward route helper. Do not claim that missing history obligation is solved by request fencing. |
| Full React | `frontend/src/main.tsx` calls `installWorkspaceFlush()` then mounts **WorkstationApp**, not AtlasApp. `/react` and `/react/` are served by `react_api.py:419–421`; legacy React URLs redirect at 413–417. Vite uses the same source entrypoint; this report does not establish the contents of a packaged or served build. | Keep the full application and static alternative. No new root, no compiled asset rewrite. |
| React selection/store | `workstation/WorkstationApp.tsx:74–127` owns Route and sessions. `navigation.ts` owns readRoute/routeUrl/sessionKey/mergeSelection/memberSelection. `workspaceState.ts` stores preferences/drafts in tab-local session storage; `storage/projectStore`/LocalProjectRuntime handle local artifacts/snapshots. | Existing proper owners are reusable. `revision` in WorkstationApp is a refresh counter, not a verified binary revision. |
| React detail path | `AnalysisView.tsx:14–20` requests `/function?` using the actual selection; `SourceEditor.tsx:12–17` delegates polling to `useData`; `ui.tsx:15–57` tags data with URL, aborts retired requests, rejects aborted completion, and returns an empty state immediately if stored key differs from current URL. AnalysisView remounts on the session key (`WorkstationApp.tsx:203`). | The exact A/B detail-response defect below is already source-fenced here. **No React changes for this packet.** This does not certify all React hooks or full revision/draft isolation. |
| React CodeBrowser/retained panes | Active AnalysisView imports `useTool` from `CodeBrowser.tsx`; CodeBrowser is not the root. Its job hook has an alive guard and a narrower key of tool/params/locator/program/slug/refresh. `RetainedPanel.tsx` retains the last active child and supplies `active=false` without feeding inactive children new selection/refresh props. | Preserve these paths. Do not rewrite CodeBrowser or retained pane behavior to imitate the static fix. Additional project/hash/revision-key completeness remains a separate audit. |

## Exact defect and consumer consequence

### Workspace response can replace a later selected function

1. In one bound program, click function A. `selectRow(A)` (`workbench-app.js:3654–3676`) immediately calls `setSelected(A)` and `setContext(A)`, then awaits `loadWorkspace(program,A)`.
2. Before A's read completes, click B. The same code immediately selects B and starts B's workspace read.
3. Complete B's response first, then A's. `loadWorkspace` at 3590–3603 has **no generation, selection-key, abort, or current-target guard**. It unconditionally calls `applyWorkspace(data,row)`.
4. `applyWorkspace` at 3561–3588 writes overview, graph, detail, and `setSelected(data.selected || row)` plus `setContext(...)`. A therefore becomes selected again even though B was the later intent. The fallback `/function` read at 3665–3676 also unconditionally writes detail/graph/overview.
5. `toolContext` at 5172–5187 derives addr/name from selected and program/slug from current App state. `executeAction` at 5259–5274 combines those with `currentLocator()`. After a cross-project/program transition, late A can consequently provide the address/name while action context supplies B's current program/locator. This is a source-permitted wrong-target composition, not a claim that a mutation was executed.

### Evidence polling can merge A text under B even before A workspace wins

`loadFunctionEvidence` at 3607–3651 increments `evidenceSeqRef` only when a new evidence chain begins. Selecting B, `resetTabState`, and `selectProgram` do not synchronously invalidate that counter. An A evidence read already pending can settle while B's workspace read is waiting, pass the sequence check, and merge decompile/assembly into the current `detail` at 3639–3646. A late A workspace response can also start a new A evidence chain after B's chain and wrongly become newest.

The retry callback checks a sequence, but the recursive call obtains the *current* counter again for nonzero attempts; a chain should instead carry one immutable request token through every attempt. The fetch URL also reads `program` from its creation closure instead of an explicit request context.

### Existing displayed content is unkeyed during loading

`selectRow` does not clear or key existing `detail`. Listing consumes current selected/name with old `detail.assembly`/preview (`6259–6300`). `lastDecompile` is updated whenever detail **or selected** changes (`4350–4362`), so merely selecting B while A text remains can record A text with B's name/address. Decompile then uses `liveText || lastDecompile.text` at 6338–6365. Clearing after an effect is insufficient: stale data must already be hidden on the render that uses B.

`ListingRows` (`2691–2759`) has useful cancellation/sequence guards, but its dependencies are only addr/program/assemblyText and it renders unkeyed local state. Same program/address in another locator is not a new dependency. Reuse that component while adding the owning selection identity at its call boundary (or a keyed state projection inside it).

## Existing backend contract: preserve it

Both roots use `API=/dashboard/api/workbench`. `router.py:624–678` maps existing requests to `list_functions`, `function_detail`, and `program_workspace` with slug, program, locator, and addr; no endpoint change is needed.

- `workbench.py:1487–1532`: function inventory resolves a locator+program through `program_binding`; a project binding can select an artifact slug different from the session project slug. It does not indiscriminately fall back to slug when an explicit project/program binding was requested.
- `program_workspace` at 1981 onward reads the specified store project/program. At 2014–2023 it can replace a project slug with the matching artifact slug. Returned payload at 2208–2234 contains locator, program, slug, selected, listing, graph, decompile, overview.
- At 2067–2080, a requested address is mapped to a preceding function entry (or first function). This is **not** proof that every arbitrary data address belongs to that function. Request address and returned function center are distinct identities; blindly requiring selected.addr===requested addr would break existing behavior, while blindly navigating to returned selected.addr loses data-address intent.
- `function_detail` at 2238 onward may return a completed observation directly or combine workspace/source witness data. It need not return every top-level identity field. The client must preserve its captured request envelope, rather than infer missing identity from whichever selection is current when the response arrives.
- Do not add required server request fields, fabricate a revision ID, change `program_binding`, bypass catalog operations, or alter authentication parsing. Client request generations are cancellation ownership, not artifact/content revisions or recovered-byte proof.

## Smallest source implementation packet

**Application ownership: only** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js`. Keep changes local to App's existing selection/read paths and their consumers. Authentication work may touch the same evidence reader; preserve its error parsing/messages and coordinate hunks before editing. No Python change, new store, new root, endpoint, migration, recovery action, or compiled React assets.

1. Introduce a small App-local immutable request envelope and current intent ref. Capture active session/project locator, program, request slug, requested address, available corpus identity/content identity, and a monotonically increasing **UI intent generation**. Do not use `sessionRevision` or `corpusRevision` as an artifact revision; do not invent absent hashes. Logical IDs remain separate from concrete address/build. Capture and canonicalize identity once before asynchronous work; no `currentLocator()` or closure-program substitution after awaits.
2. Begin/invalidate an intent synchronously when the UI changes the selected row or concrete target, on tab reset/restore, program selection, locator admission/open, target clear, and reload of that selection. Unmount retires the token. Route remaining direct slug/program target setters through the same invalidation seam, or otherwise make each render's target identity mask older packets. Ref invalidation must happen before a stale completion could be admitted; an effect alone is not the admission boundary. Do not turn an old continuation into a fresh intent.
3. Propagate the same envelope through workspace, fallback detail, evidence fetch, diagnostic job lookup, retry callback, and state commits. Gate before follow-on reads as well as after **every** await and before every selected/context/detail/graph/overview/last-function update. An obsolete workspace returns an explicit ignored/null outcome; `selectRow` must not interpret that as permission to start its fallback. Abort/timer cleanup is useful, but token equality remains authoritative if transport cancellation loses a race.
4. Store/derive the selected detail bundle with its envelope key. At render time, use only packets matching the current concrete intent; show B's selected label plus a loading/empty state, never A's source/assembly/graph as B. Include error/queued/empty packets in the same rule. Either atomically store detail/graph/overview together or key every projection; do not leave a raw unkeyed consumer. Supply a stable concrete selection key to ListingRows (for example as its React key) so project/address changes cannot retain another target's instruction rows. A same-target evidence refresh should not remount/reset focus/scroll unnecessarily.
5. Apply backend fields only *inside* the admitted envelope. Returned locator/program, if present, must agree with the captured project/program after existing normalization. Do not reject an otherwise admitted workspace solely because its resolved artifact slug differs from the requested project slug; keep request identity and resolved artifact identity separate. Do not join a late response to the newest request via matching address alone. A no-address program-open request can adopt its returned initial function only while that exact intent is still current. An explicit row/address intent must not be silently replaced by a different returned center; retain requested address and treat resolved function as evidence metadata. Do not assert a counterpart or function-containment relation the payload does not prove.
6. Update last-decompile only from an admitted function-evidence packet using **that packet's** captured/resolved function label/address and concrete program identity. A selection-only render must never relabel old text. Preserve a last valid function within the same concrete target when inspecting data, clearly identify it as the previous function, and never show that fallback across another program/project/build. No blanket clear on every address change that destroys the intended data-address/last-function behavior.
7. Page context, toolContext, Listing controls, graph navigation, `AgentDecompileUI.getToolContext/getSiblings`, and action defaults consume only current primary selection and admitted evidence. Clearing a selection also clears stale page-context address/name/logical-id attributes; an old response cannot restore them. Do not modify explicit already-captured job targets or background job ownership. Existing read-only action allowlisting, catalog submission, confirmation, and batch semantics remain intact.

### All existing loadWorkspace call sites

| Caller | Required token lifecycle |
|---|---|
| `selectRow` at 3659 | Begin explicit row intent before immediate selected/context update. Pass token through workspace and optional fallback/evidence. Never start fallback/poll after an ignored response. |
| `selectProgram` at 3929 | Begin program intent before setter/reads. Workspace and ensure-program branch share that intent; neither may undo a later row selection. |
| `ensureGhidraProgram` at 3989 | It already checks ensureSeqRef around admission/read, but it writes first-row/overview/detail at 3963–3988 before calling workspace. Carry the original target/intent through these writes too. Capture a fresh selection token only at the original authorized UI entry, not after ensure resolves. If a newer row has been selected, do not select the first result or initiate an obsolete workspace read. |

`reloadProject` at 4659–4676 reaches the same reader through selectRow; it must capture the selected target before its earlier awaits and refuse stale continuation after a switch. `resetTabState`/`restoreTabSession` at 3892–3916 and target setters reached from Explorer, import/open/remove, binary/sibling buttons must invalidate or project out old packets. This is selection admission only; do not add analysis, make a new server writer, or change import/authentication behavior.

### Retained browse, checked-set, and draft boundaries

- `checkedAddrs` is already separate (`3447`); range/toggle helpers and `4315–4327` clear on slug/program change and prune on row replacement. `resetTabState` also clears it. Preserve those mechanisms. This report does **not** prove locator-only/check-confirmation batch isolation; that remains an explicit next child. Do not claim request fencing closes F11.
- MatchReview in both surfaces uses server selection/tokens and an independent checked set (static `1097–1122`; React `workstation/MatchReview.tsx`). Do not merge that set with the primary code selection or rewrite its decision protocol.
- Static SymbolTree (`2478` onward) resets on program only and its own asynchronous caches are not fully scoped to locator; it is a separate observed browse-read gap. Do not call the whole static UI selection-safe after this packet. Its callbacks into primary selection must obey the same current selection admission boundary; if an old retained browse callback supplies no verifiable current scope, refuse that callback rather than accepting an address into a new binary. Full cache/navigation repair can remain the next packet.
- React SourceEditor drafts/models/views (`SourceEditor.tsx:28–66`) are keyed by locator/slug/program/addr/kind, not binaryHash/projectId/content revision. This is a separate concrete source limitation, not justification to change React for the static response race. Draft conflict/identity acceptance remains open.
- Preserve React `mergeSelection` target clearing, logical member binding and absent/ambiguous counterpart explanations (`navigation.ts:28–54`, `LogicalNavigator.tsx:39–85`). Full logical-switch and data-address/last-function acceptance remains open.

## Regression contract for later authorized verification

No tests were authored, collected, imported, or run here. The current report authorization excludes them. A later implementation packet can add one focused behavioral fixture (suggested new path `tests/test_static_workbench_selection_isolation.py`) only if that run authorizes tests. Exercise the **real App reader/consumer glue** with deferred mocked reads and captured action bodies; string-presence tests alone are insufficient. Existing `tests/test_dashboard_flow_ui.py` primarily asserts source markers and imports project/backend/DB machinery, so do not treat it as a safe standalone source checker or run it in this mission.

| Scenario | Required observable result |
|---|---|
| A workspace pending; select B; resolve B then A | Selected/status/page-context stay B; A writes and follow-on evidence requests are ignored; next action body is B. |
| A detail already visible; select B; leave B pending | On the first B render A text/assembly/graph are not labeled B. Last-function fallback, if allowed in that same target, retains A's own label/address and explicit previous-function status. |
| A evidence pending; B workspace pending; then A evidence settles | No merge into B, no A retry admission, no B-labeled A lastDecompile. Repeat with delayed diagnostic job lookup. |
| A fallback detail pending; B selected; A succeeds/fails/returns queued or empty | No stale detail, graph, overview, error/status, or fallback chain. |
| Same program/address strings under a different locator/session/build | Rendered packet, ListingRows local state, and page/action context do not reuse A. Old callback cannot create a new intent. |
| Program open has workspace plus ensure-program pending; then explicit B row selected | Ensure's first-row setters and subsequent workspace do not steal selection. Repeat when ensure completes before its nested workspace. |
| Reload awaits binaries/preview while user switches | Reload cannot reselect its old row under the new project or start a stale detail read. |
| Reset/close target or unmount during request/retry | No late state/page-context write or new polling/read admission. Existing server jobs remain owned and untouched. |
| Current request returns project-to-artifact slug resolution | Admit current packet, retain its resolved artifact provenance; do not require project slug equality or copy stale mapping from another request. |
| Explicit data address differs from returned function center | Preserve inspected data address; do not invent containment/equivalence; previous valid function is separately labeled and remains target-scoped. |
| Same concrete target refresh and current queued-to-complete evidence | Fresh current response replaces current evidence; focus/scroll/drafts and independent checked set survive appropriately. |
| Static SymbolTree callback from old scope; current scope callback | Refuse unverifiable obsolete selection callback; allow explicitly current callback. No rewrite of its independent cache in this packet. |
| React A/B detail path | Source disposition is reuse; later browser proof should confirm URL masking/abort, no inactive retained pane competition. No claim that generic useTool or draft revisions are fully qualified. |

Completion of this source packet requires an owned diff showing request ownership at all listed ingress/await/consumer points and review against these cases. Runtime/browser proof, installed/static asset delivery, full React proof, source revision binding, Back/Forward viewport, absent counterparts, range/select-all, draft conflict, keyboard/screen reader/reduced motion, narrow layout, and whole U15 acceptance remain separately open.

## Investigation receipt

Read-only source searches/reads plus this report write only. No source edits, staging, commits, tests, collection, builds, typechecks, proof scripts, project imports, browser/runtime/process/catalog/DB queries or creation, services, systemctl, restarts, ports, or publication. Parent may dispatch the narrow implementation separately after reviewing this contract.
