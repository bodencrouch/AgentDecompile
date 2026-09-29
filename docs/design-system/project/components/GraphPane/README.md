# GraphPane

The function graph beside the code: basic blocks of the current function, or the calls around a function, drawn as focusable links whose arrow keys follow edges, with zoom and pan buttons, bounded depth that says "truncated" in words, a list form (APG tree) that is always one toggle away, and a rooted Calls graph that works as a navigator: Enter on a node is Go, and the graph keeps its root, zoom and scroll while the selection stays inside it.

**Use it** as the Graph view of the Code Browser, beside Listing and Decompile (`views=…,graph`), never as a separate page. **Blocks** shows the control-flow graph of the function holding the cursor. **Calls** shows callers or callees around one root function to a bounded depth; walk it with the arrow keys (focus movement, not a Go) and press Enter on a node to read that function's code in the primary views. **Hold this pane** when the graph should stop following altogether.

**Consumer provides** for Blocks: the function, build and the blocks from existing analysis (start address, instruction count, role entry or exit, up to two key lines such as calls and the terminator) and typed edges (taken, fall-through, unconditional, back edge); which block holds the cursor; and whether the function exceeds the drawing bound. For Calls: the root, direction and depth, and nodes and edges from the stored call index with each node's callee count and whether it was cut by the depth or breadth bound. In both: layout positions, the analysis generation and read time, and the not-loaded state for builds that are not open.

