# ContainerTree

A dismantled delivery artifact as a navigable tree: installer payload, image sections, resources and sidecars, each with origin and identity.

**Consumer provides** the hierarchy with member offsets, parser, content hash, and protection or packing state per node.

- Mono rows; the selected node uses `row-selected-bg`. Right column shows size, parser and hash in `ink-muted`.
- Unsupported or protected regions stay marked with a word, never hidden. Layout is context: the tree is a first-class view, not a side quest.
- Extraction is bounded; nested archives open recursively. The picture expands only as members are actually discovered.
