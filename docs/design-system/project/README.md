AgentDecompile turns opaque compiled and packaged software into provenance-anchored evidence that agents and operators can read almost as fluently as source. This design system covers every surface that carries that promise: the static 8080 workbench, the optional full workspace (the Vite app at `/react/` or on 5174), and the recovery diagrams that explain the pipeline. The same tokens, glyphs and state vocabularies apply to all three, so the UI, the diagrams and the agent-facing exports can never disagree about what a claim means.

It should feel like **an IDE fused with a flight deck**. You always know where you are in the corpus. Power is one gesture away. Async work stays in peripheral vision. Nothing celebrates an outcome the receipts do not support.

One theme ships: **Graphite**, dark and single-accent, taken directly from the recovery diagrams. Density (comfortable or compact) is the only user preference. There are no decorative themes.

## Principles

1. **Ground truth is the bytes.** Every name, type, candidate and proof shows where it came from: address, section or package path, the tool or witness, and its conflicts. A value without provenance is drawn as unknown, never as fact.
2. **Claim tiers never blur.** Verified, advisory, context hint and byte authoritative always look different (see ClaimTier). Readability never implies parity.
3. **Separate facts stay separate.** Compilation, ABI checks, tested behavior, local match, linked match, replacement contribution and whole-file equality are seven independent facts. Each one is `not_run`, `passed`, `failed`, `unknown`, `unsupported` or `stale`. Never sum them into a score, a bar or one "verified" badge.
4. **Shared codebase first, concrete build always available.** The primary selection is a logical entity across builds. Bytes, ABI, addresses and edits stay scoped to one concrete build. An absent counterpart stays visibly absent.
5. **Draw the work, not a status report.** Show the actual blocks under comparison, the actual source diff and the actual field moving from donor to recipient. Motion follows observed events only. A spinner beside the word "Running" is never acceptable.
6. **Missing evidence blocks its claim. An unhealthy resource blocks its dependents. Ready independent work continues.** Failure is drawn at its real unmet dependency, never as a whole-app stop.
7. **Color is semantics.** Color is reserved for the one accent (focus and selection), addresses, fact and lifecycle states, the six work families, and claim status. Everything else is graphite.
8. **Never color alone.** Every state has a glyph and a word.

## Visual foundations

**Surfaces.** `chassis` is the ground (the diagram canvas); `pane` holds panes, dialogs and diagram cards; `raised` is hover and menus; `well` holds evidence: listing, decompile, hex, diff and log tail. Depth comes from surface steps and 1px `line` rules. Only popups cast `shadow-popup`.

**Text.** `ink` on every surface. `ink-strong` for titles, selected labels and all text on family header fills. `ink-muted` for secondary text on chassis, pane, raised and well; on `selection` it becomes `ink`. `ink-disabled` carries no information.

