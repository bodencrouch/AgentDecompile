# PipelineMap

The recovery overview diagram as live navigation: stages 0–8 with their gates, lanes A–E under the concurrency bracket, the five locks, the resolution ladders and the export row. Every node is a link to the live view it summarizes.

**Use it** as the full corpus view `panel=pipeline` (the home of the Recovery workspace), as a band in the Triage layout, and as the target of `~node` go-to and `node=` deep links. It keeps the overview diagram's names, order and family colors, and the node ids of `pipeline-model.json`, drawn at the app type scale.

**Consumer provides** for each node, by `pipeline-model.json` id: the counts per fact axis with their state words, the gate text and how many are waiting at it with the oldest age, each lock's access state and owner (a job, or an external process with its identity as reported), each lane's ownership and liveness, each ladder's terminal outcome counts, each export's publication state and basis, which node holds the current selection, and the revision of the served model.

- It is HTML navigation, not a picture and not buttons: a `<nav>` of nested ordered lists (rows, then nodes). Every node is an `<a href>` of the form `?project=…&node=‹id›`. A node link resolves against the active project and never opens one. No node has a verb: no Run, Start, Retry or Pause.
- **Node ids come only from `pipeline-model.json`**: `stage-0`…`stage-8`; `gate-0`, `gate-1`, `gate-3`…`gate-8` (stage 2 has no gate and says "No gate"); `lane-A`…`lane-E`; `ladder-A`…`ladder-F`; `lock-1`…`lock-5`; `export-hookpack`, `export-lua`, `export-headers`, `export-readiness`, `export-divergence`, `export-receipts`, `export-projects`. Nested ids (`lane-X-card-N`, `ladder-X-N`) are reached from a node's Peek and from deep links, not drawn as nodes.
- **Where a node goes.** Enter on a stage, gate, lane, ladder or export goes to its filtered live view in place (the Functions list filtered to "waiting at gate 4" with `f=node:gate-4`, a lane's activity, a ladder's runs) and pushes one stop. Enter on a **lock** pushes one stop to `dock=jobs&f=resource:‹key›` with the OwnershipPanel expanded; the primary selection does not move. Applying `f=node:‹id›` shows the FilterChip "Under gate-4 ×" on the host list.
- **Connects.** Producers and consumers are written once, as a static "Connects:" line taken from the model's `connects` text, and are the node link's `aria-describedby`. They are never a live region.
- Counts are per fact axis, each a glyph + number + word under the axis name ("Compilation: ✓ 1,204 passed · ✕ 38 failed · ○ 912 not run"). Axes are never summed, and there is no percentage, bar, ratio or ETA. Stage 8 shows C+floor and max-C as separate axes.
- Gates: the `gate` diamond, "Gate N:" with the model's gate text, and "◇ N waiting at gate" (or "none waiting"). ◇ always means waiting at a gate; ◷ always means stale.
- Lanes stack under a `gate`-amber bracket that is also written out: "run concurrently with stages 1–8, where ownership permits". Each lane has a 4px family rule, its Connects line in italic `ink-muted`, and its counts. Lanes C and E are dashed and say "separately owned"; they show liveness words only (last event, workers, leases) and are never controlled from here.
- Locks: the lock glyph in `lock`, the model's lock text, and ResourceState access words: ● owned with the owner job and managed or external, ○ free, ⊠ quarantined. An external owner reads "external · no job" with the process identity as reported. A lease countdown is never shown.
- Ladders: family rule, method count, and named terminal outcomes in bold `fact-failed` ("— 14 unresolved", "⇉ 2 contested"). "Refuse, never zero" where it applies.
- Exports: `gate`-outlined cards with publication words: "current · basis …", "◷ stale · basis changed …", "○ not run".
- The node that holds the current selection has `aria-current="step"`, a 2px `ink-strong` frame and the words "Selection here: ‹entity›". The accent is not a status.
- **Only stated edges are drawn** and followed by the arrow keys. Edges the model marks as interpretations wait for review, and any crosswalk from lifecycle states is shown only inside Explain, labelled "(interpretation)".
- A visible legend on the same view spells out every glyph, the gate diamond and the dashed "separately owned" frame, and is the nav's `aria-describedby`.
- Motion: a count changes in place when its receipt arrives. Nothing pulses, flows or spins.
- Layout by container width: all nine stages in one row at 1180px or more, five per row with → between neighbours at 700px or more, and one vertical list in dependency order below 700px. All text uses `type-kicker` 11 and `type-ui` 12, never the `dia-*` sizes.
- **Coarse pointer.** Each node has one 44px row-menu button carrying the one link menu (Peek, Open beside, Copy link, and Reveal in). There is no long-press.
- Both surfaces render the same list from the same node counts; the static 8080 surface may omit the family rules, never the words.

