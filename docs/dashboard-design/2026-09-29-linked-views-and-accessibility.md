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

The units answer each habit: information comes to the selection (Peek, rail sections, XrefPanel, CounterpartStrip, outcomes on the row); comparison opens beside instead of replacing (SplitCompare, Hold); the location lives in the URL and history (location schema, NavigationBar); and result sets can be collected into worklists stepped with one key (F8).

## Per-journey ledger

Before = documented or implied view switches. After = switches with the units in place (keystrokes inside one view are not counted as switches; region focus moves and history steps are named in the Main units cell but not counted). Estimates, not observations.

Each journey is credited once, to the unit named first in its Main units cell. A unit that only helps names the journey in its own text without claiming the reduction again. This ledger is authoritative: component README estimates that differ are to be aligned to it.

| Journey | Task | Before | After | Main units |
|---|---|---:|---:|---|
| J01 | Inspect a function in build A, then see its counterpart(s) in builds B-D (address, divergence class, identity-edge state), and return to build A | 5 | 1 | UX-05 strip and derived split (≥700px; 2 below 700px; reading by Peek alone: 0 where cached) |
| J02 | From a function's proof state (seven facts), open the receipt behind a fact and the job that produced it | 5 | 1 | UX-10 fact → receipt → job links, read by Peek at 0; the 1 is the dock-tab change to open the job (+1 below 700px) |
| J03 | Find which pipeline stage / concurrent lane produced a given receipt or job | 4 | 0 | UX-10 StageChip on the row where plan §2.1 maps the verb; otherwise "stage: unmapped" |
| J04 | Understand why a stage/entity/objective is blocked and what continues | 5 | 1 | UX-12 FailureRecord expands in place |
| J05 | Go from a diagram concept (stage gate, lock, lane, ladder step) to the live entities/jobs currently at it | 5 | 1 | UX-08 go to anything (`~gate-4`) |
| J06 | From a readiness x coverage matrix cell (entity x build) open the resolution-ladder evidence and any contested pair | 4 | 1 | UX-13 (Peek reads the ladder at 0; Enter selects in place) |
| J07 | Review a candidate match and check the bytes/blocks of both endpoints before deciding | 8 | 0 | UX-16 master-detail and held pair; +1 modal confirm per decision, +1 per session for the Review preset |
| J08 | Recover from a refused (stale/missing basis) review decision | 4 | 1 | UX-16 batch refusal recovery (the new confirm; only changed rows re-read) |
| J09 | Follow a cross-reference from code and return to where you were | 4 | 0 | UX-07 in place: 1 region move and 1 Alt+← back, not view switches; 0 per further reference; below 700px 2 per reference by tab, 0 with `]`/`[` |
| J10 | Relate an instruction row to its decompiled statement and vice versa | 6 | 0 | UX-03 reflected cursor (≥700px; 2 below 700px) |
| J11 | Rename or retype a local variable seen in the decompiler | 6 | 0 | UX-15 edit in place (F2, type, Enter) |
| J12 | Edit a function signature / calling convention / custom storage and verify that dependent views updated | 5 | 1 | UX-15 edit in place; +1 per caller verified (Enter decompiles it) |
| J13 | From a decompiler variable/field inspect its structure type, offsets and uses, then apply/refine the type | 5 | 2 | UX-15 Peek type and Retype in place; changing the structure still opens the type view |
| J14 | Investigate a vtable: slots, targets, callers, class layout, and the same slots on other builds | 6 | 2 | UX-07 Slots tab (rows from the UX-13 slots mode, aligned by ladder E); the 2 open a slot's counterpart beside |
| J15 | Diagnose a decompile artifact (extraout/unaff/wrong return) before changing a prototype | 6 | 4 | UX-03 callers and bytes co-visible; data flow and the prototype edit stay their own verbs |
| J16 | Explore the call graph and read code of nodes along the way | 3 | 0 | UX-03 following graph beside code (when Graph and Decompile are the two panes; 2 per node below 700px) |
| J17 | Walk every member of a logical identity across builds | 6 | 1 | UX-09 worklist: collect the members once, then F8 (0 per member after the first) |
| J18 | Find out why a function has its name: winning tier, donor build, rejected alternatives, conflicts | 4 | 0 | UX-06 "Why this name" rail section |
| J19 | From a job in the dock, see which entities/builds it changed | 4 | 1 | UX-10 ActivityRecord Changed line → filtered Functions |
| J20 | From an actual-work event (propagation, repair, verify), inspect the underlying diff/evidence and step through history | 4 | 1 | UX-10 work-view event opens its evidence beside |
| J21 | Inner loop: run a catalog verb on the selected function and read its outcome | 5 | 2 | UX-14 `.` then Run; outcome read on the row (+ConfirmDialog only for batch, destructive or cross-build verbs) |
| J22 | Run one verb on a checked set and verify each function's result | 7 | 2 | UX-14 outcome cell per row, independent of batch size when the job reports per-target units |
| J23 | Consult a corpus panel (Cross-match, Recovery, STABS, Knowledge, Review) for the current function and come back | 3 | 0 | UX-06 rail sections (via Show all: 2) |
| J24 | Use Atlas similarity map / report / explorer page and return to the same function | 3 | 2 | UX-02 `panel=` views; 0 re-selection |
| J25 | Follow a link between the static workbench and the React app without losing the destination | 3 | 1 | UX-02 shared schema (U172); +1 confirm when the link names another project |
| J26 | Switch the inspected build while keeping the same logical entity | 3 | 1 | UX-05 position-keeping build switch (anchor partner where anchors exist; otherwise the function start, stated) |
| J27 | Open a Ghidra program whose corpus inventory/binding is missing and get to its functions | 4 | 2 | UX-12 empty state under the UX-01 dead-end rule (notice → armed strip → confirm) |
| J28 | Detect and act on starvation: oldest unreviewed row, oldest waiting lane, job past deadline | 4 | 1 | UX-11 PipelineMap Peek: the oldest wait is a link |
| J29 | Pause/resume admission and understand exactly what it drains and which lanes it does not own | 4 | 1 | UX-11 "What this pauses" beside Pause (one activation, no view switch) |
| J30 | Import binaries, watch the admitted work, then start working on the new build | 4 | 1 | UX-10 walkable provenance (+1 below 700px) |
| J31 | After a project merge, inspect a conflicting name/type in its build | 4 | 1 | UX-01 typed links (2 when the item is only in the other project and a switch is chosen) |
| J32 | Check where context pieces were placed and resolve proposed-label conflicts | 3 | 1 | UX-01 typed links (≥1100px; 2 below 700px) |
| J33 | See why an entity is not runtime-usable (e.g. not_detourable) on a build and whether other builds are | 4 | 1 | UX-13 (Peek reads the refusal at 0; +1 region jump to read the card with a screen reader) |
| J34 | From a whole-image delta, get to the offending function/data region and its object diff | 4 | 1 | UX-01 typed links |
| J35 | Understand a stale fact: what dependency changed and when revalidation runs | 3 | 0 | UX-04 stale Peek (1 when the dependency change is not recorded or not cached) |
| J36 | From strings/imports/exports/sections/bookmarks get to use sites and bytes | 3 | 1 | UX-01 typed links |
| J37 | Do any cross-view journey on a narrow viewport (<700px, 598x912) | 6 | 2 | UX-21 NarrowFlow (1 if the counterpart is only peeked; 3 if a job record must be opened; +1 below 480px tall) |
| J38 | Keyboard / screen-reader user: go from a job-transition announcement to the result and back to the entity | 4 | 2 | UX-18 "Go to last announcement" (`g j`) to the job row; Go 1; Back 1 |
| J39 | Iterate on candidate source repair: diagnostic -> changed line -> compile -> objdiff | 4 | 1 | UX-01 typed links |
| **Total** | 39 journeys | **174** | **41** | about 76% fewer switches (estimates) |

The largest single gains are the inner code loop (J09 + J10: 10 view switches per function down to 0 at ≥700px, leaving one region move and one Back; about 4 below 700px), match review (J07: 8 → 0 per decision, plus one modal confirm), local edits (J11: 6 → 0) and batch verification (J22: 7 → 2, independent of batch size when the job reports per-target units).

### Compiler-aware, outputs and parity journeys (2026-09-29)

Same columns and counting rules as the table above: view switches only, keystrokes inside one view not counted, region focus moves (the `g` leader, F6) and history steps named but not counted, modal confirms named but not counted. Before = documented or implied view switches today, in Ghidra (one program per window, per the parity specification's click paths) plus the current dashboard and docs. After = with the U192–U198 components and the reserved U199–U218 parity block, as their READMEs design them. "Four builds" means build-a … build-d. Estimates, not observations; nothing was run. Each journey is credited once, to the unit named first; U199–U218 credits are provisional until that block is integrated, and a layout preset claims no journey (LayoutPresets).

| Journey | Task | Before | After | Main units |
|---|---|---:|---:|---|
| J40 | Walk a pointer chain through three structs (`this->cache->entries[i].name_len`) and compare each hop's offset on two builds | 8 | 0 | U195 PointerWalk: `p` opens the walk as a rail section; per-build offset cells, the layout strip and the step Peek read all three structs at 0 (Before: a type view per struct per build, one program switch, the return; +4 per further build). Enter on a step's type is 1. The Walk pointers preset (`g then 7`) adds one pick per session |
| J41 | Find why a function differs between two builds: compiler (flags, toolchain, link) or source | 6 | 1 | U194 VariantRelation: the pair drill row names the class, its level word, the deciding evidence and each tool's opinion (Before: program switch, each build's header and PDB info, the diff report, the source record in the docs, the return). 0 when CompilerLayer's cross-build note already classes the range (U196, not credited again). The Explain build difference preset (`g then 6`) adds one pick per session |
| J42 | Explain a non-matching rebuild: which differences are register choice, order, stack slots, inlining, flags or source, and what to try next | 5 | 1 | U197 MatchExplain beside ObjectDiff: class table with counts and a next step; FrameLayout arrives as a kept card at 0; the 1 is the Go to ToolchainEvidence when the class is a toolchain or flags mismatch (0 otherwise). Before: the diff read row by row, the stack editor, the recipe in the docs, the receipt, the return |
| J43 | Check which compiler, linker and flags built each of four builds, and whether the rebuild toolchain can byte-match each | 8 | 1 | U193 ToolchainEvidence: one facts × builds grid with level words and the pinned-toolchain row (Before: per build, a program switch and its header, PDB or detector output) |
| J44 | Find one vtable slot's target on every build | 7 | 0 | U198 VTableBrowser: `g then v` is a region move; each cell names the slot's target per build by logical method, with its edge word. Opening one target is Enter, 1 (J14, credited to U177, covers opening a counterpart beside). Before: the vftable on build-a, then a program switch and a vftable lookup on each of three builds |
| J45 | Compare one function's stack frame across four builds | 8 | 0 | U198 FrameLayout: `g then f` is a region move; logical-slot rows with one offset column per build, ESP frames normalised and flagged. Before: the stack editor on build-a, a program switch and stack editor on each of three builds, the return |
| J46 | Find every output or export of the project and whether each is current on each build | 5 | 1 | U192 OutputsCatalog: `panel=outputs` shows status per build (▣ ◐ ◷ ▷ ○ ∅ □) with the 8080 axis apart; Peek reads the ArtifactCard at 0. Before: the dock's jobs, the receipt list, the pipeline diagram, the inventory and DELIVERY_STATUS docs |
| J47 | Edit a struct field on one build and propose it to its counterparts on two other builds | 9 | 1 | U199–U218 TypeEditor: opened from the field token (1); the layout check per build and the Propose group are in the same editor; +1 modal confirm for the proposal and +1 when the edit resizes. Before: the type manager and structure editor on the donor, then a program switch, type manager and editor per recipient, the return |
| J48 | Change a function's prototype on one build, see which callers it affects, and propose it to a counterpart | 6 | 1 | U199–U218 SignatureEditor: opens inline under the signature line (0); callers carry "◷ predates job" in References (0); Propose with its ABI gate is in the same editor; the 1 is the Go to the recipient's counterpart to read its outcome; ConfirmDialog for the prototype change and for the proposal; +1 per caller decompiled, as in J12 (credited to U185). Before: the signature dialog, the call tree, a program switch and the dialog on the counterpart, back to the callers, the return |
| J49 | Search bytes or an instruction pattern across four builds | 8 | 1 | U199–U218 SearchWorkbench: "All builds" scope, the per-build "What will be searched" lines, and a ResultsTable with per-build hit columns in one secondary area (1); +1 per hit visited. Before: the search window on build-a, then a program switch and the search window on each of three builds, the return |
| J50 | Compare the memory map (blocks, ranges, permissions) across four builds | 7 | 1 | U199–U218 MemoryMapTable: the Sections scope's Show all (1), then `a` Align builds (0) with the variance-class column. Before: the memory map window on build-a, then a program switch and the window on each of three builds |
| J51 | Undo a propagated edit on the donor and on each recipient, and see which receipts it makes stale | 5 | 1 | U199–U218 EditHistory: `panel=history` (1); the propagated row names donor and recipients, and the Program segment switches lists in place (0); +1 modal confirm per build undone. Before: the propagation job in the dock, its receipt, then each program's undo list (donor and two recipients) |
| J52 | Run one analyzer (one-shot) on a selection on one build and read the result | 4 | 1 | U199–U218 AnalyzerPanel: `panel=analysis` (1); the ActionStrip's one-shot Run, the build's analysis-state card and the log tail are in the panel. Before: a program switch, the analysis dialog or One Shot menu, the log or console, the return |
| J53 | Export C for one function on one build and find the output with its basis | 4 | 2 | U199–U218 ExportDialog (1, a modal): one job per build; the artifact link lands on the invoking row; opening its ArtifactCard is 1. Before: the decompiler's Export to C dialog, the file chooser, the file manager, the dock to find the job |
| J54 | Navigate the symbol tree to one namespace and see it on each of four builds | 7 | 1 | U199–U218 SymbolTree: the navigator's Symbols scope (1) in Logical · all builds, with one presence column per build and "namespace differs" in words. Before: the symbol tree on build-a, then a program switch and a tree search on each of three builds |
| J55 | See what the compiler did to one function on each build (inlining, a magic divide, /GS or EH scaffolding) and in what order | 5 | 0 | U196 CompilerLayer: `c` toggles the layer in the visible code wells (not a view switch); each band carries its presence line per build; TransformTimeline is `g then t`, a region move. Before: a program switch per other build to compare listings by eye, the research notes, the return |
| **Total** | 16 journeys | **102** | **13** | about 87% fewer switches (estimates, truncated); the original 39-journey total above is unchanged |

