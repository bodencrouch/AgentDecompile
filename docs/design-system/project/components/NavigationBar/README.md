# NavigationBar

The row that says where you are and gets you back: Back and Forward with the Recent menu, the one go-to-anything field, breadcrumbs with sibling menus, the Update panes control, Layout, Reload and Copy link.

**Use it** once per workspace, under the Workspaces tablist and above the CounterpartStrip, the PipelineBreadcrumb and the center panes. It owns history and the deep link. It never runs an action.

**Consumer provides** this tab's history stops (label, entity, build, address, one snippet with its read time, stop time, and whether an edit was saved there) and the older Recent entries from durable workspace state; go-to results grouped by kind, with the coverage searched; the breadcrumb path (project › build › section › function) with each level's siblings; for the Build menu, each build's counterpart address, divergence class, identity-edge word and locator word for the current entity; the Update panes mode; the active worklist, if any; and the canonical URL for the current state.

- **History** follows the Linked views History rules; this component renders them.
  - Back and Forward act on the primary history, the same stack as the browser buttons, Alt+←/→ and mouse buttons 4 and 5. They restore workspace, views, split, viewport and the focused element, and never open, close or re-point held panes or kept cards.
  - Back is named for its destination ("Back to Actor::LoadFromTemplate"). When the move changes the program, its description says what clears first: "Back · clears 12 checked rows on build-a". At the tab's first stop in-app Back is `aria-disabled` with "no earlier location in this tab".
  - Back has no history menu, no Alt+↓ and no long-press.
- **Recent** is an APG Menu Button beside Back; right-click on Back opens the same menu.
  - It lists up to 20 of this tab's stops. Each shows its label, build and address, one `type-code-small` snippet labelled "as read ‹time›", the stop time and "✎ edited" where an edit was saved. The current stop has the selection shape and the word "current".
  - The **Changed since visited** filter (a `menuitemcheckbox`) keeps the stops whose entity and build appear in a job's recorded change units after the visit, each with its job link and time. Jobs that recorded no units, or only reused evidence, do not qualify.
  - Picking a stop in this tab traverses with `history.go`. Picking an older durable entry is a Go. Recent is client state; it is never evidence.
- **Go to anything** is one APG combobox over the one engine that CommandPalette shares.
  - Ctrl/Cmd+P focuses it. Ctrl/Cmd+G focuses it with `:` typed; its first, highlighted row is the last address jump ("Last: build-b:0041b2c0"), so Enter repeats it visibly. Ctrl/Cmd+K opens the modal CommandPalette with `>` typed.
  - Below `bp-compact` (1100px) the field collapses to a button, and P and G open the same engine in the palette dialog.
  - No typed character ever opens a dialog or changes context (WCAG 3.2.2). `>` lists commands inline in the same listbox. The words "help", "keys" or "shortcuts" list the option row "Keyboard shortcuts · Ctrl/Cmd+/", which opens the sheet on Enter.
  - The empty query lists Recent locations, Marks, Recent actions and Recent jobs. ↑ in an empty field recalls earlier queries.

| Prefix (first character only) | Finds | Example |
|---|---|---|
| `@` or `::` | symbol | `@ResourceRef::Resolve` |
| `:` | address in the inspected build first; `build-b:` names another build | `:0041b210`, `build-b:0041b2c0` |
| `#` | logical id | `#88` |
| `!` | job | `!a3f9` |
| `%` | receipt, or a basis digest | `%7c21`, `%9f3c` |
| `~` | pipeline node (`pipeline-model.json` id) | `~gate-4`, `~lane-C` |
| `>` | command, listed inline | `>match siblings` |
| `$` | string | `$resource.cfg` |
| `'` | marks and program bookmarks | `'a`, `'before repair` |

