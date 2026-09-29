# ReadinessMatrix

Entity × build readiness: locator status and observed status as separate glyph axes, row-for-row equal to the readiness report.

**Consumer provides** rows keyed by stable key, one column per build, each cell's locator status, member and observed status, the landed address or addresses, plus the per-build environment facts.

- Each cell: the LocatorGlyph, then a thin rule and the observed status in `type-code-small`. The status word is in the cell's accessible name and in `.sr-only`; a visible legend sits under the grid and is tied to it with `aria-describedby`.
- Coverage phrasing names scope: "resolvable on {build-a, build-b}, ambiguous on build-c, absent on build-d".
- A plain-language "what you can do on this build" line sits under each build header. The build header links to that build's runtime capabilities.
- **Cell grammar.** Focus alone binds nothing. Alt+↓ peeks the ladder run (members tried in family order, each reason, the member used, the terminal OutcomeTag, observed status on its own line). **Enter** writes one selection (entity + build) and moves focus to the EntityBuildCard in the evidence rail, whose header links back: "from ReadinessMatrix · row 12 · build-c". **Shift+Enter** opens SplitCompare with that build. Enter on a ⇉ contested cell opens two held panes labelled "contested · no winner". Enter on an unresolved cell opens the ladder run; it never picks an address.
- Filter chips ("Only contested", "Unresolved on build-c") narrow the rows (`f=`) and `w` collects the rows into a worklist. A **vtable slots** mode (ladder E) makes rows the slots of one vtable; each cell peeks its slot target.
- Locator status, observed status and identity-edge state stay separate; nothing is summed.

**Linking**

- **Publishes:** `entity` and `build` on Enter (one history stop) · `cmp` on Shift+Enter (Open beside creates a Held pane) · `hold` for the contested pair (two held centre panes) · `f` for its filter chips (replaceState).
- **Follows:** `project` and `f`; commit-on-Enter (an expensive corpus view). A selection made elsewhere marks its row without moving focus. The matrix itself is not holdable.
- **Targets rendered:** cell → the EntityBuildCard for that entity × build, with its back-link · build header → that build's runtime capabilities (`ws=evidence&panel=runtime`) · row header → the logical entity in Compare (`ws=compare`) · ambiguous and contested cells → their ladder evidence; contested also names both candidates as links marked "no winner". Cell names read "build-c: pinned, module_rva, non-portable; observed: not run".
- **Peek source:** Alt+↓ on a cell reads the stored ladder run and observed status for that entity × build; nothing is fetched.
- **Absent copy:** "absent" and "unresolved" are plain words · "Not loaded. Open build-c to read it." · "contested · no winner" on the held pair.
- **Target-size exception:** none; cells are at least 24px (28px rows). With a coarse pointer each row adds one 44px row-menu button carrying the link menu.

**Keyboard**

- APG Grid with cell focus and one tab stop: ←/→ across builds, ↑/↓ across entities, Home/End first and last cell in the row, Ctrl+Home/Ctrl+End first and last cell in the grid, PageUp/PageDown one viewport.
- Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 reveals in. `w` (focus-scoped, remappable) makes a worklist of the filtered rows.

**Accessibility**

- `role="grid"` with `aria-rowcount` and `aria-colcount`; entity row headers `th scope="row"`, build headers `th scope="col"`. Focus is a 3px inset outline; sticky headers get scroll padding (WCAG 2.4.11). Cells are at least 24px.
- Announcements only on Enter (the binding), never while arrowing (WCAG 3.2.1, 4.1.3).

**Removes switching:** opening the Evidence workspace, the readiness report and the Compare workspace to see why one cell is in its state and what can be done on that build (J06, J14, J33).