The largest gains here are the per-build reads that today cost a program switch per build: toolchain (J43: 8 → 1), stack frames (J45: 8 → 0), pointer chains (J40: 8 → 0), byte search (J49: 8 → 1) and field propagation (J47: 9 → 1, plus its confirms). These tables are not summed: the second table's journeys overlap in part with J12, J13 and J14, which keep their own credits.

## Units

Each unit lists what changes, why it removes switching, its accessibility contract and its doctrine safeguards. P0 units are the foundation the others assume. "Already in the design system" means specified in the design-system docs, not implemented. Each unit claims only the journeys the ledger credits to it and names the ones it supports.

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
- A link naming another project lands on a StateNotice with "Switch to ‹project›" armed and confirm-gated beside "Stay", because opening admits work (U105).
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

### U173 · Code Browser composite, finished (P0; UX-03)
Already in the design system: the Views toolbar (`views=`), DecompileView and HexStrip with the reflection mark, and `r`, `h`, `x`, `]`, `[`. Still missing: "analysis tabs" left in 90, NavigationBar and the Workstation preview; a GraphPane README; Listing's reflection and Linking; a reflection section in 35.
- **Views toolbar**: at most two center panes plus the HexStrip. A third view replaces a named one (Graph ↔ Decompile), said before and announced after; the last visible view is aria-disabled with its reason. Side by side when the Code Browser is at least 2 × `split-min-w` wide, stacked below; under 700px the NarrowFlow "Code views" tablist keeps the cursor. Turning a view on never analyzes.
- **Reflection** (35): one cursor; every visible view marks the mapped set with the existing mark (raised fill, 3px ink-muted bar, "↔ line 7", ▸). A missing mapping is a sentence, never inferred. Pointer brushing is an optional dotted outline that moves nothing. `r` moves focus to the reflected row by a fixed target table.
- **Highlight all** (`h`): up to four, lettered A–D, a box, never an underline; "text match" unless keyed by variable identity; other builds only through recorded anchors.
- **One composite header** replaces per-well headers and joins `sticky-offset`.
- **Graph** follows by marking the current node and re-roots only on an explicit Re-root; there is no held graph.
- **Proof wells**: diagnostic → SourceRepairDiff line → rebuilt rows (line table) → target rows (ObjectDiff receipt, "aligned ≠ equivalent"); a mapping from an older compile is marked stale.

*Removes:* J10 6 → 0 at ≥700px (2 below); J16 3 → 0 per node when Graph and Decompile are the two panes; J15 6 → 4. J34, J36 and J39 are credited to U171.
*Components:* CodeBrowser, DecompileView, HexStrip, Listing, GraphPane (new README), Workstation.
*Accessibility:* the Views bar is an APG Toolbar and Workspaces a separate tablist; wells are h3 regions reached by Tab and the `g` leader (F6 stays region cycling); cursor, reflection, brushing and highlight differ in shape, also in forced colors.
*Safeguards:* read-only; mappings only from the decompile projection, line tables and receipts, each labelled. The React CodeBrowser was reported unmounted (N2, 2026-09-21); not verified from docs.
*Acceptance (future):* no "analysis tab" wording and one selected tab per tablist; GraphPane and Listing carry Linking blocks; at 320×256 one well shows with its cursor line.

### U174 · Peek everywhere (P0; UX-04)
Already in the design system: the Peek README (forms, Alt+↓, rest delays, cached, not-loaded and stale states), NarrowFlow's sheet, and "no tooltip" in the fact, capability, locator and name components. Still missing:
- **A content table by target type**, cache-only: code (6 lines in the card, 12 inline); XREF[n] (first 20, then "n more · Open"); fact (word, stamp, receipt, job, StageChip); ◷ stale (old → new basis, the dependency that changed, the revalidation job or "Revalidation: none recorded"); ◇ gate wait with age; ladder run with observed_status on its own line; counterpart (edge word, divergence, lines around an evidenced anchor only, "aligned ≠ equivalent"); job ("as of 14:02", no poll); name, type, slot and capability refusal.
- **Footer**: Open · Open beside (a Held pane) · Keep (button, or Shift+K inside the Peek; `keep=`) · Copy link. A nested peek replaces the content with "‹ back".
- **One focus-relative Esc order** in keymap.json, 85 and 90: peek, sheet, menu or hint → edit mode → the topmost modal → an armed ActionStrip holding focus (fields kept) → a transient extent → a transient filter → from a secondary or held pane to the primary. Esc never clears the checked set, holds, kept cards or drafts. The count chip's × leaves "Checked set cleared (4) · Undo" beside the chip until the next check change.
- **Triggers**: hover only on link tokens and whole-strip buttons, switchable off; focus rest off at 400% zoom and below 700px; Peek in the 44px row menu for coarse pointers; NarrowFlow's sheet (at most 64% of the pane), and the inline form below 480px viewport height.

*Removes:* J35 3 → 0 (the stale Peek). It supplies the reads for J01, J02, J06, J09, J13, J18 and J33, credited to their owners.
*Components:* Peek, NarrowFlow, EntityRow (tooltip → Peek), CounterpartMatrix, HeldPane, EvidenceRail, DecompileView.
*Accessibility:* 1.4.13 (4px gap bridged, 300ms grace, no timeout); a non-modal dialog; aria-expanded only while open; aria-keyshortcuts once per well; never covers the trigger (2.4.11).
*Safeguards:* cache-only ("Not loaded. Open to read it." is an answer, not a fetch); no prefetch; dated snapshots; only Open changes the selection.
*Acceptance (future):* a Peek row for every link target; the same seven Esc steps in keymap.json, 85 and 90; no "K keeps" or `hold=card:` left.

