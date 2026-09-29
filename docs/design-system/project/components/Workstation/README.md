# Workstation

The whole shell composed from the system: a banner header with the one workflow control, session tabs, a separate Workspaces tablist, the NavigationBar, the navigator with the single Functions list, the Code Browser with its Views toolbar, the evidence rail, the work view, the activity dock and the status line. Each is a named landmark or region.

**Use it** as the reference composition for both surfaces (the static 8080 workbench and the optional full workspace). They may differ in richness but not in regions, selection, location schema or semantics. Below 700px the same regions show one at a time; NarrowFlow owns that layout and this README does not restate it.

**Consumer provides** the active project and related-build scope, the session tabs, the primary location (entity, inspected build, address) and the parsed URL, the function working set, evidence for the selection, counterparts and pipeline position for the CounterpartStrip and PipelineBreadcrumb, live activity, and the viewer's durable layout and View settings.

- **Grid from tokens.** The body grid is `var(--navigator-w) 1px minmax(0,1fr) 1px var(--evidence-w)`, and the dock row is `var(--dock-h)`. Splitter keys, drag, the pane-header size menu and LayoutPresets write those custom properties from durable layout state, per viewer, never from fixed pixel widths. Bounds come from the size tokens (`navigator-min`…`rail-max`, `evidence-min`…`rail-max`, `dock-min`…`dock-max`, max 46dvh).
- **Header** (`header`, the banner): name, the active project as the page's h1 with its kind chip and related-build scope, **Go to anything** (Ctrl/Cmd+P), **Commands** (Ctrl/Cmd+K), the WorkflowControl, and Help as the last item.
- **Two separate tablists**: "Sessions" (SessionTab) and "Workspaces" (Code Browser · Compare · Recovery · Evidence). Each tablist has exactly one selected tab. Session tabs use manual activation; workspace and dock tabs activate automatically because their panels are cached.
- **NavigationBar** under the Workspaces tablist: Back, Forward and the Recent menu, go to anything, breadcrumbs with sibling menus, **Update panes: As I move / On Enter**, Layout, Reload and Copy link.
- **Views toolbar** in the Code Browser: Listing, Decompile, Hex and Graph are `aria-pressed` toggles (`views=`), at most two center panes plus the HexStrip. Two panes sit side by side when the Code Browser is at least 2 × `split-min-w` wide, stacked below that. Strings, Imports, Exports, Sections, Symbols and Bookmarks are navigator scopes. References (with Calls and Slots modes) and Outline live in the evidence rail. Program Info is the build crumb's Peek and the rail's build header. Matching is the CounterpartStrip. There is no analysis tablist and no "More…" select.
- Under the Views toolbar: the **CounterpartStrip** line (every build's counterpart with locator glyph, word and edge word) and the compact **PipelineBreadcrumb** line.
- Listing and Decompile own the center and share one reflected cursor (Linked views, Reflection). There is exactly one Functions surface.
- **Evidence rail** sections are APG disclosures (an h3 holding a button), in this order: Kept · Pipeline · Why this name · Facts · References (with Calls and Slots) · Outline · Counterparts · Cross-match summary · Recovery · Timeline. Collapsed state is per viewer, in durable workspace state. **Expand all** and **Collapse all** are in the rail header menu and the palette. Corpus sections are headed "For ResourceRef::Resolve · build-b" and end with Show all (`panel=`). Sections are kept as cards, never held.
- **Collapse strips.** A collapsed navigator, rail or dock leaves a 24px disclosure button with a stable name, "Navigator", "Evidence" or "Activity", with `aria-expanded`, `aria-controls` and `aria-keyshortcuts` ("Control+B", "Control+Alt+B", "Control+J"; Meta on macOS). Collapsing the region that holds focus moves focus to its strip. Strips are hidden below 700px.
- **Splitters** are real separators (`role="separator"` with `aria-valuenow/min/max`, `aria-valuetext` and `aria-controls`) with a bordered 3:1 grip in `splitter-grip`. Arrows move `splitter-step` (16px) and Shift+arrows 64px; Home and End go to the minimum and maximum (APG); Enter collapses and restores; clicking the grip toggles collapse. **Reset** is in each pane header's size menu (an APG Menu Button: Narrow, Default, Wide, Collapse, Reset). Nothing requires dragging (2.5.7).
- **Dock**: Activity · Recovery · Logs · Jobs · Problems as a tablist, plus two region toggles.
  - **Selection only** is one dock-level `aria-pressed` toggle with a stable name and state words beside it ("On · ResourceRef::Resolve · build-a"). It applies to Jobs, Problems and Logs with ProblemsList's semantics: the entity across builds, or the build when the selection is build-scoped. While it is on, the FilterChip "Selection only: ‹entity› · ‹build› ×" shows (`f=scope:selection`); ProblemsList's own checkbox reflects the same filter. Logs are filtered by job (the logs of jobs whose records name the target), never by searching log text.
  - **Freeze updates** is per region (WCAG 2.2.2) and reads "Frozen at 14:02 · 7 events since". Actions from frozen rows act on the current record.
  - Ctrl/Cmd+J only shows or hides the dock. "Go to last announcement" (`g j`, palette) focuses the row of the last announced transition.
  - The dock is a grid row, never an overlay. There are no toasts.
- **Work view**: no pane follows active work. Its header chip reads "Job a3f9 is at ‹node› · Go"; Go is an explicit link.
- **View settings** is one per-viewer group in the View menu: Density, Increase contrast, Reduce motion, Screen-reader verbosity, Advance to Analyze after a pick, Brush on hover and Peek on hover. It is stored in durable workspace state beside the keymap diff, never in the URL or browser storage. Density is the only appearance choice; the others are adaptations, not themes.
- The preview uses generic sample data; never ship product or binary names in defaults.

**Linking**

- **Publishes:** `project` and `session` (session tabs), `ws` (Workspaces tablist), `views` (Views toolbar), `dock` (dock tabs) and `panel` (full corpus views). Its composed owners publish `entity`, `build` and `addr` (Functions grid, Listing cursor, matrices), `hold` (Open beside: at most two held center panes) and `keep` (Kept cards). On the static 8080 surface without split panes, Open beside reads "Open beside (new window)". pushState on Go, a workspace switch, a build switch and opening or closing a `cmp` pair; replaceState for cursor moves, typed filters, `views`, `dock`, `hold` and `keep`.
- **Follows:** the whole location schema. Every history stop restores workspace, views, split, viewport and the focused element; Back and Forward never open, close or re-point holds. Following panes settle after `settle-delay`; the NavigationBar's Update panes control switches them to commit-on-Enter. The shell itself is not holdable.
- **Targets rendered:** every region renders its components' targets per the typed-link table: address and symbol → Code Browser · logical id → Compare · counterpart → Code Browser for that build · fact → the receipt card in the rail · job → the dock Jobs record · basis → the ProvenanceStamp detail · pipeline node → the PipelineMap. The status line's basis links to its detail; the work view's chip links to the job's node.
- **Peek source:** each component's own cached evidence; the shell adds none.
- **Absent copy:** an unbound or empty build is a StateNotice naming the program and cause, following the dead-end rule · "Not loaded. Open to read it." in the rail · "unresolved" and "absent" as plain words in the CounterpartStrip.
- **Target-size exception:** the splitter's 6px `splitter-hit` zone is below 24px and relies on the WCAG 2.5.8 Equivalent exception: the splitter keys, the pane-header size menu, the collapse strips and the View menu reach every size. Every other control is 24px or more; 44px below 700px and with a coarse pointer.

**Keyboard**

- Global, always with a modifier: Ctrl/Cmd+P go to anything, Ctrl/Cmd+K commands, Ctrl/Cmd+G go to address, Alt+←/→ back and forward, F6 / Shift+F6 cycle regions in visual order with focus memory, Ctrl/Cmd+B navigator, Ctrl/Cmd+Alt+B evidence rail, Ctrl/Cmd+J dock, Alt+PageDown/PageUp next or previous build with a counterpart, F8 / Shift+F8 the active worklist. Where the platform takes a key (`keymap.json` `platformCautions`), the `g` leader, the palette and the menus reach the same command.
- Skip links (first in Tab order): Skip to Functions, Listing, Evidence, Activity.
- Splitters: arrows 16px, Shift 64px, Home/End minimum and maximum, Enter collapses or restores.
- Layout presets: `g` then 1…5 in any list, grid or tree; also the View menu and the palette.
- The link grammar (Enter, Shift+Enter, Alt+↓, Shift+F10, Ctrl/Cmd+Enter; Shift+K inside a Peek or card) is the same in every region. Esc follows the one Esc order in the Keymap section.

**Accessibility**

- Landmarks: `header` (banner) with Help last; navigation "Project"; the one `main`, labelled by the workspace name only; complementary "Evidence"; regions "Work view", "Activity" and "Status" (the status line is not live).
- Headings: h1 the active project; h2 each region; h3 each rail section.
- The Views toolbar is an APG Toolbar (one tab stop, `aria-pressed`); the Workspaces and Sessions tablists are APG Tabs, each with one selected tab. Focus returns to the invoker, never to `body`.
- One polite status region and one assertive alert region per page.
- Sequences such as "g then 1" go in `aria-describedby` text, never in `aria-keyshortcuts`.

**Removes switching:** the analysis tablist and its "More…" select, the separate Xrefs and Matching tabs, full-page corpus routes, and Tab travel between regions. The ledger credits each journey to the unit that owns its component (for example J09 to U177, J10 and J16 to U173, J23 to U176, J37 to U191, J38 to U188); the shell claims none itself.
