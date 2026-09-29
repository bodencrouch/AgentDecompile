# CallHierarchy

Who calls this function and what it calls, as a tree that expands lazily from the stored xref index to depth 1–3 (default 2), says "depth limit reached" and "not indexed here" in words, and can add one column per build: "present", "absent", "unresolved" or "not loaded".

**Use it** as the **Calls** mode of the References section in the evidence rail (beside XrefPanel's Grid, Slots and Outline modes), movable to the dock with "Move to dock / Move to rail". It follows the selection until kept. Use GraphPane's Calls graph when a drawing helps; use this tree when the answer is a list of paths.

**Consumer provides** the root function and build; the direction; the depth; for each node from the stored xref index: the function (name, logical id, address), the call-site address in its parent, the number of call sites, how many callers or callees it has in the index, and whether its children are in the index; recursion (a node already on the path); unresolved indirect calls; the index's generation and read time; and, with the per-build column on, for each other build whether the same call path exists through accepted identity edges and resolved locators, is absent, has an unresolved counterpart, or cannot be read because the build is not open.

- Header: kicker "Calls", "Incoming to ‹function›" or "Outgoing from ‹function›", the build, depth and direct count, the sync state ("Follows selection", or "Kept · not following selection" with a broken-chain icon and **Follow selection**) and **Keep**.
- Toolbar (APG Toolbar): **Direction** Incoming | Outgoing with counts, **Depth** 1 | 2 | 3, **Per-build column** (`aria-pressed`). Pressed toggles are bold `ink-strong` with a 2px `tab-active-rule`, never color alone.
- Treegrid rows are 28px, `type-ui` 12 with mono names and addresses. The first column indents 20px per level and starts with a `ink-muted` twisty (▸ closed, ▾ open, `aria-hidden`). Columns: Caller (or Callee), Call site (`address` link), Calls (count), then one "‹build› path" column per build when the per-build column is on, divided by a 1px `line`.
- **Lazy, from the index only.** Opening a node reads its children from the stored xref index; while that read is outstanding the row says "… Reading the stored index for N callers" and has `aria-busy`. No spinner. A node whose children are not in the index opens to one row "∅ Callers of ‹function›: not indexed here" with why ("The stored index covers build-a gen 40; this function changed in gen 42"). The view never runs reference analysis, decompiles or opens a program.
- **Bounded, in words.** A node at the chosen depth that has children in the index says "depth limit reached · 4 callers" in italic `ink-muted` under its name; raising Depth or pressing → on it goes one level further, up to 3. Beyond the first N rows at a level, a link row "7 more callers at depth 1" opens the full list filtered in place (`f=calls.dir:in`).
- **Honest rows.** A recursive call is "↺ recursive · already in the path, not expanded". A thunk or jump says "jump". An indirect call with no resolved target is the instruction text with "indirect · target unresolved; no target is guessed". Absent, unresolved and not-loaded are words, never an empty cell.
- **Per-build column**: "present" (`ink`), "absent" (italic `ink-muted`), "◌ unresolved" and "○ not loaded" (`fact-unknown` glyph plus word). Paths come only from accepted identity edges and resolved locators; candidate, ambiguous and contested counterparts read "unresolved" with their locator word in the row's Peek, never "present". A caption under the grid says "Reachability, not proof." Reachability never raises a fact.
- Footer: the source and read time ("From the stored xref index · build-a gen 42 · 13:58:07") and the key hints. A kept tree says when it was kept and whether its index changed since ("◷ Index changed since kept · Refresh").
- Stale responses never land: each lazy read carries the selection generation and the node; a late read for a closed node or an old root is dropped. A refresh of the same root keeps focus, open nodes and scroll.
- Both surfaces read the same index and render the same rows; the static 8080 surface may render the tree as nested lists with the same words.

**Linking**

- Publishes nothing on focus; Enter publishes the selection (Go).
- Follows the primary selection (function and build) unless kept.
- Renders function links (Code Browser at the function), call-site address links (the Listing at that call), and the "N more" filter link. Alt+↓ peeks the function or call site from cache; Shift+Enter opens it beside; K keeps the tree; Shift+F10 reveals in Code Browser, Graph (Calls), Compare and Copy link.
- Absent: "not indexed here", "no callers in the index", "absent", "unresolved" and "not loaded" as words.

**Keyboard**

- APG Treegrid with one tab stop and row focus first: ↓/↑ move between rows; → opens a closed row (reading its children from the index), or on an open row moves into its cells; ← closes an open row, or on a closed row moves to its parent, or from a cell moves back toward the row. Home/End go to the first or last row; Ctrl+Home/Ctrl+End likewise across the whole tree; PageUp/PageDown move a viewport.
- Enter on a row goes to the function; Enter on the call-site cell goes to the call site (focus moves to that Listing row). Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the row menu.
- While focus is inside the grid only, `i` and `o` switch direction (as in XrefPanel) and `*` opens every sibling of the focused row within the depth limit. They are remappable and can be turned off (WCAG 2.1.4).
- The toolbar precedes the grid in Tab order.

**Accessibility**

- `role="treegrid"` with `aria-readonly="true"`, named for its content ("Incoming calls to ResourceRef::Resolve, build-a, depth 2, with call paths on build-b, build-c and build-d") and described by the "Reachability, not proof" caption. Rows carry `aria-level`, `aria-setsize`, `aria-posinset` and, when they have children, `aria-expanded`.
- A row reads as one sentence: "Actor::Spawn, level 2, depth limit reached, 4 callers, call site 0041f11c, 1 call, build-b present, build-c not loaded, build-d absent". Twisties and glyphs are `aria-hidden` beside their words.
- The direct count is announced once in the polite region when the root, direction or depth changes ("Incoming calls to ResourceRef::Resolve on build-a, depth 2: 12 direct callers"); opening a node relies on `aria-expanded` and announces nothing else. Lazy reads never announce.
- WCAG 3.2.1 and 3.2.2: focus and toolbar changes never navigate; only Enter goes.
- Rows are 28px and toolbar controls 24px; 44px below 700px, where the tree becomes a Navigate rail view. Sticky headers get `scroll-padding` so the focused row is never hidden (WCAG 2.4.11).
- Forced colors keep the 3px inset focus and map dividers to `CanvasText`.

**Removes switching:** J09, following a reference from code and returning, loses the call-tree dialog (4 → 1 with XrefPanel). J16 drops from 3 switches per node to 1 because the callers or callees sit beside the code in the rail, and J15, diagnosing a decompile artifact, reads callers beside the decompile (part of 6 → 2). The per-build column answers "does this path exist on the other builds?" without the Compare workspace.
