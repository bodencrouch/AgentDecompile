# Static dashboard redesign: the Ghidra reversing guide's Code Browser (:8080/dashboard)

Date: 2026-09-28

Research + design spec only. No product source was edited for this document.

**Scope guardrail:** static dashboard only (`dashboard/static/*`, plain JS/htm
served without a build step). No Vite / `dashboard/frontend/` edits proposed —
that tree was read only to recover the guide-to-action mapping its
`GuideWorkflows.tsx` already encodes. This scoping follows
[`../FRONTEND_INTENT.md`](../FRONTEND_INTENT.md) §2's 2026-09-28 note: the
static 8080 surface is the conventional RE GUI and follows the Ghidra reversing
guide's Code Browser arrangement; the Vite surface is a different, real-time
all-in-one workstation built from the separate browser-RE reference set at
FRONTEND_INTENT §7. Both share one backend with field parity; nothing here
changes that.

**Ancestor document:** this spec's guide-chapter table (§1.1) and gap analysis
(§2.3) build directly on
[`2026-09-20-ghidra-guide-capability-inventory.md`](2026-09-20-ghidra-guide-capability-inventory.md)'s
per-chapter capability table — same chapter numbering, same gap findings
(continuous Listing, structures/vtables with zero direct references). Read that
inventory first if the "why" behind a gap here is unclear; this doc is its
implementation follow-on, not independent research.

**Existing visual foundation:** the Ghidra/IDA Code-Browser chrome this redesign
targets is already implemented (2026-08-31) in `workbench-chrome.css`,
`workbench-sidebar.css`, `workbench-editor.css`, `workbench-dialogs.css` and
`workbench-overlays.css` — see the task briefs and reports under
[`../plans/wb-control-briefs/`](../plans/wb-control-briefs/) (`chrome.md`,
`sidebar.md`, `editor.md`, `dialogs.md`, `overlays.md` and their `*-report.md`
companions), with the token-to-widget cascade documented in
[`mediate-report.md`](../plans/wb-control-briefs/mediate-report.md). The slices
in §6 below extend this existing token-only widget kit. They introduce no new
visual language and must not invent hex values — `mediate-report.md` already
removed all raw hex from these five files; see §5.4.

**Pinned anchors** (all file:line citations below are against these exact
files — re-check before implementing, the tree is live and mutates during
sessions):

| File | sha256 | mtime | lines |
|---|---|---|---|
| `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js` (**the live-served copy**) | `97dcda9dfebfbb71a41ad285cb0b6e776d8478ea19c382616bd1e47b21e7598c` | 2026-09-28 01:30:22 | 5948 |

**Caution:** a worktree copy of the same path diverged from what the server
actually loads (different sha256, 6210 lines — 262 more than the live copy;
mtimes within 7ms of each other, consistent with both written by the same
sync/deploy event and then diverging). The worktree copy was grepped for the
same terms and action IDs as §2.3/§3 below (`guide`, `vtable`, `SymbolTree`,
`DataTypeManager`, and all nine zero-wired `mcp.*` action IDs) — all zero, same
as the live copy. The extra 262 lines are not guide/Code-Browser-related; the
gaps this spec reports hold against both copies. HTML emitter confirmed at
`dashboard/workbench.py:2315-2319`
(`<script src="/dashboard/static/workbench-app.js?v=live29" defer>`, plus
`react.js`, `react-dom.js`, `htm.js`, `dashboard.js`). Any implementer must
still diff and reconcile the two copies before editing — this spec cites only
the live copy. Flagged again in §7 Open questions.

All line-number anchors below were re-verified against the live copy by
`grep -n` immediately before this revision (`Modal`, `WORKBENCH_COMMANDS`,
`ConfirmDialog`, `CorpusNavBar`, `CommandPalette`, `SplitHandle`, `showToast`,
`renderEditorBody`, `wb-listing-preview`, `wb-status-error`, `wb-last-action`
all landed on the exact lines cited).

---

## 1. Guide synthesis

Source: the Ghidra reversing guide — an external wiki walkthrough of the
Ghidra Code Browser workflow, fetched in full via the wiki's raw markdown. Not
linked here to keep this document name-neutral; the guide is reference
material external to this product. 16 numbered sections, 38 embedded
screenshots (one per described UI moment, full inventory in §1.2). Three
screenshots were opened directly and visually verified (§1.3); the rest are
described from the guide's own captions only — **not independently viewed**,
treat as unverified if precision matters.

The guide's linked reference subpages (file-format and editor-field
references) are "see also" material for *after* the walkthrough, not
dependencies the workflow itself requires — **not fetched**, out of scope by
the task's own "keep it to what's relevant" rule.

### 1.1 Ordered workflow (guide §1-16 -> Ghidra panel used)