**The accent.** `accent` (the diagrams' identity blue) is the only chrome accent: focus ring, active tab rule, links, hovered splitter. It never means good, running or done. Focus is a solid `focus` outline, 2px on bordered controls and 3px inset on rows, cells and tabs; it holds 3:1 on every surface and is never hidden under sticky chrome.

**Type.** DejaVu Sans for interface and diagrams, DejaVu Sans Mono for all evidence; both ship as font files. Weights are 400 and 700 only. App chrome runs `type-kicker` 11 · `type-ui` 12 · `type-body` 13 · `type-pane-title` 15 · `type-section` 20, and nothing in the app is larger. Diagram styles (`dia-*`) reproduce the generator sizes exactly. Addresses, digests, times, byte counts and job ids are always mono with tabular figures; addresses take `address`.

**Geometry.** App chrome is square (`radius-none`). Chips use `radius-chip`. Rounded corners belong to diagrams: `radius-band` for lane headers, `radius-card` for stage cards, ladders and panels, `radius-contract` for contract boxes, `radius-milestone` for capability cards.

**Spacing.** `space-1`…`space-9` (2, 4, 6, 8, 12, 14, 16, 24, 34px). Rows are dense: `space-2` vertical, `space-4` horizontal. Pane bodies pad `space-5`.

**Layout.** One `100dvh` shell. Navigator `navigator-w` 240px (180–480), evidence rail `evidence-w` 260px (200–480), activity dock `dock-h` 170px (100–420, max 46dvh). Splitters are a 1px `splitter-rule` with a 6px hit zone. Below `bp-compact` (1100px) rails shrink and keyboard hints hide. Below `bp-single-pane` (700px) one primary pane shows at a time, with 44px targets. See the Layout section.

**Motion.** 120ms surface flash after palette navigation and palette fade; 180ms dock open. Nothing else animates unless it replays an observed event. Freeze, step and history controls accompany every animated work view. Never auto-pan away from the operator. Under `prefers-reduced-motion` all motion is removed and the same change is shown as a static before/after.

## Linked views and accessibility

Every mention is a typed link with one activation grammar (Enter goes, Shift+Enter opens beside, Alt+↓ peeks, K keeps, Shift+F10 reveals in). Every pane follows the one selection or is explicitly **Held**. Detail opens in place, outcomes land on the row that invoked them, and the location lives in the URL so Back, Forward and shared links restore it exactly. See the Linked views section. Keyboard-only, screen-reader, low-vision and motor access are part of the same contract: see the Accessibility section.

## The six work families

The overview diagram and the app share one family palette. Each family has a deep `-fill` for headers and bands and a bright `-ink` for titles, tags, section labels and edges. Family color says *which work*; it never says whether the work passed.

| Family | Tokens | Where it appears |
|---|---|---|
| Identity | `lane-identity-fill` / `lane-identity-ink` | Stage 1; ladder A; identity edges |
| Source recovery | `lane-recovery-fill` / `lane-recovery-ink` | Main pipeline; stages 2–6 |
| Cross-build unification & export | `lane-unify-fill` / `lane-unify-ink` | Lanes A and B; ladders B–E; export band |
| Runtime reuse / learn | `lane-runtime-fill` / `lane-runtime-ink` | Lane C; ladder F; runtime capabilities |
| Verification & determinism | `lane-verify-fill` / `lane-verify-ink` | Stages 7–8; lane D |
| Intake / cross-cutting | `lane-intake-fill` / `lane-intake-ink` | Stage 0; lane E (distributed compute) |

`gate` (amber) marks gates and concurrency brackets. `lock` (salmon) marks one-owner serialization points.

## Content fundamentals

Plain, operational English from the operator's side. Sentence case; only `type-kicker` labels are uppercase. Short declarative sentences. Say what happened: "Job a3f9 finished (corpus.cross-place). Recipient verification: not run."

- Keep verbatim: "A finished job is not a match." · "Real C and a complete executable are separate facts." · "Select a function to decompile, rename, and match siblings." · "Missing evidence blocks its claim. An unhealthy resource blocks its dependents. Ready independent work continues."
- Claim boundaries use ≠: "candidate ≠ acceptance", "compile admits candidate, not replacement", "floor ≠ recovered C", "local zero ≠ full-image or behavior proof".
- Unknown is an answer: "Not measured", "Progress unknown", "Checking whether the operation completed". Never invent a percentage or ETA.
- Never write "Success!", "All done!", "Matched!", "≥90% recovered", "100% confidence", "works on all builds", "Project data combined." or an application-wide "Working…".
- No product, game, binary or company names in design artifacts, defaults or samples. Use generic slugs such as `build-a`, `win32-1.03`, `corpus-alpha`.
- Label reused evidence as reused and historical receipts as historical.
- The full rule set is in the Copy section.

## Iconography

There is no logo and no icon font. Set the name **AgentDecompile** in DejaVu Sans Bold. State glyphs are text characters in DejaVu Sans Mono from one fixed vocabulary (see State vocabularies). Diagram glyphs are drawn: the gate diamond, the lock, the concurrency bracket, arrows with explicit triangular heads, and numbered ladder circles (see DiagramLegend). Interface icons, where needed, are 1.5px line icons at 16px in `ink-muted`. No emoji anywhere.