- `?` is not a prefix, because decorated names start with it; a query that starts with `?` is searched as a symbol. The detected scope shows as a removable chip in the field ("Scope: addresses ×"). Prefix chips under the field insert their prefix; they are the reliable path on touch and on dead-key layouts.
- **Addresses.** `:0041b210` resolves in the inspected build first, highlighted. Other builds whose mapped sections contain the same number follow as separate rows, "same number on build-c · a different place, not a counterpart". Counterparts come only from recorded edges. A link whose `addr` has no `build` lists the builds that contain it; nothing is guessed.
- **Scope and honesty.** Search covers stored indexes of the active project only, with coverage in words ("not searched: build-d, not loaded"). Jobs, receipts and marks that exist only in another project read "in corpus-beta · not open"; Enter lands on the cross-project StateNotice (Switch armed, Stay). A row that switches the inspected build says so before activation, in its text and `aria-describedby`: "only on build-b · clears 4 checked rows on build-a". Typing never navigates; Enter or a click does. Ambiguous text, such as a hex string that is also a job id, lists both groups and never jumps.
- Rows name type, target build, per-build locator words, destination, an action's binding and a job's StageChip.
- **Breadcrumbs**: project › build › section › function, then the cursor address in `address`. Each level is an `.ad-link` with a visible level kicker and a 24px ▾ sibling menu. The build crumb's Peek is the program's Info.
- **The Build menu** (the build crumb's ▾, also `g b`) is a flat APG Menu, one item per build.
  - Each item shows the counterpart address, the divergence class (1↔1, 1↔N, ≠) and the identity-edge word (accepted or candidate), in words and in its accessible name.
  - An absent build is the word "absent" as an `aria-disabled` item, never a link. Unresolved says "unresolved" the same way.
  - Candidate and ambiguous items carry "Opening one does not accept it". A contested build lists both candidates, "contested · no winner".
  - Picking an item is a Go: one stop, the entity kept, the cursor mapped only through recorded anchor pairs. It never re-resolves an address into another build. A program that is not open reads "Not loaded · Open build-c"; opening it is explicit.
- **Update panes: As I move / On Enter** is a two-option radio group. "On Enter" switches every following pane to commit-on-Enter; every following pane's header says its mode ("Follows · on Enter"). Below 700px it is forced to "On Enter" and the collapsed bar says so. The follow and hold state of each pane lives in that pane's header (Hold this pane), not here.
- **Worklist.** While a worklist is active, the MarksList stepper sits under this bar at 700px and wider. Below 700px the bar shows one chip button, "Worklist 4 of 12", that opens the stepper as a bottom sheet.
- **Layout ▾** is LayoutPresets' menu button. **Reload** re-reads stored evidence for the view; it never reanalyzes. **Copy link** copies the canonical URL and says "Copied link to ResourceRef::Resolve, build-a" in the polite region.
- Surfaces: `pane` bar with 1px `line` rules, controls at `control-h-comfortable`, the field in a `well` framed by `line-control`, popups on `dialog-bg` with `shadow-popup`. Menu rows are 28px with a mono snippet line; the active row uses `row-selected-bg` plus the 3px `accent` bar.
- Narrow (below 700px): rows wrap to two lines (name and type; build and destination), per-build glyphs collapse to "on 3 of 5 builds" with the list in `aria-describedby` and Peek, the palette is a full-width sheet whose prefix chips wrap, and rows are 44px. Check at 598×912 and 320×256.

**Location**

`location-schema.json` is the parameter, alias and history contract; this component renders it and keeps no copy. Copy link emits readable canonical names only: `project`, `session`, `entity`, `build`, `addr`, `ws`, `panel`, `views`, `cmp`, `hold`, `keep`, `dock`, `job`, `receipt`, `type`, `f`, `q`, `page`, `t`, `node`, `wl`.

- `hold` carries held center panes only (`kind:id@build[:addr][~basis]`, at most two); `keep` carries Kept cards. `views` names co-visible code views. `node` is any `pipeline-model.json` id.
- Never in a link: the checked set, drafts and credentials. A link is a place, never a command; opening it reads existing analysis only.
- A link that names another project never switches: it shows the cross-project StateNotice. An explicit URL wins over a restored session tab only within the active project.
- A target that no longer resolves keeps the original context and says so in words ("no longer resolves on build-b"); the URL changes only when the operator picks.

**Linking**

- **Publishes:** the primary location on a go-to pick, a crumb, a Build menu item or an older Recent entry (Go, one history stop); a Recent stop in this tab traverses with `history.go` instead. `ws` and `panel` when a pick opens a workspace or a full corpus view. The Update panes mode is per-viewer view state and never in the URL.
- **Follows:** the primary location. The breadcrumbs, the Build menu and the Recent current mark update after the settle. Not holdable.
- **Targets rendered:** project · build → the Navigator program row · section → the Listing at the section start · function and address → the Code Browser at that build · counterpart build items with their edge word · logical id → Compare · job → the dock Jobs record · receipt and basis digest · pipeline node → the PipelineMap node · string, mark and program bookmark → their address. Link names read "Address 0041b210, build-b".
- **Peek source:** Alt+↓ on a highlighted result, crumb or Recent entry reads its cached Peek (listing lines, facts, the stored job record, the node's model text). The build crumb's Peek reads the stored program inventory.
- **Absent copy:** "absent" and "unresolved" (disabled Build menu items) · "Opening one does not accept it" · "contested · no winner" · "no earlier location in this tab" · "not searched: build-d, not loaded" · "in corpus-beta · not open" · "same number on build-c · a different place, not a counterpart" · "No results in stored indexes."
- **Target-size exception:** none. Controls and ▾ buttons are 24px or larger; 44px below 700px and with a coarse pointer.

**Keyboard**

- Alt+← and Alt+→ go back and forward on the primary history; they are not intercepted in text fields or edit mode.
- The Recent button opens with Enter, Space or ↓, and right-click on Back opens the same menu. ↑/↓ move, Enter picks, Space toggles Changed since visited.
- Ctrl/Cmd+P, Ctrl/Cmd+G and Ctrl/Cmd+K as above. In the field ↑/↓ move through results, Enter goes, Shift+Enter opens beside, and Alt+↓ opens the list when it is closed (APG) and peeks the highlighted result when it is open.
- Breadcrumbs are links in Tab order, each followed by its ▾ menu button (APG Menu Button). `g b` in a list, grid or code well opens the Build menu.
- Update panes is an APG radio group: one tab stop, arrows move and select.
- Shift+F10 on a crumb or Recent entry opens the one link menu (Linked views).
- Esc follows the one Esc order in the Keymap section (`keymap.json` `escapeOrder`).

**Accessibility**

- The breadcrumb is `<nav aria-label="Location">` around an ordered list; the last crumb has `aria-current="location"`. Level kickers are visible. Each ▾ is named for what it lists ("Other builds for ResourceRef::Resolve") and carries `aria-haspopup="menu"` and `aria-expanded`.
- Back and Forward are named for their destination and expose `aria-keyshortcuts`; a disabled Forward stays focusable with `aria-disabled`. Recent is a menu with a `menuitemcheckbox` for Changed since visited; the current entry has `aria-current="location"`.
- Go to is an APG combobox with a grouped listbox and `aria-activedescendant`; the result count goes to the polite region once it settles. Identifiers carry `translate="no"`.
- WCAG 3.2.1 and 3.2.2: focus and typing never navigate or switch the build. A build change is stated before activation and announced after it ("Inspected build: build-b").
- WCAG 4.1.3: copy confirmations, result counts and build switches are polite status messages. Nothing is announced per keystroke except the settled count.
- Every control is at least 24px, and 44px below 700px and with a coarse pointer. The bar wraps; nothing scrolls sideways.

**Removes switching:** J05 (from a diagram concept to the live items at it) goes from 5 switches to 1 with `~gate-4`, credited to U178. The Build menu carries J26's position-keeping build switch, credited to U175. Opening the Functions list to find a symbol, or the dock to find a job or receipt by id, becomes one field.