- Pane: `pane` card with the standard header (kicker "Graph", the mode and function, the build and counts, sync state ("Follows · on Enter"), **Graph | List** toggle, **Hold this pane**) and an APG Toolbar: **Blocks | Calls**, **Callers | Callees** and **Depth 1 | 2 | 3** for Calls, **Zoom out · 100% · Zoom in · Fit**, **Pan ← ↑ ↓ →**, **Center on cursor**. Nothing requires dragging (WCAG 2.5.7); the canvas also scrolls in both directions in its own `well` viewport.
- Nodes are real `<a href>` links over the location schema, absolutely placed on a canvas: `pane` fill, 1px `line-control` frame, `type-code-small` mono. The address is the link text (`address`, dotted underline); mnemonics `ink-strong`, symbol operands `lane-identity-ink`, counts and roles ("entry", "exit", "root") in `ink-muted`. A Calls node shows the function name in bold `ink-strong` over its address.
- Edges are drawn in an `aria-hidden` SVG under the nodes, 1.5px `ink-muted` with explicit triangular heads: solid for taken and unconditional, a thinner 1px solid line labelled "ft" for fall-through (dashes mean hypothesis only), dotted for back edges (loops). Conditional and loop edges carry the words "taken" and "loop" on the drawing, and every edge is written in its nodes' accessible names. A legend under the canvas names each stroke. Never color alone.
- The block holding the cursor (in a Calls graph, the node holding the primary selection; in a held graph, the pane's own cursor) uses the selection shape: `selection` fill, 3px `accent` bar and the word "cursor" or "selection" in the node. Focus is a separate 2px `focus` outline; hover is `row-hover-bg`.
- **Bounded, and says so.** Calls draws at most the chosen depth (1–3, default 2) and three children per node. Nodes at the depth limit say "depth limit · N" in italic `ink-muted`; cut children become a solid-framed "+N more · not drawn" button; the footer sums it: "Truncated: depth limit reached on 3 functions; 4 callees of the root not drawn". Blocks draws at most a bounded number of blocks nearest the cursor for very large functions and says "Truncated · 412 blocks; drawing the 40 nearest the cursor". The list form always has everything the index holds.
- **List form** (Graph | List): the same nodes as an APG tree of links in the Navigation Treeview pattern (`a role="treeitem"` with `aria-owns` groups), one row per node under its parent, with its address, counts and the same words ("depth limit reached · 3 callees", "no callees in the index", "selection here" or, when held, "this pane’s cursor"). A node reached twice is listed under each parent; a recursion is "recursive, listed above" and not expanded. Tree items follow the composite-widget rule: no underline, 28px rows, 3px inset focus.
- **Following** (default; 35 Follow and hold): an expensive pane, so across functions it commits on Enter, and its header says "Follows · on Enter". When the selection moves to another function, the old graph stays dimmed (ink-muted text, no frame change) under "Shows ResourceRef::Resolve; selection is now FUN_0041c880 · Enter to load" with a **Load** button; late responses for a superseded selection are dropped. Inside the same function the cursor block updates at once; no fetch is needed. On a history restore it shows "Not loaded · Enter to load" until Enter.
- **The Calls graph is a Following pane with its root kept.** Moving within it with the arrow keys is focus movement, not a Go. Enter on a node is an ordinary Go: the primary selection moves there with one history stop, the code views follow, and focus lands on the Listing row per the 35 link table. While the selection stays inside the drawn graph, the graph keeps its root, depth, open nodes, zoom, scroll and focused node and only moves the selection shape; it never re-centers. When the selection leaves the drawn graph, the graph says "Selection is outside this graph · Re-root here" and re-roots only on **Re-root here**.
- **Held** follows the linked-views contract exactly. The constant-named toggle **Hold this pane** (`aria-pressed`) freezes the graph to its root × build with a basis token; the state words become a Held chip, "Held · Actor::LoadFromTemplate @ build-a · 6 min", in a 2px `ink-strong` frame, with "Held · read 13:52 · basis … · unchanged" (or "◷ Basis changed since held · Refresh"; "Basis at hold time not recorded"). Inside a held graph, Enter moves that pane's own cursor and its own Back/Forward, never the primary location. **Make primary** (Enter on the Held chip, or the button) is the only way it moves the one selection: to the pane's cursor, with one stop, releasing the hold. The pane stays open and becomes Following; a held pane never closes by itself. It never refreshes by itself and never switches its build.
- Read-only by construction: blocks come from existing analysis and calls from the stored call index. Drawing, zooming, holding and expanding "+N more" never start analysis, decompile, open a program or run reference analysis. A build that is not open says "○ Not loaded · Enter to load".
- Motion: none. Zoom and pan are instant; the 120ms landing flash of the code views is theirs, not the graph's. Under reduced motion nothing changes.
- Both surfaces draw from the same nodes, edges and layout; the static 8080 surface may render only the list form plus a static SVG, never dropping the words.

**Linking**

- **Publishes:** following: the primary location (`entity`, `build`, `addr`) on Enter, one history stop (focus lands on the Listing row); `views` when the pane is shown or hidden (replaceState). Held: `hold=graph:…@build[~basis]` (replaceState); Make primary pushes one stop.
- **Follows:** commit-on-Enter (an expensive pane); inside the same function the cursor block follows at once; the Calls graph keeps its root while the selection stays inside it and re-roots only on Re-root here. Holdable with **Hold this pane**; a held graph obeys the HeldPane rules.
- **Targets rendered:** block and function nodes → the Code Browser at that build and address (focus lands on the Listing row per the 35 link table; in a held graph, the pane's own cursor) · the selection link in the header · the held basis → the ProvenanceStamp detail. The link menu is the one flat menu of 35 (Open · Open beside · Peek; Reveal in Code Browser, Compare, Navigator; Copy link · Copy address); nodes have no Edit group. Link names start with the visible address or function: "0041b240, 3 instructions, ends jne 0041b216 …".
- **Peek source:** Alt+↓ on a node reads the peek cache: a block's cached instructions, a function's facts and counterparts; Shift+K inside the Peek keeps it. Nothing is fetched and nothing is decompiled.
- **Absent copy:** "no callees in the index" · "not indexed here" (beyond the stored call index) · "depth limit · N" and "+N more · not drawn" · "Truncated · 412 blocks" · "Selection is outside this graph · Re-root here" · "Not loaded · Enter to load" (a build that is not open).
- **Target-size exception:** none; nodes are at least 40px tall and 120px wide, toolbar buttons 24px, tree rows 28px; 44px below 700px, and with a coarse pointer each list-form row has one 44px row-menu button carrying the link menu.

**Keyboard**

- The canvas is one tab stop with roving focus; Tab lands on the cursor or selection node.
- ↓ follows an outgoing edge to a successor (callee); ↑ follows an incoming edge back to a predecessor (caller), preferring the edge you arrived by. When a node has several, ←/→ move among the alternatives of that edge set and the move is announced ("successor 2 of 2, taken"). Home goes to the entry block or root, End to the exit block or last node. These are focus moves; they never move the selection.
- Enter goes: in a following graph the primary selection moves and focus lands on the Listing row, as for any address link; the graph keeps its own focused node, so returning to the graph resumes the walk at the same node. In a held graph Enter moves the pane's own cursor and focus stays in the pane. Shift+Enter opens beside. Alt+↓ peeks. Shift+F10 opens the link menu. `r` moves focus to the Listing row at the block's first instruction (35 Reflection).
- Composite-scope keys, only while focus is inside this pane, remappable and off under the `off` profile (WCAG 2.1.4): `+`, `-` and `0` zoom in, zoom out and fit; in Calls, `i` and `o` switch to callers and callees; in the list form, `*` expands every sibling within the depth limit. The toolbar buttons are the other path. The viewport scrolls to keep the focused node visible (operator-initiated); it never pans on its own.
- In the list form: APG Tree keys (↑/↓, → opens or moves to the first child, ← closes or moves to the parent, Home/End; typeahead on names starts with `/` into a visible filter field); Enter goes; Enter on "+N more" lists them from the index.
- Esc follows the one order in `keymap.json` `escapeOrder`; in a held graph it returns focus to the primary pane.
- Ctrl/Cmd+Enter on a node keeps the browser's new tab.

**Accessibility**

- The canvas is `role="group"` named "Control-flow graph of ResourceRef::Resolve, build-a, 5 blocks, 7 edges" and described by the legend. Each node's name starts with its visible address or function and adds its role, size, terminator and edges in words: "0041b240, 3 instructions, ends jne 0041b216. Successors: 0041b216 taken, loop back edge; 0041b246 fall-through." The SVG is `aria-hidden`.
- The list form is the structural equivalent and is always available by toggle; a screen-reader user can stay in it. Toggling keeps the focused node.
- `aria-current="true"` marks the cursor block, the selection node, or a held pane's own cursor, with the word visible too ("cursor", "selection", "this pane's cursor"). A Go from the graph announces once: "Selection: Archive::OpenMember, build-a. The graph keeps its root." Moving focus announces nothing beyond the node name (WCAG 3.2.1).
- Truncation is text in the node, the footer and the tree, never only a frame. Node text truncated by the node width is complete in the accessible name, the list form and the Peek.
- Targets: nodes are at least 40×120px; toolbar buttons 24px; 44px below 700px, where the pane opens in the list form by default.
- Forced colors: frames, edges, heads and labels map to `CanvasText`; the cursor node maps to `Highlight`/`HighlightText`.

**Removes switching** (counts from the plan ledger):

- J16 explore the call graph and read code of nodes along the way: 3 → 0 when Graph and Decompile are the two panes (2 per node below 700px), credited to U173. The graph sits beside the code and keeps its root while each Enter shows the node's code.
- J15 diagnose a decompile artifact: 6 → 4 with the Code Browser composite (U173); the graph removes its graph-tab round trips.

**Parity extensions (2026-09-29)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): D07, G02, G08, G09, G10, P10)

