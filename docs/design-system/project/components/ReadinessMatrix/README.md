# ReadinessMatrix

Entity × build readiness: locator status and observed status as separate glyph axes, row for row equal to the readiness report. It is the corpus view `panel=readiness` and the single owner of the vtable slots × builds rows.

**Use it** as the full corpus view in the Corpus workspace (`ws=evidence&panel=readiness`), reached from "Show all" on the rail's readiness section and from go to. Its **slots mode** (a `type` naming a vtable, for example `type=Actor::vtable`) makes the rows the slots of one vtable aligned by the stored ladder E results; XrefPanel's Slots mode shows the same rows at rail width and links "Open slots matrix".

**Consumer provides** rows keyed by stable key, one column per build, each cell's locator status, member and observed status, the landed address or addresses, and the per-build "what you can do" line from the shared readiness projection; in slots mode, the slot rows from ladder E with each cell's slot target.

- Each cell: the LocatorGlyph, then a thin rule and the observed status in `type-code-small`. The status word is in the cell's accessible name and in `.sr-only`; a visible legend sits under the grid and is tied to it with `aria-describedby`.
- **The primary cell** (the selected entity on the inspected build) shows the selection shape: `selection` fill plus the 3px `accent` bar.
- Coverage phrasing names scope: "resolvable on {build-a, build-b}, ambiguous on build-c, absent on build-d".
- Under each build header, a plain-language "what you can do on this build" line comes from the shared readiness projection, never composed client-side. The build header links to that build's runtime capabilities (`ws=evidence&panel=runtime&build=build-c`).
- **Cell grammar** (a cell-focus matrix). Arrows move focus only; focus alone binds nothing. Alt+↓ peeks the ladder run (members tried in family order, each reason, the member used, the terminal OutcomeTag, observed status on its own line).
  - **Enter** on a resolved, pinned, degraded or unresolved cell writes the one selection, entity + build (one history stop, one polite message). Focus stays on the cell; the EntityBuildCard in the evidence rail follows, reached with F6 or `g e`. The cell's `aria-describedby` says so before activation: "Enter: inspect ResourceRef::Resolve on build-c (changes the inspected build)". On an unresolved cell the card shows the ladder run and never picks an address.
  - **Ambiguous and contested cells** are APG Menu Buttons (`aria-haspopup="menu"`, named "2 candidates, no winner" or "3 candidates, none picked"). Their menu lists each candidate address (Enter goes, Shift+Enter opens beside), then **Compare candidates** and **Open ladder run**; the footer reads "Opening one does not accept it." Compare candidates opens the Compare workspace with two `hold` entries, each pane labelled "candidate 1 of 2 · contested · no winner". Only the Compare workspace shows that split.
  - **Shift+Enter** on a single-address cell opens that build beside as a Held pane.
  - A cell whose program is not open lands on "Not loaded. Open build-c to read it."
- Filter chips ("Only contested", "Unresolved on build-c") narrow the rows (`f=locator:contested`, `f=locator.build-c:unresolved`). `w` collects the rows into a worklist; while a build filter is active the worklist items are entity × build, otherwise entities.
- Locator status, observed status and identity-edge state stay separate; nothing is summed.
- **Narrow form.** Below a 480px container, one entity's builds are shown as a list (build, glyph, word, observed status; ambiguous and contested as menu buttons). Otherwise the grid is a labelled 2-D scroll container, with 44px cells below 700px.
- Read-only by construction: the matrix reads the stored readiness report, ladder runs and capability receipts. It never runs a ladder, opens a program or probes a live process.

**Linking**

- **Publishes:** `entity` and `build` on Enter (one history stop; focus stays on the cell) · `cmp` and a `hold` on Shift+Enter (a Held pane) · `ws=compare` with two `hold` entries from Compare candidates · `f` for its filter chips (replaceState when typed or removed, pushState when applied from a link) · `type` for the slots mode.
- **Follows:** `project` and `f`; commit-on-Enter (an expensive corpus view). A selection made elsewhere marks its cell with the selection shape without moving focus. The matrix itself is not holdable.
- **Targets rendered:** cell → selects that entity and build in place, with the EntityBuildCard following (35 typed links, "matrix cell") · build header → that build's runtime capabilities (`panel=runtime`) · row header → the logical entity in Compare (`ws=compare`) · ambiguous and contested cells → their candidate menu, each candidate a link marked "no winner" for contested · Open ladder run → the ladder run's receipt (`receipt=6a0e` with `project`, `entity` and `build`). Cell names read "build-c: pinned, module_rva, non-portable; observed: not run".
- **Peek source:** Alt+↓ on a cell reads the stored ladder run and observed status for that entity × build; nothing is fetched.
- **Absent copy:** "absent" and "unresolved" are plain words · "Not loaded. Open build-c to read it." · "2 candidates, no winner" · "Opening one does not accept it."
- **Target-size exception:** none; cells are at least 24px (28px rows), 44px below 700px. With a coarse pointer each row adds one 44px row-menu button carrying the link menu.

**Keyboard**

- A cell-focus APG Grid with one tab stop: ←/→ across builds, ↑/↓ across entities, Home/End to the first and last cell in the row, Ctrl+Home/Ctrl+End to the first and last cell in the grid, PageUp/PageDown one viewport. Arrows move focus only; Enter commits.
- Enter as above; Shift+Enter opens beside; Alt+↓ peeks; Shift+F10 opens the one link menu (Open · Open beside · Peek; Reveal in Compare, the Evidence rail, Pipeline map; Copy). On an ambiguous or contested cell, Enter, Space or ↓ opens its candidate menu, and Esc returns to the cell (`keymap.json` `escapeOrder`).
- `w` (focus-scoped, remappable) makes a worklist of the filtered rows; typeahead starts with `/`, as in every grid, because plain letters are commands.

**Accessibility**

- `role="grid"` with `aria-rowcount` and `aria-colcount`; entity row headers `th scope="row"`, build headers `th scope="col"`, inside a labelled scroll container. Focus is a 3px inset outline; sticky headers get scroll padding (WCAG 2.4.11).
- The primary cell has `aria-selected="true"` and the words "the primary selection" in its name; the selection shape is fill plus bar, never color alone.
- Announcements only on Enter (the selection), never while arrowing (WCAG 3.2.1, 4.1.3): "ResourceRef::Resolve, build-c: pinned, module_rva; observed not run".

**Removes switching** (counts from the plan ledger):

- J06 from a matrix cell to its ladder evidence and any contested pair: 4 → 1 (U183; Peek reads the ladder at 0, Enter selects in place).
- J33 why an entity is not runtime-usable on a build and whether other builds are: 4 → 1 (U183).
- J14 the same vtable slots on other builds: 6 → 2, credited to References in place (U177), whose Slots tab shows these slot rows.

## Behavior

- "Opening a candidate does not accept it." (formerly in the Key tooltip and the `≠ accept` chip under the contested menu)
- "From the shared readiness projection: locate only; reading and calling are not checked." (formerly the projection tip)
- "Column head: what a mod can do on that build. Fill and accent bar: the primary selection." (formerly in the Key tooltip)
