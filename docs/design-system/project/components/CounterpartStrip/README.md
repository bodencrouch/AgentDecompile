# CounterpartStrip

One strip per composite that shows the current logical entity's counterpart on every build: build name, address link, locator glyph and word, divergence class and identity-edge state. Each counterpart is a typed link, and switching to it keeps the entity and maps the cursor through recorded anchors only.

**Use it** once, above the Code Browser beside the PipelineBreadcrumb, and in its compact form in the evidence rail's entity header. Never one strip per well. It shows one entity, the primary selection, and follows it. It replaces opening the Compare workspace to learn where else the entity exists.

**Consumer provides** the logical entity (id and name) and the build count. For every build in the related-build scope, in corpus order: the build name, and either the counterpart address or the absence; the locator status and its word (resolved(member), pinned(member) with `module_rva` or `section_offset`, degraded, ambiguous with its candidates, unresolved, contested with both addresses); the divergence class (1↔1, 1↔N, ≠); the identity-edge state (accepted, candidate, rejected, unresolved or none); whether that counterpart is open beside; and the recorded anchor pairs between the inspected build and each counterpart (the same anchor read SplitCompare aligns on). It also provides the source and read time of the stored cross-build index.

- **Every build appears, in corpus order, including the inspected one.** The inspected build keeps its place, so cells never reorder when the build switches. It takes the selection shape: `selection` fill, a 3px `accent` bar, `aria-current="location"` and the words "inspected build".
- **Each cell has two lines.** Line 1: the LocatorGlyph (`ink-strong` ●, `address` ◎, `fact-stale` ◑ and ⋯, `fact-unknown` ◌, `fact-failed` ⇉), the build name underlined as the link text, and the address in `address` mono. Line 2, at 11px in `ink-muted`: the locator word, the divergence notation in bold mono `ink-strong`, and the IdentityEdge mini line with its word. Cells are 36px tall on `pane` with a 1px `line` frame.
- **Position-keeping build switch.** One rule for the strip, the breadcrumb build ▾, go to and Alt+PageDown/PageUp (Workstation layout). The entity is kept. The cursor maps only through recorded anchor pairs: on an anchor it lands on the partner; between anchors it lands on the nearest preceding anchor's partner and says "nearest anchor above 0041b213; rows between anchors are not paired". It never interpolates by offset or order. The announcement names the basis: "Inspecting build-c, 0041c7a2, nearest anchor to 0041b213 (rare ref; identity edge candidate)". With no anchors: "No instruction mapping for build-c; showing function start".
- **Candidate edges go**, labelled "candidate" in the cell, the announcement and the landing header. Accepted edges say "accepted". No counterpart link exists without a recorded edge.
- **Absent and unresolved never jump.** An absent cell has a dashed `line-control` frame on `chassis`, no address, the italic word "absent", the locator word and "no edge". It is a button that opens the reason (a Peek: ladder outcome, members tried, a link to the ladder receipt). Enter on it stays: "build-d: no counterpart (unresolved); staying on build-a", and the Peek offers **Open build-d**, which opens build-d's Functions list and carries no address.
- **Ambiguous and contested never pick.** The cell says "2 candidates" or "2 addresses" and is an APG Menu Button whose menu lists every candidate as a link with its channel and margin, then **Compare candidates** (the Compare workspace with two held panes, each "candidate 1 of 2 · contested · no winner") and **Open ladder run**. The footer says "Opening one does not accept it." A contested build never opens two held panes in the Code Browser.
- **Program not open:** the cell still shows its locator; Enter or its Peek says "Not loaded. Open to read it." with an explicit Open. **Another project:** 35's cross-project StateNotice (Switch armed and confirm-gated, Stay).
- **Checked set.** Never carried across a build switch. The cell's `aria-describedby` says "clears 4 checked rows on build-a" before activation, and the polite region confirms after. There is no ConfirmDialog.
- **Open beside** marks the cell with a `beside` tag while that counterpart is shown in SplitCompare as a Held pane.
- **No identity** is an answer: "∅ FUN_0041c880 has no identity. No counterpart is claimed on any build." Nothing is inferred from names or addresses.
- **Follows, never fetches.** The strip reads the stored cross-build index and receipts only. When the selection moves, the previous cells dim (`opacity-disabled`, `inert`) behind "… Loading counterparts of ‹name›" after the 200ms settle. A late response for an old selection is dropped.
- **Layout.** A leading label (`type-kicker` "Counterparts" over the logical-id link "#88 · 4 builds" and the index read time "13:41" in mono `ink-muted`), then the cells. The row wraps and never scrolls sideways, down to 320px. The full workspace may fold trailing cells into "+N more" when the row is full; its label counts what it hides by state ("+2: 1 resolved, 1 absent"), so an absent build is never hidden silently.
- **Below 700px** the strip stays visible as one wrapping line. When it would exceed two lines, it collapses to the summary ("4 builds: 2 resolved, 1 pinned, 1 absent") and a 44px **Counterparts (3) ▾** disclosure (`aria-expanded`, `aria-controls`). The breadcrumb Build menu is the navigation path there, with the same summary, but it is not the only place counterparts are read.
- **Both surfaces** render the same cells from the same index read. The static 8080 surface may omit the `beside` tag, but never an absent cell or a word.

