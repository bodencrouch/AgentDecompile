# CallHierarchy

Who calls this function and what it calls, as an APG treegrid read from the stored call-tree and reference operations. It follows the selection at depth 1, expands one level at a time on request up to depth 3, says "depth limit reached" and "not indexed here" in words, and can add one column per build with the locator words.

**Use it** as the **Calls** mode of the References section (References · Calls · Slots, an APG tablist in the section; Calls and Slots use manual activation because they read more). The section lives in the evidence rail when the rail is open; with the rail collapsed it sits beside the code when the Code Browser is at least 880px wide and under it otherwise; below 700px it is the References tab of the Code Browser's Code views tablist. It is never moved to the dock. Use GraphPane's Calls graph when a drawing helps; use this tree when the answer is a list of paths.

**Consumer provides** the root function and build; the direction; for each node read from the existing call-tree and reference operations (no new backend or index): the function (name, logical id, address), the call-site address in its parent, the number of call sites, how many callers or callees it has in the stored index, and whether its children are in the index; recursion (a node already on the path); unresolved indirect calls; the index's generation and read time; and, with the per-build column on, for each other build the locator word of the path's counterparts and whether the stored index on that build holds the path, or that the build is not open.

- Header: kicker "Calls", "Incoming to ‹function›" or "Outgoing from ‹function›", the build, the depth read and the direct count, the sync state ("Follows · as I move", or "Kept · not following selection" with a broken-chain icon and **Follow selection**) and **Keep** (`aria-pressed`, a constant name; Shift+K while focus is inside the section). A kept tree is a Kept card in the evidence rail (`keep=calls:…`), like a kept References section.
- Toolbar (APG Toolbar): **Direction** Incoming | Outgoing with counts, **Expand to depth** 1 | 2 | 3, **Per-build column** (`aria-pressed`). Pressed toggles are bold `ink-strong` with a 2px `tab-active-rule`, never color alone.
- Treegrid rows are 28px, `type-ui` 12 with mono names and addresses. The first column indents 20px per level and starts with an `ink-muted` twisty (▸ closed, ▾ open, `aria-hidden`). Columns: Caller (or Callee), Call site (`address` link), Calls (count), then one "‹build› path" column per build when the per-build column is on, divided by a 1px `line`.
- **Follows at depth 1 only.** As the selection moves (after the settle), the tree reads only the direct callers or callees. Deeper levels are read on request: → on a row, or Expand to depth 2 or 3, reads one level from the stored index. While that read is outstanding the row says "… Reading the stored index for N callers", carries `aria-busy`, and offers **Cancel**; a cancelled or superseded read never lands. No spinner. Under **Update panes: On Enter** the tree commits on Enter like every following pane, and says "Follows · on Enter".
- **Bounded, in words.** Depth is capped at 3. A node at the depth read that has children in the index says "depth limit reached · 4 callers" in italic `ink-muted` under its name. Beyond the per-level cap, a link row "7 more callers at depth 1" opens the full list filtered in place (`f=calls.dir:in`, `f=calls.depth:1`).
- **Honest rows.** A node whose children are not in the index opens to one row "∅ Callers of ‹function›: not indexed here" with why ("The stored index covers build-a gen 40; this function changed in gen 42"). A recursive call is "↺ recursive · already in the path, not expanded". A thunk or jump says "jump". An indirect call with no resolved target is the instruction text with "indirect · target unresolved; no target is guessed". The view never runs reference analysis, decompiles or opens a program.
- **Per-build column: the locator words, never "present".** Each cell uses the locator vocabulary plus "not loaded": "resolved" (the path's counterparts resolve on that build and its stored index holds the path), "absent" (no such path in that build's stored index, or no counterpart), "◌ unresolved", "⋯ ambiguous" and "⇉ contested" (the counterpart's locator word; its Peek lists the candidates, "no winner" for contested), "○ not loaded". Absent and unresolved are plain words, never links. Paths come only from accepted identity edges and recorded locators; a candidate edge says "candidate" in the cell's name. The caption under the grid says "path in stored index ≠ runtime reachability". Reachability never raises a fact.
- Footer: the source and read time ("From the stored xref index · build-a gen 42 · 13:58:07") and the key hints. A kept tree says when it was kept and whether its index changed since ("◷ Basis changed since kept · Refresh").
- Stale responses never land: each lazy read carries the selection generation and the node; a late read for a closed node or an old root is dropped. A refresh of the same root keeps focus, open nodes and scroll.
- Both surfaces read the same index and render the same rows; the static 8080 surface may render the tree as nested link lists with expand links and the same words.

**Linking**

- **Publishes:** the primary location on Enter (Go, one history stop; focus lands on the Listing row at the function or call site, per the 35 link table). Keep publishes `keep=calls:88@build-a~gen42` (replaceState). Direction, depth and the per-build column are view state of the section (`f=xref.mode:calls`, `f=calls.dir:…`, `f=calls.depth:…`, replaceState), never history stops.
- **Follows:** the primary selection (function and build) after the settle, at depth 1, until kept; commit-on-Enter under Update panes: On Enter. Keepable as a card, not holdable (sections are kept, never held).
- **Targets rendered:** function → the Code Browser at the function · call site → the Listing at that call, same build · "N more" → the full list filtered in place · per-build words are text, not links, because reachability is not a location. Link names read "Symbol Actor::Spawn, build-a" and "Address 0041f11c, build-a".
- **Peek source:** Alt+↓ reads the peek cache for the function or call site and, for a per-build word, the counterpart's stored locator row and ladder run. Shift+K inside a Peek keeps it. Nothing is fetched and no reference analysis runs.
- **Absent copy:** "not indexed here" · "no callers in the index" · "depth limit reached · N callers" · "recursive · already in the path, not expanded" · "indirect · target unresolved; no target is guessed" · per build: "absent", "unresolved", "ambiguous", "contested · no winner", "not loaded".
- **Target-size exception:** none; rows are 28px and toolbar controls 24px; 44px below 700px, and with a coarse pointer each row has one 44px row-menu button carrying the link menu.

**Keyboard**

- APG Treegrid with one tab stop and row focus first. Moving is focus movement, never a Go: ↓/↑ move between rows; → opens a closed row (reading its children from the index), or on an open row moves into its cells; ← closes an open row, or on a closed row moves to its parent, or from a cell moves back toward the row. Home/End go to the first or last row; Ctrl+Home/Ctrl+End likewise across the whole tree; PageUp/PageDown move a viewport.
- Enter on a row goes to the function; Enter on the call-site cell goes to the call site (focus moves to that Listing row). Shift+Enter opens beside (a Held pane); Alt+↓ peeks; Shift+F10 opens the one link menu (Open · Open beside · Peek; Reveal in Code Browser, Compare, Navigator; Copy link · Copy address).
- Composite-scope keys, only while focus is inside the grid, remappable and off under the `off` profile (WCAG 2.1.4): `i` and `o` switch direction, and `*` opens every sibling of the focused row within the depth cap. The toolbar buttons are the other path.
- Esc follows the one order in `keymap.json` `escapeOrder`; while a lazy read is outstanding, Cancel on the row stops it.
- The toolbar precedes the grid in Tab order.

**Accessibility**

- `role="treegrid"` with `aria-readonly="true"`, named for its content ("Incoming calls to ResourceRef::Resolve, build-a, depth 1, with call paths on build-b, build-c and build-d") and described by the "path in stored index ≠ runtime reachability" caption. Rows carry `aria-level`, `aria-setsize`, `aria-posinset` and, when they have children, `aria-expanded`.
- A row reads as one sentence: "Actor::Spawn, level 2, depth limit reached, 4 callers, call site 0041f11c, 1 call, build-b resolved, build-c not loaded, build-d absent". Twisties and glyphs are `aria-hidden` beside their words.
- The direct count is announced once in the polite region when the root or direction changes ("Incoming calls to ResourceRef::Resolve on build-a: 12 direct callers"); opening a node relies on `aria-expanded` and announces nothing else. Lazy reads never announce.
- WCAG 3.2.1 and 3.2.2: focus and toolbar changes never navigate; only Enter goes.
- Sticky headers get `scroll-padding` so the focused row is never hidden (WCAG 2.4.11). Forced colors keep the 3px inset focus and map dividers to `CanvasText`.

**Removes switching** (counts from the plan ledger):

- J09 follow a cross-reference and return: 4 → 0, credited to References in place (U177); the call-tree dialog goes.
- J16 explore the call graph and read code of nodes: 3 → 0, credited to U173 (the Graph beside the code); this tree is the list form of the same walk.
- J15 diagnose a decompile artifact: 6 → 4 (U173); callers are read beside the decompile.

**Parity extensions (2026-09-29)**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): G07, G13.

- **Filters (G07).** A filter row above the tree: a name filter (matches as the tree's typeahead does, but hides non-matching branches and says "12 hidden"), **Hide thunks** (a thunk collapses into its target with "via thunk"), **Collapse duplicates** (a callee reached twice under one parent shows once with "2 call sites"), and the depth selector (1, 2 or 3, the existing limit). Filters are per viewer and apply to every build column alike; recursion and "not indexed here" markers are never hidden.
- **Common callers (G13).** A multi-root mode: with several functions in the checked set or the active worklist, **Common callers of N functions** reads `get-call-graph` in `common_callers` mode on the inspected build and lists functions that call every root, with the call sites per root. A root absent on that build is named ("Archive::OpenMember is absent on build-d; common callers of the other 2"). The roots are frozen when the mode opens, and the header lists them as links.
- Both are read-only and per build. The preview is unchanged; the additions are a filter row and a mode in the Calls header.
