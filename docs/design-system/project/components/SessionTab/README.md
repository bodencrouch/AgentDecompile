# SessionTab

A persistent project session: one tab per open project or binary, with a kind chip.

**Consumer provides** the human title, the project kind (`gpr`, `shared-fs`, `shared-http`, `bin`, `draft`), selected state and a close action.

- The active tab is `pane` with a 2px `accent` top rule and `ink-strong` title; inactive tabs are `ink-muted` on `chassis`.
- The kind chip is outlined in its `kind-*` color with an uppercase mono label; the word always accompanies the color.
- Double-click renames inline. Closing a tab clears its session, never the corpus binaries.
- A saved tab is not proof that its locator is reachable; show a StateNotice in the workspace when it is not.
