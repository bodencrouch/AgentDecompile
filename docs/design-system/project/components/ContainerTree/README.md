# ContainerTree

A dismantled delivery artifact as a navigable tree: installer payload, image sections, resources and sidecars, each with origin and identity.

**Consumer provides** the hierarchy with member offsets, parser, content hash, protection or packing state per node, and for each member that is an imported build, that build's id.

- Mono rows; the selected node uses `row-selected-bg` plus the 3px bar. Right column shows size, parser and hash in `ink-muted`.
- Unsupported or protected regions stay marked with a word, never hidden. Layout is context: the tree is a first-class view (a Navigator scope), not a side quest.
- A member that is an imported build shows that build as a link; a member that is not imported says "not imported" and offers nothing that imports on activation.
- Extraction is bounded; nested archives open recursively. The picture expands only as members are actually discovered.

**Linking**

- **Publishes:** `build` (and its function list) when Enter goes to a member that is an imported build; selecting a node without a build writes nothing.
- **Follows:** `project`; the tree marks the node holding the inspected build without moving focus. Not holdable.
- **Targets rendered:** an imported member → the Code Browser for that build · a section node → the Listing at the section start in that build · a member's extraction receipt → its receipt card · a duplicate member → the build it aliases.
- **Peek source:** Alt+↓ on a member reads the stored extraction record (offset, parser, hash, protection).
- **Absent copy:** "not imported" (plain) · "protected region · unsupported parser" · "not discovered yet" for unexpanded archives. Never an automatic import.
- **Target-size exception:** none; tree rows are 24px.

**Keyboard**

- APG Tree view: ↑/↓ move, → opens or moves to the first child, ← closes or moves to the parent, Home/End, typeahead. Enter goes to a member's build; Alt+↓ peeks; Shift+F10 opens the one link menu.

**Accessibility**

- `role="tree"` named for the artifact; items carry `aria-level`, `aria-expanded` and `aria-selected`. Expander glyphs are `aria-hidden`; protection states are words.

**Removes switching:** opening the import list and the project tree to find which build an extracted member became (J30, J36).
