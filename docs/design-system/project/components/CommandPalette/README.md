# CommandPalette

Ctrl/Cmd+K: the universal entry to catalog actions, go-to surfaces and recent jobs; one engine shared with go to anything (Ctrl/Cmd+P) and go to address (Ctrl/Cmd+G).

**Consumer provides** the query and grouped results (Actions, Go to, Recent jobs) with the highlighted row; for each row its type, target build, per-build locator state and where it opens; for actions, the bound target and binding, or the reason it is unavailable.

- A `dialog-bg` sheet with `shadow-popup` over the `overlay` scrim; the query field is a `well`.
- **One engine.** Ctrl/Cmd+K opens it with `>` preselected (verbs and surfaces); Ctrl/Cmd+P is the same engine for places (`@` symbol, `:` address, `#` logical id, `!` job, `%` receipt or basis, `~` pipeline node, `$` string, `'` marks and worklists, `?` help); Ctrl/Cmd+G opens it with `:` typed. The prefix table lives in the NavigationBar; this component does not keep its own copy.
- Rows name type, target build, locator state and where they open ("opens Compare"). A place row is a Go: Enter goes, Shift+Enter opens beside. Picking an action **arms** the ActionStrip with the target prefilled; it never posts. Unavailable actions stay in the list, `aria-disabled` with the reason.
- Previews are cache-only: Alt+↓ peeks the highlighted result without fetching. Recent actions and repeat-last jump are remembered per viewer.

**Linking**

- **Publishes:** nothing itself. A place pick navigates like its link (`entity`, `build`, `addr`, `job`, `receipt`, `node`, one history stop); an action pick writes the ActionStrip.
- **Follows:** the primary selection (actions bind it: "Match siblings for ResourceRef::Resolve"); results are searched from stored indexes only. Not holdable.
- **Targets rendered:** address or symbol → the Code Browser at that build · logical id → Compare with the CounterpartMatrix · job → the dock Jobs record · receipt → the receipt card · basis → the ProvenanceStamp detail · pipeline node → the PipelineMap node · worklist → its first item and the worklist chip.
- **Peek source:** Alt+↓ on the highlighted result reads its cached Peek content (listing lines, facts, job readouts); nothing is decompiled or fetched.
- **Absent copy:** "only on build-b · choosing it switches the inspected build" · "not indexed here" · "No results in stored indexes." · the unavailable reason ("Needs a function selection").
- **Target-size exception:** none; options are 28px rows (44px below 700px).

**Keyboard**

- ↑↓ move, Enter picks, Shift+Enter opens a place beside, Alt+↓ peeks, Esc closes and returns focus to the invoker. ↑ in an empty field recalls history. `>` switches between places and commands.

**Accessibility**

- APG Combobox and grouped Listbox inside a modal dialog, with `aria-activedescendant`; unavailable options carry `aria-disabled` and a description. The result count is a polite status.

**Removes switching:** choosing the right list view before searching, and reopening the palette for places versus verbs (J05, J38).