| # | Guide step | Ghidra panel/tool | Guide anchor |
|---|---|---|---|
| 1 | Orient: one workspace, address-centered | Code Browser shell | `#1-introduction` |
| 2 | Open a repo -> a program | Project window, Code Browser | `#2-ghidra-repos-and-projects` |
| 3 | Learn the shell: connect, refresh, go-to | Code Browser chrome | `#3-code-browser-overview` |
| 4 | Search/browse symbols, classes, namespaces, labels, imports, exports | **Symbol Tree** (left dock) | `#4-symbol-tree` |
| 5 | Browse type archives, structs/unions/enums/function types, hide pointers, find uses | **Data Type Manager** (dock) | `#5-data-type-manager` |
| 6 | Read address/bytes/mnemonic/operands, nav by instruction/function/label, define data, xrefs | **Listing** (center, primary -- "ground truth") | `#6-the-listing` |
| 7 | Read the reconstructed C for the function under the cursor; rename (L); edit signature | **Decompile** (right dock) | `#7-decompile-view` |
| 8 | Call trees, memory map, bookmarks, symbol table, functions table, scripting console | Secondary docks | `#8-other-code-browser-tools` |
| 9 | Inspect/edit function name, namespace, convention, return type, params, flags | Function editor | `#9-Functions` |
| 10 | cdecl / stdcall / fastcall / thiscall -- who cleans the stack | Calling-convention selector | `#10-Calling-Conventions` |
| 11 | Custom return/parameter storage (ST0, EAX:EDX, float-to-long) | Function storage editor | `#11-Returns-and-Custom-Storage` |
| 12 | Structure fields, offsets, sizes; labeled vs `field_N` | Structure editor (in Data Type Manager) | `#12-Structures` |
| 13 | Vtable slots, inheritance, resolving indirect calls | Vtable / structure editor | `#13-VTables` |
| 14 | Template instantiations | Data Type Manager | `#14-Template-Classes` |
| 15 | Diagnose `extraout`/`unaff`/stack-slot reuse via listing+callers, not decompile alone | Listing + Decompile + call trees | `#15-Common-Decompile-Issues` |
| 16 | Close: guide is reference, not law | -- | `#16-Closing` |

### 1.2 Screenshot inventory -- 38 frames, description only

38 frames total (`frame_00-00-00` through `frame_00-50-40`), each with a
plain-English caption in the guide's own text. Referenced here by frame ID
only, described in words -- no image files or hotlinks are carried into this
repository. Three frames were opened directly and visually verified (marked
**seen**, §1.3); the rest are cited from guide text only -- treat their exact
visual layout as **unverified**.

| Frame | Depicts |
|---|---|
| 00-00-00 | Code Browser overview |
| 00-00-35 | Project repos organized by version/platform |
| 00-00-50 | **Seen.** Full Code Browser window, a Windows build -- see §5.1 |
| 00-01-15 | **Seen.** Symbol Tree pane, described in §1.3 |
| 00-02-15 | Symbol Tree pane with search |
| 00-02-25 | Symbol tree expanded for a class with many functions |
| 00-03-20 | Data Type Manager overview |
| 00-03-35 | Data Type Manager archives: the target executable, Windows, Built-in types |
| 00-04-10 | Structure editor for a game-object structure |
| 00-05-25 | Find uses of a type |
| 00-05-50 | **Seen.** Listing as primary view, described in §1.3 |
| 00-06-20 | Listing navigation: label double-click, conditional jump |
| 00-07-00 | Cross references (xrefs) for a symbol |
| 00-07-50 | Data section: defining a string via right-click -> Data |
| 00-09-25 | Decompile view, reconstructed C-like code |
| 00-10-50 | Decompile with function/label navigation and rename (L) |
| 00-11-45 | Function call trees and memory map |
| 00-13-00 | Symbol table with filters |
| 00-14-05 | Functions view with calling-convention filter |
| 00-16-35 | Function list and edit context |
| 00-18-15 | Edit function view: update function and namespace |
| 00-18-30 | Function signature: name, convention, return type, `this` in ECX |
| 00-19-15 | Calling-convention selector: thiscall |
| 00-20-50 | stdcall return with stack cleanup |
| 00-22-45 | thiscall: `this` in ECX, e.g. a minigame object call |
| 00-26-35 | Custom storage and float-to-long, in Data Type Manager |
| 00-27-15 | A read-float function with custom return storage ST |
| 00-29-35 | float-to-long custom return type, usage in caller |
| 00-30-30 | Structure editor: name, size, fields with offsets |
| 00-31-20 | Decompile showing a manager/client relationship at offset 4 |
| 00-32-10 | Vtable concept and inheritance |
| 00-33-50 | A creature-class vtable: destructor and cast functions |
| 00-34-45 | Creature type, vtable at offset 0 via a parent game-object class |
| 00-37-20 | Vtable call in listing at +24, resolving to an update function |
| 00-39-30 | Data Type Manager: multiple template instantiations |
| 00-44-10 | An `extraout` variable, e.g. a ushort read as int |
| 00-48-25 | Stack-param violation: param one overwritten |
| 00-50-40 | Unaffected register and return value from a vtable call |

### 1.3 The three verified frames

- **00-00-50** ("Code Browser opened for a Windows build") -- the full window,
  not a slide. Confirms the real spatial arrangement: a docked, tabbed panel
  top-left (tree + filter box -- Symbol Tree) with a second, smaller docked
  panel below it; **Listing** center-left, largest pane, address/bytes/mnemonic
  columns with syntax coloring; **Decompile** right, roughly matching Listing's
  width, function signature + body; a row of *three* smaller docked panels
  along the bottom (a table, a filter box, a type tree). This is the direct
  evidence for §5.1's layout.
- `frame_00-01-15` ("Code browser with symbol tree visible") -- a presentation
  slide with a cropped inset, not the full window. Confirms Symbol Tree
  *contents*: tree rows with folder/class icons and green function-leaf icons
  nested under a namespace/class hierarchy (a top-level namespace, then a
  class, then a subclass), a **Filter** box pinned at the panel's bottom.
- `frame_00-05-50` ("Listing as primary view") -- also a cropped slide inset.
  Confirms Listing *contents*: address (left, teal), raw bytes, mnemonic +
  operands (color-coded by token type), a thin colored flow/xref gutter on the
  right edge marking branch targets.