**Linking**

- **Publishes:** `node=` on Enter (one history stop), with the node's filter (`f=node:‹id›`, or `dock=jobs&f=resource:‹key›` for a lock). It never moves the primary location. Keep in a node's Peek publishes `keep=node:‹id›`.
- **Follows:** nothing on focus. The counts follow the active project's projection, and the current-node mark follows the primary selection. Not holdable; a node's Peek can be kept as a card.
- **Targets rendered:** pipeline node → its filtered live view · lock → the dock Jobs record filtered by resource · the owner job → the dock Jobs record · the selection's entity in "Selection here" → the Code Browser. Link names read "Gate 4, compile admits candidate, not replacement, 64 waiting, oldest 2 h 10 min".
- **Peek source:** the served `pipeline-model.json` (title, gate text, "From the pipeline design · model rev ‹8 hex›", "Design description ≠ this item's evidence") and the node's cached counts, owners and the StarvationMeter's oldest wait, whose age words are links. Nothing is fetched.
- **Absent copy:** "No gate" (stage 2) · "none waiting" · "external · no job" · "not run" · named terminal outcomes as words, never a link to a guess.
- **Target-size exception:** none. Nodes are whole-card targets; 44px below 700px and with a coarse pointer.

**Keyboard**

- One tab stop. Tab lands on the node that holds the current selection, or on `stage-0`. Focus then roves:
  - ←/→ follow the model's stated edges. Along the main row that is stage → its gate → next stage. On a lane, ← goes to what it consumes and → to what it feeds, taking the first in model order. On locks, ladders and exports, ←/→ move to the previous or next node in the row.
  - ↑/↓ move across rows: main row, then lanes A to E one per row, then locks, ladders and exports, landing on the nearest column.
  - Home/End go to the first or last node in the row; Ctrl+Home and Ctrl+End go to `stage-0` and the last export.
- Moving focus is focus movement, never a Go. Enter goes; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the one link menu. Browser modifiers keep their meaning.
- Typeahead on a stage number or lane letter works only while focus is inside the map. The map binds no single-letter commands, so typeahead needs no `/` prefix; `g` stays the leader.

**Accessibility**

- Browse mode reads it as an outline: a heading per row, ordered lists and links. The roving tabindex only shortens the Tab sequence; every node stays in the accessibility tree.
- Each link reads as a sentence, and counts are words. Glyphs are `aria-hidden`. The nav's `aria-describedby` points at the legend; each node's points at its Connects line.
- Family, gate, lock and ownership are written as words as well as drawn.
- WCAG 3.2.1: moving focus across nodes never filters or navigates; only Enter does.
- WCAG 4.1.3: counts are never announced. A gate transition of the selected entity is announced once in the polite region.
- Forced colors map frames and the bracket to `CanvasText` and the current node to `Highlight`.

**Removes switching:** J28 (act on starvation) goes from 4 switches to 1: the oldest wait is a link in a node's Peek, credited to U181. The map also serves J05 through `~gate-4` (credited to U178) and J03 (credited to U180).
