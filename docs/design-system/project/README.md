AgentDecompile Workstation is the visual language of a reverse-engineering instrument: open compiled software as naturally as a source repository, watch the actual evidence change, and never be told a result the receipts do not support. It should feel like **an IDE fused with a flight deck**. You always know where you are in the corpus, power is one gesture away, async work stays in peripheral vision, and the UI never celebrates.

One theme ships: **Graphite**. It is deliberately dark and single-accent. Do not add decorative themes; density is the only user preference.

## Principles

1. **Color is semantics, not decoration.** Color is reserved for four things: `address`, focus/selection (`accent`, `selection`), lifecycle and proof facts (`fact-*`), and pipeline lanes (`lane-*`). Everything else is graphite neutrals (`chassis`, `pane`, `raised`, `well`, `line`, `ink*`).
2. **One accent.** `accent` is the only blue in the chrome. It marks focus, the active tab, links and a hovered splitter. It never means "good", "running" or "done".
3. **Never color alone.** Every state carries a glyph and a word (see FactBadge, StateNotice, LocatorGlyph). A reader with no color vision gets the same information.
4. **No green celebration.** `fact-passed` colors the glyph and word of a named fact that has a receipt. It never fills a banner, a row or a progress bar. "A finished job is not a match."
5. **Separate facts stay separate.** Compilation, ABI, tested behavior, local match, linked match, contribution and whole-file equality are independent facts, each `not_run`, `passed`, `failed`, `unknown`, `unsupported` or `stale`. Never merge them into one accuracy score or a third bar.
6. **Draw the work, not a status report.** Motion follows observed events only. No spinner beside the word "Running", no looping pretend-work, no timer-driven progress. Unknown internals are shown as unobserved.

## Content fundamentals

Plain, operational English, written from the operator's side. Short declarative sentences. Sentence case for everything except `kicker` labels, which are uppercase.

- Keep these lines verbatim: "Real C and a complete executable are separate facts." · "A finished job is not a match." · "Select a function to decompile, rename, and match siblings."
- Controls say exactly what happens: **Pause admission**, **Resume**, **Decompile**, **Match siblings**, **Move 3 rows to verification**. After the action, report the observed outcome: "Job a3f9 finished (mcp.match-function). Validate: not run."
- Never write "Success!", "Completed with flying colors", "All good", or a model name in a human-facing error.
- Errors name what failed and the next step: "`kb` is required. Enter it in the action strip." Transient read errors (408, 429, 5xx, timeout) are information, not alarms: keep the last content and say "Reconnecting. Showing data from 14:02."
- Unknown is a real answer. Write "Not measured", "Unobserved", "No receipt" rather than inventing a percentage or ETA.
- Evidence keeps its scope: say "byte-identical in k2.exe 1.0.3" rather than "matched".
- Use Ghidra's object model: a *project* contains folders and *programs*. Reserve *repository* for Ghidra Server shared storage.
- No emoji anywhere. Glyphs come from the fixed vocabulary below.

## Visual foundations

**Surfaces.** Depth comes from surface shifts and 1px `line` rules, never shadows. `chassis` is the ground; `pane` holds rails, headers, dock and dialogs; `raised` is hover and menus; `well` is where evidence lives (listing, decompile, hex, log tail, inputs). Only popups (`shadow-popup`) cast a shadow.

**Text.** `ink` on every surface; `ink-strong` for titles and the selected label; `ink-muted` for secondary text on `chassis`, `pane`, `raised` and `well` only. On `selection`, secondary text is promoted to `ink`. `ink-disabled` is for disabled controls and never carries meaning.

**Type.** Three families: `sans` (IBM Plex Sans) for interface, `mono` (IBM Plex Mono) for all evidence, `cond` (IBM Plex Sans Condensed) for diagrams. Load them from Google Fonts; DejaVu Sans / DejaVu Sans Mono are the named fallbacks and match the diagram generators. The chrome scale is `kicker` 11 · `ui` 12 · `body` 13 · `pane-title` 15 · `section` 20. Nothing in the app chrome is larger than `section`; `diagram-title` (32) is for diagrams only. Addresses, hashes, byte counts, times and job ids are always `mono` with tabular figures, colored `address` when they are addresses.

**Geometry.** The workstation is square: `radius-none` on panes, controls, tabs, rows and dialogs. `radius-chip` (2px) on chips and keyboard hints. `radius-node` (6px) belongs to diagrams only. Controls are `control-h` (24px) at desktop density, `control-h-roomy` (28px) in roomy density, `touch-h` (44px) below 700px.

**Spacing.** Use the `space-1`…`space-8` steps (2, 4, 6, 8, 12, 16, 24, 32px). Rows are dense: `space-2` vertical, `space-4` horizontal. Pane bodies pad `space-5`.

**Layout.** One `100dvh` shell, top to bottom: header (brand, project scope, search, one workflow control) → session tabs → analysis tabs → navigation bar (Back, Forward, go-to address or symbol) → workspace → activity dock → status line.