---

## 2. Current dashboard inventory

The rendered `/dashboard` page is a `noscript`-safe SSR skeleton
(`workbench.py`) that React **replaces wholesale** --
`ReactDOM.createRoot(root).render(e(App))` at `workbench-app.js:5945-5946`, not
`hydrateRoot`. The skeleton's section IDs (`wb-functions`, `wb-graph`, ...) do
not match the React app's own IDs (`wb-fnbrowse`, `wb-inspect`, ...); this is
cosmetic (the skeleton is replaced before paint in normal use) but means the
skip-link's `href="#wb-functions"` in the SSR shell points at a target React
removes.

Verified live at 1440x900 and 630x900 via the Browser pane (`GET`-only, no
Open/Add/Analyze clicked).

### 2.1 Layout regions (App component, `workbench-app.js:2333-5947`)

| Region | Lines | What's there today |
|---|---|---|
| `wb-chrome` header | 5426-5443 | Brand mark, function filter, palette-shortcut hint, job pulse |
| `RepoStatus` + workflow control | 5444-5451 | "Resume pipeline" -- the top-level pause/resume control (FRONTEND_INTENT §6 supersession) |
| `wb-menubar` | 5452-5548 | File / Edit / View / Analyze / Server / Help, hover-or-click open |
| `wb-sessions` tab strip | 5549-5614 | One tab per open project (not per document) |
| `wb-app-shell` | 5792-5903 | Two-column flex: `aside#wb-sidebar` + `SplitHandle` + `div.wb-editor` |
| `aside#wb-sidebar` ("Explorer") | 5793-5872 | **Flat** project->program list only. No class/namespace/label/import/export tree. Resizable 180-900px via `beginResize` (5874) |
| `CorpusNavBar` (editor tabs) | 1974-2010, used 5889 | `EDITOR_PRIMARY` = Listing / Functions / Call trees / Match / Recover, plus a `<details>` "More" for 12 secondary surfaces |
| `wb-editor-body` -> `renderEditorBody()` | 4848-5422 | One pane at a time, switched by `centerTab` -- see §2.2 |
| `LogDock` | 2238+, used 5904-5922 | Bottom dock, resizable 72-640px, tabs for Log/Jobs; optional side-rail mode >=1280px (`workbench.css:1964-1990`) |
| `footer.wb-status` | 5928-5940 | Source, program, selection, job count, error/last-note |

**Correction against an earlier draft of this spec:** per-stage run buttons
already exist today -- `StepLadder` (929) receives `onRun=${runLadderStep}`
(`runLadderStep` defined 4800) and is used at 4882 (Corpus ladder) and 4916
(per-build pipeline). The Pipeline tab's own quick-action set
(`QUICK_ACTION_SETS.pipeline`, ~1476-1486) is numbered "1 Extract" through "8
Objdiff audit" -- literally one button per named stage. This sits in tension
with FRONTEND_INTENT §9's "per-stage buttons stay banned," but it is an
existing condition, not something this redesign introduces or should silently
repeat. The guide rail in §5.3 is deliberately navigation-only -- it does not
add a ninth instance of this pattern.

### 2.2 What "Listing" (the default tab) actually renders (5342-5421)

Not a Ghidra Listing. It's two `<pre>` blocks side by side:

- `.wb-listing-pane` -> `#wb-listing-preview` (5390-5392): one opaque text
  blob from `detail.preview`, no per-instruction rows, no clickable
  address/bytes/mnemonic columns, no inline xref markers.
- `.wb-decompile-pane` -> `#wb-decompile-preview` (5399-5404): the decompiled
  C as another text blob.
- Grid is `1.1fr / 0.9fr` (`workbench-editor.css:745-751`), collapses to a
  single column under 1100px (`workbench-editor.css:957-962`).
- A 5-button toolbar (Analyze/Decompile/Match/Recover/Fields..., 5361-5381) is
  the only per-function action surface in this pane.

### 2.3 Guide-chapter -> action-catalog reachability

`GET /api/v1/actions` returns 223 action IDs (verified). `GuideWorkflows.tsx:20-328`
(Vite frontend, read-only reference) already groups the guide into 8 workflow
chapters mapped to exact `mcp.*` action IDs -- reused below instead of
re-deriving a mapping. Wiring count = literal occurrences of the action id
string inside `workbench-app.js` (a proxy for "has a dedicated button/panel"
vs. "exists only in the generic Commands/palette list of all 223 actions").

