# CounterpartMatrix

One logical entity across every build: counterparts, divergence class, identity edge, locator status and facts, with unmatched builds left visibly absent. Builds are the rows.

**Use it** as the Compare workspace's primary view for one entity (a logical-id link lands here, focus on the entity's row, 35 typed links). The CounterpartStrip is a separate component that shows the same counterparts as one line above the Code Browser.

**Consumer provides** the logical entity, and per build: the concrete address or the absence, divergence class (1↔1, 1↔N, ≠), identity-edge state, locator status and word (with candidates for ambiguous and contested), facts, and the recorded anchor pairs used to keep the cursor across a build switch.

- **Rows are builds**, in corpus order; the inspected build's row carries the selection shape. Bytes, ABI, addresses and edits stay per build.
- An absent counterpart is written "absent" in italics; a blank cell is never filled with a guess. Every counterpart link shows its edge word (accepted or candidate).
- **Row grammar** (a row-selection grid). ↑/↓ move between builds; ←/→ move across the row's cells to reach its links. Arrows never switch the build.
  - **Enter** on a build row switches the inspected build and keeps the entity, mapping the cursor through recorded anchors only (the CounterpartStrip rule: on an anchor, its partner; between anchors, the nearest preceding anchor's partner, stated; never interpolated). Focus stays on the row. The switch is described before activation, including any checked-set clearing ("clears 4 checked rows on build-a"), and announced once after.
  - On an absent or unresolved row, Enter explains the absence and stays: "build-d: no counterpart (absent); staying on build-a".
  - On an ambiguous or contested row, Enter opens the candidate menu (every candidate as a link, then Compare candidates and Open ladder run; "Opening one does not accept it."). A contested row never opens two held panes here.
  - **Shift+Enter** opens that build beside as a Held pane (SplitCompare). **Alt+↓** peeks the row (ladder run, edge evidence or facts).
- **Build-switch copy:** "No instruction mapping for build-c; showing function start" when no anchors exist; "build-d: no counterpart (absent); staying on build-a" when there is no counterpart. Nothing is guessed. Alt+PageDown / Alt+PageUp step to the next or previous build with a single-address counterpart and an accepted or candidate edge, from anywhere in the center region.
- The fact column is the FactBadge strip: one ≥24px button that opens a Peek.
- Read-only by construction: it reads stored identity edges, locator rows, ladder runs and fact rows; nothing is matched or decompiled.

**Linking**

- **Publishes:** `build` (and the mapped `addr`) on Enter, one history stop, entity kept · `cmp` and a `hold` on Shift+Enter (Open beside creates a Held pane) · `ws=compare` with two `hold` entries from Compare candidates.
- **Follows:** `entity` (the one logical entity) and marks `build` (the inspected build's row); commit-on-Enter (a matrix: arrows move focus only). The matrix is not holdable; its Open-beside panes are.
- **Targets rendered:** address → the Code Browser for that build, same entity (counterpart), with its edge word · identity → the IdentityEdge evidence and its receipt card · facts → a facts Peek whose facts link to receipts · ambiguous and contested → the candidate menu, candidates marked "no winner" for contested, and the ladder run's receipt (`receipt=‹id›` with `project`, `entity` and `build`). Row names read "build-c: 00082f40, 1↔N, candidate, facts: compilation not run".
- **Peek source:** the stored identity edges, locator rows, ladder runs and fact rows for this entity; nothing is matched or decompiled.
- **Absent copy:** "absent" (italic, plain) · "unresolved" (plain) · "diverged — counterpart structurally different, possibly inlined/split" · "Not loaded. Open build-c to read it." · "No instruction mapping for build-c; showing function start" · "build-d: no counterpart (absent); staying on build-a" · "Opening one does not accept it."
- **Target-size exception:** none; cells are at least 24px (28px rows). With a coarse pointer each row adds one 44px row-menu button carrying the link menu.

**Keyboard**

- A row-selection APG Grid with one tab stop: ↑/↓ rows (builds), ←/→ cells within the row, Home/End the first and last cell in the row, Ctrl+Home/Ctrl+End the first and last row. Enter on the row as above; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the one link menu. Alt+PageDown / Alt+PageUp step builds. Esc follows `keymap.json` `escapeOrder`.

**Accessibility**

- `role="grid"` named "Counterparts of ‹entity›"; builds are row headers (`th scope="row"`). The inspected build's row has `aria-selected="true"`. A build switch is described in the row's `aria-describedby` before activation and announced once, politely, after ("Inspecting build-c, 00082f46, partner of anchor 0041b216 (callee order; identity edge candidate)"), never while arrowing.

**Removes switching** (counts from the plan ledger): J01 counterparts of a function on other builds, 5 → 1, and J26 switching the inspected build while keeping the entity, 3 → 1, are credited to U175 (CounterpartStrip and the derived split); this matrix is the Compare workspace's full form of the same rows.
