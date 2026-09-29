# NavigationBar

The row that says where you are and gets you back: Back and Forward with a recent-locations list, one go-to-anything field, breadcrumbs with sibling menus, the pane's sync state, Reload and Copy link.

**Use it** once per workspace, under the analysis tabs and above the center panes. It owns history and the deep link. It never runs an action.

**Consumer provides** the history stack (location, build, address, one snippet, time, and whether an edit was saved there); go-to results grouped by kind; the breadcrumb path (project › build › section › function) with each level's siblings; the focused pane's sync group; and the canonical URL for the current state.

- **History.** Back and Forward restore selection and viewport (scroll row and caret). Each explicit navigation (Enter, click, Open, a go-to pick) pushes one entry. Hover, peek, focus and typing never do. The **Recent** list shows the location, its build and address with one `type-code-small` snippet, the time, "✎ edited" where an edit was saved, and an **Edited only** filter. The current entry uses the selection shape and the word "current".
- **Go to anything** is one combobox for addresses, symbols, logical ids, jobs, receipts and pipeline nodes. With no prefix every kind is searched and results are grouped by kind. Scope prefixes:

| Prefix | Finds | Example |
|---|---|---|
| `@` | symbol | `@ResourceRef::Resolve` |
| `:` | address in the inspected build; `build-b:` names another build | `:0041b210`, `build-b:0041b2c0` |
| `#` | logical id | `#88` |
| `!` | job | `!a3f9` |
| `%` | receipt | `%7c21` |
| `~` | pipeline node (pipeline-model.json id) | `~gate-4`, `~lane-C` |
| `>` | command; hands the text to CommandPalette | `>match siblings` |

- A result that exists only on another build says so before it is chosen ("only on build-b · choosing it switches the inspected build"). Typing never navigates; only Enter or a click does. Ambiguous text, such as a hex string that is also a job id, lists both groups and never jumps. An address with no build prefix resolves in the inspected build only.
- **Breadcrumbs**: project › build › section › function, then the current address in `address`. Each level is an `.ad-link` with a visible level kicker and a 24px ▾ sibling menu. The build menu lists every build with its LocatorGlyph for the current logical entity. Choosing a build keeps the entity where a counterpart exists; otherwise it opens that build with a StateNotice explaining the absence.
- **Sync group**: a chain line icon plus words. "Linked · sync A" means the focused pane follows the selection; "Unlinked · held on ‹entity›" (broken chain, word first) means it does not. It is a toggle button with `aria-pressed`.
- **Reload** re-reads stored evidence for the view. It never reanalyzes.
- **Copy link** copies the canonical URL and says "Link copied" in the polite region.
- Surfaces: `pane` bar with 1px `line` rules, controls at `control-h-comfortable`, the field in a `well` framed by `line-control`, popups on `dialog-bg` with `shadow-popup`. Menu rows are 28px with a mono snippet line; the active row uses `row-selected-bg` plus the 3px `accent` bar.

**Deep link contract**

Both `/dashboard` on 8080 and `/react/` parse and emit the same parameters, so a link copied on one opens the same state on the other. Legacy names are still read and rewritten to the canonical ones.

| Parameter | Carries | Legacy name |
|---|---|---|
| `project` | active project | `slug` |
| `entity` | logical entity id | `logical_id` |
| `build` | inspected concrete build | `binary` |
| `addr` | address in `build`; requires `build` | `addr` |
| `ws` | workspace: `code`, `compare`, `recovery`, `evidence` | — |
| `views` | analysis tab | `tool` |
| `hold` | repeatable: held side panes and kept peeks, as `kind:id@build` | `pin` |
| `cmp` | compare pair, `build-a..build-b` | — |
| `node` | any pipeline-model.json node id: `stage-0`…`stage-8`, `gate-0`…`gate-8` (no `gate-2`), `lane-A`…`lane-E`, `ladder-A`…`ladder-F`, `lock-1`…`lock-5`, `failover-rule`, `export-*`, and nested `lane-X-card-N`, `ladder-X-N` | — (`focus` still scrolls to a section) |
| `job`, `receipt` | the job or receipt opened from go-to or a peek | — |
| `f` | repeatable filters as `axis:value`, for example `fact.local_match:failed`, `xref.dir:in`, `xref.scope:token` | — |

- Not carried: the checked batch set, drafts, open peeks, dock layout, density, and any action or admission. A link is a place, never a command.
- Opening a link never imports, analyzes or starts recovery. An unavailable project or program shows as unavailable.
- An explicit URL wins over a restored session tab.
- A target that no longer resolves keeps the original context and offers the nearest valid context and a search. The URL changes only when the operator picks.
- `addr` without `build` shows a notice listing builds with their locator glyphs. Nothing is guessed.
- The viewport (scroll row, caret) lives in the history entry, not in the URL.

**Keyboard**

- Alt+← and Alt+→ go back and forward. The Recent button opens with Enter, Space or ↓; ↑↓ move, Enter goes, Space toggles Edited only, Esc closes and returns focus.
- Ctrl/Cmd+P focuses go to. Ctrl/Cmd+G focuses it with `:` typed. ↑↓ move through results; Enter goes; Esc clears the list, and a second Esc returns focus to where it was before.
- In go to, Alt+↓ opens the list when it is closed (APG) and peeks the highlighted result when it is open.
- Breadcrumbs are links in Tab order, each followed by its ▾ menu button (APG Menu Button).
- Shift+F10 on any crumb or history row offers Open, Open to the side, Peek and Copy link.

**Accessibility**

- The breadcrumb is `<nav aria-label="Breadcrumb">` around an ordered list; the last crumb has `aria-current="location"`. Level kickers are visible. Each ▾ is named for what it lists ("Other builds for ResourceRef::Resolve") and carries `aria-haspopup="menu"` and `aria-expanded`.
- Back and Forward are named for their destination ("Back to Actor::LoadFromTemplate") and expose `aria-keyshortcuts`. Recent is a menu with a `menuitemcheckbox` for Edited only; the current entry has `aria-current="location"`.
- Go to is an APG combobox with a grouped listbox and `aria-activedescendant`; the result count goes to the polite region. Identifiers carry `translate="no"`.
- WCAG 3.2.1 and 3.2.2: focus and typing never navigate or switch the build. A build change is stated before activation and announced after it ("Inspected build: build-b").
- WCAG 4.1.3: "Link copied", result counts and build switches are polite status messages. Nothing is announced per keystroke except the count.
- Every control is at least 24px and 44px below 700px. The bar wraps; nothing scrolls sideways. The sync state is an icon plus words, never the icon alone.

**Removes switching:** opening the Functions list to find a symbol, the Compare workspace to reach a counterpart build, the Jobs dock or Evidence workspace to find a job or receipt by id, and repeated Back presses to return somewhere recent.

**Location schema**: the canonical parameter and alias table is in the Linked views guideline; this component renders it and does not keep its own copy. `tab` and `pin` are read as aliases of `views` and `hold`.
