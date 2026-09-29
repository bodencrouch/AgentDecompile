# SessionTab

A persistent project session tab with its project-kind chip. Each tab restores its own place; activating a tab of another project never switches the project by itself.

**Consumer provides** the human title, the kind (`gpr`, `shared-fs`, `shared-http`, `bin`, `draft`), selected state, the project the session belongs to, and the session's saved location (the `session` value) from durable workspace state.

- Tabs are `button role="tab"` in a tablist named "Sessions". The tablist contains only tabs. Active tab: `pane` fill, 2px `tab-active-rule` top rule, `ink-strong` title. Inactive: `ink-muted` on `chassis`.
- The chip is outlined in its `kind-*` color with an uppercase word; the word always accompanies the color.
- **Restore reads now.** A session tab restores its own workspace, views, selection, holds, scroll and focused element from durable workspace state (F23) and `history.state`. The data is read now; nothing is re-run, and expensive panes say "Not loaded. Open to read it." until Enter.
- **Another project.** Activating a tab whose project is not the active one shows the cross-project StateNotice (Switch armed, Stay), naming both projects. It never switches on focus or activation alone, because opening a project admits its eligible missing work.
- **Close.** The visible × is a pointer affordance only: `aria-hidden="true"`, `tabindex="-1"`, at least 24px. Keyboard users close the focused tab with Delete, which each tab's `aria-describedby` states ("Delete closes this session tab"), and the tab's link menu has "Close ‹title›". Focus then moves to the neighbouring tab. Closing is never a side effect of focus. Closing a tab clears its session, never corpus binaries.
- **Rename** in place with F2 or a double-click.
- One active project and mutation context. Tabs are views, not competing writers. A saved tab is not proof its locator is reachable; show a StateNotice when it is not.

**Linking**

- **Publishes:** `session` when a tab of the active project is activated (one history stop); the tab then restores its own `ws`, `views`, `entity`, `build`, `addr`, `hold`, `keep`, scroll and focused element. A tab of another project publishes nothing until Switch is chosen on the StateNotice.
- **Follows:** nothing else; the title and kind come from the project record. An explicit URL wins over a restored tab only within the active project. Not holdable.
- **Targets rendered:** none inside the tab; the tab itself is the session. The kind chip is not a link.
- **Peek source:** none.
- **Absent copy:** "Unavailable · the project locator for team-repository is not reachable. Its receipts are kept." (a StateNotice in the tab's panel, never an empty new project).
- **Target-size exception:** none; tabs are 32px tall and the pointer-only × is 24px; 44px below 700px and with a coarse pointer.

**Keyboard**

- APG Tabs with manual activation: ←/→ move focus, Home/End go to the first and last tab, and Enter or Space activates. Focus alone never activates a tab.
- Delete closes the focused tab and moves focus to its neighbour. F2 renames. Shift+F10 opens the tab's link menu (Rename, Close ‹title›, Close others, Move tab left, Move tab right). Moving a tab is menu-only (`tabs.move`); Ctrl+Shift+PageUp/PageDown belong to the browser.

**Accessibility**

- The tablist is named "Sessions" and is separate from the "Workspaces" tablist. Each tab's name is its title plus kind ("corpus-alpha, shared folder"), and its description says "Delete closes this session tab". The active tab has `aria-selected="true"` and `tabindex="0"`; the others `-1`.
- Session tabs never switch projects on focus (WCAG 3.2.1).

**Removes switching:** re-navigating to the same workspace, function and address after switching sessions. J25 (a link between the two surfaces) is credited to U172.