- A data-flow mode (D07).
- Vertex grouping, path highlight from/to, and selection from paths and blocks (G02).
- Bounded program-scope graphs: block flow, code flow, calls and data references (G08). "Reuse or append" is per-viewer state.
- A data-reference graph from a data item (G09).
- A block-model selector: basic, isolated entry, multiple entry, partitioned and overlapped (P10).
- "Export graph…" opens ExportDialog (G10).
- Everything is read-only and per build.

**Parity extensions, round 3 (2026-09-29)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): G03, G04, G11)

*Layouts, satellite view and saved view state (G03).*

- **Layout** is a menu button in the toolbar (`graph.layout`, no default key). Every layout draws the same nodes and edges from the same read; only positions change, and the list form does not change at all.
  - **Layered** (the default above): rows by flow depth.
  - **Nested code**: blocks placed by the nesting of the decompiled function, with a dominated block below and right of the block that decides it, and default flow aligned left. Edges leaving a block carry the statement word ("if", "if/else", "while", "switch case 3") from the decompile structure. It needs this function's cached decompile on this build. Without one it says "Nested code needs a decompile of ResourceRef::Resolve on build-a · Not decompiled in this session · Enter to decompile" and keeps the current layout; the graph never decompiles. Options: **Route edges around blocks** and **Quiet return edges**, which draws return flow at 1px and adds the word "return", never a lighter color alone.
  - **Flow chart** (each parent centered over its children, orthogonal edges) and **Flow chart, left** (each parent over its leftmost child).
  - For Calls and the program-scope graphs: **Tree**, **Radial** and **Layered, fewest crossings**. Force-directed layouts are not offered, because their positions change on every run.
  - **Relayout** re-runs the chosen layout; **Reset view** clears moved nodes, groups and hidden filters and re-runs it. Nothing relayouts on its own: when a job changes the blocks, the pane says "◷ Graph predates job a3f9 · Refresh keeps positions · Relayout".