| Guide chapter (from `GuideWorkflows.tsx`) | Key action IDs | In catalog? | Wired in static dashboard? |
|---|---|---|---|
| Orient to the project | `mcp.list-project-files`, `mcp.get-current-program` | yes | 0 direct refs -- Explorer shows project/program names but not via these calls |
| Find symbols and types | `mcp.search-symbols`, `mcp.manage-data-types`, `mcp.list-imports`, `mcp.list-exports` | yes | `search-symbols` is a **quick-action toolbar button** on the Functions tab (`QUICK_ACTION_SETS.functions`, ~1457; rendered via `quickBar("functions")`, 5170) -- reachable, but fires with no query field of its own; **`manage-data-types` 0, `list-imports` 0, `list-exports` 0** |
| Read bytes and reconstructed code | `mcp.inspect-memory`, `mcp.read-bytes`, `mcp.get-function`, `mcp.decompile-function`, `mcp.apply-data-type`, `mcp.manage-function` (rename) | yes | `decompile-function` 8 refs (well wired); `get-function` 1; `manage-function` 2; **`inspect-memory` 0, `read-bytes` 0, `apply-data-type` 0** |
| Trace relationships, keep notes | `mcp.get-references`, `mcp.get-call-graph`, `mcp.inspect-memory` (blocks), `mcp.manage-bookmarks`, `mcp.manage-comments` | yes | `get-references` is **both** a quick-action button ("Xrefs", `QUICK_ACTION_SETS.function`, ~1492) *and* a context-menu item (3888) -- the most discoverable of the gap list; `manage-bookmarks` 1 (context-menu item only, 3890); `manage-comments` 1; **`get-call-graph` 0 direct** (Call trees tab exists but is not driven through this action id -- separate graph endpoint, not re-verified) |
| Check signatures and ABI | `mcp.get-function`, `mcp.manage-function` (info/set_properties/set_storage/set_prototype) | yes | as above -- reachable only through the generic "Fields..." button (5379-5380) opening a raw parameter form |
| Recover structures and vtables | `mcp.manage-structures`, `mcp.analyze-vtables` | yes | **both 0 direct refs.** No structure/vtable panel of any kind exists in this file. |
| Compare template instantiations | `mcp.manage-data-types`, `mcp.manage-structures` | yes | 0/0, same gap as above |
| Diagnose decompiler issues | `mcp.analyze-data-flow`, `mcp.get-function`, `mcp.manage-function`, `mcp.decompile-function` | yes | `analyze-data-flow` is **both** a quick-action button ("Data flow", `QUICK_ACTION_SETS.function`, ~1493) *and* a context-menu item (3889) |