```
Active project / related-build scope · search / goto · Pause admission
┌─ Navigator ───────┬─ Listing · Decompile · Compare ──────┬─ Evidence ──────┐
│ project/programs  │ shared entity, build counterparts     │ origin, facts,  │
│ one Functions     │ synchronized listing / hex / diff     │ conflicts, edits│
├───────────────────┴───────────────────────────────────────┴─────────────────┤
│ Activity dock: Activity · Recovery · Logs · Jobs · Problems                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

`navigator-w` 288px (240-520), `inspector-w` 320px (280-480), `dock-h` 200px (120px to 65vh). Splitters are a `splitter` 1px `line` rule with a `splitter-hit` 6px zone; the rule turns `accent` on hover and focus. Arrow keys move a splitter 16px, Shift+Arrow 64px, Enter collapses and restores, Home resets. There is exactly one Functions surface; never add a second function sidebar. Below 1024px the navigator becomes a side region; below 700px one primary pane shows at a time, with a rail bar that switches Navigate, Analyze, Inspect and Activity.

**Focus.** A solid 2px `accent` outline, offset -2px inside the control. It clears 3:1 on every surface, including `selection`.

**Selection versus batch.** One primary item uses the `selection` fill. The checked set is shown by checkboxes and a count chip, never by a second fill. Changing program clears the checked set.

**Motion.** Two durations: 120ms for the surface flash after palette navigation and the palette fade, 180ms for the dock opening. Everything else is instant. Under `prefers-reduced-motion`, all motion is removed and the same change is shown as a static before/after. Animated edges in the work view appear only after their accepted or rejected event exists, with freeze, step and history controls.

**Pipeline lanes.** The recovery diagrams and the work view share one lane palette. Each lane has a deep `-fill` for headers and bands and a bright `-ink` for titles and edges on `chassis` or `pane`:

| Lane | Tokens | Covers |
|---|---|---|
| Identity | `lane-identity-fill` / `lane-identity-ink` | Stage 1 identity, candidates and accepted edges |
| Source recovery | `lane-recovery-fill` / `lane-recovery-ink` | Calibration, scaffolding, readable C, propagation, whole-image identity |
| Cross-build unification | `lane-unify-fill` / `lane-unify-ink` | Knowledge fusion, portable signatures, export; diagram gates |
| Runtime reuse | `lane-runtime-fill` / `lane-runtime-ink` | Pack, preflight, observe, learn the build |
| Verification | `lane-verify-fill` / `lane-verify-ink` | Determinism basis, gates, receipts |
| Intake / distributed | `lane-intake-fill` / `lane-intake-ink` | Intake, cross-cutting work, distributed compute |

`lane-fault-fill` marks ownership locks and failover in diagrams. Lane colors identify *which work*; they never say whether it passed.

**Project kinds.** Session tabs carry a kind chip: `kind-gpr` (local .gpr), `kind-shared-fs` (shared folder), `kind-shared-http` (Ghidra Server), `kind-bin` (raw binary), `kind-draft`.

## State vocabularies

Four vocabularies are drawn on separate axes and never rolled into one badge.

**Proof facts** (FactBadge), one per named fact:

| State | Glyph | Token |
|---|---|---|
| passed | ✓ | `fact-passed` |
| failed | ✕ | `fact-failed` |
| stale | ◷ | `fact-caution` |
| unknown | ? | `fact-unknown` |
| unsupported | ⊘ | `fact-unknown` |
| not_run | ○ | `fact-unknown` |

**Surface lifecycle** (StateNotice): loading, empty, disconnected, unavailable, stale, unsupported, partial, conflict, reconnecting, approval-required, failed, recovered. Each has its own copy and keeps the last received content where it has any.

**Locator per entity × build** (LocatorGlyph): resolved(member), pinned(member), degraded(member, reason), ambiguous, unresolved, contested.

**Identity edges** (LocatorGlyph edges): candidate (dashed), accepted (solid), rejected (struck), unresolved (dotted).

## Iconography

The source defines no icon set and no logo. Set the name **AgentDecompile** in `sans` at `pane-title` weight 600; do not draw a mark. Status uses the text glyphs above, rendered in `mono`. Interface icons, when needed, are 1.5px-stroke line icons at 16px in `ink-muted`, turning `ink` on hover; never filled, never colored except by the state they report. No emoji.

## Do and don't

- Do put Listing and Decompile in the primary workspace; inspectors and the dock are resizable and collapsible.
- Do show the owner, operation, source and target builds, and last observation for every job. If progress is not measured, say "Not measured" and show the last event time.
- Do keep one workflow control: **Pause admission / Resume**, scoped to the active project. There is no Start button and no per-stage Run button.
- Don't use cards, statistic strips, gradients, floating dashboards or a giant blank upper workspace.
- Don't use toasts; notifications go to the activity dock.
- Don't steal focus, scroll or drafts on refresh.
- Don't show raw JSON as the default result; put the human summary first and raw output behind a disclosure.
