# GraphPane

The function graph beside the code: basic blocks of the current function, or the calls around a function, drawn as focusable links whose arrow keys follow edges, with zoom and pan buttons, bounded depth that says "truncated" in words, a list form (APG tree) that is always one toggle away, and a held form that works as a navigator.

**Use it** as the Graph view of the Code Browser, beside Listing and Decompile (`views=…,graph`), never as a separate page. **Blocks** shows the control-flow graph of the function holding the cursor. **Calls** shows callers or callees around one function to a bounded depth. Hold a Calls graph to explore a neighbourhood while reading each function's code in the primary views.

**Consumer provides** for Blocks: the function, build and the blocks from existing analysis (start address, instruction count, role entry or exit, up to two key lines such as calls and the terminator) and typed edges (taken, fall-through, unconditional, back edge); which block holds the cursor; and whether the function exceeds the drawing bound. For Calls: the root, direction and depth, and nodes and edges from the stored call index with each node's callee count and whether it was cut by the depth or breadth bound. In both: layout positions, the analysis generation and read time, and the not-loaded state for builds that are not open.

- Pane: `pane` card with the standard header (kicker "Graph", the mode and function, the build and counts, sync state, **Graph | List** toggle, **Hold**) and an APG Toolbar: **Blocks | Calls**, **Depth 1 | 2 | 3** for Calls, **Zoom out · 100% · Zoom in · Fit**, **Pan ← ↑ ↓ →**, **Center on cursor**. Nothing requires dragging (WCAG 2.5.7); the canvas also scrolls in both directions in its own `well` viewport.
- Nodes are real `<a href>` links over the location schema, absolutely placed on a canvas: `pane` fill, 1px `line-control` frame, `type-code-small` mono. The address is the link text (`address`, dotted underline); mnemonics `ink-strong`, symbol operands `lane-identity-ink`, counts and roles ("entry", "exit", "root") in `ink-muted`. A Calls node shows the function name in bold `ink-strong` over its address.
- Edges are drawn in an `aria-hidden` SVG under the nodes, 1.5px `ink-muted` with explicit triangular heads: solid for taken and unconditional, dashed for fall-through, dotted for back edges (loops). Conditional and loop edges carry the words "taken" and "loop" on the drawing, and every edge is written in its nodes' accessible names. A legend under the canvas names each stroke. Never color alone.
- The block holding the cursor (or, in a held graph, the node holding the primary selection) uses the selection shape: `selection` fill, 3px `accent` bar and the word "cursor" or "selection" in the node. Focus is a separate 2px `focus` outline; hover is `row-hover-bg`.
- **Bounded, and says so.** Calls draws at most the chosen depth (1–3, default 2) and three children per node. Nodes at the depth limit say "depth limit · N" in italic `ink-muted`; cut children become a dashed "+N more · not drawn" button; the footer sums it: "Truncated: depth limit reached on 3 functions; 4 callees of the root not drawn". Blocks draws at most a bounded number of blocks nearest the cursor for very large functions and says "Truncated · 412 blocks; drawing the 40 nearest the cursor". The list form always has everything the index holds.
- **List form** (Graph | List): the same nodes as an APG tree of links in the Navigation Treeview pattern (`a role="treeitem"` with `aria-owns` groups), one row per node under its parent, with its address, counts and the same words ("depth limit reached · 3 callees", "no callees in the index", "selection here"). A node reached twice is listed under each parent; a recursion is "↺ recursive, listed above" and not expanded. Tree items follow the composite-widget rule: no underline, 28px rows, 3px inset focus.
- **Following** (default): an expensive pane, so across functions it commits on Enter. When the selection moves to another function, the old graph stays with dashed node frames and a StateNotice "◷ Showing ResourceRef::Resolve · The selection moved to FUN_0041c880" with **Draw now**; late responses for a superseded function are dropped. Inside the same function the cursor block updates at once; no fetch is needed.
- **Held** (a navigator): a 2px `ink-strong` frame and the word **Held** with what it holds, its age and depth, its own Back and Forward, **Make primary** and **Release**. Activating a node moves the primary selection there (the code views follow) while the graph keeps its layout, zoom, scroll and focus: it never re-centers and never refreshes by itself. When its basis changes it says "◷ Basis changed since held · Refresh". It never switches its build silently.
- Read-only by construction: blocks come from existing analysis and calls from the stored call index. Drawing, zooming, holding and expanding "+N more" never start analysis, decompile, open a program or run reference analysis. A build that is not open says "○ Not loaded. Open to read it."
- Motion: none. Zoom and pan are instant; the 120ms landing flash of the code views is theirs, not the graph's. Under reduced motion nothing changes.
- Both surfaces draw from the same nodes, edges and layout; the static 8080 surface may render only the list form plus a static SVG, never dropping the words.

