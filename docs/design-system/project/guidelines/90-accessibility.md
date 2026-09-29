# Accessibility

Accessibility is part of the operating model, not a later pass. A keyboard-only, screen-reader, low-vision or motor-impaired operator must reach every capability the mouse user reaches, on both surfaces, with the same state vocabulary. Most of these rules also remove clicks for everyone.

## Foundations

- **Dark scheme is declared.** `.ad` sets `color-scheme: dark`, so native scrollbars, checkboxes and inputs render on Graphite.
- **Numbers line up.** `.ad` sets `font-variant-numeric: tabular-nums`; live counters never change width.
- **Identifiers are never translated or reordered.** Addresses, symbols, mnemonics, digests and action ids carry `translate="no"` and isolate their direction.
- **Hidden words.** `.sr-only` carries words that are visually implied by a glyph, a column or a legend.

## Selection, focus and links

- **Selection is a shape, not a color.** The one primary selection uses `selection` fill **plus** a 3px `accent` bar at the inline start. On the fill, `ink-muted` text is promoted to `ink` automatically, state words switch to `ink-strong`, and control borders (`line-control`, 2.37:1 there) are promoted to `ink-muted` (3.78:1). Glyphs keep their hue; a failed glyph uses `fact-failed-on-selection` (5.23:1), which is never used for a word. The fill alone is 1.6:1 against its surroundings; the bar and the promoted text carry the meaning.
- **Focus** is a solid `focus` outline: 2px at offset 0 on bordered controls, 3px inset (`focus-inset-w`) on rows, cells, tabs, in-row inputs and anything inside an overflow-clipped container, including token links in code wells (house rule from WCAG 2.4.13). Never a box-shadow ring. 3:1 or better on every surface including `selection`.
- **Focus is never hidden** (WCAG 2.4.11, aiming at 2.4.12 in Listing and the Functions grid): scroll containers set block-start `scroll-padding` to the sticky stack (`sticky-offset`: the sticky header and an armed ActionStrip, plus the Code Browser's composite header and the worklist stepper when shown) and inline-start padding to sticky row headers; focused rows scroll with `block: nearest` inside their own well; Peeks and menus flip so they never cover the focused item; the dock is a grid row, never an overlay.
- **Links look like links.** Anything that navigates (addresses, symbols, counterparts, job ids, receipt ids, logical ids, node ids) is `.ad-link`: its own color token plus a dotted underline at rest and a solid underline on hover and focus. Affordance never depends on color. Items inside composite widgets whose role already says they act (menu items, listbox options, tree items, grid rows) are exempt from the underline; inside a block link only the name is underlined. Inside code wells, token links show their underline on the current, hovered or focused line only, so dense code stays readable; their accessible names still say what they link to. Because an underline means a link there, reflection is the `raised` fill, a 3px `ink-muted` bar and "↔ line N", and Highlight all (`h`) is a 1px `ink-strong` box with its letter A–D and a count in words on its legend chip; neither is ever an underline (Linked views, Reflection).
- **The accent is not a status.** Fresh evidence, the current rail step, the running unit, the TaskLifecycle now-frame, the WorkTimeline cursor and primary buttons use `ink-strong` and a 2px frame, not the accent. A held pane uses the same 2px `ink-strong` frame (`held-frame`) plus a HELD tag that stays visible at every scroll position, and its grid is named with "held, as read ‹time›" ("Held listing, build-b, as read 13:54").

## Contrast

- Text: 4.5:1 minimum on its ground in every state, including the selected row. The token notes name the grounds each ink is safe on.
- Non-text: 3:1 for control boundaries (`line-control`), focus, glyph frames and any mark that carries meaning. `line` (1.5–1.7:1) is decorative only; interactive boundaries never rely on it. The splitter grip is a bordered element in `splitter-grip` (3.24:1 or better), never a gradient; the 6px hit zone relies on the 2.5.8 Equivalent exception (Targets, below).
- Data graphics: adjacent segments are separated by 2px `chassis` gaps and patterns, and every graphic has a text key with values.
- `prefers-contrast: more` (and the **Increase contrast** View setting, which is an adaptation, not a theme) raises `line` and `line-node` to `line-control`, `ink-muted` to `ink`, focus to 3px, the selection bar to 4px with a 1px `ink-strong` row outline, shows hover as an outline, and borders family and fault headers in `ink-strong`. The in-app setting applies every one of these rules. It only adds to the operating system's preference and never switches it off.
- `forced-colors: active`:
  - Selected and current items use `Highlight` and `HighlightText`; `SelectedItem` and `SelectedItemText` are an `@supports` enhancement only. Selected items set `forced-color-adjust: none` and paint every descendant in `HighlightText` on a transparent fill, because with the default adjustment the browser draws a `Canvas` backplate behind text, and `HighlightText` on `Canvas` disappears in the common high-contrast palettes. No author color survives inside a selected item; the glyph shape and the word carry state.
  - Only the selected row carries a 3px `HighlightText` border at the inline start, with its inline padding reduced by 3px. Unselected rows never get transparent borders, because forced colors paints them.
  - Focus is 2px `CanvasText` at offset 0 on bordered controls, and 3px inset elsewhere: `HighlightText` on selected rows, `CanvasText` otherwise.
  - Popups, menus, the palette and dialogs get a 1px `CanvasText` border. Links use `LinkText`, disabled items `GrayText`. Splitter grips are `CanvasText` borders.
  - Data graphics opt out of forced colors only where their text key carries the values.

## Structure

- **Headings**: h1 is the active project; h2 each region (Location and history, Navigator, the workspace name, Evidence, Work view, Dock); every region has one name, and no two landmarks or h2s share it; h3 each rail section and each code well. Screen-reader users jump by heading instead of clicking through regions.
- **Landmarks**: header = banner (menubar, project and scope, Commands, WorkflowControl, Help last); session tabs, workspace tabs and the NavigationBar = navigation "Location and history"; navigator = navigation "Project"; center = the one `main`, labelled by the workspace name only (Code Browser, Compare, Recovery or Corpus); evidence = complementary "Evidence"; work view = region "Work view"; dock = region "Dock"; status line = region "Status" (not live).
- **Bypass**: skip links to Location, Functions, Listing, Evidence and Dock. F6 / Shift+F6 cycle regions in visual order (header, location and history, navigator, center, evidence, work view, dock) and restore each region's last-focused element. Ctrl/Cmd+B toggles the navigator, Ctrl/Cmd+Alt+B the evidence rail, Ctrl/Cmd+J the dock; hiding the region that holds focus moves focus to its collapse strip.
- **Lists as lists**: lifecycle rails, stage rails, ladders and EvidenceRail are `<ol>` with `aria-current="step"` on the current state; readouts (liveness, execution, goal progress; binding predicates) are `<dl>`; legends and keys are tied to their graphic with `aria-describedby`; an absent counterpart is the word "absent", never an empty cell.
- **Focus order and return**: DOM, reading, Tab and F6 order follow the visual order. Focus never lands on `body`. Back and Forward restore the focused element. Where focus goes:

| After | Focus lands on |
|---|---|
| a Go, a history step or a palette go | the target per the Linked views table ("Focus lands on"); a surface's heading or first item |
| a palette action | the ActionStrip's Run button |
| ActionStrip Run or Cancel | the invoker |
| closing a dialog, menu or Peek | the invoker; if it is gone, the same index in the list |
| import durably accepted | the admitted batch row, at 700px or wider with the dock open, announced once (a documented APG exception); otherwise the invoker, with "Import accepted: 3 inputs, batch b7. Go to last announcement (g then j, or the palette) shows it." |
| hiding a region that holds focus | its collapse strip |
| the focused row is removed | the nearest row, announced; the one focus move the viewer did not cause |

## Semantics per pattern

| Component | Pattern | Rules |
|---|---|---|
| SessionTab, workspace tabs, dock tabs, References modes, narrow Code views | APG Tabs | `button role="tab"` in named tablists ("Sessions", "Workspaces", "Dock", "References modes", and below 700px "Code views": Listing · Decompile · Hex · Graph · References). A tablist holds only tabs. One tab stop, ←/→ move, Home/End. Automatic activation only for workspaces and the dock, whose panels are cached. Manual activation (Enter or Space) for session tabs, because switching project sessions is not a focus side effect, for the Calls and Slots modes, and for the narrow Code views. Closing a session tab: the visible × is a pointer affordance (`aria-hidden`, `tabindex="-1"`, ≥24px); Delete closes the focused tab and is described through `aria-describedby`; the tab's link menu has "Close ‹title›". F2 renames. Each session tab restores its own workspace, `views`, selection, holds, scroll and focused element from durable workspace state and `history.state`; data is read now and nothing is re-run. A tab whose project is not the active one shows the cross-project StateNotice and never switches on activation alone. |
| Views toolbar (Code Browser) | APG Toolbar | One tab stop; `aria-pressed` toggles Listing, Decompile, Hex and Graph with stable names. At most two center panes plus the HexStrip. The replacement ("Graph replaces Decompile") and the last-view rule are in `aria-describedby` before activation, and a replacement is announced once. |
| EntityRow lists, MatchReview, CounterpartMatrix | APG Grid, row focus | `role="grid"` with a name; row headers `th scope="row"`; one tab stop with roving focus; ↑/↓ rows, ←/→ cells within the row, Home/End the first and last cell in the row, Ctrl+Home/End the first and last row; `aria-selected` on rows; checkbox cells are labels named "Check ‹entity›" (checking is not selecting). In checkable grids Ctrl/Cmd-click toggles and Shift-click extends the checked set (Linked views). |
| ReadinessMatrix and its slots mode | APG Grid, cell focus | The APG Grid keys, including Ctrl+Home/End and PageUp/PageDown. Arrows move focus only; Enter commits the cell's entity and build. |
| ContainerTree, navigator, CallHierarchy, GraphPane list form | APG Tree view / Treegrid | `aria-expanded`, `aria-level`, typeahead after `/`; → opens, ← closes or moves to parent; `*` expands siblings. |
| SymbolTree, ProgramTreeView | APG Treegrid | `role="treegrid"` named with its scope ("Symbols, corpus-alpha, logical, 4 builds"; "Program Tree, build-b"). Rows carry `aria-level`, `aria-expanded`, `aria-setsize` and `aria-posinset`; the name cell is the row header. → opens a node or moves into its cells, ← closes, moves to the parent or back out of cells; Home/End; `*` expands siblings. Both bind letter commands, so typeahead starts with `/`. Presence cells are grid cells named in words ("build-c: resolved, 00082f40, accepted"); "absent", "folded" and "inlined only" are words, never an empty cell. Shared program-tree nodes carry "also in …" and empty ones "empty" in the row name. Keys only navigate or arm (Ctrl/Cmd+X marks a cut, Ctrl/Cmd+V arms Move); every post goes through the inline editor or the ActionStrip. |
| OverviewBar | Named image plus a ranges grid | The bar is `role="img"` named "Overview, build-a, whole image, 4 lanes", takes no focus and has `aria-describedby` to its key, a real list with every kind, pattern word, value and count. The ranges list is an APG Grid with row focus, named "Overview regions, build-a"; each row reads "0041b000 to 0041bfff, function, byte entropy 6.1, 2 search hits". It is the keyboard and accessible form of the bar (2.5.8 Equivalent): pointer clicks on the lanes are an enhancement only. Kinds are patterns plus words; forced colors keep the patterns (`forced-color-adjust: none`) because the key carries every value. |
| ResultsTable, MemoryMapTable | APG Grid, row focus, checkable | `role="grid"` named by kind, source and scope ("Search memory hits, all builds, as of 14:02"). Header cells are sort buttons; sorted headers carry `aria-sort`, and the order is in the name ("Location, sorted ascending, first key"). `aria-rowcount` is the total when known and −1 when the table was cut at a limit. Check cells are `role="checkbox"` named "Check ‹row›" with a visible checked count. Per-build cells use LocatorGlyph words, and an unsearched build is the words "not searched", never an empty cell or 0. Row focus moves the Listing cursor only for rows on the inspected build (Linked views). Counts are announced politely, debounced 300ms; truncation once per run. |
| Listing | Virtualized read-only grid | `role="grid"`, `aria-readonly="true"`, named "Listing, build-b, ResourceRef::Resolve". Columns Address (row header), Label, Bytes (omitted while the HexStrip is shown), Instruction, Operands, Xrefs/Comment, with `aria-colindex`. `aria-rowcount` is −1 unless the program's row total is known; `aria-rowindex` counts from the start of the loaded section, and the address row header is the stable locator. Labels are their own rows ("label ResourceRef::Resolve, 12 xrefs"); flow glyphs are `aria-hidden` and restated as words ("jump target from 0041b230"). |
| DecompileView | Virtualized read-only grid | Columns line, code and mapping, with a whole-function `aria-rowcount`. |
| HexStrip | Virtualized read-only grid | An offset row header, 16 byte cells and ASCII, with the region's `aria-rowcount`. Find matches byte patterns and says so. |
| ObjectDiff | Read-only grid | Row header, target, candidate, and a state cell with the words "differs", "added" or "removed". |
| SourceRepairDiff | Read-only grid | Line, change word, text. |
| Every code well | Focus model | Roving focus on the row. The row's name reads its cells under the **verbosity** View setting (address full / last 4 / off; bytes off by default but reachable with →). → enters cells; inside Operands it steps token by token. Operands are spoken exactly as the Listing renders them; an optional plain-words form goes in `aria-description`, with an `aria-describedby` fallback. Cells that host InlineRename carry `aria-readonly="false"`. The focused row stays mounted. Find inside a well announces "3 of 12 matches". `aria-keyshortcuts` is set once on the well or grid, never on every token. |
| CommandPalette, go-to field | APG Combobox + Listbox in a modal dialog | `aria-activedescendant`, grouped options, result count in a polite status. |
| ConfirmDialog | APG Alert dialog | Focus starts on Cancel; Esc cancels; focus returns to the invoker. |
| Splitters | APG Window splitter | `role="separator"`, `aria-valuenow/min/max`, `aria-controls`; arrows 16px, Shift 64px, Home and End to the minimum and maximum, Enter collapses and restores. Reset is in the pane-header size menu (Narrow, Default, Wide, Collapse, Reset). The size menu and the View menu offer every size and collapse without dragging (WCAG 2.5.7). |
| WorkflowControl, ActionStrip | APG Toolbar | One tab stop, arrows between controls. |
| Job and history lists | APG Feed | `role="feed"`; each ActivityRecord is an `article` named by its title and described by its three readouts; PageDown/PageUp move between records; `aria-busy` while loading. |
| Log tails | ARIA log | `role="log"` with `aria-live="off"`; a per-job opt-in "Announce new lines", coalesced to at most one message per second ("7 new lines; last: …"); "Open in Accessible View". |
| ProblemsList | APG Treegrid, grouped by objective | Enter jumps to the entity or address. F8 / Shift+F8 step the active worklist; the Problems tab offers Collect into worklist (w) and a one-activation Step problems that creates it through the MarksList dialog. Typeahead starts with `/`. |
| Breadcrumbs | APG Breadcrumb | `nav` "Location" with an ordered list; `aria-current="location"` on the last item; build and section segments are menu buttons of siblings. |
| Rails, units, meters | Progressbar / img | `role="progressbar"` with `aria-valuetext` in words ("3 of 6 measured units done; unit 4 running"); age bars (StarvationMeter) are `role="img"` with the age in words, never `role="meter"`; the age words beside the bar are the links, outside the image. Unknown progress has no progressbar, only the words "Progress unknown". |
| Fact strips, capability chips, dense glyph cells | Named image | The strip or cell has an accessible name in words; glyphs are `aria-hidden`. A visible legend is on the same view, and Peek shows the words on focus. |
| Diffs | Text | Added, removed and changed lines carry the words "added", "removed", "differs" for assistive tech, not only color and glyphs. |

## Keyboard and shortcuts (WCAG 2.1.4)

- **Global commands use a modifier**: Ctrl/Cmd+K palette, Ctrl/Cmd+P go to anything, Ctrl/Cmd+G go to address, Alt+← / Alt+→ back and forward, F6 / Shift+F6 cycle regions (header, navigator, center, evidence, work view, dock), Ctrl/Cmd+J show or hide the dock.
- **Links share one grammar** (see Linked views): Enter goes, Shift+Enter opens beside, Alt+↓ peeks, the Keep button (Shift+K while focus is inside the Peek or card) keeps, Shift+F10 opens the link menu, Ctrl/Cmd+Enter opens a browser tab. Focus never changes workspace, build, dock tab or history, and Alt+←/→ are never intercepted in text fields or edit mode.
- **Single-character keys are focus-scoped**: j/k, x, Space, typeahead and the letter commands work only while focus is inside a list, grid or listing, and never in text fields. Inside a code well the code scope wins over the composite scope (Keymap, Precedence). In every list, grid, tree and treegrid, typeahead starts with `/`; text fields and comboboxes take plain typing.
- **Every shortcut can be turned off or remapped** in Keyboard settings. Menus and tooltips show the current binding, and controls expose it with `aria-keyshortcuts`. Sequences such as `g then 1` go in `aria-describedby` text, never in `aria-keyshortcuts`.
- **Keys the platform takes** (Keymap, Platform cautions): where GNOME or KDE take Alt+F1 or Alt+F2, or a browser takes F6 or F7, the command stays on the palette, a menu or a button, and its binding is remappable.
- Screen-reader browse modes are respected: letter commands never fire while a virtual cursor mode is plausible (focus on the document body).

## Editing without traps (WCAG 2.1.2)

Editable wells enter edit mode on Enter; Tab indents only in edit mode; Esc leaves it. "Tab moves focus" toggles with Ctrl+M on Windows and Linux and Ctrl+Shift+M on macOS, and the status line shows the state. F6 always leaves the region. Overlay rails close on Esc or when focus leaves and return focus to their rail-bar button. Esc follows the one order in the Keymap section.

## Accessible View

Alt+F2, the pane-header button, or the palette and the Help menu where the operating system takes Alt+F2, opens a modal with a read-only, soft-wrapped text area and Copy all and Close buttons.

- It holds every row already read for the current function, range, log, peek or receipt. Virtualization limits the DOM, not this text. Anything not read says "Not loaded. Open to read it." It never decompiles or starts work.
- It is a snapshot labelled "as read ‹time›". If the basis moves while it is open, it shows "◷ Basis changed since opened · Refresh" and never swaps text under the caret.
- Opened on a Held pane, a Kept card or a historical receipt, its first line reads "Held · ‹target› · ‹age›", "Kept · ‹target› · ‹age›" or "historical", then the ProvenanceStamp text.
- Code rows follow the one Screen-reader verbosity View setting. Accessible View shows the current value and links to View settings; it has no toggles of its own.
- Diffs prefix lines with "+ added", "− removed", "± differs" (the diff marker; "≠" is reserved for claim boundaries such as "local ≠ whole-image proof"). The caret starts on the focused line, and Esc returns to the same row.
- Its soft wrap with a hanging indent is the WCAG 1.4.10 path for code at 320px, and the path for exact text where screen-reader punctuation settings would alter speech. Sighted users get exact copyable text too.

## Help that stays put (WCAG 3.2.6) and no retyping (WCAG 3.3.7)

- Help is always the last menubar item on both surfaces: Keyboard shortcuts (Ctrl/Cmd+/; shows the current, remapped keymap), Accessibility help for this view (Alt+F1; the keys of the focused component), Catalog docs. The palette answers "help", "keys" and "shortcuts". Help text comes from the shared keymap document, so it cannot drift.
- ActionStrip fields prefill in this order: the bound target from the selection, then the fields last used for this action on this program, then catalog defaults; each prefilled field says where it came from ("from last run 14:02"). Catalog fields typed as targets always bind from the selection, never from the last run. Refusals keep every entered field. For an empty query, go to and the palette list Recent locations, Marks, Recent actions and Recent jobs. Drafts persist per function across navigation. Password fields allow paste and password managers.

## Live regions (WCAG 4.1.3)

One polite status region and one assertive alert region per page.

- **Navigation landings**: only the cases in Linked views, Announcements. There is no announcement per selection settle; focus is the cue.
- **Polite**: job transitions (started, finished, failed, cancelled); decision outcomes after their terminal result; import durably accepted; result counts, debounced 300ms; stale and reconnecting notices, once per transition; "N changes since you looked" summaries; and the checked-set confirmation after a program change, worded as in Linked views, History ("Cleared 4 checked rows on build-a"), with no Undo.
- **Assertive**: only conflicts and refusals that block the viewer's own action ("Decision refused: basis changed. …"). Freeze never suppresses these.
- Never announce each poll, heartbeat or log line. Announce transitions once; coalesce within 1s (one message per job transition, one per batch: "Run on 4 rows: 3 finished, 1 failed", in the Job outcome words).
- An inline StateNotice is `role=status` only when the user's own action caused it. Freezing a region pauses its polite announcements and later reports "N events since frozen".
- `aria-busy` is set only on a pane that is loading and does not hold focus.

## Content on hover or focus (WCAG 1.4.13)

Peeks and hover cards are **dismissable** (Esc), **hoverable** (the pointer can move onto them: the `peek-gap` is bridged, and a hover-opened card closes only `peek-grace` after the pointer leaves both) and **persistent** (they stay until dismissed, focus leaves, or the pointer leaves both trigger and card). They open on focus as well as hover, never steal focus, and never contain the only copy of information that is not reachable another way. `aria-expanded` and `aria-controls` are present only while a Peek is open. The `title` attribute is never the only carrier of meaning.

## Targets, dragging and reflow

- Every target is at least 24×24 CSS px (WCAG 2.5.8, met). Below 700px, and at any width with a coarse pointer, targets are 44px (house rule after 2.5.5). Small marks join a larger target: the whole fact strip is one button that opens Peek, the capability row is one button, the whole address cell is the link. Each component README names the exception it relies on. The 6px splitter hit zone relies on the 2.5.8 Equivalent exception: the splitter keys, the pane-header size menu and the View menu reach every size.
- Nothing requires dragging (WCAG 2.5.7): clicking a splitter grip toggles collapse and restore, and the pane-header size menu offers Narrow / Default / Wide / Collapse / Reset; session tabs move from their context menu or the palette; grid headers offer Fit to content / Default width; the dock moves via View; diagrams have zoom and pan buttons; the WorkTimeline track is clickable and has step buttons; import has "Choose files…"; layout presets set every splitter at once.
- Content reflows at 320×256 CSS px (1280×1024 at 400% zoom) by switching to the single-pane layout (NarrowFlow); below 480px of viewport height the header and status line stop being sticky. Only code wells, matrices and diagrams scroll in two dimensions, each in its own focusable, labelled container. Switching panes keeps each pane's scroll and focused row.
- Size tokens are minimums; rows grow. No fixed heights with `overflow: hidden` around text; text survives WCAG 1.4.12 spacing overrides. Every truncation has a reveal path that is not `title`: the full text is in the accessible name, in Peek on focus, and in the evidence rail header.

## Motion, time and updates

- `prefers-reduced-motion` (and the **Reduce motion** View setting, which only adds to the operating system's preference) removes all motion: scrolling is instant, the arrival flash becomes a static 2px `ink-strong` outline on the landed row until the next interaction, and animated edges and transfers become a before/after pair plus the event sentence. Arrival otherwise follows Linked views: focus, the selection or cursor shape, and the 120ms flash. There is no separate landed style.
- Auto-updating regions (dock, log tails, heartbeats) have a **Freeze updates** control (WCAG 2.2.2), per region; frozen regions say "Frozen at 14:02 · 7 events since", queue events without dropping them, and resume on request.
- No time limits on reading or deciding. Pending decisions never expire silently.

## View settings

One View settings group in the View menu holds every per-viewer setting: Density, Increase contrast, Reduce motion, Screen-reader verbosity and Advance to Code after a pick, plus the pointer options Peek on hover and Brush on hover. They are stored as a per-viewer diff in durable workspace state beside the keymap overrides, never in the URL or browser storage. The accessibility settings are adaptations, not themes. **Advanced** (off by default) shows advanced tools; today it gates ScriptConsole, which is hidden, not shown disabled, while it is off ("Scripts are an advanced tool. Turn on Advanced in View settings to show Scripts."). Reading a finished run's transcript in the dock never needs it. **Tool options…** in the same menu opens OptionsPanel for the per-viewer options of each code viewer; it sits beside View settings and Keyboard and does not repeat them.

## Diagrams

- Every diagram SVG has `role="img"`, `lang`, a `<title>` and a 2–4 sentence `<desc>`, and links a generated text outline as its primary accessible form.
- Diagram text colors are all 4.5:1 or better on their grounds. Two pairs are forbidden: identity ink on identity fill (4.48:1) and `ink-muted` on any family fill.
- Family, gate, lock and edge type are always written as words as well as drawn in color, dash or shape.
- In-app renderings of diagram components use the app type scale (≥11px labels, ≥12px body), never the sub-12px `dia-*` sizes, which exist only for the fixed-size print canvas.
