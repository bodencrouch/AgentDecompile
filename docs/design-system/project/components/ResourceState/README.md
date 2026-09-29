# ResourceState

A mutable resource's two separate state machines: access (free, owned, quarantined) and publication (current, revoked), with owner kind.

**Consumer provides** the resource kind and identity, its lock node, access state with its evidence, publication state and generation, and the owner (managed job, or external with process identity as reported).

- Access: ○ free · ● owned · ⊠ quarantined. Publication: current · revoked (struck). Owner: managed · external. Each is a glyph plus a word.
- Quarantine names the occupied resource and the unresolved access evidence. A lease countdown is never a release time. A byte match, timeout, changed PID or new lock file never clears it.
- Kinds: program, corpus-writer, output, PDB, Wine, save, display, port, channel, storage.
- Ownership is never inferred from job labels. An external owner is never offered kill or restart.

**Linking**

- **Publishes:** nothing; entering a resource from the PipelineMap is the map's Go.
- **Follows:** the dock's resource filter (`dock=jobs&f=resource:…`) or its host record; not holdable.
- **Targets rendered:** resource → its lock node (`?node=lock-3`), which opens the Jobs dock filtered by that resource with the OwnershipPanel expanded · managed owner → the owning job's dock record · the generation → the publication receipt card · the build a resource belongs to → the Code Browser for that build. External process identity is words.
- **Peek source:** the stored resource and lock records as the backend reported them.
- **Absent copy:** "owner: unknown" · "process identity: not reported" · "access evidence unresolved" · "not released: end of access not corroborated".
- **Target-size exception:** spacing: at most one link per cell.

**Accessibility**

- A table with the resource as row header; access and publication are separate columns with glyph plus word; "revoked" is struck and written.