**Linking**

- Publishes the primary selection only on activation (Enter or click on a node); focus and hover publish nothing.
- Follows the primary location (function and cursor) unless held; held graphs follow nothing.
- Renders node links (address or function in the Code Browser on the graph's build), the selection link in a held header, and the StateNotice actions. Alt+↓ on a node peeks its block or function from cache (instructions, facts, counterparts); Shift+Enter opens it beside; K keeps the peek; Shift+F10 reveals in Code Browser, Compare, Navigator, Copy link.
- Absent: "no callees in the index", "not indexed here" (Calls beyond the stored index) and "Not loaded. Open to read it." as words; no guessed node or edge.

**Keyboard**

- The canvas is one tab stop with roving focus; Tab lands on the cursor or selection node.
- ↓ follows an outgoing edge to a successor (callee); ↑ follows an incoming edge back to a predecessor (caller), preferring the edge you arrived by. When a node has several, ←/→ move among the alternatives of that edge set and the move is announced ("successor 2 of 2, taken"). Home goes to the entry block or root, End to the exit block or last node.
- Enter goes (in a held graph: sets the primary selection and keeps focus on the node; F6 moves to the code). Shift+Enter opens beside. Alt+↓ peeks. Shift+F10 opens Reveal in.
- `+`, `-` and `0` zoom in, zoom out and fit while focus is inside the canvas only; they are remappable and can be turned off (WCAG 2.1.4). The viewport scrolls to keep the focused node visible (operator-initiated); it never pans on its own.
- In the list form: APG Tree keys (↑/↓, → opens or moves to the first child, ← closes or moves to the parent, Home/End, typeahead on names); Enter goes; Enter on "+N more" lists them from the index.
- Ctrl/Cmd+Enter on a node keeps the browser's new tab.

**Accessibility**

- The canvas is `role="group"` named "Control-flow graph of ResourceRef::Resolve, build-a, 5 blocks, 7 edges" and described by the legend. Each node's name starts with its visible address or function and adds its role, size, terminator and edges in words: "0041b240, 3 instructions, ends jne 0041b216. Successors: 0041b216 taken, loop back edge; 0041b246 fall-through." The SVG is `aria-hidden`.
- The list form is the structural equivalent and is always available by toggle; a screen-reader user can stay in it. Toggling keeps the focused node.
- `aria-current="true"` marks the cursor or selection node, with the word visible too. A held Enter announces once: "Selection: Archive::OpenMember, build-a. The held graph keeps its place." Moving focus announces nothing beyond the node name (WCAG 3.2.1).
- Truncation is text in the node, the footer and the tree, never only a dashed frame. Node text truncated by the node width is complete in the accessible name, the list form and the Peek.
- Targets: nodes are at least 40×120px; toolbar buttons 24px; 44px below 700px, where the pane opens in the list form by default.
- Forced colors: frames, edges, heads and labels map to `CanvasText`; the cursor node maps to `Highlight`/`HighlightText`.

**Removes switching:** J16, explore the call graph and read code of nodes along the way, goes from 3 switches per node (graph tab, code tab, back) to 0: the graph sits beside the code, and a held graph keeps its exploration while each Enter shows the node's code in the primary views. J15, diagnosing a decompile artifact, loses its graph-tab round trips (part of 6 → 2 with the Code Browser composite).
