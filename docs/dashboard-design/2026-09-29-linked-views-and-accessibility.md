# Linked views and accessibility

Date: 2026-09-29
Status: **design plan, not a delivery receipt.** Nothing here is implemented in either frontend. No server, browser, build or test was run for this document; switch counts are estimates from documented click paths, not observations. Acceptance for each unit is stated as a future check.

Scope: remove tedious clicking between views in the workstation, and make every capability reachable and perceivable by keyboard-only, screen-reader, low-vision and motor-impaired operators, on both the static 8080 workbench and the optional full workspace, over the same backend. The design system (`docs/design-system/project/`) carries the rules and components; this plan carries the rationale, the per-journey ledger and the delivery units.

Governing documents are unchanged: VISION, STRATEGY, AGENTS and [FRONTEND_INTENT](../FRONTEND_INTENT.md). This plan adds units U171–U191 and the F29–F35 requirement rows in FRONTEND_INTENT; it does not reorder recovery work or authorize any live operation.

## Method

1. **Research, six parallel sweeps** (read-only; no frontend source was read):
   - a friction map of 39 operator journeys from the intent, spec, inventory, feel and plan documents;
   - a structural audit of the design system (50 findings) and an audit against the Vercel Web Interface Guidelines skill (41 findings);
   - an audit of the four diagrams as a navigation model and as accessible artifacts (23 findings);
   - external patterns from IDA, Ghidra, Binary Ninja, Cutter, x64dbg, VS Code, JetBrains, objdiff, decomp.me and Chrome DevTools (27 patterns);
   - WCAG 2.2 and WAI-ARIA APG requirements mapped to components (41 rules).
2. **Design panel**: three designers with different lenses (keyboard power user, accessibility first, corpus and evidence first) each proposed 16 improvements; a lead designer merged them into 21.
3. **Adversarial verification**: every proposal was reviewed by a skeptic for doctrine (claim boundaries, read-only browsing, one selection owner, no fabricated state, parity of both surfaces) and for accessibility and honest click counts. Required changes are folded into the units below.

## The four habits that cost clicks

Most of the documented switching comes from four habits:

- **Travelling to see**: opening another tab, page or dock tab only to read something (a callee, a counterpart, a fact's receipt, a ladder, a job).
- **Replacing to compare**: switching the inspected build or tab to compare, which destroys the context being compared against.
- **Losing the place**: pages and windows that do not carry their location, so Back, reload, links and surface switches re-navigate by hand.
- **Finding the next item by hand**: returning to a list after each item, and reading outcomes in a separate dock instead of on the row.

The units answer each habit: information comes to the selection (Peek, rail sections, XrefPanel, CounterpartStrip, outcomes on the row); comparison opens beside instead of replacing (SplitCompare, Hold); the location lives in the URL and history (location schema, NavigationBar); and result sets become worklists stepped with one key (F8).

## Per-journey ledger

Before = documented or implied view switches. After = switches with the units in place (keystrokes inside one view are not counted as switches). Estimates, not observations.

| Journey | Task | Before | After | Main units |
|---|---|---:|---:|---|
| J01 | Inspect a function in build A, then see its counterpart(s) in builds B-D (address, divergence class, identity-edge state), and return to build A | 5 | 1 | UX-05 (Peek reads them at 0) |
| J02 | From a function's proof state (seven facts), open the receipt behind a fact and the job that produced it | 5 | 1 | UX-04 + UX-10: 0 workspace switches, 1 dock-tab change; 2–3 activations |
| J03 | Find which pipeline stage / concurrent lane produced a given receipt or job | 4 | 0 | UX-10 StageChip on the row |
| J04 | Understand why a stage/entity/objective is blocked and what continues | 5 | 1 | UX-12 diagnosis in place |
| J05 | Go from a diagram concept (stage gate, lock, lane, ladder step) to the live entities/jobs currently at it | 5 | 1 | UX-08 go to anything |
| J06 | From a readiness x coverage matrix cell (entity x build) open the resolution-ladder evidence and any contested pair | 4 | 1 | UX-13 (Peek reads the ladder at 0) |
| J07 | Review a candidate match and check the bytes/blocks of both endpoints before deciding | 8 | 2 | UX-16 + UX-05 |
| J08 | Recover from a refused (stale/missing basis) review decision | 4 | 1 | UX-16 master-detail review |
| J09 | Follow a cross-reference from code and return to where you were | 4 | 1 | UX-04 read at 0 · UX-07 follow, Alt+← back |
| J10 | Relate an instruction row to its decompiled statement and vice versa | 6 | 0 | UX-03 reflected cursor |
| J11 | Rename or retype a local variable seen in the decompiler | 6 | 2 | UX-15 edit where you read |
| J12 | Edit a function signature / calling convention / custom storage and verify that dependent views updated | 5 | 2 | UX-15 edit where you read |
| J13 | From a decompiler variable/field inspect its structure type, offsets and uses, then apply/refine the type | 5 | 2 | UX-03 Code Browser composite |
| J14 | Investigate a vtable: slots, targets, callers, class layout, and the same slots on other builds | 6 | 2 | UX-07 Slots mode + UX-13 |
| J15 | Diagnose a decompile artifact (extraout/unaff/wrong return) before changing a prototype | 6 | 2 | UX-03 Code Browser composite |
| J16 | Explore the call graph and read code of nodes along the way | 3 | 0 | UX-03 graph beside code + UX-06 held graph |
| J17 | Walk every member of a logical identity across builds | 6 | 1 | UX-05 + UX-02 |
| J18 | Find out why a function has its name: winning tier, donor build, rejected alternatives, conflicts | 4 | 0 | UX-06 rail section |
| J19 | From a job in the dock, see which entities/builds it changed | 4 | 1 | UX-01 typed links |
| J20 | From an actual-work event (propagation, repair, verify), inspect the underlying diff/evidence and step through history | 4 | 1 | UX-01 typed links |
| J21 | Inner loop: run a catalog verb on the selected function and read its outcome | 5 | 2 | UX-14 outcomes on the row |
| J22 | Run one verb on a checked set and verify each function's result | 7 | 2 | UX-10 walkable provenance |
| J23 | Consult a corpus panel (Cross-match, Recovery, STABS, Knowledge, Review) for the current function and come back | 3 | 0 | UX-06 rail sections (via Show all: 2) |
| J24 | Use Atlas similarity map / report / explorer page and return to the same function | 3 | 2 | UX-02 `panel=` views; 0 re-selection |
| J25 | Follow a link between the static workbench and the React app without losing the destination | 3 | 1 | UX-02 shared schema (U172); +1 confirm when the link names another project |
| J26 | Switch the inspected build while keeping the same logical entity | 3 | 1 | UX-05 counterparts in place |
| J27 | Open a Ghidra program whose corpus inventory/binding is missing and get to its functions | 4 | 2 | UX-01 dead-end rule, plus the kept ConfirmDialog |
| J28 | Detect and act on starvation: oldest unreviewed row, oldest waiting lane, job past deadline | 4 | 1 | UX-11 diagram ↔ live |
| J29 | Pause/resume admission and understand exactly what it drains and which lanes it does not own | 4 | 0 | UX-11 scope sentence beside the control |
| J30 | Import binaries, watch the admitted work, then start working on the new build | 4 | 1 | UX-10 walkable provenance |
| J31 | After a project merge, inspect a conflicting name/type in its build | 4 | 1 | UX-01 typed links |
| J32 | Check where context pieces were placed and resolve proposed-label conflicts | 3 | 1 | UX-01 typed links (≥1100px; 2 below 700px) |
| J33 | See why an entity is not runtime-usable (e.g. not_detourable) on a build and whether other builds are | 4 | 1 | UX-13 (Peek reads the refusal at 0) |
| J34 | From a whole-image delta, get to the offending function/data region and its object diff | 4 | 1 | UX-01 typed links |
| J35 | Understand a stale fact: what dependency changed and when revalidation runs | 3 | 0 | UX-01 typed links (1 if the basis evidence is not cached) |
| J36 | From strings/imports/exports/sections/bookmarks get to use sites and bytes | 3 | 1 | UX-01 typed links |
| J37 | Do any cross-view journey on a narrow viewport (<700px, 598x912) | 6 | 3 | UX-21 narrow continuity |
| J38 | Keyboard / screen-reader user: go from a job-transition announcement to the result and back to the entity | 4 | 1 | UX-18 regions and keymap |
| J39 | Iterate on candidate source repair: diagnostic -> changed line -> compile -> objdiff | 4 | 1 | UX-01 typed links |
| **Total** | 39 journeys | **174** | **44** | about 75% fewer switches (estimates) |

The largest single gains are the inner code loop (J09 + J10: about 10 switches per function down to about 1), match review (J07: 8 → 2 per decision) and batch verification (J22: 7 → 2, independent of batch size).

## Units

Each unit lists what changes, why it removes switching, its accessibility contract and its doctrine safeguards. P0 units are the foundation the others assume.

### U171 · Typed links and one activation grammar (P0; UX-01)
Every mention of an address, symbol, counterpart, fact, receipt, job, logical id, basis digest, diagnostic, delta region, conflict, work-view event or pipeline node is an `<a class="ad-link">` over the location schema. Each resolves to exactly one place. The design-system Linked views table also says, per type, whether it moves the primary location and where focus lands.

One grammar on both surfaces:
- **Enter** go;
- **Shift+Enter** open beside (a Held pane; on 8080 without split panes, a new window labelled "(new window)");
- **Alt+↓** peek (also after a 400ms pointer rest or 800ms focus rest; focus-rest is off at 400% zoom and below 700px);
- the **Keep** button, whose Shift+K letter works only inside a Peek or card;
- **Shift+F10** opens the one flat link menu (Open · Open beside · Peek · Keep; Reveal in, listing only valid destinations; Copy link · Copy ‹typed value›);
- **Ctrl/Cmd+Enter** opens a browser tab.

In checkable grids, Ctrl/Cmd-click and Shift-click belong to the checked set; there, Open beside is Shift+Enter or the menu. Alt+Enter and Ctrl/Cmd+I were rejected for Peek (Alt+Enter means properties in many tools; Ctrl+I is Page Info in Firefox). With a coarse pointer, each row exposes one 44px row-menu button. Every component README gains a **Linking** block: Publishes, Follows, Targets rendered, Peek source, Absent copy, Target-size exception.

*Safeguards:*
- Focus never changes workspace, build, dock tab or history.
- Absent and unresolved are words. Ambiguous and contested are the word plus the ladder link, and contested lists both candidates with "no winner".
- Counterpart links show their edge word and exist only for recorded edges. Address links carry their build.
- A link naming another project lands on a StateNotice with "Open ‹project›" armed and confirm-gated, because opening admits work (U105).
- Dead ends arm at most one action from `GET /api/v1/actions`, reuse first (binding or resume when recovered analysis or receipts exist), nothing while discovery is not loaded, and never run it.
- Interception is a contract: only same-origin anchors that parse fully under the schema; no server GET for intercepted links; no speculative prefetch; the URL is the only navigation state. Whether the static surface intercepts today is **not verified from docs**.

*Acceptance (future):* both surfaces emit the same href set, accessible names and absent words for one fixture entity, checked by a read-only text diff (richness fallbacks allowed); every target type opens its one destination; the Linking block exists in every component README. Observe on 8080 only when authorized.

### U172 · One location schema and browser-backed history (P0; UX-02)
`docs/design-system/project/location-schema.json` is loaded by both surfaces. It holds readable names (`project`, `session`, `entity`, `build`, `addr`, `ws`, `panel`, `views`, `cmp`, `hold`, `keep`, `dock`, `job`, `receipt`, `type`, `f`, `q`, `page`, `t`, `node`, `wl`), one alias table (`p`, `e`, `b`, `a`, `sp`, `slug`, `logical_id`, `binary`, `tool`, `tab`, `pin` → `keep`, `window=wb-*`, `focus=`) and a mapping for every documented legacy window.
- `ws` keeps four workspaces. `panel` addresses full corpus views (Report, Atlas, Review, Builds, Pipeline map) and is the target of every "Show all". Explorer is the Navigator region.
- `hold` is for held center panes only (`kind:id@build[:addr][~basis]`, at most two). `keep` is for Kept cards.
- pushState on:
  - Go (including Make primary, job or receipt links and Show all);
  - a workspace switch;
  - a build switch;
  - opening or closing a `cmp` pair.
- replaceState, throttled to after the settle, for focus, cursor, filters, views, dock, hold and keep.
- Browser Back, Alt+←/→ and mouse buttons are the app's history.
  - Each stop restores workspace, views, split, viewport (anchor address plus caret) and focus (region, component, row key).
  - Back and Forward never open, close or re-point holds.
  - A Recent menu (right-click on Back) lists this tab's last 20 stops. Back itself has no history menu.
- Restore reads now: cached panes render from stored evidence, and expensive panes say "Not loaded. Open to read it."
- Never in the URL: the checked set, drafts, credentials.

*Safeguards:*
- A URL or history stop naming another project never switches it: a StateNotice names both projects, with Switch armed and Stay.
- History moves clear the checked set on a program change (announced first), cancel an open ConfirmDialog, rebind the ActionStrip without arming it, and never replay an action.
- Holds carry a basis token ("◷ Basis changed since held"; "Basis at hold time not recorded").
- Reads are keyed by location token and selection generation.
- `history.state` and Recent are non-authoritative client state.

*Acceptance (future):*
- Both surfaces parse `location-schema.json` identically, with an empty diff and lossless round trip of parameters a surface cannot render.
- Reload, a shared link and a surface switch land on the same entity, build, address and focused element.
- A read-only grep finds no alias names in design-system preview hrefs.

### U173 · Code Browser composite (P0; UX-03)
A Views toolbar (aria-pressed toggles, `views=` in the URL) replaces the analysis tablist: Listing and Decompile side by side at ≥1100px, stacked at 700–1099px, one view with "Show in other view" below 700px; a HexStrip under the listing; Graph beside when chosen. One reflected cursor: focusing a token marks the mapped rows in every visible view (gutter bar plus underline, never color alone); Enter moves the cursor for all views; missing mappings say "No instruction mapping for this statement". Focus-scoped `r` moves focus to the reflected row; `h` highlights all occurrences. Xrefs and Matching leave the center tablist (see U177, U175).
*Removes:* J10 6 → 0 and most of J09, J13, J15, J16, J34, J36, J39.
*Components:* DecompilePane, HexStrip, GraphPane, CodeBrowser, FunctionOutline.

### U174 · Peek everywhere (P0; UX-04)
A content table by target type (code lines in the host view's own form; facts with their receipt, job and StageChip; stale basis old → new; gate waits with age; ladder runs; counterparts; jobs' three readouts; name provenance). One Esc order (close peek → close menu → clear transient filter; Esc never clears the checked set). Keep is carried as `keep=`. Below 700px Peek is a bottom sheet.
*Safeguards:* cache-only by construction; "Not loaded. Open to read it." is an answer, not a fetch; stale stays labelled.
*Accessibility:* WCAG 1.4.13 dismissable, hoverable, persistent; opens on focus too; never steals focus.

### U175 · Counterparts in place (P0; UX-05)
A CounterpartStrip above the Code Browser names every build's counterpart with locator glyph and word, divergence and edge state; Enter switches the inspected build **keeping the instruction position** through backend alignment ("No instruction mapping for build-c; showing function start"; "build-d: no counterpart (unresolved); staying on build-a"); Shift+Enter opens SplitCompare; Alt+PageDown/PageUp step builds. SplitCompare aligns on anchors with a linked scroll, F7 next difference and collapsed equal runs. Compare stays the N-way workspace.
*Safeguards:* counterparts only from recorded identity edges and locators; contested has no winner; equal rows in a split say "local; ≠ whole-image proof".

### U176 · Follow, Hold and Kept (P1; UX-06)
Following panes update after a 200ms settle (`settle-delay`), keep prior content dimmed with "Loading ‹name›", cancel obsolete requests and set aria-busy; an **Update panes** control ("As I move" / "On Enter") switches to commit-on-Enter. The constant-named **Hold this pane** toggle (aria-pressed, state words "Following · sync A" / "Held · ‹entity› @ ‹build› · ‹age›") freezes a pane to entity × build × address, with a basis token, its own history, "◷ Basis changed since held · Refresh" and Make primary; at most two center panes, further holds become Kept cards. The evidence rail absorbs the corpus panels as selection-scoped sections ("For ResourceRef::Resolve · build-b") with "Show all".
*Safeguards:* still one selection owner; held and kept are read-only and never silently refresh; the ActionStrip binds only the primary.

### U177 · XrefPanel, call hierarchy, vtable slots, outline (P1; UX-07)
References live in the evidence rail (movable to the dock). XREF[n] hints are links; focus-scoped `x` focuses the panel from a code well; `]`/`[` step the code cursor through the panel's rows while focus stays in the code; `w` collects rows into a worklist. Modes: Calls (incoming/outgoing tree, depth 1–3, "depth limit reached"), Slots (vtable slots with per-build columns) and Outline.
*Safeguards:* reads the stored xref index only ("not indexed here"); cross-build rows only through accepted edges and resolved locators.

### U178 · Go to anything (P1; UX-08)
One engine behind Ctrl/Cmd+P (the NavigationBar field), Ctrl/Cmd+K (palette, `>` preselected) and Ctrl/Cmd+G (`:` typed). Prefixes `@` symbol, `:` address, `#` logical id, `!` job, `%` receipt or basis, `~` pipeline node, `>` command, `$` string, `'` marks and worklists, `?` help. Rows name type, target build, per-build locator state and where they open; actions show their binding or are aria-disabled with the reason. Repeat-last jump.
*Safeguards:* read-only search; previews cache-only; actions only arm the ActionStrip.

### U179 · Marks, recent locations and worklists (P1; UX-09)
Focus-scoped `m`+letter marks an entity and address (resolves per build through the locator); `'`+letter jumps; marks carry notes and are context-hint tier. Recent locations gain "Edited only" and "Touched by jobs" filters. Any result set can become a worklist (`w`); F8 / Shift+F8 step it from anywhere; the active worklist is a NavigationBar chip with "4 of 12".
*Safeguards:* marks are not evidence; a worklist is view state, never a job queue; worklists carry an as-of stamp.

### U180 · Walkable provenance (P1; UX-10)
`pipeline-model.json` gains `catalog_verbs` per stage and lane; a StageChip ("5 Propagation · lane A") appears on every job, receipt, problem and go-to row and links to the PipelineMap node. ProvenanceStamp becomes a link group (receipt, job, basis, witness). ActivityRecord gains a "Changed" line that applies a removable FilterChip ("Changed by a3f9 ×"), build links, produced receipts and linkified log lines. EntityTimeline shows one entity's receipts, jobs, fact changes and edits in order.
*Safeguards:* links only where a record names the target (no timing correlation); reused and historical labels carried through; unmapped verbs say "stage: unmapped".

### U181 · Diagram ↔ live loop (P1; UX-11)
Diagram outlines and draw.io nodes link to their in-app location (`?node=gate-4`), generated from the model. The PipelineMap peeks counts, oldest waiting age and lock owner; Enter on a lock opens the Jobs dock filtered by that resource with the OwnershipPanel expanded. WorkflowControl carries a scope sentence whose nouns are node links ("Pausing drains admission for stages 1–8; lanes C and E are separately owned"). An **Explain** disclosure on failures, gate waits, ladder rows and the live StageCard renders the node's Trying to / How / In → out / Gate text from the model.
*Safeguards:* nodes are links, never Run buttons; counts per fact axis, never summed; external owners stay external.

### U182 · Diagnosis in place (P1; UX-12)
FailureRecord and ObjectiveSummary fields become disclosures and links in a fixed order (reason, scope, evidence excerpt, owner and resource, freshness, spend, wake condition, what continues, Explain). The dock's ProblemsList is a grid grouped by pipeline node; F8 steps problems from anywhere; starvation bars link to the row, lane or job they measure; empty states arm (never run) the one fix; the dock has Freeze updates.
*Safeguards:* failures drawn at their real unmet dependency; empty is not permission to analyze.

### U183 · Matrices as 2-D grids (P1; UX-13)
ReadinessMatrix and CounterpartMatrix are APG grids with cell focus: arrows, Home/End, Ctrl+Home/End, PageUp/PageDown. Alt+↓ peeks the ladder run; Enter writes entity + build and focuses the EntityBuildCard in the rail (with a back-link "from ReadinessMatrix · row 12 · build-c"); Shift+Enter opens SplitCompare; a contested cell opens two held panes "contested · no winner".
*Safeguards:* locator status, observed status and identity-edge state stay separate; Enter on an unresolved cell opens the ladder, never picks an address.

### U184 · Outcomes on the row; Enter always means Go (P0; UX-14)
An OutcomeCell (compact TaskLifecycle) on every targeted row: "a3f9 · running · unit 3 of 6", then the terminal word and the facts whose receipts that job wrote. Checked-set runs get one cell per row and a summary chip whose words are filters; the run becomes a worklist. The ActionStrip stays armed after Run ("Submitted a3f9 · pending"), focus-scoped `.` repeats the armed action on the focused row, and prefill order is selection → last fields for this action on this program → catalog defaults, each labelled with its origin. Enter always means Go (the old "Enter opens the last action strip" is superseded).
*Safeguards:* catalog path unchanged (keys only arm; mutations confirm); no optimistic outcomes; lifecycle is never merged into facts.

### U185 · Edit where you read (P1; UX-15)
A TokenContextMenu typed by token kind (local: rename, retype; parameter: signature, storage; field: apply type; call: callee signature; any: peek type, show uses, show data flow, copy), each mutating label naming its binding. F2 edits inline with the naming-convention hint; the IDA-style profile adds focus-scoped n, y and ;. After the terminal result, a BeforeAfterBand shows the re-read change in place.
*Safeguards:* catalog only; after-state only from a re-read; edits scoped to one concrete build.

### U186 · Master-detail review (P1; UX-16)
MatchReview's focused row drives an inline or rail detail (CandidateAlignment, IdentityEdge, divergence components, alternatives with margin) that follows j/k after the settle. Focus-scoped `o` opens both endpoints as a held pair beside the queue; `d` arms Decide bound to the checked set. A refused decision (changed basis) shows a BasisDelta of only what changed ("changed since you looked", "new", "no longer on this page") and unchecks changed rows.
*Safeguards:* review is an override, never a gate; decisions stay token-bound; stale decisions are never resubmitted automatically.

### U187 · Layout presets and persistent layout (P2; UX-17)
Presets Read, Compare, Review, Triage and Verify rebuild set every splitter, collapse, view toggle and dock tab in one pick (palette, View menu, NavigationBar). Pane sizes come from tokens and persist per viewer; each pane header has a size menu; rails have 24px collapse strips; session tabs restore their own state.
*Safeguards:* view preferences only, never selection, binding or action.

### U188 · Regions and one remappable keymap (P0; UX-18)
`keymap.json` and guideline Keymap, read by both surfaces: scopes (global with a modifier, region, composite, code well, edit mode), browser-reserved list, profiles (default, IDA-style), Esc order. Landmarks, headings, skip links, F6 region cycling with focus memory, Ctrl/Cmd+B / Ctrl/Cmd+Alt+B / Ctrl/Cmd+J toggles, and a `g` leader with which-key hints where browsers take F6. KeymapEditor, ShortcutSheet (Ctrl/Cmd+/) and ChordHint.
*Accessibility:* WCAG 2.1.4 (single keys focus-scoped, remappable, can be turned off), 2.4.1, 2.4.3, 3.2.6.

### U189 · Screen-reader reading of code and one live-region policy (P1; UX-19)
Code wells are read-only grids with exact cell text, verbosity settings, labels as rows, flow restated as words, in-well find, and an Accessible View (Alt+F2) plain-text mirror. One live-region catalogue: transitions only, coalesced, logs `aria-live=off`, Freeze pauses announcements.

### U190 · Perceivable states in every mode (P1; UX-20)
One focus rule (2px on bordered controls, 3px inset on rows, cells and tabs; never box-shadow); forced-colors rules rewritten (SelectedItem, CanvasText borders, LinkText, GrayText, splitters as borders); selected-row promotion extended (a lighter failed tone keeps glyph hue on selection); splitter grip ≥3:1 at rest; accent reserved for focus, the active tab and links; Increase contrast and Reduce motion toggles.

### U191 · Narrow-viewport continuity (P1; UX-21)
The rail bar is a tablist with per-pane scroll and focus memory; Enter or tap (never focus) advances from Navigate to Analyze with a history stop; Inspect opens as a half-height bottom sheet; counterparts collapse into the breadcrumb Build menu and SplitCompare into a segmented toggle; the dock collapses to one status line defaulting to "Selection only"; acceptance at 598×912 and 320×256.

## Accessibility baseline already applied to the design system

Selection shown by fill plus a 3px bar; muted text and state words promoted on the fill; accent removed from statuses; links underlined; 24px targets; real tabs, grids, combobox, alert dialog and separator semantics in previews; spoken words for glyph-only cells; progress roles; diff words; prefers-contrast and forced-colors support; color-scheme; tabular numerals; log tails keep the newest text; guideline sections Linked views and Accessibility. See the design system for the rules.

## Diagram changes already applied

`docs/dashboard-design/pipeline-diagram/pipeline-model.json` now holds every diagram's content with stable node ids and typed edges (drawn edges separate from inferred ones, each inferred edge with its basis). All four SVGs render from it with `role="img"`, title, description and language, one `<g id>` per node in reading order, family words, full legends and no overlapping text (a measured collision check refuses to write otherwise). Generated text outlines anchored by node id are the primary accessible form, and the node ids are the deep-link vocabulary for the PipelineMap, PipelineBreadcrumb, go-to (`~node`) and Explain. See that directory's README for hashes and the supersession note.

## Conflicts and supersessions

| Earlier | Now |
|---|---|
| "Enter opens the action strip with the last action" (feel.md Essay AC) | Enter always means Go; `.` repeats the armed action (U184). |
| Toolbar search filters functions only; Ctrl+P "search functions" | Ctrl/Cmd+P is go to anything; the Functions filter stays a plain grid typeahead (U178). |
| Checks persist "until Esc" (decisions.md, Phase C) | Esc never clears the checked set; use the count chip × or Clear checked (U174, U188). |
| Analysis tablist with a "More…" select | Views toolbar; Xrefs and Matching move to the rail and Compare (U173, U177). |
| Single-letter global shortcuts (S, O, N, G) | Modifier globals; single letters focus-scoped and remappable (U188). |
| `pin=` in links | `keep=` for Kept cards and `hold=` for held panes; "pinned" is reserved for the locator status (U172). |
| Back button history menu | The Recent menu (right-click on Back); Back and Forward never change holds (U172). |
| "Link panes" toggle | "Update panes: As I move / On Enter" (U176). |
| "One page, minimal tabs" vs dense tabs | Co-visible views plus rail sections; tabs remain only for workspaces, sessions and the dock (U173, U176). |

## Open questions

- Whether the static 8080 surface intercepts same-origin anchors inside server-rendered fragments for all corpus windows at once, or window by window.
- Which catalog verbs map to which stage and lane (`catalog_verbs`); unmapped verbs show "stage: unmapped" until decided.
- Whether "Increase contrast" persists per viewer only, or also per project.
- 22 inferred diagram edges marked "interpretation" need review (listed in the pipeline-diagram README).
