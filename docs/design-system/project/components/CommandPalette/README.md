# CommandPalette

Ctrl/Cmd+K: the modal entry to catalog actions, places and recent jobs. It is the same engine as the NavigationBar's go-to field, opened as a dialog with `>` typed.

**Use it** from Ctrl/Cmd+K anywhere, from the header's **Commands** button, and wherever the go-to field is collapsed or absent: below `bp-compact` (1100px), Ctrl/Cmd+P and Ctrl/Cmd+G open this same engine in the dialog, with nothing typed or with `:` typed.

**Consumer provides** the query and grouped results (Actions, Go to, Recent jobs, Help) with the highlighted row; for each place its type, target build, per-build locator words and where it opens; for each action its label from `GET /api/v1/actions`, the bound target and binding, or the reason it is unavailable; the coverage that was searched.

- A `dialog-bg` sheet with `shadow-popup` over the `overlay` scrim; the query field is a `well`.
- **One engine.** The prefix table, address rules and project scope live in the NavigationBar README; this component does not keep its own copy. Ctrl/Cmd+K opens it with `>` typed (commands); deleting the `>` searches places in the same listbox. No typed character ever opens another dialog or switches context (WCAG 3.2.2).
- **Help is a row, not a mode.** The words "help", "keys" or "shortcuts" list "Keyboard shortcuts · Ctrl/Cmd+/", "Accessibility help for this view", "Accessible View" and "What this server offers"; Enter opens them. `?` is not a prefix.
- **Rows** name type, target build, locator words and where they open ("opens Compare"). A place row is a Go: Enter goes, Shift+Enter opens beside. A row that switches the inspected build says so before activation ("only on build-b · clears 4 checked rows on build-a"). Results that exist only in another project read "in corpus-beta · not open"; Enter lands on the cross-project StateNotice.
- **Actions arm, never post.** Action labels come from the catalog; the design system names no action ids. Picking an action arms the ActionStrip with its target bound from the selection and focuses Run; it never posts. Unavailable actions stay in the list, `aria-disabled`, with the reason ("needs a function selection"). A job row shows its StageChip as text.
- Previews are cache-only: Alt+↓ peeks the highlighted result without fetching. Recent actions and the recent query history are per viewer, in durable workspace state.
- Narrow: below 700px the palette is a full-width sheet, rows wrap to two lines (name and type; build and destination), per-build glyphs collapse to "on 3 of 5 builds", prefix chips wrap, and rows are 44px.

**Scripts section (future).** This section appears only once scripts are catalog entries (parity C05); until then there is no Scripts section and no key. When it exists, it sits after Actions and lists recent scripts first. Enter opens the script's run confirm (target builds named); it never runs the script. There is no new default key: the Quick Action launcher is this palette section.

**Linking**

- **Publishes:** nothing itself. A place pick navigates like its link (`entity`, `build`, `addr`, `job`, `receipt`, `node`; one history stop). An action pick writes the ActionStrip, never the location.
- **Follows:** the primary selection (actions bind it: "Match siblings for ResourceRef::Resolve"); results come from stored indexes of the active project only. Not holdable.
- **Targets rendered:** address or symbol → the Code Browser at that build · logical id → Compare with the CounterpartMatrix · job → the dock Jobs record · receipt → the receipt card · basis → the ProvenanceStamp detail · pipeline node → the PipelineMap node · mark or program bookmark → its address.
- **Peek source:** Alt+↓ on the highlighted result reads its cached Peek content (listing lines, facts, the stored job record, the node's model text); nothing is decompiled or fetched.
- **Absent copy:** "only on build-b · choosing it switches the inspected build" · "not searched: build-d, not loaded" · "in corpus-beta · not open" · "No results in stored indexes · Search the program for ‘‹q›’…" (the second part is an option row that opens SearchWorkbench prefilled in text mode, Ctrl/Cmd+Shift+F; nothing runs until its Enter) · the unavailable reason ("needs a function selection").
- **Target-size exception:** none; options are 28px rows (44px below 700px and with a coarse pointer).

**Keyboard**

- ↑/↓ move, Enter picks, Shift+Enter opens a place beside, Alt+↓ peeks, ↑ in an empty field recalls history. Esc follows the one Esc order in the Keymap section: the palette is a modal, so Esc closes it and returns focus to its invoker.

**Accessibility**

- APG Combobox and grouped Listbox inside a modal dialog, with `aria-activedescendant`; unavailable options carry `aria-disabled` and a description. The result count is a polite status once it settles.

**Removes switching:** choosing the right list view before searching, and reopening the palette for places versus verbs. J05 (`~gate-4`, 5 → 1) is credited to U178; J38's path to the job row is `g j` (U188).
