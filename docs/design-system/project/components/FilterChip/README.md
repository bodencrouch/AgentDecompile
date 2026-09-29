# FilterChip

A filter that a link applied to a list, grid or dock tab, shown above it in words with a 24px remove button: "Changed by a3f9 ✕", "Only contested ✕", "Selection only ✕".

**Use it** wherever activating a link narrows rows instead of going somewhere: the ActivityRecord's Changed line (Functions grid filtered to what the job changed), an OutcomeCell batch summary word ("1 failed"), ObjectiveSummary and FailureRecord count links, a ReadinessMatrix or CounterpartMatrix filter ("Only contested", "Unresolved on build-c"), the dock's "Selection only", a PipelineMap node's filtered live view, and "N more" rows in the XrefPanel. The typed text filter of a list is not a FilterChip; it stays in its field. The host grid owns the filter; the chip only shows it.

**Consumer provides** the host (list, grid or dock tab, with its build), the active filters as `axis:value` pairs from the location's `f=` parameters, each filter's words and its source (the job, receipt, node, entity or control that applied it), the row count before and after filtering in the host's unit ("functions", "rows", "jobs"), whether the source is still changing (a running job), and how many checked rows and whether the primary selection are hidden by the filters.

- **Words, not codes.** The chip reads as a phrase: "Changed by a3f9", "Only contested", "Unresolved on build-c", "Selection only: ResourceRef::Resolve · build-b". Values (job ids, builds, symbols) are mono `ink-strong` with `translate="no"`; the rest is `type-ui` 12 `ink`. Long text wraps inside the chip; it is never truncated.
- Frame: 1px `line-control` on `pane`, `radius-chip`. An applied chip is solid; `.ad-filt` dashed checkboxes stay the in-toolbar toggles, a different thing. A chip whose source is still changing is dashed and says "· so far" ("Changed by b7e2 · so far"); its count says "so far · job running" and grows only as the job records units.
- Two parts: the words are a button that opens the filter's menu; the ✕ is a separate 24px button named "Remove filter: ‹words›" (for example "Remove filter: Changed by a3f9"), divided by a 1px `line`. Hover is `row-hover-bg`; the open menu leaves the words on `raised`.
- The menu, in order: **Open source** (a typed link: job, receipt, node or entity; Enter goes, Alt+↓ peeks), **Collect rows as a worklist** (`w`), **Copy link with this filter**, **Remove filter**.
- **Count**: "3 of 1,188 functions" in `ink-muted` beside the chips, tabular figures. From two chips on, a quiet **Clear filters** button follows the count.
- **Filters narrow rows only.** Applying or removing one never changes the primary selection, the inspected build, the checked set or any held pane. A selection outside the filters stays the selection and panes keep following it ("Selection String::CStr is outside these filters; panes still follow it."). Checked rows hidden by a filter stay checked and are counted ("2 checked rows are hidden and stay checked"). Actions bound to the checked set name hidden rows before they run.
- **No rows** is a StateNotice (∅, `.info`) that names the cause from the source record and the explicit next step as a link ("The record of job a3f9 names 3 changes, all on build-b. Open build-b"). The build never switches by itself.
- **Record-named only.** "Changed by" rows come from the units the job recorded, never from timing. A job that recorded no units offers no Changed link; its record says "Changed entities: not recorded".
- **Selection only** in the dock is one filter with two faces: the toggle (ActivityRecord's `aria-pressed` button, ProblemsList's `ad-filt` checkbox) applies it, and the chip shows it with its target ("Selection only: ResourceRef::Resolve · build-b"). Removing the chip releases the toggle.
- **URL.** Each chip is one repeatable `f=axis:value` from the shared axis vocabulary (`f=changed:a3f9`, `f=outcome:failed`, `f=locator:contested`, `f=locator.build-c:unresolved`, `f=scope:selection`, `f=xref.dir:in`). Per `location-schema.json`, `f` uses replaceState: applying, removing and Clear filters never push a stop. The link that applies a chip pushes one stop only when it is also a Go (it switches the build, workspace or dock tab, as "3 recipients on build-b" does from build-a). A shared link restores the same chips; opening it reads existing data only.
- Both surfaces render the same chips from the same `f=` parameters and axis vocabulary. The static 8080 surface may render the menu as a plain list of links under the chip.

**Linking**

- **Publishes:** `f` for its host (replaceState). Never the primary location, a hold or a keep.
- **Follows:** the host's location. A build or program switch clears build-scoped chips and says so once ("Filter Changed by a3f9 removed: it names build-b"). Not holdable.
- **Targets rendered:** in the menu, the filter's source as a typed link (job → the dock Jobs record, receipt → its receipt card, node → the PipelineMap node, entity → the Code Browser); the no-rows notice's next step ("Open build-b", a build switch). Link names read "Job a3f9, corpus.cross-place, finished".
- **Peek source:** Alt+↓ on the menu's source link reads that record from cache (the job's three readouts, the receipt, the node); nothing is fetched.
- **Absent copy:** "0 of 1,204 functions" with the no-rows notice · "Source job a3f9 is no longer in dock history" (the chip keeps its words and stored rows, or is removed with a notice; never re-derived) · "Changed entities: not recorded" (no chip is offered).
- **Target-size exception:** none; both parts are 24px tall and the ✕ is 24px wide; 44px below 700px.

**Keyboard**

- The chips of one host form an APG Toolbar with one tab stop, placed before the host's grid in Tab order: ←/→ move across every words button and ✕, Home/End go to the first and last.
- Enter, Space or ↓ on the words opens the menu (APG Menu Button); ↑/↓ move, Enter picks, Esc closes and returns to the words.
- Delete or Backspace on either part removes that chip; focus moves to the next chip's words, else the previous chip, else the host grid's focused cell. Never to `body`.
- Esc never removes a chip. The keymap's Esc order stays: the open peek or menu, then edit mode, then a dialog, then a transient filter typed in this view.
- `w` (in the menu, or focus-scoped in the host grid) collects the filtered rows as a worklist. It is remappable and can be turned off (WCAG 2.1.4).

**Accessibility**

- The group is `role="toolbar"` named for its host ("Filters on Functions, build-b") and `aria-describedby` the count. The words button has `aria-haspopup="menu"` and `aria-expanded`, and `aria-describedby` naming its source ("From job a3f9, corpus.cross-place, Changed line").
- Remove buttons are named "Remove filter: ‹words›" and expose `aria-keyshortcuts="Delete"`; the ✕ glyph is `aria-hidden`.
- The result count is announced once in the polite region after it settles (debounced 300ms): "Filter applied: Changed by a3f9. 3 of 1,188 functions on build-b." and "Filter removed: Changed by a3f9. 1,188 functions." A "so far" count is not re-announced as it grows; the job's end is announced once by the dock.
- WCAG 3.2.2: applying a filter changes only the host's rows; it never navigates, moves focus away from the invoker or switches the build.
- Targets: both parts are 24px tall and the ✕ is 24px wide (WCAG 2.5.8); 44px below 700px. Focus is a 2px inset `focus` outline on each part.
- Forced colors map the frame and divider to `CanvasText`; the dashed "so far" frame keeps its dash and its words.

**Removes switching:** J19, from a job to the entities it changed, goes from 4 switches (dock, log, Functions list, search by hand) to 1: the Changed link filters the list in place. J22 with N = 4 goes from 7 to 2 together with OutcomeCell: "1 failed" filters the batch to the failed row. In J06 and J33, "Only contested" and "Unresolved on build-c" replace scrolling the matrix, and the dock's "Selection only" replaces reading unrelated jobs to find the selection's.