**Linking**

- **Publishes:** Enter publishes a new `build` and `addr` with the same `entity` (one pushState stop, the build switch). Shift+Enter publishes `cmp` and a `hold` for the new Held pane (replaceState). Compare candidates publishes `ws=compare` with two `hold` entries.
- **Follows:** the primary location's `entity` after the settle, and marks `build` as current. Not holdable; the panes it opens are.
- **Targets rendered:** counterpart links (the Code Browser for that build, same entity, with the edge word; focus stays on the now-inspected cell) · the logical id (Compare with the CounterpartMatrix) · receipt and ladder links inside the Peek · candidate addresses in the candidate menu, marked "no winner" for contested.
- **Peek source:** Alt+↓ reads the stored locator row, ladder run and identity edge for that entity × build, and the first cached lines when the program is open; a counterpart Peek is anchor-only with "aligned ≠ equivalent". Nothing is matched or decompiled.
- **Absent copy:** "absent" (a button with the reason, never a link) · "build-d: no counterpart (unresolved); staying on build-a" · "2 candidates" · "contested · no winner" · "No instruction mapping for build-c; showing function start" · "Not loaded. Open to read it." · "∅ ‹name› has no identity. No counterpart is claimed on any build."
- **Target-size exception:** none; cells are at least 36px tall, and 44px below 700px, with a coarse pointer at any width.

**Keyboard**

- The cells form an APG Toolbar with one tab stop. Tab enters on the last focused cell, or on the inspected build. ←/→ move between cells, Home/End go to the first and last cell, and Tab leaves the strip. The logical-id link is a separate tab stop before the toolbar. Arrowing never switches the build (WCAG 3.2.1).
- **Enter** on a counterpart switches the inspected build by the position-keeping rule; focus stays on the now-inspected cell. From a code well (Alt+PageDown), focus stays on the mapped row. Enter on the inspected cell does nothing.
- **Alt+↓** peeks the counterpart read-only. On an absent cell it shows the reason.
- **Shift+Enter** opens the counterpart beside as a Held pane in SplitCompare. The primary selection and inspected build do not change.
- **Ctrl/Cmd+Enter** opens the counterpart's URL in a browser tab (links only). **Shift+F10** opens the one link menu (Open · Open beside · Peek; Reveal in Code Browser, Compare, Evidence; Copy link · Copy address).
- **Alt+PageDown / Alt+PageUp** (`build.next`, `build.prev`), anywhere in the center region, go to the next or previous build with a single-address counterpart (resolved, pinned or degraded) and an accepted or candidate edge. They skip absent, unresolved, ambiguous and contested builds and announce the skipped builds by state; those stay visible in the strip.
- The `g` leader's `g c` moves focus into the strip at the inspected cell.
- On an ambiguous or contested cell, Enter, Space or ↓ opens the candidate menu (APG Menu Button). Inside it, ↑/↓ move, Enter goes, Shift+Enter opens beside, Alt+↓ peeks and Esc returns to the cell (Esc order in `keymap.json`).

**Accessibility**

- `role="toolbar"` labelled "Counterparts" and described by a hidden sentence naming the keys and the checked-set clearing. Each cell's accessible name is a full sentence with type, target and state: "Counterpart on build-c, address 0041c7a2, pinned, module_rva, non-portable; diverged; identity edge candidate". Glyphs and the edge line are `aria-hidden`, and their words are visible.
- The inspected cell carries `aria-current="location"`. An absent cell is a button that opens a Peek; it carries `aria-expanded` and `aria-controls` only while that Peek is open. Multi-candidate cells are APG Menu Buttons with `aria-haspopup="menu"` and `aria-expanded`.
- WCAG 3.2.2: Enter, Alt+PageDown and the build menu state the switch and any checked-set clearing in `aria-describedby` before activation.
- WCAG 4.1.3: one polite message per switch, naming its mapping basis; "Loading counterparts of ‹name›" is sent once. A refresh of the same entity announces nothing.
- WCAG 1.4.10: the strip reflows to 320px by wrapping cells; below 700px the disclosure keeps it to two lines.
- Identifiers carry `translate="no"`. The source line gives its read time in words ("Read from the stored cross-build index at 13:41").

**Removes switching** (counts from the plan ledger):

- J01 inspect a function on build A, then its counterparts on B–D, and return: 5 → 1 at ≥700px, 2 below, 0 when read by Peek alone where cached (U175, with SplitCompare's derived pane).
- J26 switch the inspected build while keeping the entity: 3 → 1 (U175); the instruction position is kept where anchors exist, otherwise the function start is stated.
