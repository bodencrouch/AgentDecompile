# SessionTab

A persistent project session tab with its project-kind chip.

**Consumer provides** the human title, the kind (`gpr`, `shared-fs`, `shared-http`, `bin`, `draft`), selected state and a close action.

- Active tab: `pane` fill, 2px `tab-active-rule` top rule, `ink-strong` title. Inactive: `ink-muted` on `chassis`.
- The chip is outlined in its `kind-*` color with an uppercase word; the word always accompanies the color.
- One active project and mutation context: opening another project offers an explicit switch or merge with both identified. Tabs are views, not competing writers.
- Double-click renames inline. Closing a tab clears its session, never corpus binaries. A saved tab is not proof its locator is reachable; show a StateNotice when it is not.