**Reading this table:** every action exists server-side and is technically
reachable through Commands (`wb-tools`, palette `mod+K`) which lists all 223
actions generically with a raw field-by-field form (`ToolField`, 311-497).
Three IDs (`search-symbols`, `get-references`, `analyze-data-flow`) are
already one click away as quick-action buttons -- corrected from an earlier
pass of this table that called them context-menu-only. "0 direct refs" for the
*other* nine IDs (`manage-data-types`, `manage-structures`, `analyze-vtables`,
`inspect-memory`, `read-bytes`, `apply-data-type`, `list-imports`,
`list-exports`, `get-call-graph`) means *no dedicated panel, button, or menu
item anywhere* -- exactly the FRONTEND_INTENT §4.2 complaint ("raw JSON as the
default result", "cards of internal commands"). Guide chapters 4 (half), 12,
13, 14 have **no first-class surface at all** today; that is the central gap
this redesign closes.

**Open, load-bearing question this table exposes (see §7):**
`mcp.manage-data-types` and `mcp.manage-structures` are flagged
`danger: true, mutating: true` at the catalog level (`GET /api/v1/actions`,
verified), even though the *read* modes a browse panel needs (`mode:
"archives"`, `"info"`, `"find_uses"`, `"list"`, `"validate"`) are
non-destructive per `GuideWorkflows.tsx`'s own params. `executeAction`
(4156-4241) gates any `act.mutating` action behind a confirm dialog
(4170-4184) unless called with `skipConfirm: true`. A Types dock that
auto-populates on selection (slice 4) must not fire a scary "Run
manage-structures? This is destructive" prompt for passive browsing -- this is
unresolved, not solved, by this spec.

---

## 3. Accessibility findings (file:line, `workbench-app.js` unless noted)

| # | Finding | Evidence | Criterion |
|---|---|---|---|
| A1 | `Modal` (Open/Save As/Add binary/Shortcuts) does not close on Escape -- its own `onKeyDown` (1552) only traps Tab; the page-level Escape handler (3184-3188) clears palette/confirm/context-menu but never `dialog`. Cancel and x are still reachable by mouse/Tab, so this is not a literal keyboard trap -- the gap is against the WAI-ARIA APG Dialog (Modal) pattern's expectation that Escape closes the dialog | 1543-1585, 3176-3191 | WAI-ARIA APG Dialog pattern; 2.4.3 Focus Order for the missing exit path |
| A2 | No focus return to the invoking control when `Modal` or `CommandPalette` closes -- focus moves into the dialog (1547-1548) but nothing restores it on close | 1543-1585, 2012-2181 | 2.4.3 Focus Order |
| A3 | `CommandPalette` is `role="dialog"` without `aria-modal="true"`; `aria-activedescendant` (2106) points at plain `<button>` elements with no `role="option"`/`listbox` container | 2102-2181 | 4.1.2 Name, Role, Value |
| A4 | Menubar items (`wb-menu-list`) are a plain `<ul>`/`<button>` list with `aria-haspopup`/`aria-expanded` on the trigger (5527) but no `role="menu"`/`"menuitem"` and no arrow-key navigation between items | 5452-5548 | 4.1.2, WAI-ARIA menu pattern |
| A5 | `SplitHandle` (Explorer resize, LogDock resize) is `role="separator"` with `aria-orientation`/`aria-label` but **mouse-only** -- `onMouseDown` only, no `onKeyDown`, no `tabindex` -- not keyboard-reachable at all | 2212-2217; used 5873, 5921 | 2.1.1 Keyboard |
| A6 | Editor tabs (`CorpusNavBar`) communicate "active" via a CSS class only -- no `aria-selected`/`aria-current` on `wb-corpus-nav-item` buttons. **Scope correction:** session tabs are fine -- they already carry `aria-selected=${on}` on the `role="tab"` element (5561); this finding is `CorpusNavBar` only | 1974-2010, 1985-1991, 1999-2005 | 4.1.2 |
| A7 | Session tabs: `role="tab"` on a `<div>` wrapper that contains a separately-focusable `<button>` (5561-5593) -- not the WAI-ARIA tablist pattern (tab itself should be the focusable, roving-tabindex element). Distinct from A6's state-announcement gap -- session tabs already announce `aria-selected` correctly, they just aren't focusable/arrow-navigable as a tablist | 5549-5614 | 4.1.2, WAI-ARIA tab pattern |
| A8 | Single-key shortcuts `j`/`k`/`x`/`Space`/`Enter`/`Escape` bound at `window` level, guarded only by "is focus in an editable field" (3194-3253) -- not scoped to the Functions list having focus, no on/off toggle | 3194-3253 | 2.1.4 Character Key Shortcuts |
| A9 | Non-error toasts are silent to assistive tech: `showToast()` (2702-2728) routes info/success through `lastNote` -> `<span id="wb-last-action" className="wb-hint">` (5939) with **no** `aria-live`. Only the error path gets `role="alert"` (5936) | 2702-2728, 5928-5940 | 4.1.3 Status Messages |
| A10 | Contrast (WCAG relative-luminance formula, computed against the exact tokens in `workbench.css:10-45`): `--text-muted #8c8c8c` is 4.9:1 on `--bg #1e1f22` (passes AA) but **4.1:1 on `--bg-panel #2b2d30`** (fails AA 4.5:1) -- and `.wb-hint` (`workbench.css:1398`) uses exactly this token pervasively across panel-backed surfaces. `--text-dim #6e6e6e` is **3.2:1 on bg / 2.7:1 on panel** -- fails AA outright, used for non-decorative copy at `workbench-chrome.css:96,128,246,284,322,327,460,488,571,588,597`, `workbench.css:827,1481`, `workbench-overlays.css:57,118,580`, `workbench-dialogs.css:152`, `dashboard.css:850` | tokens: `workbench.css:10-45` | 1.4.3 Contrast (Minimum) |
| A11 | `JobLiveRegion` (1832-1834, wired 5625) is a correct `aria-live="polite"` pattern -- cited as a **positive** precedent to reuse for A9's fix, not a defect | 1832-1834 | -- |
| A12 | **Checked, not a gap:** `prefers-reduced-motion` is handled -- `window.matchMedia("(prefers-reduced-motion: reduce)")` in `dashboard.js:362`, plus a `@media (prefers-reduced-motion: reduce)` block in `dashboard.css:949`. Both files load on `/dashboard` (confirmed in the page `<head>`). Still not independently re-verified: a full computed-contrast audit of `--kind-*` badge colors, and hit-target sizing on the dense `wb-fnb-table` row controls -- mark those two unverified. | `dashboard.js:362`, `dashboard.css:949` | -- |

**Positive finding, for calibration:** the app already implements a real focus
trap (1543-1568), `j`/`k` row navigation with range-select (3212-3229), an
accessible `aria-live` job-status region (1832-1834), and per-platform
accelerator labels (1839-1849). This is not a blank slate -- the redesign
should extend these patterns, not replace them.

---

## 4. Web-guideline findings

| Finding | Evidence |
|---|---|
| Two competing "Functions" surfaces are explicitly banned by product doc, not just style: FRONTEND_INTENT §4.2 last paragraph and §9 row "Two left trees including Functions" record the user's own removal of a duplicate sidebar Functions list. Any Symbol Tree added here must route its Functions node into the *existing* `wb-fnbrowse` table, never render its own rows. | `FRONTEND_INTENT.md:135-138,428` |
| "Draw the work, not decoration" -- no invented percentages, no simulated progress, freeze/step/history over auto-pan. Directly constrains the guide rail's step-state design in §5.3 below. | `FRONTEND_INTENT.md:160-188` |
| No Start button; the only workflow control is pause/resume + scope (already implemented, 5446-5450) -- a guide rail must not add per-step "Run" buttons. | `FRONTEND_INTENT.md:286-313` |
| Copy must be plain: verb-first, at most one adjective per sentence, no buzzwords. Existing copy mostly complies already (e.g. "Drop a binary or project here", "Pick a program in Explorer") -- new rail/panel copy should match that register. | plain-copy house rules |

---

## 5. Target layout

### 5.1 Wide (>=1440px) -- mirrors the guide's Code Browser arrangement

Supported by the one full-window frame verified this session (§1.3,
`frame_00-00-50`): docked tree+filter top-left, Listing center-left as the
largest pane, Decompile right at comparable width, a row of smaller docked
panels (table/filter/type-tree) along the bottom. The wireframe below keeps
that shape and fits it around the dashboard's *existing* zones rather than
inventing new chrome.

```
+------------------------------------------------------------------------------------------+
| AD AgentDecompile   [Filter functions...           ^K]   Resume pipeline   3 running       | toolbar (existing)
+------------------------------------------------------------------------------------------+
| File  Edit  View  Analyze  Server  Help                                                    | menubar (existing)
+------------------------------------------------------------------------------------------+
| [repos]  [Workspace.gpr]  +                                                                | session tabs (existing)
+--------+-------------------------------------------------------------+---------------------+
| GUIDE  | Listing  Functions  Call trees  Match  Recover  More...     |  Decompile          | <- existing tab strip,
|        +-------------------------------------------------------------+  f_CEntity::update   |    unchanged
| 1 Orient*| Listing  target.exe   f_0040a3c0 [Analyze][Fields..]                     | +-------------------+ |
| 2 Symbols o| +--------+------+---------------------------+------+ |  | void __thiscall   | |
| 3 Listing o| |address |bytes | mnemonic   operands        |xref  | |  | CEntity::update    | |
| 4 Trace  o | |0040a3c0|55    | PUSH  ebp                  |      | |  | (float dt)        | |
| 5 Signat o | |0040a3c1|8bec  | MOV   ebp,esp               |      | |  | {                 | |
| 6 Structs o| |0040a3c3|51    | PUSH  ecx                  |->L_12| |  |   this->hp -= dt; | |
| 7 Tmplt  o | |  ...   |      |                             |      | |  |   ...             | |
| 8 Diagnos o| +--------+------+---------------------------+------+ |  | }                 | |
|        |  kind: gpr . /home/.../repos . 32 programs . 4102 funcs  |  +-------------------+ |
+--------+-------------------------------------------------------------+---------------------+
|EXPLORER|                                                                                     |
| repos  |                                                                                     |
| SYMBOL |  (right column above is the persistent Decompile dock -- visible from Listing,      |
| TREE   |   Functions, Call trees and Match tabs alike, not only "Listing"; retains last       |
| >Classes| valid function per guide §7, per FRONTEND_INTENT F09 "connected views")             |
|  >Target|                                                                                     |
|   update|                                                                                     |
| >Namespaces                                                                                   |
| >Labels|                                                                                       |
| >Imports| (DLLs)                                                                               |
| >Exports|                                                                                      |
+--------+-------------------------------------------------------------------------------------+
| Log   Jobs   Types  < existing LogDock, one tab added                              [Hide]^   |
|  Types tab = Data Type Manager (archives/structs/enums, guide §5,12,14) + Vtables §13         |
+------------------------------------------------------------------------------------------+
| repos . target.exe   f_0040a3c0   idle                                     Ready       | status bar (existing)
+------------------------------------------------------------------------------------------+
```

Five zones, three of them new: **Guide rail** (far left, narrow), **Symbol
Tree** (below Explorer, same left column), **persistent Decompile dock**
(right, lifted out of the Listing-only split). Toolbar, menubar, session tabs,
tab strip, LogDock and status bar are the *existing* components, unmoved -- the
redesign is additive composition, per FRONTEND_INTENT §8 ("Extend/reconcile
those; do not nest... or create another store").

### 5.2 Narrow (~630px) -- verified against the live page, not just described

At 630px the current build already stacks Explorer above the editor
(`workbench.css:1618-1636` -- corrected from an earlier pass of this spec that
cited `workbench-editor.css`; the `@media (max-width: 1100px)` block setting
`.wb-app-shell { flex-direction: column }` lives in `workbench.css`) but the
Explorer list consumes ~45% of the viewport height before any Listing content
is visible (confirmed via screenshot). Target:

```
+----------------------------+
| AD  [Filter...     ^K]     | toolbar
| . . . . . . . .  <- guide  | guide rail collapses to a horizontal
|                    dot strip, tap a dot -> sheet with that chapter's
|                    title + guide link + "Open panel"
+----------------------------+
| [Explorer v]  Listing v    | Explorer + Symbol Tree become a
+----------------------------+ slide-over drawer. `view.explorer`
| Listing  f_0040a3c0        | (`mod+shift+E`, catalog line 1866) is
| +--------+------+--------+ | already wired -- `runCommand` calls
| |addr    |bytes |mnem/ops| | `jumpTo("wb-sidebar")` at line 3991 --
| |...     |      |        | | but that only scroll-flashes the
| +--------+------+--------+ | always-visible sidebar. The drawer's
|                            | hide/show toggle is new behavior this
|                            | handler must be extended with, not a
| [Show Decompile v]         | reuse-as-is (see Open Questions)
+----------------------------+ Decompile becomes a same-pane toggle,
| Log Jobs Types       [^]   | not a side column (reuses the existing
+----------------------------+ <=1100px single-column collapse already
| repos.f_0040a3c0.idle      | in workbench-editor.css:957-962
+----------------------------+ status bar
```

Explorer/Symbol Tree drawer and Listing/Decompile toggle both reuse
`readUiPref`/`writeUiPref` (1667-1680) -- same mechanism already used for
density and jobs-dock placement, no new persistence layer.

### 5.3 Guide rail step state -- observable only, never invented

Each of the 8 rail items (from `GuideWorkflows.tsx`'s own chapter titles,
reused verbatim to avoid a second taxonomy) shows one of three states, each
derived from state the app already has in scope, never a fabricated
"completed" checkmark (FRONTEND_INTENT §4.3):

| State | Token | Derived from |
|---|---|---|
| Not reachable yet | `--st-partial` (dim) | no `dossier.ok` / no `program` selected |
| In view | `--accent` (highlighted) | the rail item's target pane is the current `centerTab` |
| Has evidence | `--st-proven` (dot filled) | the pane's own data is non-empty (`selected`, `detail.decompile.text`, a non-empty type/structure list, etc.) |

Clicking a rail item calls the existing `jumpTo`/`scrollToSurface`
(1682-1693) and opens the guide anchor in a new tab -- it never calls
`executeAction`. This keeps the "no Start button, no per-stage buttons" rule
intact (FRONTEND_INTENT §9 row "no Start button... per-stage buttons stay
banned").

Rail and hint copy states the project -> program -> address hierarchy and
must not restate the guide's own shorthand as implementation rules -- the
capability inventory already enumerates ten such traps (PE exports != entry
point, returns don't universally live in EAX, "a repo is an executable" is not
the object model, a cleaner decompile is not validation, etc.):
[`2026-09-20-ghidra-guide-capability-inventory.md:112-134`](2026-09-20-ghidra-guide-capability-inventory.md).

### 5.4 Tokens

No new hex values -- `workbench-tokens.css` says widget CSS must consume its
tokens, not invent colors, and that discipline extends to this redesign.
Reuse: `--bg-panel` (Symbol Tree / rail background), `--border` /
`--border-strong` (dividers, already used for `SplitHandle`), `--accent` /
`--focus` (active rail step, active tab), `--st-proven` / `--st-partial` /
`--st-failed` (rail state, §5.3), `--font-mono` (Listing rows, already used
for `.wb-preview`). One deliberate exception proposed in §3/A10's fix: either
migrate `--text-dim` usages that carry legible (non-decorative) copy to
`--text-muted`, or add a single new AA-safe gray token to
`workbench-tokens.css` (the canonical token file) rather than hand-picking hex
per component -- default recommendation is the migration (zero new tokens),
see Open Questions.

**Why this is Phase B now:** this redesign is the Phase B layout reshape that
[`../prototypes/dashboard-flow-evolution/decisions.md`](../prototypes/dashboard-flow-evolution/decisions.md)
(2026-08-31, "Sign-off: Phase A interactions sufficient; U4 layout reshape not
required unless dogfood proves otherwise") deferred pending dogfood evidence.
That evidence is the guide-chapter reachability gap in §2.3 above
(structures/vtables/data-types: zero direct references anywhere) and the
accessibility findings in §3 -- not a stylistic preference. Acceptance should
be read against
[`../prototypes/dashboard-operator-feel/feel.md`](../prototypes/dashboard-operator-feel/feel.md)'s
§64 "Phase B success signals" (e.g. "new operator finds cross-match in under
10 seconds"). See also
[`../prototypes/dashboard-operator-feel/2026-09-28-static-surface-scope-note.md`](../prototypes/dashboard-operator-feel/2026-09-28-static-surface-scope-note.md)
for how `feel.md` now scopes to the static surface specifically.

---

## 6. Implementation plan

Every slice is additive composition over the files above; none proposes a new
store, a second Functions list, or a Vite change. Acceptance checks are
**browser-driven** (Browser pane / Playwright), not curl and not new test
files or fixtures -- see §7 for why.

| # | Slice | Files / functions touched | Acceptance check |
|---|---|---|---|
| 0 | **Prototype shell.** Wrap the existing `aside#wb-sidebar` + `wb-editor` in a 4-zone CSS grid (guide rail / explorer+symbol-tree placeholder / editor / decompile dock), pure re-flow, no new data fetching. Gate behind a "Use classic layout" View command using the existing pref mechanism. | `workbench-app.js:5792-5903` (render tree only); new grid rules in `workbench-editor.css` | Screenshot at 1440px shows 4 zones simultaneously without switching tabs; screenshot at 630px shows graceful stacking; every `WORKBENCH_COMMANDS` id (1851-1898) and every `SURFACES`/`CORPUS_NAV` id (41-64, 1595-1608) still resolves from the menu and the palette; every deep link still resolves through `bootWindow`/`editorTabFor`/`BROWSE_ANCHOR_WINDOW` (1614-1643) -- check `?window=wb-match`, `#functions`, and `?mode=static&window=wb-corpus&binary=...` specifically; toggling "classic layout" reproduces the same regions and tabs as today's pre-change screenshot (not a byte-identical claim -- a screenshot can't show that) |
| 1 | **Symbol Tree**, real data, Functions node routes into the existing table (never a second list). Wire `mcp.list-project-files`, `mcp.get-current-program`, `mcp.search-symbols`, `mcp.list-imports`, `mcp.list-exports` -- all confirmed `danger:false, mutating:false, long_running:false` in the catalog, so they return synchronous JSON via `POST /api/v1/actions/<id>` (no job, no polling) but land in the generic raw-JSON reaction panel (5406-5418) today -- this slice's real work is parsing that JSON into tree nodes, not fetching it differently. | new `SymbolTree` component in `workbench-app.js`; reuses `executeAction`/`API` | Expand Classes/Namespaces/Imports/Exports against a real open program; click a function leaf -> confirm it selects the row in the *existing* `wb-fnbrowse` table (5162-5227), no second row list rendered anywhere |
| 2 | **Continuous Listing.** Replace the `#wb-listing-preview` text blob (5390-5392) with an address/bytes/mnemonic/xref row table, backed by `mcp.inspect-memory` (instruction/navigate) + `mcp.get-references` -- both confirmed non-mutating/non-long-running, same synchronous-JSON note as slice 1 -- falling back to today's `detail.preview` text when the structured feed errors. | `workbench-app.js:5353-5397`; new `ListingRows` component | Select a function; confirm rows are individually navigable (not just scrollable text) and an xref marker is visible on at least one branch instruction |
| 3 | **Persistent Decompile dock.** Lift `.wb-decompile-pane` (5399-5405) out of the Listing-only branch into the slice-0 right column so it updates from Functions/Call trees/Match too, retaining the last valid function per guide §7. | `workbench-app.js:4848-5422` (control flow only) | While on the "Functions" tab, click a row; confirm the right-hand Decompile dock updates without switching to "Listing" |
| 4 | **Types dock** (Data Type Manager + Structures + Vtables) as a new LogDock tab beside Log/Jobs. Wire `mcp.manage-data-types` (archives/info/find_uses), `mcp.manage-structures` (list/info/validate), `mcp.analyze-vtables` (analyze -- this one alone is `mutating:false`). **Blocked on the open question in §2.3/§7:** `manage-data-types` and `manage-structures` are catalog-flagged `mutating:true`, so `executeAction`'s default confirm gate (4170-4184) would prompt on every tree expand unless this slice explicitly passes `skipConfirm:true` for read-only modes -- resolve that before building, don't silently bypass the gate. | `workbench-app.js:2238+` (`LogDock`); new `TypesPanel` | Open the Types tab; browse an archive; inspect one structure; run "Find uses of a type"; confirm a result click updates the Listing/Decompile selection; confirm no confirm-dialog interrupts ordinary browsing |
| 5 | **Guide rail**, 8 chapters from `GuideWorkflows.tsx`, each a nav-only link (pane focus + guide anchor), state per §5.3. | new `GuideRail` component; reuses `jumpTo`/`scrollToSurface` (1682-1693) | Click each of the 8 items; confirm it focuses the right pane and opens the correct guide anchor in a new tab; confirm zero `executeAction` calls fire from the rail itself |
| 6 | **A11y remediation**: Escape closes `Modal` (A1), focus returns to invoker (A2), `SplitHandle` keyboard-resizable with `tabindex`+arrow keys (A5), `aria-selected`/`aria-current` on tab items (A6/A7), non-error toasts get an `aria-live` region (A9), `--text-dim`->`--text-muted` migration for legible copy (A10). | exact lines cited in §3 | Tab to a modal trigger, open, press Escape, confirm focus returns; arrow-key resize a split handle; trigger a success toast and confirm it's announced (aria-live region present in the accessibility tree) |

Slices 1-6 are independently shippable and reversible; each only adds a
component and wiring, none removes an existing surface or action.

---

## 7. Open questions

Recorded, not resolved here -- resolving these is implementation work, out of
scope for this integration pass.

| Question | Recommended default |
|---|---|
| **Unresolved -- blocks slice 4 as designed.** `mcp.manage-data-types`/`mcp.manage-structures` are catalog-flagged `mutating:true` even for their read-only modes (§2.3). Should a browse-only Types dock call `executeAction` with `skipConfirm:true` for `mode` values known to be read-only (`archives`/`info`/`find_uses`/`list`/`validate`), or should the backend split these into separate read/write action IDs? | Recommend the backend split (cleaner, matches how every other guide-chapter action is already read/write-separated by ID) but that is outside "static dashboard only" scope -- record it as a cross-cutting backend request, and treat `skipConfirm:true` gated on an explicit client-side allowlist of read-only mode values as the fallback if the backend change isn't taken. Do not ship slice 4 with either left silently unresolved. |
| Acceptance-check method: read-only `curl` for GET checks vs. browser-driven checks. | Default to **browser-driven** acceptance checks for every slice (as written in §6) -- the stricter, more specific project constraint. Use curl only for this document's own drafting, not for slice acceptance. |
| Two divergent copies of `workbench-app.js` exist (live copy 5948 lines vs. a worktree copy at 6210 lines, different sha256, mtimes 7ms apart). Which is authoritative for implementation? | Treat the **live-served copy** as ground truth (it's what `workbench.py:2319` actually serves); the worktree's extra 262 lines were checked and are not guide/Code-Browser-related (see the caution note above), but still diff-and-reconcile before editing -- do not silently overwrite either. |
| `view.explorer` (`mod+shift+E`, declared `workbench-app.js:1866`) is wired (`runCommand`, 3991) but only to `jumpTo("wb-sidebar")` -- a scroll-flash, not a hide/show toggle. Should the narrow-width drawer (§5.2) extend this same command, or introduce a separate `view.explorer-drawer` command? | Extend the existing command: at >=1100px keep today's scroll-flash behavior (sidebar is always visible, flashing it is enough), at <1100px change its behavior to toggle the drawer. One command, width-conditional behavior -- avoids a second command id with near-identical wording in the palette. |
| `view.jobs-rail` (>=1280px, `workbench.css:1964-1990`, sets `.wb-app-shell { margin-right }`) docks Jobs on the *right* edge -- the same edge §5.1 gives to the persistent Decompile dock. Not resolved this session. | Default: Decompile wins the right edge; `view.jobs-rail` degrades to the bottom-dock behavior it already has as a fallback at that width, and stays reachable as a menu/palette command (keep it in the reachability-invariant check in slice 0) even if its side-rail layout is suppressed. Revisit if users rely on the side-rail specifically. |
| Should the Types dock (slice 4) live in the bottom `LogDock` (space-constrained, but reuses the existing resizable/collapsible dock with zero new chrome) or as a fourth persistent column (matches Ghidra's own separate Data Type Manager window more literally, but competes for width with Symbol Tree + Decompile on anything under ~1600px)? | Bottom dock, per the wireframe in §5.1 -- cheaper (reuses `LogDock`), reversible (just another tab), and the guide itself treats Data Type Manager as one of several dockable-but-secondary tools (§8 "Other Code Browser Tools"), not co-equal with Listing/Decompile. |
| `--text-dim` contrast fix (A10): migrate existing usages to `--text-muted`, or add one new token? | Migrate first (zero new tokens, `--text-muted` already passes AA on `--bg-base`); only add a new token to `workbench-tokens.css` if the migration is later found to remove a needed visual distinction between "muted" and "dim" states. |
