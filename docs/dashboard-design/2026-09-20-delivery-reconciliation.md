# Dashboard delivery reconciliation — 2026-09-20

This is a source-inspection report, not an activation or browser-validation receipt.
No builds, tests, HTTP requests, recovery submissions, process changes, or requests
to port 5174 were made during this investigation.

## Authority and source roots

The operational authority is
`/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/AGENTS.md`
and its current `STRATEGY.md`. The runtime mirror's
`/home/brunner56/agentdecompile-nvme/AGENTS.md` explicitly delegates to these
documents. They require the existing 8080 surface and catalog, preservation of
executing/canonical differences, and in-process Python reload instead of routine
restart. They prohibit systemctl, competing dashboard ports, and filesystem
tests under the current mission constraints, and builds used merely for
documentation validation. Required production asset packaging is a separate
implementation step; this investigation performed none.

The compared dashboard directories are:

- Runtime: `/home/brunner56/agentdecompile-nvme/src/agentdecompile_recovery/corpus/dashboard/`
- Isolated implementation: `/home/brunner56/agentdecompile-worktrees/forgiving-inputs-20260920/src/agentdecompile_recovery/corpus/dashboard/`

Paths in the following sections are relative to these directories, with the
applicable root identified. Source line numbers describe the inspected revision
and may move as implementation continues.

## Why 8080 selects the static workbench

Runtime `router.py:112–128` owns `/dashboard`. It defaults the `mode` query
parameter to `static` and calls `render_workbench(static_mode=True)`. Any other
mode invokes `react_entry_redirect`. This is deliberate route selection, not a
response to missing compiled React assets.

Runtime `workbench.py:2168` owns `render_workbench`; its script declaration near
line 2312 loads `/dashboard/static/workbench-app.js?v=live29`.

Runtime `react_api.py:26–28` assigns the packaged asset directory to
`static/react`, the canonical asset URL to `/react/`, and the compatibility URL
to `/dashboard/static/react/`. `react_index_response` near line 109 checks the
index and directly referenced assets before returning the entry. Routes near
lines 411–420 redirect legacy React entry URLs to `/react/`. Routes near lines
450–469 serve confined asset paths and SPA fallback under `/react/`.

Runtime `static/react/index.html` exists and references these existing files:

- `static/react/assets/index-DRkK2x2d.js`
- `static/react/assets/index-CJIG6QTn.css`

The asset directory also contains Monaco and parser workers. The inspected
assets were dated September 15. Presence on disk establishes neither equivalence
to current TypeScript source nor successful browser execution.

## Existing roots have diverged

| Concern | Runtime source | Isolated source |
| --- | --- | --- |
| `frontend/src/main.tsx` | Mounts `WorkstationApp`; installs workspace flush | Mounts `App`; installs workspace flush and imports `style.css` |
| `frontend/vite.config.ts` base | `/react/` | `/dashboard/static/react/` |
| Packaged output | `../static/react` | `../static/react` |
| Development API target | Existing 8080 backend by default | Existing 8080 backend by default |
| `frontend/src/workstation/WorkstationApp.tsx` | Existing workstation implementation | File differs from runtime; not an interchangeable copy |

The runtime Vite configuration additionally handles malformed URL paths and
asset content negotiation. Carrying the isolated entry/configuration wholesale
into runtime would regress existing delivery decisions. Development and packaged
delivery should build the same reconciled source; no Vite process needs to be
started or altered to make that source decision.

The isolated repository's root `pyproject.toml:128` already includes
`static/*`, `static/react/*`, and `static/react/assets/*` as dashboard package
data. Another application packaging mechanism is unnecessary.

## Automatic preparation hazards

Isolated `frontend/src/App.tsx:426–435` automatically posts to
`/dashboard/api/workbench/prepare` when readiness and selected locator/program/slug
change. Runtime `frontend/src/AtlasApp.tsx:365–373` also automatically prepares
selected context. Mounting either root unchanged would allow navigation to admit
work. Do not use these roots as the replacement shell or nest them inside it.

Runtime `frontend/src/workstation/WorkstationApp.tsx:183,198` instead exposes
**Prepare analysis…** through the existing action dialog and tracks the explicitly
submitted job. Its inspected startup hooks read inventories, jobs, preparation
records, and local storage; no equivalent selection-triggered preparation POST
was found in that component. This observation is limited to inspected source,
not proof about all downstream components or backend read-side behavior.

## Compatibility URL gaps

Runtime unified page routing lives at
`/home/brunner56/agentdecompile-nvme/src/agentdecompile_recovery/unified_pages.py`.
Its `create_unified_router` near line 748 includes the dashboard router. Existing
corpus, Atlas, report, and operations aliases redirect to `/dashboard` with
`window=wb-*` selection hints.

Runtime `frontend/src/workstation/navigation.ts:6–17` parses `view` and workstation
selection fields. It does not interpret the legacy `window=wb-*` vocabulary or
the complete `App` query vocabulary, including `binary_hash`, `function_id`, and
`project_id`. Changing only the default dashboard handler would therefore lose
the intended destinations of existing links. Preserve query/fragment selection
through the delivery redirect and translate supported legacy destinations in the
existing navigation owner as their corresponding surfaces are migrated.

## Consolidation seam and first implementation slice

Use the existing `frontend/src/workstation/WorkstationApp.tsx` as the shell.
It already owns selection, session tabs, action catalog/dialog, activity dock,
source export, local artifacts, and retained matching/scratch state.
`workstation/AnalysisView.tsx` already reuses `CodeBrowser.useTool`.
`workstation/RetainedPanel.tsx` preserves child state while withholding new props
from inactive tools. These are existing integration points, not reasons to add
another root application.

1. Reconcile isolated `main.tsx` and Vite delivery configuration against the
   current runtime WorkstationApp and `/react/` arrangement, preserving unrelated
   changes and inspecting each file difference before transfer.
2. Add the first migrated child surface to WorkstationApp using its existing
   `selection`, `onSelect`, `onAction`, `notify`, and `revision` contract. Reuse
   CodeBrowser/GuideWorkflows children where applicable; avoid App/AtlasApp roots
   and their preparation effects.
3. Extend the existing workstation navigation parser for the selection aliases
   and legacy window destinations used by that surface. Keep destination gaps
   explicit until the corresponding surfaces exist.
4. Preserve `/dashboard` as the complete static alternative and `/react/` as the
   packaged entry for the optional full Vite application. Do not demote static8080
   to a temporary fallback, make Vite development-preview-only, or add another
   backend, catalog, recovery scheduler or independent application state owner.
   Standalone5174 operation is a required delivery mode but is not authorized to
   run during the current recovery mission.

## Asset installation and activation boundary

The existing Vite configuration sets `emptyOutDir: true`. Building directly into
the live asset directory could remove files referenced by pages already open in
a browser. When building is authorized, produce the package outside the live
asset directory, install its new hashed assets first, and publish the new index
last using a same-filesystem atomic replacement. Preserve the old hashed assets
through the handoff so existing pages can still load their deferred chunks.
Do not blindly replace the runtime source tree or prune its asset directory.

Asset handlers read the filesystem per request; installing assets does not
inherently require replacing the server. A Python dashboard-handler change must
use the existing in-process reload mechanism, after corroborating serving
PID/start time, cwd, loaded module path, and revision as required by canonical
instructions. A rejected reload is not permission to restart. Activation and
browser verification remain separate work; this report performed neither.
