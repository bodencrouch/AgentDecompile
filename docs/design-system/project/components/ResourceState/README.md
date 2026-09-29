# ResourceState

A mutable resource's two separate state machines: access (free, owned, quarantined) and publication (current, revoked), with owner kind.

**Consumer provides** the resource kind and identity, its lock node, access state with its evidence, publication state and generation, and the owner (managed job, or external with process identity as reported).

- Access: ○ free · ● owned · ⊠ quarantined. Publication: current · revoked (struck). Owner: managed · external. Each is a glyph plus a word.
- Quarantine names the occupied resource and the unresolved access evidence. A lease countdown is never a release time. A byte match, timeout, changed PID or new lock file never clears it.
- Kinds: program, corpus-writer, output, PDB, Wine, save, display, port, channel, storage.
- Ownership is never inferred from job labels. An external owner is never offered kill or restart; one with no job record reads "external · no job".
- It renders inline, as reported, in a FailureRecord's owner-and-resource field; unknown values say "unknown".

**Linking**

- **Publishes:** nothing; entering a resource from the PipelineMap is the map's Go.
- **Follows:** the dock's resource filter (`dock=jobs&f=resource:…`) or its host record; not holdable.
- **Targets rendered:** resource → its lock node (`?node=lock-3`); Enter on that node in the PipelineMap pushes one stop to the Jobs dock filtered by that resource (`dock=jobs&f=resource:lock-3`) with the OwnershipPanel expanded · managed owner → the owning job's dock record · the generation → the publication receipt card · the build a resource belongs to → the Navigator program row for that build (the inspected build does not change). External process identity is words.
- **Peek source:** the stored resource and lock records as the backend reported them.
- **Absent copy:** "owner: unknown" · "process identity: not reported" · "external · no job" · "access evidence unresolved" · "not released: end of access not corroborated".
- **Target-size exception:** spacing: at most one link per cell. With a coarse pointer each row carries one 44px row-menu button with the same link menu; there is no long-press.

**Accessibility**

- A table with the resource as row header; access and publication are separate columns with glyph plus word; "revoked" is struck and written.