### U175 · Counterparts in place (P0; UX-05)
Already in the design system: CounterpartStrip, SplitCompare, Ctrl/Cmd+\ (split), Alt+PageDown/PageUp and F7. Still missing:
- **One CounterpartStrip per composite** above the Code Browser, plus a compact form in the rail header, never one per well. Enter goes, Shift+Enter opens a Held pane, Alt+↓ peeks. Below 700px it folds into the breadcrumb Build menu ("4 builds: 2 resolved, 1 pinned, 1 absent").
- **Position-keeping build switch**, one rule for the strip, build menu, go-to and Alt+PageDown. Keep the entity; map the cursor only through recorded anchor pairs (between anchors, the nearest preceding anchor's partner, said in words); never interpolate. No anchors: "No instruction mapping for build-c; showing function start". No counterpart: stay, with "Open build-d" carrying no address. Ambiguous and contested open the candidate menu; candidate edges go and say "candidate". Clearing the checked set is stated before and confirmed after, with no dialog.
- **Split inside the Code Browser.** Ctrl/Cmd+\ opens a derived pane (the primary plus a build); Shift+Enter a Held pane; Follow again turns held into derived. Enter in a derived pane is Go; held panes follow HeldPane. A shared PaneHeader carries state words, build menu, Hold this pane, "Scroll lock · on anchors", Swap and Close. A contested locator is one contested pane; two held panes only in Compare. SplitCompare publishes `cmp`, `views` and `hold`, not `sp`, `v` or `ws=compare`.
- **Differences**: F7 with SplitCompare's words (`±` differs, "▸ 9 unchanged lines", "local zero ≠ full-image or behavior proof").

*Removes:* J01 5 → 1 at ≥700px (2 below); J26 3 → 1. The strip is also the member list that U179 collects for J17.
*Components:* CounterpartStrip, SplitCompare, PaneHeader (new, shared with U176), EvidenceRail, NavigationBar, NarrowFlow.
*Accessibility:* the strip is an APG Toolbar with sentence names; arrowing never switches; one polite message per switch naming its basis; below 700px an APG tablist "build-a · follows | build-c · derived".
*Safeguards:* counterparts only from recorded edges; no invented positions; the ActionStrip binds the primary. Whether both surfaces can read the anchor pairs today is not verified from docs.
*Acceptance (future):* no `sp`, `v` or Code Browser `ws=compare` left; switching ResourceRef::Resolve from build-a to build-c lands on the anchor partner and says so.

### U176 · Follow, Hold and Kept, finished (P1; UX-06)
Already in the design system: following after `settle-delay`, Update panes, Hold this pane, `hold` and `keep`, and HeldPane. Still missing:
- **Drift** (fixed during integration, 2026-09-29): "Link panes" in CodeBrowser and NavigationBar; "Current differs" instead of "◷ Basis changed since held · Refresh"; the Held icon in the stale color; "held at a stage gate" in 20 (now "waiting").
- **Follow boundaries**: following never crosses a project, opens a program or decompiles on a miss; aria-busy only on panes without focus; each following pane states its mode. A commit-on-Enter pane says "Shows ResourceRef::Resolve; selection is now Actor::LoadFromTemplate · Enter to load".
- **The armed ActionStrip never retargets**: "Bound to ResourceRef::Resolve · selection is now Actor::LoadFromTemplate · Rebind".
- **Hold** only on center and secondary panes, through PaneHeader. The HELD tag stays visible while scrolling, because the 2px ink-strong frame also marks fresh evidence. A third center Hold becomes a Kept card and says so.
- **Kept cards** (`keep=`): at most three; a fourth is refused ("Three cards kept; release one"), never evicted. Enter in a kept card goes; in a held pane it moves that pane; each footer says which.
- **Selection-scoped rail sections** (disclosures, per-viewer collapsed state): Kept, Pipeline, Why this name, Facts, References, Counterparts, Cross-match summary, Recovery, Timeline. Corpus sections read "For ResourceRef::Resolve · build-b" with Show all (`panel=`). The list lives in 30 and Workstation; EvidenceRail is the ladder component. The Knowledge entry keeps its own claim tier, outside name precedence.

*Removes:* J18 4 → 0; J23 3 → 0 (2 via Show all). J16 uses the following graph (U173) and J14 a Kept Slots card (U177), credited there.
*Components:* PaneHeader (new), HeldPane, CodeBrowser, NavigationBar, NameProvenance, ActionStrip, Workstation, keymap.json (pane commands).
*Accessibility:* arrows never change context; at most one polite message per settle, after load, only facts not in the row name, switchable off; 2.2.2 is met by Freeze, not by Hold.
*Safeguards:* one selection owner; held and kept never refresh silently; no new store.
*Acceptance (future):* no "Link panes", "Current differs" or "held at a stage gate" left; one rail section list; pane commands in keymap.json.

### U177 · References in place (P1; UX-07)
Already in the design system: XrefPanel's grid; `x`, `]`/`[` and `g o`; References out of the center in 30. Still missing:
- **One placement** (the CodeBrowser rule): References (with Calls and Slots) and Outline in the evidence rail when it is open; otherwise beside the code at ≥880px Code Browser width, else under it; below 700px a "References" tab. No dock placement.
- **XREF[n]** is a typed link (an "xref hint" row in 35): Enter focuses References at that build and address without moving the primary location; Alt+↓ peeks.
- **Snapshot stepping**: `]`/`[` or Previous/Next buttons step the code cursor while focus stays. The first step snapshots the list ("Kept · stepping references to ResourceRef::Resolve · 3 of 12 · as listed 14:02", `keep=`) and pushes one stop; later steps replace it, so one Alt+← returns to the origin. Steps stop at the ends and never change build or touch the worklist.
- **Modes** (manual-activation tabs, `f=xref.mode:`): Calls is a treegrid over the existing call-tree operations, following at depth 1 and expanding on request to 3, with "path found / no path in stored index" per build and "path in stored index ≠ runtime reachability". Slots shows U183's slot rows at rail width, aligned by stored ladder E results, never by index; off a vtable it is aria-disabled with the reason.
- **Outline** is the one CodeBrowser Outline projection; no FunctionOutline and no Ctrl/Cmd+Shift+O.
- **Scope precedence** edit > code > composite > region > global, so `x` in a code well means references; punctuation keys accept AltGr.

*Removes:* J09 4 → 0 view switches (1 region move and 1 Alt+← back; below 700px 2 per reference by tab, 0 with `]`/`[`); J14 6 → 2.
*Components:* XrefPanel, CallHierarchy (new README), CodeBrowser, Listing (Linking block), KeymapSettings.
*Accessibility:* Calls has treegrid attributes and aria-busy; each step is announced once ("Reference 3 of 12"); buttons are the touch path; per-build columns collapse to "on 3 of 5 builds" at 320×256.
*Safeguards:* stored indexes and ladder E results only ("not indexed here"); cross-build rows through recorded edges; stepping state is Kept and never refreshed silently.
*Acceptance (future):* 35 has the xref-hint row; XrefPanel and CodeBrowser state one narrow placement; after three `]` steps one Alt+← returns to the origin.

### U178 · Go to anything (P1; UX-08)
Already in the design system: NavigationBar go-to with prefixes, and a separate CommandPalette. This unit makes them one engine.
- **Three keys.** Ctrl/Cmd+P focuses the NavigationBar go-to combobox; Ctrl/Cmd+G focuses it with `:` typed and the last address jump as the highlighted first row; Ctrl/Cmd+K opens the modal palette with `>`. Below 1100px, P and G open the same engine in the palette. The Functions filter stays a filter.
- **Prefixes**, first character only: `@` symbol, `:` address, `#` logical id, `!` job, `%` receipt or basis, `~` node, `>` command, `$` string, `'` marks and worklists. `?` is not a prefix, because decorated names start with it; help is Ctrl/Cmd+/, the Help menu and a "help" option row. Program bookmarks are their own group. `::` starts a symbol. The detected scope is a removable chip; prefix chips are the touch and dead-key path. Typing never opens a dialog.
- **Rows** name type, target build, per-build locator words, destination, an action's binding and a job's StageChip. A row that switches builds says so first ("clears 4 checked rows on build-a"). Unavailable actions show the one fix from the dead-end rule.
- **Honest search** over stored indexes of the active project, with coverage in words ("not searched: build-d, not loaded"). A bare address resolves in the inspected build first; the same number elsewhere is "a different place, not a counterpart". Results only in another project read "in ‹project› · not open" and land on the cross-project StateNotice.
- **Corpus surfaces** focus their rail section; Shift+Enter or Show all opens `panel=`.
- The empty query lists Recent locations, Marks, Recent actions and Recent jobs. The field is `goto`, not `q`. In grids with letter commands, typeahead starts with `/`.

*Removes:* J05 5 → 1 (`~gate-4`). It also serves J03, J17, J23, J28 and J36 without credit; J18 belongs to U176.
*Components:* NavigationBar, CommandPalette, KeymapSettings, StateNotice preview (bare "G" → Ctrl/Cmd+G), ProblemsList.
*Accessibility:* an APG combobox with a grouped listbox; no change of context on input (3.2.2); scope announced once; rows wrap at 320×256.
*Safeguards:* read-only; actions only arm; never switches projects; superseded queries dropped.
*Acceptance (future):* NavigationBar, CommandPalette, 30 and keymap.json give P, G and K the same roles; no README says a typed character opens a dialog.

### U179 · Marks, program bookmarks, recent locations and worklists (P1; UX-09)
MarksList and ProblemsList exist and are amended; no new components.
- **Marks** are per-viewer annotations: `m` + letter marks the concrete build and address; "Set logical mark…" marks the entity, resolved on other builds through the locator and backend alignment. `'` + letter jumps (physical key, dead-key safe). Marks, notes (labelled "note") and worklists carry no claim tier and never feed context fusion, propagation or agent bundles.
- **Program bookmarks** (stored in the analysis program) are a separate, read-only Bookmarks navigator scope with category, comment and an address link. "Save as program bookmark" arms the catalog action for one build; the bookmark appears after a re-read.
- **Recent** gains "Changed since visited", from jobs' recorded change units after the visit; jobs that only reused evidence do not qualify.
- **Worklists** come only from Collect (`w`, toolbar, row menu): a snapshot "as of 14:02" with a source link. At ≥700px a stepper toolbar reads "position 4 of 12 · 7 visited · 3 handled"; below 700px a chip "Worklist 4 of 12" opens it as a sheet. Its height joins `sticky-offset`.
- **F8 / Shift+F8** step the active worklist only (U182), move selection and focus like Go, never wrap, wait while an editor or unsent strip fields are open, and stop once at a program boundary ("Next: build-c · clears 4 checked rows on build-b"). No Alt+F8; the stepper buttons and palette serve keyboards without function keys.
- **Words**: "visited" is automatic; "Handled" is an optional checklist toggle, "not a review decision · starts no work"; never "done" or "checked off". The item grid is not checkable. A vanished target "no longer resolves on build-b"; another viewer's `wl=` reads "Worklist not available here".

*Removes:* J17 6 → 1 (collect the members once, then F8). F8 also serves J04, J14, J22, J28, J31 and J32, credited elsewhere.
*Components:* MarksList, ProblemsList, NavigationBar, ClaimTier, Listing (gutter letter).
*Accessibility:* one message per step ("Item 4 of 12: ResourceRef::Resolve, build-b, conflict"); boundary and end stops announced once; the stepper never obscures focus (2.4.11).
*Safeguards:* marks are not evidence; a worklist is view state, never a job queue; bookmark writes go through the catalog; marks live in durable workspace state per viewer.
*Acceptance (future):* no "done" or "checked off" in MarksList; ClaimTier no longer lists marks; 30 lists Bookmarks as a navigator scope.

### U180 · Walkable provenance (P1; UX-10)
StageChip, EntityTimeline, FilterChip and ProvenanceStamp exist and are amended.
- **catalog_verbs** is one verb-keyed map in pipeline-model.json, filled only from the consolidated plan §2.1: stages 1–7, the export verbs (to export nodes) and the proposed corpus jobs (stages 2, 5 and 7). Stage 0 is open, add and resume; stage 8 has no verb; no verb maps to a lane by name. Parity writes and person-requested jobs say "requested · no stage"; an unmapped verb says "stage: unmapped". A future check compares it with a GET /api/v1/actions snapshot.
- **StageChip** reads "5 Propagation" (a lane part only when mapped) on jobs, receipts, problems and go-to rows, and links to the PipelineMap node.
- **ActivityRecord** keeps two lines apart: "Targets" (what the job was asked to act on) and "Changed" (what its receipts recorded). "Changed: 3 (recorded units) · Show in Functions" applies the FilterChip "Changed by a3f9 ×"; with no units it reads "Changed entities: not recorded", with no filter. Build links land on the Navigator program row. Log lines link only structured fields; a free-text address links only when the job names one build, labelled "from log text".
- **Filter history**: typing, editing or removing a filter replaces; applying one from a link (the Changed line, Show all) is a Go and pushes.
- **Dock "Selection only"**: one toggle for Jobs, Problems and Logs, shown as a FilterChip; logs are filtered by job record, never by log text.
- **EntityTimeline**: a human/agent filter only where the actor is recorded; moving between events writes no history.
- **Work view**: events open their evidence beside. No pane follows active work; the header chip reads "Job a3f9 is at ‹node› · Go".
- **ImportAdmission**: with the dock open at ≥700px, focus moves to the admitted batch row (a documented exception); otherwise it returns to the invoker.
- **MergeReview and ContextPlacement** get Linking blocks; other-project items land on the cross-project StateNotice.

*Removes:* J02 5 → 1 (read by Peek; 1 dock-tab change to the job); J03 4 → 0 where §2.1 maps the verb; J19, J20 and J30 4 → 1. Add 1 below 700px where the dock is involved. J22 is credited to U184.
*Components:* StageChip, ActivityRecord, FilterChip, EntityTimeline, WorkTimeline, ImportAdmission, MergeReview, ContextPlacement.
*Accessibility:* the dock history is an APG Feed; only the WorkTimeline track is a slider; filter changes are announced once.
*Safeguards:* record-named links only, no timing correlation; targets ≠ changed; reused and historical labels carried through.
*Acceptance (future):* catalog_verbs holds only §2.1 entries; FilterChip and location-schema.json agree on filter history; read-only diff, no generator run.

### U181 · Diagram ↔ live loop (P1; UX-11)
Already in the design system: pipeline-model.json, outlines, draw.io cells linking to outline anchors, PipelineMap peeks, the live StageCard, OwnershipPanel's expanded form and the "Design target:" prefix. Still missing:
- **In-app node links**: the backend-served outline links each node to `?node=‹id›`; repo outlines write it as code text. No host, port or project is emitted; a node link resolves against the active project and never opens one. A draw.io cell keeps its single outline link.
- **PipelineMap**: producers and consumers as a description and a static "Connects:" line, never live; a 44px row menu for coarse pointers; Enter on a lock pushes one stop to `dock=jobs&f=resource:‹key›` with OwnershipPanel expanded and the primary unchanged; external owners read "external · no job".
- **What this pauses**: a disclosure beside Pause, outside the toolbar's roving set, holds a sentence composed from the backend's reported scope ("Pausing stops new write admission (gate 0) for corpus-alpha; work already admitted drains; lanes C and E are separately owned and keep running."), or "Scope not reported".
- **Explain** on failures, gate waits, ladder rows and the live StageCard renders the node's text from the served model, headed "From the pipeline design · model rev ‹hash›" and "Design description ≠ this item's evidence".
- **Companion edges**: only edges marked stated are drawn; interpretation edges wait for review. TaskLifecycle and FailureRecord crosswalks are recorded as interpretations and shown only inside Explain.
- **60-diagrams**: the prefixes carry meaning and italic is decoration. Per-region overview views are an optional P2.

*Removes:* J28 4 → 1 (the oldest wait is a link in the PipelineMap Peek); J29 4 → 1 (the disclosure beside the control; no view switch). J03, J04, J05 and J33 are credited to U180, U182, U178 and U183.
*Components:* PipelineMap, WorkflowControl, StageCard, FailureRecord, TaskLifecycle, EvidenceRail, the pipeline-diagram generators.
*Accessibility:* disclosures never move focus and reflow at 320×256; family, gate, lock and edge words are always written; counts are never live.
*Safeguards:* nodes are links, never Run buttons; counts per fact axis; scope from the backend; design text is never evidence.
*Acceptance (future):* no host, port or project in outlines; only stated edges drawn; Explain names the model revision. No generator run is claimed under the current mission.

### U182 · Diagnosis in place (P1; UX-12)
ProblemsList already exists as a treegrid grouped by objective; this unit amends it with FailureRecord, ObjectiveSummary, StarvationMeter and StateNotice.
- **FailureRecord in one order**: reason; lifecycle rail; classification; scope; evidence; owner and resource; freshness; attempts and budget; recovery action (fallback, retry owner, persistent budget); wake condition; what continues; escalation only when unavoidable; Explain. A `<dl>` with typed links and disclosures; expand state in durable workspace state. The evidence excerpt is read on expand only, never on focus, hover or prefetch. "What continues" links to the dock jobs filter, and to Functions only when the backend names function targets.
- **ObjectiveSummary** keeps its five fields; the values become links.
- **ProblemsList** gains a StageChip per row, a node filter (`f=node:gate-4`) from the PipelineMap and the coarse-pointer row menu; 90 calls it a treegrid.
- **Stepping problems**: F8 steps only the active worklist. "Step problems" collects the current rows as a snapshot worklist in one activation; with none active, F8 says "No active worklist" and names both paths.
- **StarvationMeter** bars stay role=img; the age words are links.
- **Empty states** name program and cause, show reuse evidence and any pending admission first, and only then arm at most one catalog action for the primary selection: never run, never while discovery is not loaded, never an analysis action while reuse evidence exists, no fixed action ids.
- **Dock**: Freeze per region ("Frozen at 14:02 · 7 events since"); `g p` opens Problems.

*Removes:* J04 5 → 1; J27 4 → 2 (notice → armed strip → confirm; the fix stays explicit). J35, J38 and J39 are credited to U174, U188 and U171.
*Components:* FailureRecord, ObjectiveSummary, ProblemsList, StarvationMeter, StateNotice, MarksList, Workstation, 50.
*Accessibility:* disclosures never move focus; headings relative to the host; one polite message per F8 landing; stepper buttons and 44px targets below 700px; empty states name cause and fix (3.3.1, 3.3.3).
*Safeguards:* failures drawn at their real dependency; no Run, Start or per-stage buttons; duplicate admission refused; no kill or restart for external owners; 8080 renders `<details>` in the same order.
*Acceptance (future):* one field order in FailureRecord, 50 and the preview; no action id in any empty state.

### U183 · Matrices as keyboard grids (P1; UX-13)
Already in the design system: ReadinessMatrix (cell grammar, keys, filters, `w`, slots mode, legend), EntityBuildCard, and the LocatorGlyph and EvidenceRail rules. The remaining defects are in those files.
- **ReadinessMatrix** is an APG Grid with cell focus (arrows, Home/End, Ctrl+Home/End, PageUp/PageDown). Arrows move focus only; the matrix commits on Enter, a documented exception to Following.
- **One cell grammar**: Alt+↓ peeks the stored ladder run. Enter on a resolved, pinned, degraded or unresolved cell selects entity + build in place (one stop, one message) and focus stays on the cell, whose description says the build will change. Shift+Enter opens the counterpart beside. Ambiguous and contested cells are menu buttons ("2 candidates, no winner") listing each candidate, "Compare candidates" (Compare with two holds, "candidate 1 of 2 · contested · no winner") and "Open ladder run". An unopened build says "Not loaded. Open build-c to read it."
- **EntityBuildCard** follows in the rail. Its back-link reads "from ReadinessMatrix · ResourceRef::Resolve · build-c" through the history row key (no row index, no `focus=cell:`); Shift+K or Keep keeps it; "What you can do" comes from the shared readiness projection; at most one catalog action is armed, with the lane C lock owner shown.
- **CounterpartMatrix** (rows = builds) is a row-focus grid; Enter switches build and keeps the entity.
- **Build headers** link to `panel=builds&build=build-c` (see Open questions).
- **Slots**: the ReadinessMatrix slots mode owns the slot × build rows; U177 shows them at rail width.
- **Narrow**: under a 480px container, one entity's builds as a list; 44px cells below 700px; the primary cell carries the selection shape.

*Removes:* J06 4 → 1 (Peek reads the ladder at 0); J33 4 → 1 for sighted users, plus 1 region jump (F6 or `g e`) with a screen reader. J01 and J26 are credited to U175, J14 to U177.
*Components:* ReadinessMatrix, EntityBuildCard, CounterpartMatrix, HeldPane, LocatorGlyph, EvidenceRail, XrefPanel, 90.
*Accessibility:* row and column headers; names in words; 90 separates row-selection grids from cell-focus matrices.
*Safeguards:* locator, observed and edge state never merged; Enter never picks a candidate; entity-scoped verbs disabled on a contested binding; no score; the same grid on 8080.
*Acceptance (future):* no "opens two held panes" or `focus=cell:` left; matrix rows equal the readiness JSON for corpus-alpha.

### U184 · Outcomes on the row; Enter always means Go (P0; UX-14)
Enter = Go and the prefill order are already recorded; this unit corrects the OutcomeCell and ActionStrip drafts.
- **OutcomeCell** shows the latest job whose own record names the row's target, and who submitted it ("a3f9 · running · unit 3 of 6 · by you"), then a terminal word from 20-state-vocabularies. Terminal facts read as of the job (receipt and time, or "reused receipt") and turn historical when the FactStrip changes. HTTP 202 reads "pending · job a3f9"; an ambiguous submit reads "checking". No record binding, no cell: client memory is never the source. In the navigator the cell wraps.
- **Batches**: one cell per row only when the record reports per-target units, else "in batch job a3f9 · per-row outcome not reported". A run-summary chip, separate from the checked-set count, reads "4 runs: 1 running · 2 finished · 1 failed"; each word filters. "Collect failed as worklist (w)" is explicit.
- **ActionStrip** stays armed after Run: "Submitted a3f9 for 0041b210 · pending". Focus-scoped `.` rebinds the armed action to the focused row and focuses Run; it never posts. Run posts once and is aria-disabled while the same verb and target is in flight ("Already submitted a3f9 for this target") or checking. Target fields always bind from the selection; other fields prefill from the last run (labelled, durable workspace state), then catalog defaults; one Run plus "Reset to catalog defaults". Esc disarms only with focus in the strip.
- **Changed lines**: after the terminal result, stored or cached reads mark "changed by job a3f9"; an uncached decompile says "Not decompiled in this session · Enter to decompile".
- **Checked set** clears on a program change through Back's description and a polite confirmation; no dialog on navigation.

*Removes:* J21 5 → 2 (`.` then Run; ConfirmDialog only for batch, destructive or cross-build verbs); J22 7 → 2, independent of batch size when per-target units are reported. J12, J19, J27 and J30 are credited to U185, U180, U182 and U180.
*Components:* OutcomeCell, ActionStrip, TaskLifecycle, EntityRow, ConfirmDialog, 20, 70.
*Accessibility:* one polite message per transition, batches coalesced; frozen cells say "Frozen at ‹time›"; the job link is the named 22px-in-24px exception.
*Safeguards:* keys only arm and only Run posts; no optimistic outcomes; lifecycle never merged into facts; duplicates refused.
*Acceptance (future):* keymap list.repeat never posts; for job a3f9 both surfaces draw the same cell on the same row.

### U185 · Edit where you read (P1; UX-15)
Already in the design system: InlineRename and DecompileView's token menu for locals. This unit extends them; there is no separate TokenContextMenu.
- **An Edit group in the one link menu** (Shift+F10, context-menu key, right-click, or the row menu with a coarse pointer): flat, with items from GET /api/v1/actions, and missing ones aria-disabled with the reason. Local: Rename…, Retype…, Comment…. Parameter: also Edit signature…, Edit storage…. Field: Peek type, Retype field…. Callee: Edit callee signature…. Listing label or data: Rename label…, Set data type…, Comment…. Any token: Peek type, Highlight uses, Find references, Trace data flow… (arms only), Copy. Mutating labels name their binding ("Rename parameter param_1 in ResourceRef::Resolve · build-b").
- **Keys**: F2 on a local, parameter or label (and n, y and ; in the second keymap profile) opens InlineRename, with a new Comment mode, under the line, never over it. Enter or Save posts once; drafts persist in durable workspace state.
- **Confirm tiers**: single-target edits confirm in place. Structure-layout changes that resize, overwrite or clear components, and callee-signature edits, use ConfirmDialog naming the type or callee, the build and the known use count ("uses not indexed").
- **BeforeAfterBand** is its own component, inserted under the changed statements with neutral + − ± markers and words ("Before / after job a3f9 · read 14:03"). The after side comes only from the job record or a decompile cached after the terminal result; otherwise "Decompile predates job a3f9 · Enter to decompile". Dependents show "◷ predates job a3f9"; nothing re-decompiles automatically.
- **StorageEditor** opens inline; Save stays enabled; an unchanged draft posts nothing ("No storage change to submit"). Its reported resubmission defect is from a source read, not observed live.

*Removes:* J11 6 → 0 (F2, type, Enter); J12 5 → 1 plus one per caller verified; J13 5 → 2. J15 stays with U173.
*Components:* DecompileView, Listing, InlineRename, BeforeAfterBand, StorageEditor, Peek, 35.
*Accessibility:* labels start with the verb (2.5.3); editors never cover the edited line (2.4.11); nothing is announced on pending, and one terminal message follows ("Rename saved: param_1 is now itemCount on build-b, job a3f9."); focus returns to the token.
*Safeguards:* catalog only; observed after-state only; one build per edit; naming conventions are hints; the same menu on 8080.
*Acceptance (future):* 35's link menu has the Edit group; no TokenContextMenu or "SourceRepairDiff variant" left; an unchanged storage draft posts nothing.

### U186 · Review from the keyboard; re-read only what changed (P1; UX-16)
Already in the design system: ReviewDetail (detail in place or beside by width, j/k, o, d, per-row refusal), OutcomeCell and the Review preset. Still missing:
- **Master-detail**: the detail follows the focused row after `settle-delay` and reads cache only; Enter expands; F7 steps alignment anchors. It shows CandidateAlignment, IdentityEdge, the U17 fields in order ("unavailable" where missing) and alternatives with their margin. It is never mirrored into the rail.
- **Controls**: a visible 24px button per key. `o` re-points the Review held-pair slot, never adding holds; its header reads "candidate ≠ acceptance · aligned ≠ equivalent" with the edge state as of the hold, and "◷ Basis changed since held · Refresh" after the decision. `d` arms Decide for the checked set; ConfirmDialog names count and target.
- **Batch refusal recovery** keeps the page cursor, scroll anchor and focus on the invoker. In BasisDelta, a part of ReviewDetail, unchanged rows keep their check; changed rows are unchecked ("± changed since you looked"); new rows read "+ new since you looked"; rows that left the page sit in a dated, collapsed, non-checkable group. "Changed only" is session-local; after a reload it reads "Changes since the previous basis are not available; all rows need re-reading." "Step changed rows" makes them the worklist explicitly. Deciding again needs a new confirm.
- **Starvation**: the oldest-unreviewed age links to that row.
- MergeReview and ContextPlacement use the same master-detail; their journeys stay with U171. ReviewDetail and SplitCompare preset keys become `g` then 3 and `g` then 2.

*Removes:* J07 8 → 0 per decision, plus one modal confirm and one Review preset pick per session; J08 4 → 1, with only changed rows re-read.
*Components:* MatchReview (U17 fields with thresholds_version, OutcomeCell, keys), ReviewDetail, SplitCompare, CandidateAlignment, StarvationMeter, MergeReview, ContextPlacement.
*Accessibility:* an APG Grid; an alertdialog with focus on Cancel; a refusal is assertive while focus stays put; the change table reflows at 320×256 with del/ins and words.
*Safeguards:* review is an override, never a gate; decisions are token-bound and never resubmitted; departed rows are never decidable; the checked set and snapshots never enter the URL.
*Acceptance (future):* a refused batch of three rows keeps page, anchor and focus and unchecks only the changed rows.

### U187 · Persistent, token-driven layout (P2; UX-17)
Already in the design system: LayoutPresets (seven presets, View menu, palette, `g` then 1…7), the pane-header size menu and the rail toggles. Still missing:
- **Token-driven grid**: the Workstation grid in bundle.css hardcodes 200px and 220px (WDG-38). It reads `--navigator-w`, `--evidence-w` and `--dock-h`, written by splitter keys, drag, the size menu and presets, and stored per viewer in durable workspace state (F23) as a diff. localStorage is at most a non-authoritative try/catch cache.
- **Collapse strips**: each rail and the dock gets a 24px disclosure button with a stable name ("Navigator", "Evidence", "Activity"), aria-expanded and aria-keyshortcuts. Collapsing the region that holds focus moves focus to its strip. The strips are hidden below 700px, where NarrowFlow applies.
- **Splitters per APG**: arrows 16px, Shift+arrows 64px, Home/End to the minimum and maximum, Enter collapses and restores. Reset lives in the size menu, superseding "Home resets" in 30, 90 and LayoutPresets.
- **Session tabs** restore their own workspace, views, selection, holds, scroll and focused element from durable workspace state and history.state; data is read now and nothing re-runs. They use manual activation; a tab of another project shows the Switch/Stay StateNotice.
- The Workstation preview drops the superseded analysis tablist and names the 6px splitter's target-size exception (the size menu and strips are the equivalents).

*Removes:* no ledger credit. Collapsing or restoring a region becomes one click or chord instead of a drag; preset counts stay with LayoutPresets.
*Components:* bundle.css, Workstation, SessionTab, LayoutPresets, 30, 90.
*Accessibility:* single-pointer alternatives to dragging (2.5.7); 24px strips; session tabs never switch projects on focus (3.2.1); strips hidden at 320×256; a CanvasText border and a state word in forced colors.
*Safeguards:* view state only; sizes never in the URL; Back does not step through layouts; both surfaces read the same size state.
*Acceptance (future):* `.ad-ws-body` reads the three custom properties; 30, 90 and LayoutPresets state Home/End per APG; SessionTab uses manual activation.

### U188 · One remappable keymap, finished (P0; UX-18)
Already in the design system: keymap.json, the Keymap guideline, KeymapSettings (editor, shortcut sheet, which-key) and 90's landmarks, skip links and F6. There are no new KeymapEditor, ShortcutSheet or ChordHint components. Still missing:
- **Precedence and clicks**: code wins over composite inside code wells; `list.toggle` (Ctrl/Cmd-click) and one Shift-click meaning per 35's grid rule; the shortcut sheet is Ctrl/Cmd+/ (`?` is not bound); `link.revealIn` is labelled "Link menu".
- **Leader**: the existing letters stay, plus `g p` (Problems), `g b` (build menu) and `g g` (go to address); the second profile's go to address becomes `g` then `g`. The which-key hint has no timeout (`chord-hint-delay` 500ms).
- **Profiles**: default, the second profile and off. "Esc goes Back in a code well" is opt-in per viewer and off by default. F12 and Ctrl/Cmd+Enter are never rebound. Esc follows U174's order.
- **Reserved and platform keys**: add Ctrl+Tab and Ctrl+PageUp/PageDown; Ctrl+Shift+PageUp/PageDown are browser-taken; `platformCautions` lists F6, F7, Alt+F1 and Alt+F2 on common Linux desktops, F8 behind Fn, and Ctrl+Alt as AltGr, each with its menu or palette path.
- **Dock**: Ctrl/Cmd+J only shows or hides the dock; "Go to last announcement" (`g j`, palette) focuses the last announced job row.
- **Focus rules** in 90 for user-initiated transitions. The one exception: when the focused row is removed, focus moves to the nearest row and is announced.
- **Shell preview**: a banner with Help last, navigation "Project", main named by the workspace only, complementary "Evidence", regions "Work view", "Activity" and "Status"; h1/h2/h3; four skip links; tab roles; the Views toolbar.
- **Keep** is written the same everywhere: the Keep button, or Shift+K inside a Peek or card.

*Removes:* J38 4 → 2 (`g j` to the job row; Go 1; Back 1). For J22 it is error prevention, not fewer switches: a stray Esc no longer drops the checked set.
*Components:* keymap.json, 85, 90, 30, KeymapSettings, Workstation, tokens.json, design-system README, FRONTEND_INTENT F29.
*Accessibility:* 2.1.1, 2.1.2, 2.1.4, 2.4.1, 2.4.3, 3.2.6; sequences such as "g then 1" go in aria-describedby, not aria-keyshortcuts.
*Safeguards:* keys only navigate or arm; no binding can post or admit work; overrides are a per-viewer diff in durable workspace state; both surfaces load one keymap.json.
*Acceptance (future):* one binding per key per scope after precedence; `platformCautions` and `dock.lastAnnouncement` exist; no "K keep" or "Shift+Shift+K" left.

### U189 · Screen-reader reading of code and one live-region policy (P1; UX-19)
Already in 90: exact operands, verbosity, labels as rows, logs with aria-live=off, Accessible View and Freeze; keymap.json has Alt+F2 and in-well find. Still missing:
- **Per-well grids**. Listing: Address row header, Label, Bytes (absent while the HexStrip shows), Instruction, Operands, Xrefs/Comment, with aria-rowcount −1 unless known. DecompileView: line, code, mapping. HexStrip: offset, 16 bytes, ASCII. ObjectDiff: target, candidate, state word. SourceRepairDiff: line, change word, text.
- **Focus model**: focus roves on rows; → enters cells and steps operand links token by token; F2-editable cells are aria-readonly=false. Operands read exactly as rendered; a plain-words form goes in aria-description with an aria-describedby fallback; flow glyphs become words ("jump target from 0041b210").
- **Accessible View** gets a README: every row already read ("Not loaded" otherwise, never a decompile); a snapshot "as read ‹time›" with "◷ Basis changed since opened · Refresh"; Held, Kept and historical sources labelled. It soft-wraps, so it is the 1.4.10 path for code at 320px and the character-exact path.
- **One live-region policy**: no settle announcements (focus is the cue; landings only in 35's cases). Polite: job transitions, decision outcomes, "Import durably accepted", result counts, stale notices once per transition, "N changes since you looked", "Cleared 4 checked rows on build-a". Assertive only for conflicts and refusals of the viewer's own action, never suppressed by Freeze. Coalesced within 1s; the opt-in "Announce new lines" at most once per second. This replaces "transitions only".
- **OS-taken keys**: where the desktop takes Alt+F1 or Alt+F2, the palette, Help menu and pane-header button remain; a second Ctrl/Cmd+F passes to browser find.
- **Verbosity** is a View setting (U190).

*Removes:* no ledger credit; an off-screen range becomes one modal read for assistive-technology users.
*Components:* AccessibleView (new README), Listing, DecompileView, HexStrip, ObjectDiff, SourceRepairDiff, 90, 30, 85.
*Accessibility:* 1.3.1, 4.1.2, 4.1.3, 2.2.2, 2.1.1, 1.4.10.
*Safeguards:* read-only; announcements never summarize facts or merge accepted and candidate counterparts; held and historical text labelled; the same templates on both surfaces.
*Acceptance (future):* 90 lists five per-well column sets and no settle announcement; the AccessibleView README exists.

### U190 · Perceivable states in every mode (P1; UX-20)
Already in the design system: the 3px inset focus rule, ProvenanceStamp's Fresh frame, RepresentationBar cues, grouped fact and capability targets, and the Increase contrast and Reduce motion toggles in 90. Still missing, mostly in bundle.css and tokens.json:
- **Focus everywhere**: 2px on bordered controls; 3px inset (`focus-inset-w`) on rows, cells, tabs, in-row inputs and links in clipped wells.
- **Forced colors, all ten blocks**: selected items use Highlight/HighlightText (SelectedItem only under @supports) and descendants inherit; focus is CanvasText, 3px inset HighlightText on selected rows; only the selected row carries the 3px inline-start border; popups get a CanvasText border; data graphics opt out only where a text key carries the values.
- **Selected rows**: line-control → ink-muted (3.78:1); words ink-strong; glyphs keep their hue (with an optional glyph-only `fact-failed-on-selection`).
- **Splitter grip**: a bordered element in `splitter-grip` (≥3:1); the 6px hit zone names the 2.5.8 equivalent exception.
- **Reserved accent and glyphs**: WorkTimeline uses ✓, ✕ and plain ticks with words and an ink-strong cursor (no accent, no ◇); ImageDeltaMap hatches differing regions with "✕ ‹n› bytes" and a key.
- **Existing cues kept**: reflection's fill and bar; highlight-all as a box, never an underline; "Held · ‹entity› @ ‹build› · ‹age›"; arrival per 35 (focus, selection shape and the 120ms flash; a static outline under reduced motion). There is no separate landed style.
- **View settings**: one per-viewer group in the View menu (density, Increase contrast, Reduce motion, screen-reader verbosity, auto-advance), in durable workspace state beside the keymap diff, never in the URL or browser storage. Increase contrast mirrors the whole prefers-contrast block; a new `.reduce-motion` class mirrors reduced motion; both only add to OS preferences. Density stays the only appearance choice.
- **Coarse pointers**: 44px targets at any width.

*Removes:* no ledger credit; it keeps J02, J06, J09, J10 and J33 usable in forced-colors, high-contrast, reduced-motion and touch use.
*Components:* bundle.css, tokens.json, 90, WorkTimeline, ImageDeltaMap, CodeBrowser, Workstation, design-system README.
*Accessibility:* 1.4.1, 1.4.3, 1.4.11, 2.4.7, 2.4.11, 2.5.8; 2.4.13 as a house rule.
*Safeguards:* Graphite stays the only theme; the accent only for focus, the active tab, links and the hovered splitter; no behavior change; the same tokens on both surfaces.
*Acceptance (future):* in forced colors, selected items render every descendant in HighlightText with no author color (they set forced-color-adjust:none only because the default Canvas text backplate hides HighlightText in common palettes; guideline 90); no `.ad-landed`; WorkTimeline uses neither the accent nor ◇.

### U191 · Narrow-viewport continuity (P1; UX-21)
Already in the design system: NarrowFlow, CodeBrowser's narrow tablist and SplitCompare's narrow switcher. NarrowFlow becomes the one narrow contract, reconciled with 35.
- **Advance on a code pick**: Enter or tap on an entity, address, symbol, string or import use site selects it, pushes one stop and shows Analyze; focus lands on the Listing row with one polite message. Project items go through the Switch StateNotice. Below 700px "Update panes" is forced to "On Enter" and says so. Back restores the previous stop and its pane; the rail's Navigate tab returns without changing the selection. Advance can be turned off in View settings.
- **Inspect sheet**: non-modal, at most 64% of the pane (`sheet-h`), with Full height and Close. It opens on Alt+↓, the row-menu Peek or the Inspect tab, never on focus rest; below 480px viewport height it opens as the full Inspect pane.
- **Counterparts**: the strip stays one wrapping line with a 44px "Counterparts (n) ▾" disclosure; the Build menu shows address, divergence class and edge word per build. Open beside is the second segment of an APG tablist, "build-a · primary | Held · build-c · ‹age›", read-only, with the ActionStrip naming the primary; 8080 opens a new window.
- **Dock**: Activity is a full rail pane; other panes show one status line with the latest transition and counts of other running and failed work, "Selection only" by default with Show all. This replaces the 23dvh dock.
- **Header**: the project name and a wrapping scope sentence stay; only search moves into Go to; WorkflowControl keeps its scope in a disclosure. Below 480px tall, header and status line are not sticky. Code wells contain horizontal overscroll; any coarse pointer gets 44px.

*Removes:* J37 6 → 2 (1 if the counterpart is only peeked; 3 if a job record must be opened; +1 below 480px tall).
*Components:* NarrowFlow, NavigationBar, CounterpartStrip, SplitCompare, CodeBrowser, WorkflowControl, 30, 35, tokens.json (`sheet-h`, `bp-short-h`).
*Accessibility:* 2.5.8 is met at 24px and 44px is the house rule (2.5.5); 1.4.10 at 320×256 with the short-height rule; focus never advances by itself (3.2.1).
*Safeguards:* no narrow-only state; navigation never starts work; counterparts always carry edge word and divergence; the status line never hides other work.
*Acceptance (future):* both surfaces at 1440×900, 598×912 and 320×256 CSS px and a coarse pointer at 768×1024, with the 1.4.12 overrides; on 8080 now, and on the Vite app only when separately authorized.

## Compiler-aware views and project outputs (2026-09-29)

Status: **design only, not a delivery receipt.** Nothing here is implemented in either frontend, and no server, browser, build, test, detector or compiler was run for it. This section adds units U192–U198, reserves U199–U218, and adds requirement rows F36–F38 in [FRONTEND_INTENT](../FRONTEND_INTENT.md) (source [Q2]). The existing units above are unchanged.

**Premise.** The builds of a project are variants of one application: the same source compiled differently, or built from older or newer source. So these views are keyed by the logical entity (function, field, slot, transformation, artifact), with the builds as columns. Each difference between builds is classified by variance class (≈ compile, ∼ entropy, ≠ source, ? unknown; ≡ identical is not a class) and shown with its evidence level (witness or record solid; hypothesis (heuristic) dashed with its basis; unknown as a word). A class is solid only when source, toolchain and flag identity are recorded for both builds.

**Research inputs** (text references; nothing in them was compiled or run):
- [MSVC optimization for decompilation](../research/2026-09-29-msvc-optimization-for-decomp.md): the transformations (T1–T13, I1–I8), the object model (§6), toolchain identification (§7), matching practice and "matching is not functionally equivalent" (§8.3), and UI implications (§9).
- [Exports and outputs inventory](../research/2026-09-29-exports-and-outputs-inventory.md): the eight output groups (A–H), each artifact's producer, claim tier and current status.
- [Reference RE UI patterns](../research/2026-09-29-reference-re-ui-patterns.md): structure and pointer patterns (A), compiler-explanation patterns (B) and diff and match patterns (C).

**Shared safeguards for U192–U198.**
- Read-only by construction. Each view reads stored parses, detector output, records, receipts and comparison results. None of them compiles, compares, detects, binds, exports or opens a program to draw itself; at most one fix is armed from `GET /api/v1/actions`, and it is never run.
- No guessed facts. Missing evidence is the word unknown, with nothing drawn in; "absent" is a plain word, never a link to a guess.
- Evidence levels are always shown as words, and a hypothesis never becomes a witness by repetition.
- Effective ≠ byte match; accuracy ≠ acceptance; compiling C ≠ verified recovery. Separate claims stay separate, builds and tools' scores are never averaged, and percentages are truncated, never rounded up.
- Nothing is observed live on 8080 until authorized. Every acceptance below is a future check.

New vocabularies and schema entries land in the design system: guideline 20 (Evidence level, Variance class, Cross-build comparison, Artifact status, compiler annotation tags, match explanation classes), 70 (copy), 35 (typed-link rows for artifact, toolchain fact witness, and type or field), 30 and the README (where the views live), `location-schema.json` (`panel` outputs, toolchain and variants; `artifact`, `walk` and `layers`; six hold and keep kinds; eleven filter axes), `keymap.json` and `tokens.json`.

### U192 · Every output in one catalog: OutputsCatalog and ArtifactCard (P1)
What changes: one corpus view, `ws=evidence&panel=outputs`, lists every export, output and result in the inventory's eight groups, as artifact × build. Each cell shows the artifact status (delivered ▣, partial ◐, stale ◷, future ▷, never run ○, no report ∅, reference □). Each row shows its producer (verb, StageChip from `catalog_verbs` or "stage: unmapped", pipeline node), its claim tier with the ≠ sentence that says what it is not, its basis, and the separate 8080 axis (⊡ not observed). Opening an artifact (`artifact=`) shows the ArtifactCard: proves and does not prove, identity and hashes, produced by (with "provider differed"), bundle members, coverage by build with measures kept separate, changes since the previous report, acceptance kept separate, the determinism rule, and its 8080 observation.

Why: "which outputs exist, for which builds, and how much is real today" currently takes the dock, the diagram, the receipts and the docs. One grid and one card answer it, and the status words stop "delivered" from being read as "live" or "accepted".
*Components:* OutputsCatalog, ArtifactCard, StageChip, ClaimTier, ProvenanceStamp, FactBadge, FilterChip, StateNotice; guidelines 20, 35 and 70; `location-schema.json` (`panel=outputs`, `artifact`, keep kind `artifact`, axes `artifact.status`, `artifact.group`, `artifact.build`, `artifact.file`, `tier`, `observed`); `keymap.json` (`outputs.copyPath`, `c` in the grid only); token `artifact-delivered`.
*Accessibility:* a row-focus APG Grid named "Outputs of ‹project› by artifact and build", group headers as rowgroup disclosures, each build cell's accessible name carrying the status word and the 8080 word; the not-observed notice is `role="note"`, not a live region; the card is a section with h4 subsections; a narrow list form below 480px containers; 24px targets, 44px below 700px.
*Safeguards:* "Delivered" means only that a bounded receipt exists; the 8080 observation is its own axis and never implied by status; a never-produced artifact shows "tier when produced", never a tier chip; accuracy numbers never appear as acceptance ("Accuracy ≠ acceptance"); "previous report not found · changes not available", never "no changes"; "varies across builds · not averaged"; "done" only at exactly 100%, with truncated percentages; no merge across source revisions; Download only for a recorded stored file with its hash; a historical observation from a port outside 8080 stays historical.
*Acceptance (future):* every row of the outputs inventory appears once in its group with a status per build; no artifact without a receipt reads delivered; no ClaimTier chip on a never-produced artifact; the 8080 column reads "not observed" for every artifact until an authorized observation exists.

### U193 · Toolchain evidence by build: ToolchainEvidence (P1)
What changes: `ws=evidence&panel=toolchain` shows compiler, linker and flag facts × builds (Rich header, linker version, PDB and CodeView, CRT startup, /GS, EH model, LTCG, /Oy, ILT, hotpatch, ICF, string pooling), each cell an evidence value with its level word, value and basis, and each row linked to its research section. The last row is the pinned rebuild toolchain; a mismatch with the evidence shows the ⇄ notice ("its compiles are compile checks only") and arms at most one catalog action. A pair list under the grid says what the evidence suggests for each pair of builds, and links to VariantRelation.

Why: whether builds can be the same source compiled differently, and whether the rebuild toolchain can byte-match each one, currently means opening each program's headers, PDB and detector output one at a time.
*Components:* ToolchainEvidence, StateNotice, ProvenanceStamp; guidelines 20 (Evidence level) and 35 (toolchain fact witness link); `location-schema.json` (`panel=toolchain`); tokens `evidence-solid-frame`, `evidence-hypothesis-frame`, `dash-hypothesis`.
*Accessibility:* a cell-focus APG Grid named "Toolchain evidence by fact and build", facts as row headers and builds as column headers; the level word is visible in every cell and the frame is the second cue; the mismatch box is a note with ⇄ plus words; identifiers carry `translate="no"`.
*Safeguards:* a witness address link always carries its build; a hypothesis names its basis, sample and what was not checked; a solid absence names what was checked, and an unchecked absence is unknown; the build summary uses solid values only; nothing is parsed, detected, compiled, pinned or downloaded from here.
*Acceptance (future):* every cell shows one of the four level words; no hypothesis appears in a column summary without its word; a build without a pinned toolchain reads "unknown · not pinned".

### U194 · How builds relate: VariantRelation (P1)
What changes: `ws=compare&panel=variants`, with `cmp` selecting one pair, shows each pair of builds with its toolchain, flag and link differences (from U193) and the count of entities in each variance class, each count with its level. A small map gives the overview; the pair table carries the same information as a grid. Activating a count applies `f=vrel:‹class›` and lists the entities behind it, each with its addresses, the deciding evidence and each tool's own opinion.

Why: telling compiler differences from source changes currently means opening each pair's toolchain headers, diff report and entity list separately.
*Components:* VariantRelation, FilterChip, CounterpartMatrix (entry link), ToolchainEvidence (pair links); guideline 20 (Variance class); `location-schema.json` (`panel=variants`, axis `vrel`).
*Accessibility:* the map is a named group whose SVG is `aria-hidden` and whose labels are real text; the pair table is a row-focus APG Grid described by the class legend; every count's accessible name carries count, class, pair and level; the drill announces once, debounced.
*Safeguards:* a class is solid only with recorded source, toolchain and flag identity for both builds; bodies never compared read "unknown · nothing is counted until the bodies are compared"; counts are per pair, never summed, averaged or turned into a score; scores from different tools are never compared or averaged; opening an entity decides nothing.
*Acceptance (future):* no solid class for a pair without recorded identity on both sides; no total across pairs; each drill row names its tool for every score.

### U195 · Walking a pointer: PointerWalk (P1)
What changes: `p` on an operand or expression in a code well (or the link menu or palette) opens the walk: an ordered chain of steps (root, offset and dereference, index and stride, field, this-adjust thunk, vptr to vftable slot, union), each with the address arithmetic in the inspected build, the typed reading, its evidence level, the cross-build word (≡ same in all builds, ± differs: consistent pattern, ± differs, − absent in build-x), one offset cell per build and a variance class where builds differ. A layout strip shows the struct at the current step, with a key table as its accessible form. The chain is carried as `walk=chain[:step]` (replace).

Why: following `this->cache->entries[i].name_len` across builds currently means re-typing offsets in each build's structure editor and comparing them by eye.
*Components:* PointerWalk, Listing, DecompileView, SplitCompare, VTableBrowser and FrameLayout (Reveal in); guidelines 20 and 35 (type or field link); `location-schema.json` (`walk`, kinds `type` and `walk`); `keymap.json` (`code.walk`).
*Accessibility:* the steps are an `<ol>` with `aria-current="step"`, each step's name a full sentence; per-build cells are a named group and the inspected cell says "inspected" in text; the layout strip is `role="img"` described by the key table; arithmetic is read as rendered, with a plain-words `aria-description`.
*Safeguards:* keyed by logical field chain, never by position or one binary's address; a union lists both readings as hypotheses and picks neither; an unresolved base is the word unknown with nothing typed; the walk never decompiles or re-types on its own ("Not decompiled in this session · Enter to decompile").
*Acceptance (future):* every step shows a level word; no step has a type without a record, witness or named hypothesis basis; absent builds are plain words.

### U196 · What the compiler did: CompilerLayer and TransformTimeline (P1)
What changes: a Compiler layer toggle (`c`, `layers=compiler`) adds a gutter column (`annot-gutter-w`) to Listing, DecompileView and SplitCompare with one of 15 tags (INL, ICF, GS, EH, SEH, DIV, TAIL, SW, FPO, ILT, HP, STR, LOOP, INTR, CC), a band with a plain phrase, the evidence level, per-build presence and its variance class, and remarks under decompiled lines. `a` and Shift+A step the annotations. TransformTimeline lists the same annotations for one function across a `cmp` pair in conventional stage order, from the inferred source to the observed bytes of both builds, under the claim line "Reconstructed explanation, not observed compiler passes."

Why: seeing that a call was inlined in two builds and not in two others, or that a divide is a magic multiply, currently means knowing each idiom by heart and comparing listings side by side.
*Components:* CompilerLayer, TransformTimeline, Listing, DecompileView, SplitCompare, FilterChip; guideline 20 (compiler annotation tags); `location-schema.json` (`layers`, kind `xform`, axes `xform`, `variance`, `presence`); `keymap.json` (`code.compilerLayer`, `code.annotationNext`, `code.annotationPrev`, `code.timeline`); token `annot-gutter-w`.
*Accessibility:* each tag is a word and brackets are `aria-hidden`; bands and remarks are rows of the well's grid, named in words; annotated rows append the tag word; the legend is a `<dl>`; verbosity "off" drops bands to the tag word; the timeline is an `<ol>` whose description includes the claim line; hidden annotations are counted, never dropped silently.
*Safeguards:* only stored detector output is drawn; a build without detector output shows "No detector output for ‹build› · Not loaded", never a guess; scaffolding stays visible and labelled; "folded with N functions" never picks one name; the timeline never claims observed passes and says when the legacy toolchains emit no optimization remarks.
*Acceptance (future):* every band shows a level word and a presence line; no annotation appears for a build without detector output; the timeline's first text is the claim line.

### U197 · Why it is not a byte match: MatchExplain (P1)
What changes: beside ObjectDiff in Recovery and Compare, and as a rail section, MatchExplain explains a stored comparison receipt. It shows Local match, Linked match and Whole-file equality as separate FactBadges, an Effective match state of its own, a class table of the nine classes (register allocation only, scheduling, stack slot or local ordering, relocation or address only, constant, branch structure, inlining, toolchain or flags mismatch, source difference) with counts, evidence and a next step in words, the rows with lettered register pairs, and identity opinions, each with its own matcher and score.

Why: a near miss currently shows as a diff to be read row by row. Classifying the rows says whether to change source, flags or nothing, and points to FrameLayout or ToolchainEvidence when the cause is there.
*Components:* MatchExplain, ObjectDiff, FactBadge, FrameLayout, ToolchainEvidence; guidelines 20 (match explanation classes) and 70; `location-schema.json` (axis `diffclass`); `keymap.json` (`code.explain`).
*Accessibility:* status items are separate named elements, never one badge; the effective-match state reads its full words; class table and rows are APG Grids with row focus; register pairs are lettered and framed (solid and dashed), never colour alone; Accessible View lists classes, then rows.
*Safeguards:* effective ≠ byte match, and an effective match is never counted as byte-identical or as Local match; a fuzzy percentage is truncated and labelled "not a claim"; scores from different matchers are never compared, averaged or merged; a historical receipt is labelled historical ("◷ compiled from r14; source is r15"); with no receipt, "Nothing is compiled from here."
*Acceptance (future):* no fixture shows "effective match" as a passed Local match; no combined score across matchers; every class shows a count, "—" with a hypothesis, or unknown.

### U198 · Frames and vtables per build: FrameLayout and VTableBrowser (P2)
What changes: FrameLayout shows one function's stack frame per build, higher addresses first, by logical slot (arguments, return, saved registers, EH node, cookie, buffers, locals, spill, alignment), with offsets per build and flags for /GS buffer ordering, slot reuse and FPO; ESP frames are normalised and say so. VTableBrowser shows the class hierarchy with RTTI presence per build and a slot table keyed by logical method, with added and shifted slots, differing overrides, adjustor thunks, deleting destructors and folded targets.

Why: comparing frames and vftables across builds currently means opening each build's stack editor and each vftable and matching slots by index, which breaks as soon as a base class gains a virtual.
*Components:* FrameLayout, VTableBrowser, PointerWalk, MatchExplain, DecompileView; guideline 20; `location-schema.json` (kinds `frame` and `vtable`); `keymap.json` (`code.frame`, `code.vtables`).
*Accessibility:* FrameLayout is a named table with slot tags as row headers read in words, and its flags are text included in the table's description; VTableBrowser is an APG Tree plus an APG Grid with cell focus, cells read index, target and state in words; mangled names carry `translate="no"`.
*Safeguards:* rows are keyed by logical slot or method, never by offset or index; frame-pointer and stack-pointer offsets are never compared raw; "insufficient alignment to pair slots" instead of a wrong mapping; one folded address never picks one name; slot order changes are source variance only as a hypothesis unless source digests are recorded.
*Acceptance (future):* no raw EBP-against-ESP offset comparison; every folded target lists all its entities; builds without RTTI show names only from identity edges, dashed.

### U199–U218 · Ghidra Code Browser parity (26 components plus extensions; detailed separately)
The [Ghidra Code Browser functional parity specification](2026-09-29-ghidra-code-browser-parity.md) maps 224 Ghidra features. After four rounds, **all 224 are designed** (round 4 added FunctionStartPatterns for X08 and the KeymapSettings Scripts group for C05). **121 are backed** by a documented tool or need no server call, and **103 need a catalog action**, each proposed in the [catalog contracts](2026-09-29-catalog-contracts-for-parity.md) (113 entries: 39 reads, 37 writes, 21 jobs, 16 schema gaps).

Components: ListingFieldLayout, OverviewBar, SymbolTree, ProgramTreeView, MemoryMapTable, ResultsTable, SearchWorkbench; TypeManager, TypeEditor, SignatureEditor, StackFrameEditor, ReferenceEditor, RegisterValuesEditor, PatchEditor; AnalyzerPanel, ScriptConsole, VersionControlPanel, ExportDialog, OptionsPanel, EditHistory; ProgramValidation, ProgramSettings, DebugInfoImport, FunctionIdManager, ProjectWindow; FunctionStartPatterns. Parity extensions live in Listing, DecompileView, GraphPane, SplitCompare, HexStrip, Peek, XrefPanel, CallHierarchy, NavigationBar, MarksList, EntityTimeline, SymbolTree, ResultsTable, PropagationTransfer, ReviewDetail and SignatureEditor.

*Safeguards:* functionality, not Ghidra's theme; every write names one build and goes through a catalog action; propagation is a separate gated Propose step; one writer; no analysis on open; imported evidence never overwrites a stronger tier.
*Acceptance (future):* each parity row's design passes against its Ghidra help page; each "needed" row's contract exists in the catalog before its control is enabled; nothing runs on 8080 until authorized.

### Decisions and conflicts resolved during integration

- **≈ changes meaning.** ≈ is compile variance only. "Differs: consistent pattern" is `±` plus those words. Alignment markers keep ↔ ± − +; ± and − mean the same in both sets, and ≡ is used only for N-build comparison.
- **≠ on two axes.** ≠ is both the divergence class ("≠ diverged") and source variance ("≠ source changed"). The word always travels with the glyph, and the two classes never share a cell.
- **Keys.** `p` (`code.walk`) and `c` (`code.compilerLayer`) were checked against precedence, the leader map, `browserReserved`, the ida profile and every code-scope single key; neither conflicts. Annotation stepping was proposed as `}` / `{`, which collide in code scope with ListingFieldLayout's arrow keys, so it is `a` / Shift+A. VTableBrowser keeps `g then v`. VersionControlPanel also proposed `g then v`; version control (`vcs.open`) is menu and palette only, because it is a project-level action and vtables are a code-well jump. OverviewBar also proposed `g then v`; `overview.focus` is registered with no default key and is reached from its Show key button and the palette. CompilerLayer names `a` / Shift+A, matching `keymap.json`.
- **Artifact keep kind is build-independent.** An artifact may be corpus-scoped (the export bundle), so `keep=artifact:‹id›` needs no build.
- **`vrel` and `variance`.** `vrel` filters the entities of one `cmp` pair in VariantRelation; `variance` filters annotations, steps, slots or items in the code views. Both take compile, entropy, source and unknown; identical is not a value.

### Usability audit, round 4 (2026-09-29)

A first-time, keyboard-only and screen-reader walk-through of the whole design system found 40 issues (11 high). All were fixed; the decisions are:

- **One typeahead rule:** in every list, grid, tree and treegrid, typeahead starts with `/`; text fields and comboboxes take plain typing.
- **Keys:** presets are `g then 1…7` everywhere; a **Ghidra key profile** (l, ;, t, d, c, f, all arming only) sits beside IDA; next and previous function are Ctrl/Cmd+↓/↑; F2 renames a function from its name in Listing and DecompileView; `a` is always the build-scope key; OutputsCatalog copies with Ctrl/Cmd+C; reorders are Alt+Shift+↑/↓; every leader chord is a remappable command; `=` and `file:` go-to prefixes; `?` is literal; Ctrl/Cmd+F8 marks handled and steps; more punctuation keys are layout-safe; closed session tabs can be reopened.
- **One name per thing:** the Corpus workspace (`ws=evidence`), the Evidence rail, the Dock with Events and Objectives tabs, Recovery facts in the rail; a Location and history landmark with its own skip link and F6 stop; an APG Menubar (File, Edit, View, Select, Search, Analysis, Tools, Project, Help); "Builds ▾" is the only build menu.
- **Copy:** "Not available on this server yet. ‹what still works› · What this server offers" replaces every "catalog action needed"; visible labels say "Prepare", "Undo…", "Redo…", "Pause new work", "Restore" and "Check ‹name›", never "Arm", "(catalog)", admission or a tool id; one set of follow words ("Follows · as I move", "Follows · on Enter", "Held · …", "Counterpart of … · derived"); panes say "Not loaded · Enter to load"; "address selection" for Ghidra's selection; "Stay at this address on rebase"; "rebuild toolchain" instead of "pinned".
- **States:** derived panes are the third pane kind; the Functions list has empty, no-match and loading states; build-column grids have one narrow form (NarrowFlow); the rail lists its Ladder section; validator and version-control glyphs follow guideline 20 (✕, ⊘, ✓ latest, ✎ not checked in).

## Accessibility baseline already applied to the design system

Selection shown by fill plus a 3px bar; muted text and state words promoted on the fill; accent removed from statuses; links underlined; 24px targets; real tabs, grids, combobox, alert dialog and separator semantics in previews; spoken words for glyph-only cells; progress roles; diff words; prefers-contrast and forced-colors support (their bundle.css defects are listed in U190); color-scheme; tabular numerals; log tails keep the newest text; guideline sections Linked views and Accessibility. See the design system for the rules.

## Diagram changes already applied

`docs/dashboard-design/pipeline-diagram/pipeline-model.json` now holds every diagram's content with stable node ids and typed edges (drawn edges separate from inferred ones, each inferred edge with its basis). All four SVGs render from it with `role="img"`, title, description and language, one `<g id>` per node in reading order, family words, full legends and no overlapping text (a measured collision check refuses to write otherwise). Generated text outlines anchored by node id are the primary accessible form, and the node ids are the deep-link vocabulary for the PipelineMap, PipelineBreadcrumb, go-to (`~node`) and Explain. See that directory's README for hashes and the supersession note.

## Conflicts and supersessions

| Earlier | Now |
|---|---|
| "Enter opens the action strip with the last action" (feel.md Essay AC) | Enter always means Go; `.` rebinds the armed action to the focused row and focuses Run, and only Run posts (U184). |
| Toolbar search filters functions only; Ctrl+P "search functions" | Ctrl/Cmd+P and Ctrl/Cmd+G focus the one go-to field and Ctrl/Cmd+K opens the palette; the Functions filter stays a filter, and in grids with letter commands typeahead starts with `/` (U178). |
| Checks persist "until Esc" (decisions.md, Phase C) | Esc never clears the checked set; the count chip × or Clear checked does, with an inline Undo beside the chip (U174, U188). |
| Analysis tablist with a "More…" select | Views toolbar with at most two center panes plus the HexStrip; References (Calls, Slots) and Outline in the rail; Matching becomes the CounterpartStrip and SplitCompare (U173, U175, U177). |
| Single-letter global shortcuts (S, O, N, G) | Modifier globals; single letters focus-scoped and remappable; code scope wins over composite inside code wells (U177, U188). |
| The second keymap profile's single `g` for go to address in code wells | `g` then `g`, so the leader keeps working in code wells (U188). |
| `pin=` in links | `keep=` for Kept cards and `hold=` for held panes; "pinned" is reserved for the locator status (U172). |
| Back button history menu | The Recent menu (right-click on Back); Back and Forward never change holds (U172). |
| "Link panes" toggle; "Linked/Unlinked" | "Update panes: As I move / On Enter" and the "Hold this pane" toggle (U176). |
| "One page, minimal tabs" vs dense tabs | Co-visible views plus rail sections; tabs remain only for workspaces, sessions and the dock (U173, U176). |
| Filters always replace history (location-schema `f`) | Typing, editing or removing a filter replaces; applying a filter from a link ("Changed by a3f9", Show all) is a Go and pushes (U172, U180). |
| Splitter "Home resets" (30, 90, LayoutPresets) | Home/End go to the minimum and maximum (APG); Enter collapses and restores; reset is in the pane size menu or a double-click on the grip (U187, U188). |
| Layout and other per-viewer choices in browser storage (localStorage) | Durable workspace state per viewer (F23), stored as a diff beside the keymap overrides; localStorage at most a non-authoritative try/catch cache (U187). |
| "Density is the only user preference" (design-system README); accessibility toggles with no home | One per-viewer View settings group in the View menu (density, Increase contrast, Reduce motion, screen-reader verbosity, auto-advance) in durable workspace state, never in the URL or browser storage; density stays the only appearance choice (U189–U191). |
| Session tabs with automatic activation | Manual activation; another project's tab shows the Switch/Stay StateNotice (U187). |
| A separate TokenContextMenu on Shift+F10 | One flat link menu with an Edit group whose items come from GET /api/v1/actions (U185). |
| Every mutation confirms through ConfirmDialog (ActionStrip draft) | Single-target inline edits confirm in place; ConfirmDialog for batch, destructive and cross-build changes, including structure-layout and callee-signature edits (U184, U185). |
| BeforeAfterBand as a SourceRepairDiff variant | Its own component with neutral markers; after-state only from the job record or a post-terminal cache; stale dependents read "◷ predates job", with no automatic re-decompile (U185). |
| A contested cell or locator opens two held panes | A candidate menu; "Compare candidates" opens Compare with two holds; in the Code Browser, one contested pane (U175, U183). |
| A held graph as navigator; panes that follow active work | The graph follows and re-roots only on Re-root; no pane follows work, and the Work view chip reads "Job a3f9 is at ‹node› · Go" (U173, U180). |
| F8 steps Problems when no worklist is active; runs and refusals become worklists by themselves | F8 steps only the active worklist; worklists come only from Collect (`w`) or an explicit "Step problems" / "Step changed rows" (U179, U182, U184, U186). |
| One announcement per selection settle (90); "transitions only" (30) | No settle announcements; landings only in the cases 35 lists; one catalogue of transitions and settled results (U189). |
| Ctrl/Cmd+J opens the dock at the last transition and "again returns" | Ctrl/Cmd+J only shows or hides the dock; "Go to last announcement" (`g j`) reaches the job row (U188). |
| A landing style until the next navigation | No separate landed style: focus, the selection or cursor shape and the 120ms flash; a static outline under reduced motion (U190). |
| Marks and notes at the context-hint tier; viewer marks standing in for program bookmarks | Marks and notes are per-viewer annotations with no claim tier, never an input to context fusion, propagation or agent bundles; program bookmarks are a separate read-only Bookmarks scope (U179). |
| One job line for what it targeted and what it changed | Separate "Targets" (asked to act on) and "Changed" (recorded by its receipts) lines (U180). |
| A fixed pause-scope sentence; Explain from the outline markdown | Scope composed from the backend's report; Explain from the served model with its revision, labelled design text (U181). |
| Dock at 23dvh below 700px; Open beside into Inspect (NarrowFlow) | Activity is a rail pane plus a one-line status; Open beside is the Held second segment of the split tablist (U191). |
| Ctrl/Cmd+Alt+digit layout presets (ReviewDetail, SplitCompare) | `g` then 1…7, which is AltGr-safe (U186, U187). |

## Open questions

None remain open for the design. Each question raised during this plan is listed with where it was decided. Items that need an observation of the running product are listed separately as verification debt: they are not design questions, and nothing assumes their answer.

Decided (2026-09-29):

- **Anchor interception on the static surface** is all corpus windows at once: one delegated handler at the document root applies the link grammar (Enter = Go, Shift+Enter = Open beside, Alt+↓ = Peek) to every same-origin anchor, including those inside server-rendered fragments. A per-window rollout would give the same link two behaviors depending on the window, which the linked-views rules forbid (35, Link interception contract, "One handler for every window").
- **Catalog verbs outside stages 1–7**: export verbs map to export nodes ([consolidated plan §2.1](2026-09-21-consolidated-design-plan.md#21-canonical-stage-order-recovery), "Verbs outside stages 1–7"; `catalog_verbs` in pipeline-model.json; StageChip "export · hookpack"). Stage 0 is open, add and resume, not a verb; stage 8 has no verb; no verb maps to a lane by name.
- **Interpretation edges and crosswalks** in the pipeline model: reviewed against the authorities; see the pipeline-diagram README, "Interpretation review".
- **One word per job outcome**: 20-state-vocabularies "Job outcome" (pending, admitted, waiting, running, checking, finished, failed, cancelled). OutcomeCell and 90's batch example use exactly these words.
- **`fact-failed-on-selection`** is adopted (tokens.json, `salmon-200`, 5.23:1 on the selection fill; glyph only).
- **Tab moves focus**: Ctrl+M on Windows and Linux, Ctrl+Shift+M on macOS (Cmd+M minimizes there). `tabs.move` stays menu-only ("Move tab left/right" in the tab's menu and the palette), because Ctrl+Shift+PageUp/PageDown belong to the browser (keymap.json).
- **Layout presets 6 and 7**: `g then 6` (Explain build difference) and `g then 7` (Walk pointers), registered in `keymap.json`. The rail forms for VariantRelation (one pair, scoped to the selection) and TypeEditor (read-only, following the walk's current step) are in those components' READMEs.
- **Line styles**: one vocabulary for the whole app (20-state-vocabularies, "Line styles"). Dashed means unproven and nothing else; states such as pending, off or absent are solid with their word; unknown has no frame.

Verification debt (each needs an authorized observation on 8080; never assumed):

- whether the static surface already intercepts anchors, and in which windows;
- whether the anchor pairs SplitCompare aligns on are exposed to both surfaces;
- the live catalog's verb list compared with `catalog_verbs`.

Decided during integration (2026-09-29):

- F8 with no active worklist shows "No active worklist" and offers an explicit "Step problems" (UX-12). It never creates a snapshot by itself.
- A checked set cleared by a program change is not restored on return, and there is no Undo around program changes. Back's description announces the clear before it happens (35 History). An explicit Clear checked keeps its inline Undo.
- Highlight-all (h) is a 1px ink-strong box plus a gutter count ("5 occurrences"), never an underline and never a letter badge.
- `panel` is registered for report, atlas, review, builds, pipeline, readiness, names, reuse and runtime (`location-schema.json`).
- The static surface's current anchor interception, the anchor pairs SplitCompare needs, and the live catalog's verb list are **not verified from docs**. Each is a future check on 8080, only when authorized.

## Known inconsistencies (from the outputs inventory)

Recorded 2026-09-29 from a read of [the exports and outputs inventory](../research/2026-09-29-exports-and-outputs-inventory.md) (cited below as `inventory:line`, path `docs/research/2026-09-29-exports-and-outputs-inventory.md`). Nothing was run or queried to check them. All seven are resolved below (2026-09-29). Where the underlying data stays incomplete, the views say so in words and never pick a side silently.

1. **Artifact count: 57 in the summary, 67 in the table.** The integration brief reports a summary figure of 57 artifacts. The master table (inventory:68-145) has 67 artifact rows in eight groups: A 10, B 11, C 9, D 13, E 14, F 5, G 3, H 2. No "57" appears in the inventory's current text (read-only check, 2026-09-29), so the lower figure comes from an earlier draft or a derived summary.
   *Resolution:* the table is authoritative. The inventory gets one count line derived from the table ("67 artifacts in 8 groups"), any summary quoting 57 is corrected, and OutputsCatalog's acceptance ("every row of the outputs inventory appears once in its group", U192) checks against table rows, never a summary number. *Owner:* the inventory (`docs/research/2026-09-29-exports-and-outputs-inventory.md`); OutputsCatalog README for the acceptance wording. *Done:* the inventory carries the count line under its master table.
2. **U89 header-producer evidence disagrees.** The unit ledger's partial evidence for U89 is the synthetic recovered-project manifest schema, while DELIVERY_STATUS attributes the partial prerequisite to the legacy header path; neither is the `build_types_header` producer U89 names (inventory:76, :302-309, :1300-1301).
   *Resolution:* A5 stays "partial" with the note "evidence names a different producer"; its ArtifactCard lists both citations as they are, and nothing reads delivered until a receipt names the header producer itself. The ledger and DELIVERY_STATUS are reconciled to one statement. *Owner:* [DELIVERY_STATUS](../DELIVERY_STATUS.md) (lines 67-71), reconciled with the [weekend unit ledger](../plans/2026-09-27-weekend-unit-delivery.json). *Done:* DELIVERY_STATUS (Phase 12 audit paragraph) now states that U89's ledger evidence is the synthetic manifest module and that the header producer has no delivery evidence yet, matching the ledger.
3. **D1–D7 and U120–U125 are "landed" or ✔ in the portable plan but unverified in the ledger** (inventory:140, :1166-1170, :1302-1303).
   *Resolution:* status in every view comes from the ledger, never from plan checkmarks (STRATEGY: historical checkmarks do not establish delivery). G1 reads "future · plan marks ✔, ledger unverified", and the portable plan's marks are annotated as historical. *Owner:* the [weekend unit ledger](../plans/2026-09-27-weekend-unit-delivery.json); annotation in the [portable plan](../plans/2026-09-21-portable-signatures-codecaves-generic-plan.md). *Done:* the portable plan opens with "Status marks are historical", pointing to the ledger.
4. **Export verbs are missing from `catalog_verbs`**, so `export-hookpack`, the future `export-bundle`, `export-lua-bindings`, `readiness-report` and `diff-builds` jobs read "stage: unmapped" (inventory:47-52, :1304-1306).
   *Resolution:* no lane or stage guess before a decision. The decision maps export verbs to the export-target nodes (not to a numbered stage), recorded beside the existing open question on stage 0, stage 8 and the lanes. OutputsCatalog's Produced-by column already renders the unmapped word. *Owner:* [pipeline-model.json](pipeline-diagram/pipeline-model.json) `conventions.catalog_verbs`, with the decision in the [consolidated plan](2026-09-21-consolidated-design-plan.md) §2.1. *Done:* decided in the consolidated plan §2.1 ("Verbs outside stages 1–7") and recorded in `catalog_verbs` (`exports`, `label`, `status`); StageChip renders "export · hookpack".
5. **`export-hookpack`, `backfill`, `verify-determinism` and `attest` lack U104 admission flags** (`mutating`, `identity_scope`, `long_running`), so pause cannot name or drain export work (inventory:228-229, :1307-1308).
   *Resolution:* U104 adds the three flags to these verbs. Until then, U181's "What this pauses" names them as "not covered by pause: admission flags missing", and nothing implies that pausing drains them. *Owner:* the [portable plan](../plans/2026-09-21-portable-signatures-codecaves-generic-plan.md) (U104), with the scope wording in WorkflowControl. *Done:* U104 already names all four verbs and their flags (portable plan, U104); until it is delivered, U181's wording stands.
6. **`byteExactRecoveredC` is a compatibility alias for a raw local count** (`rawLocalObservedC`, B4), and any counter still using it reads as recovered C (inventory:532-534, :1309-1310).
   *Resolution:* every counter is relabelled from the canonical field, "raw local observations", with its claim line ("does not certify semantic identity, current toolchain, linked contribution or a full rebuilt image"). The alias name never appears as a label, and a total built from it is never shown as verified recovery or whole-image acceptance. *Owner:* guideline [20-state-vocabularies](../design-system/project/guidelines/20-state-vocabularies.md) and [70-copy](../design-system/project/guidelines/70-copy.md) for the label; the [raw local observations receipt](../verification/2026-09-27-raw-local-observations.md) for the field. *Done:* 70-copy fixes the label and claim line.
7. **The historical source ZIP evidence came from ports the current mission forbids** (the 2026-09-08 run on non-8080 ports; inventory:81, :434-439, :1311-1312).
   *Resolution:* A10 stays "partial (historical)". Its ProvenanceStamp reads historical with "observed outside 8080 · not a current delivery receipt", it offers no Download, and "the current max-C ZIP" stays open until an authorized observation on 8080. No view counts it as delivered or observed. *Owner:* [DELIVERY_STATUS](../DELIVERY_STATUS.md) (lines 327-331); OutputsCatalog and ArtifactCard for the rendering. *Done:* the rendering rule stands as written; nothing else needs to change.