- **Satellite view** (`graph.satellite`, no default key; a toggle, `aria-pressed`): an overview of the whole drawing in a corner of the viewport, with a 2px `ink-strong` frame marking what the viewport shows. Clicking or dragging in it scrolls the viewport; it never moves focus or the selection. **Corner** (top left, top right, bottom left, bottom right) and **Hide** are in its own menu. It is a pointer convenience and is `aria-hidden`: Fit, Center on cursor, the pan buttons and the list form reach everything it does (WCAG 2.5.7). Below 700px it is hidden.
- **Saved view state.** Per viewer, in durable workspace state (never the URL, never program data), keyed by entity, build, graph kind and layout: the layout and its options, zoom, scroll, moved nodes, groups, hidden filters, and the satellite's corner and visibility. **On open** has three values: **Fit the graph**, **Zoom to the cursor block** or **Restore my view** (default). A restored view says "Restored your view of ResourceRef::Resolve on build-a · saved 13:52 · Reset view". View state for build-a is never applied to build-c, whose blocks are different code.

*Vertex and edge filters and selection popups (G11).*

- **Filter…** (`graph.filter`, no default key) opens a non-modal popup listing the vertex kinds and edge kinds found in this graph, each a checkbox with its count: vertex kinds entry, exit, body, contains a call, group (and for Calls: function, thunk, external, depth limit); edge kinds taken, fall-through, unconditional, back edge (and for Calls: call, tail call). Kinds come from the read's own properties; none is guessed. Unchecking hides.
- **Hidden says so.** The footer reads "4 blocks and 6 edges hidden by filter · Show all", each neighbor's name adds "1 successor hidden", and the list form keeps hidden nodes in a collapsed group, "Hidden by filter (4)". A filter never removes anything from a count; counts read "5 blocks · 4 hidden".
- **Checked nodes.** Space or `x` checks the focused node (a graph-local checked set, like list rows); Enter still goes. The link menu's **Graph selection** group then offers:
  - **Check node** and **Uncheck node**; **Invert checked**; **Clear checked**;
  - **Grow from sources** (adds nodes with edges into the checked set), **Grow to targets** (adds nodes the checked set reaches directly) and **Grow to whole component**;
  - **Hide checked** and **Hide unchecked** (the same hidden filter, listed in the footer);
  - **Show checked as a new graph**, which opens a Held graph pane of just those nodes with their edges, basis-stamped, read-only;
  - **Group checked** and **Ungroup** (row G02; groups are per-viewer view state);
  - **Make address selection**: the checked blocks' addresses become an address selection in the Listing on this build (G02).
- **On an edge**, reached from a node's name ("successor 2 of 2, taken"), the menu offers **Go to edge source** and **Go to edge target** (focus moves; the selection does not) and **Check edge**, which checks both ends.
- **No hover popups.** Peek is Alt+↓ on a node, and hover brushing follows the View setting "Brush on hover" (off by default), so Ghidra's Display Popup Windows toggle is not needed.
- **Accessibility.** The Filter popup is an APG dialog (non-modal) with one fieldset per kind group; counts are in each checkbox name ("fall-through, 3 edges, shown"). Hiding and grouping are announced once ("4 blocks hidden by filter"). Checked nodes carry `aria-selected="true"` and the visible word "checked".

*No in-vertex editing (G04, decided).* Ghidra lets the listing inside a vertex be edited in place. Here graph nodes are links, and no node is an editor.

- **Why.** A node is a typed link: Enter goes, Shift+Enter opens beside and Shift+F10 opens the one link menu. An editor inside it would give one target two meanings of Enter and break the link table. Node text is also truncated to the node width, so an edit could act on text the operator cannot fully see, and held graphs are read-only by contract.
- **Where edits happen.** In the Listing, DecompileView and the other editors, with their catalog Edit groups, InlineRename and confirm tiers. From a node, `r` moves focus to the Listing row at the block's first instruction, where F2 and the Edit group act on that build.
- **After an edit.** The graph shows the change after the terminal result: an affected node carries "✎ job a3f9" until the next navigation, and the header says "◷ Graph predates job a3f9 · Refresh" when the blocks changed.
- The link menu keeps no Edit group; this is a decision, not a gap.

*Keyboard (round 3).* Keymap ids, composite scope, no default keys: `graph.layout`, `graph.satellite`, `graph.filter`. Space and `x` check a node (`list.check`). Everything else is in the link menu.

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- ≠ auto relayout (chip removed): "Per-viewer view state · nothing relayouts or decompiles on its own"
- ≠ other builds (chip removed): "This view is per viewer and never applies to another build."
- read ∅ guess: "Kinds come from the read; none is guessed."
- ≠ editor · r Listing (chip removed; the footer keeps the r keycap): "Edits happen in the Listing: r moves focus to 0041b240 there. Nodes are links, not editors."
- Not loaded title (shortened): "Not loaded · Enter to load"; the render now shows "Not loaded · build-c" with one action, Load build-c.
