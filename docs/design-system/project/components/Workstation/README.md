# Workstation

The whole shell composed from the system: a banner header with the one workflow control, session tabs, a separate Workspaces tablist, the NavigationBar, the navigator with the single Functions list, the Code Browser with its Views toolbar, the evidence rail, the work view, the activity dock and the status line, each a named landmark or region.

**Use it** as the reference composition for both surfaces (static 8080 workbench and the optional full workspace). They may differ in richness but not in regions, selection, location schema or semantics.

**Consumer provides** the active project and related-build scope, the session tabs, the primary location (entity, inspected build, address) and the parsed URL, the function working set, evidence for the selection, counterparts and pipeline position for the CounterpartStrip and PipelineBreadcrumb, and live activity.

- Regions follow the Layout section: navigator `navigator-w`, evidence `evidence-w` (shrinking to `navigator-min` and `evidence-min` below `bp-compact`), dock `dock-h`. The grid is built from those tokens, never fixed pixel widths.
- **Header** (`header`, the banner): name, the active project as the page's h1 with its kind chip and related-build scope, **Go to anything** (Ctrl/Cmd+P), **Commands** (Ctrl/Cmd+K), the WorkflowControl, and Help as the last item.
- **Two separate tablists**: "Sessions" (SessionTab) and "Workspaces" (Code Browser · Compare · Recovery · Evidence). No strip ever has two selected items.
- **Views toolbar** replaces the analysis tablist in the Code Browser: Listing, Decompile, Hex and Graph are `aria-pressed` toggles in any combination (`views=`). Listing and Decompile sit side by side at ≥1100px, stacked at 700–1099px, one at a time below 700px with "Show in other view". Strings, Imports, Exports and Sections are navigator scopes; References, Calls and Outline live in the evidence rail; Matching is the CounterpartStrip. There is no "More…" select.
- Under the view title: the **CounterpartStrip** line (every build's counterpart with locator glyph, word and edge word) and the **PipelineBreadcrumb** line (one crumb per stage for this entity on this build).
- Listing and Decompile own the center and share one reflected cursor. There is exactly one Functions surface.
- **Splitters** are real separators (`.ad-split-h`, `role="separator"` with `aria-valuenow/min/max` and `aria-controls`) with a 3:1 grip; clicking the grip collapses and restores, and the pane-header menu offers Narrow / Default / Wide / Collapse / Reset, so nothing requires dragging.
- **Dock**: Activity · Recovery · Logs · Jobs · Problems as a tablist, plus **Selection only** and **Freeze updates** toggles; "Frozen at 14:02 · 7 events since" when frozen. The dock is a grid row, never an overlay.
- Below 700px only one primary pane shows at a time; a rail bar tablist switches Navigate, Analyze, Inspect and Activity, keeping each pane's scroll and focused row. Enter or tap (never focus) advances from Navigate to Analyze.
- The preview uses generic sample data; never ship product or binary names in defaults.

**Linking**

- **Publishes:** `project` and `session` (session tabs), `ws` (Workspaces tablist), `views` (Views toolbar), `dock` (dock tabs) and `panel` (full corpus views); its composed owners publish `entity`, `build` and `addr` (Functions grid, Listing cursor, matrices) and `hold` (Open beside, at most two held centre panes; Kept cards are `keep=`). On the static 8080 surface without split panes, Open beside reads "Open beside (new window)". pushState on Go, workspace switch, build switch and split open; replaceState for cursor moves and typed filters.
- **Follows:** the whole location schema. Every history stop restores workspace, views, split, held panes, viewport and the focused element, and the landing is announced once. Following panes settle after `settle-delay`; the NavigationBar's Link panes toggle switches them to commit-on-Enter. The shell itself is not holdable.
- **Targets rendered:** every region renders its components' targets (Linked views table): address and symbol → Code Browser · logical id → Compare · counterpart → Code Browser for that build · fact → receipt card in the rail · job → dock Jobs record · basis → ProvenanceStamp detail · pipeline node → PipelineMap. The status line's basis links to its detail; the work view's "Work is at …" chip links to that entity and build.
- **Peek source:** each component's own cached evidence; the shell adds none.
- **Absent copy:** an unbound or empty build is a StateNotice naming the program and cause with one armed fix ("No function inventory in the corpus store for build-e. The Ghidra program is bound.") · "Not loaded. Open to read it." in the rail · "unresolved" and "absent" as plain words in the CounterpartStrip.
- **Target-size exception:** equivalent: splitters are 1px rules with a `splitter-hit` zone; the pane-header size menu and the View menu offer the same sizes and collapse (WCAG 2.5.8 equivalent, 2.5.7). Every other control is 24px or more, 44px below 700px.

**Keyboard**

- Global, always with a modifier: Ctrl/Cmd+P go to anything, Ctrl/Cmd+K commands, Ctrl/Cmd+G go to address, Alt+←/→ back and forward, F6 / Shift+F6 cycle regions in visual order with focus memory, Ctrl/Cmd+B navigator, Ctrl/Cmd+Alt+B evidence rail, Ctrl/Cmd+J dock, Alt+PageDown/PageUp next or previous build with a counterpart, F8 / Shift+F8 the active worklist.
- Skip links (first in Tab order): Skip to Functions, Listing, Evidence, Activity.
- Splitters: ←/→ move 16px, Shift 64px, Enter collapses or restores, Home resets.
- The link grammar (Enter, Shift+Enter, Alt+↓, Shift+F10, Ctrl/Cmd+Enter; Shift+K keeps inside a Peek or card) is the same in every region.

**Accessibility**

- Landmarks: `header` (banner), navigation "Project", the one `main` labelled by the workspace name, complementary "Evidence", region "Work view", region "Activity", region "Status" (not live). Headings: h1 the active project, h2 each region, h3 each rail section.
- The Views toolbar is an APG Toolbar (one tab stop, `aria-pressed`); the Workspaces and Sessions tablists are APG Tabs. Focus returns to the invoker, never to `body`.
- One polite status region and one assertive alert region per page.

**Removes switching:** the analysis tablist and its "More…" select, the separate Xrefs and Matching tabs, full-page corpus routes, and Tab travel between regions (J09, J10, J16, J23, J24, J37, J38).
