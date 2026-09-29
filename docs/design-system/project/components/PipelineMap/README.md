# PipelineMap

The recovery overview diagram as live navigation: stages 0–8 with their gates, lanes A–E under the concurrency bracket, the five locks, the resolution ladders and the export row, where every node is a link to the filtered live view it summarizes.

**Use it** as the home of the Recovery workspace and as the target of `~node` go-to and `node=` deep links. It keeps the overview diagram's names, order and family colors, and the node ids of pipeline-model.json, drawn at the app type scale.

**Consumer provides** for each node, by pipeline-model.json id: the counts per fact axis with their state words, the gate text and how many are waiting at it, each lock's access state and owner, each lane's ownership and liveness, each ladder's terminal outcome counts, each export's publication state and basis, and which node holds the current selection.

- It is HTML navigation, not a picture and not buttons: a `<nav>` of nested ordered lists (rows, then nodes), every node an `<a href>` whose link carries `node=<id>`. No node has a verb: no Run, Start, Retry or Pause.
- Node ids come from pipeline-model.json: `stage-0`…`stage-8`; `gate-0`, `gate-1`, `gate-3`…`gate-8` (stage 2 has no gate and says "No gate"); `lane-A`…`lane-E`; `ladder-A`…`ladder-F`; `lock-1`…`lock-5`; `export-hookpack`, `export-lua`, `export-headers`, `export-readiness`, `export-divergence`, `export-receipts`, `export-projects`. Nested ids (`lane-X-card-N`, `ladder-X-N`) are reached from a node's Peek and from deep links, not drawn as nodes.
- Counts are per fact axis, each a glyph + number + word under the axis name ("Compilation: ✓ 1,204 passed · ✕ 38 failed · ○ 912 not run"). Axes are never summed, and there is no percentage, bar, ratio or ETA. Stage 8 shows C+floor and max-C as separate axes.
- Gates: the `gate` diamond, "Gate N:" with the model's gate text, and "◷ N waiting at gate" (or "none waiting").
- Lanes stack under a `gate`-amber bracket that is also written out: "run concurrently with stages 1–8, where ownership permits". Each lane has a 4px family rule, its connects line in italic `ink-muted`, and its counts. Lanes C and E are dashed and say "separately owned"; they show liveness words only (last event, workers, leases) and are never controlled from here.
- Locks: the lock glyph in `lock`, the model's lock text, and ResourceState access words: ● owned with the owner job and managed or external, ○ free, ⊠ quarantined. A lease countdown is never shown.
- Ladders: family rule, method count, and named terminal outcomes in bold `fact-failed` ("— 14 unresolved", "⇉ 2 contested"). "Refuse, never zero" where it applies.
- Exports: `gate`-outlined cards with publication words: "current · basis …", "◷ stale · basis changed …", "○ not run".
- The node that holds the current selection has `aria-current="step"`, the selection shape (`selection` fill plus 3px `accent` bar) and the words "Selection here: ‹entity›".
- A visible legend on the same view spells out every glyph, the gate diamond and the dashed "separately owned" frame.
- Motion: a count changes in place when its receipt arrives. Nothing pulses, flows or spins.
- Layout by container width: all nine stages in one row at 1180px or more, five per row with → between neighbours at 700px or more, and one vertical list in dependency order below 700px, with 44px targets below the 700px viewport breakpoint. All text uses `type-kicker` 11 and `type-ui` 12, never the `dia-*` sizes.
- Both surfaces render the same list from the same node counts; the static 8080 surface may omit the family rules, never the words.

**Keyboard**

- One tab stop. Tab lands on the node that holds the current selection, or on `stage-0`. Focus then roves:
- ←/→ follow dependencies from the model's edges. Along the main row that is stage → its gate → next stage. On a lane, ← goes to what it consumes or depends on and → to what it feeds, produces or is consumed by, taking the first in model order. On locks, ladders and exports, ←/→ move to the previous or next node in the row.
- ↑/↓ move across rows: main row, then lanes A to E one per row, then locks, ladders and exports, landing on the nearest column.
- Home/End go to the first or last node in the row; Ctrl+Home and Ctrl+End go to `stage-0` and the last export.
- Enter follows the link and opens the filtered live view in place (for example the Functions list filtered to "waiting at gate 4", a lane's activity or a lock's owner record) and pushes history. Browser modifiers keep their meaning.
- Alt+↓ opens a Peek of the node: its gate, counts per axis, the oldest waiting age (StarvationMeter) and owners.
- Typeahead on a stage number or lane letter works only while focus is inside the map.

**Accessibility**

- Browse mode reads it as an outline: a heading per row, ordered lists and links. The roving tabindex only shortens the Tab sequence; every node stays in the accessibility tree.
- Each link reads as a sentence, and counts are words. Glyphs are `aria-hidden`. The nav's `aria-describedby` points at the legend.
- Family, gate, lock and ownership are written as words as well as drawn.
- WCAG 3.2.1: moving focus across nodes never filters or navigates; only Enter does.
- WCAG 4.1.3: counts are not announced on poll. A gate transition of the selected entity is announced once in the polite region.
- Forced colors map frames and the bracket to `CanvasText` and the selection to `Highlight`.

**Removes switching:** the static overview image, the Recovery ladders page and hand-built dock filters. The operator reads the pipeline and opens the filtered live view from the same place.
