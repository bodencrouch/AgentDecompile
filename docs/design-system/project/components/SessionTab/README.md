# SessionTab

A persistent project session tab with its project-kind chip; each tab restores its own workspace, views, selection, scroll and focus.

**Consumer provides** the human title, the kind (`gpr`, `shared-fs`, `shared-http`, `bin`, `draft`), selected state, the session's saved location (the `session` value), and a close action.

- Tabs are `button role="tab"` in a tablist named "Sessions". Active tab: `pane` fill, 2px `tab-active-rule` top rule, `ink-strong` title. Inactive: `ink-muted` on `chassis`.
- The chip is outlined in its `kind-*` color with an uppercase word; the word always accompanies the color.
- Close is a separate 24px button named "Close ‹title›" beside the tab, outside the tab order; Delete on the focused tab does the same and moves focus to its neighbor.
- One active project and mutation context: opening another project offers an explicit switch or merge with both identified. Tabs are views, not competing writers.
- F2 (or double-click) renames inline. Closing a tab clears its session, never corpus binaries. A saved tab is not proof its locator is reachable; show a StateNotice when it is not.

**Linking**

- **Publishes:** `project` and `session` when a tab is activated (one history stop); the tab then restores its own `ws`, `views`, `entity`, `build`, `addr`, `hold`, scroll and focused element.
- **Follows:** nothing else; the title and kind come from the project record. An explicit URL wins over a restored tab. Not holdable.
- **Targets rendered:** none inside the tab; the tab itself is the session. The kind chip is not a link.
- **Peek source:** none.
- **Absent copy:** "Unavailable · the project locator for team-repository is not reachable. Its receipts are kept." (a StateNotice in the tab's panel, never an empty new project).
- **Target-size exception:** none; tabs are 32px tall and Close is 24px.

**Keyboard**

- APG Tabs with automatic activation (the panel is cached): ←/→ move, Home/End first and last; Delete closes the focused tab; F2 renames; Ctrl+Shift+PageUp/PageDown move the tab; Shift+F10 opens its menu (Rename, Close, Close others, Move).

**Accessibility**

- The tablist is named "Sessions" and is separate from the "Workspaces" tablist. Each tab's name is its title plus kind ("corpus-alpha, shared folder"). The active tab has `aria-selected="true"` and `tabindex="0"`; the others `-1`.

**Removes switching:** re-navigating to the same workspace, function and address after switching projects (J25).
