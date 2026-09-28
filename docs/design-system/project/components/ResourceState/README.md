# ResourceState

A mutable resource's two separate state machines: access (free, owned, quarantined) and publication (current, revoked), with owner kind.

**Consumer provides** the resource kind and identity, access state with its evidence, publication state and generation, owner (managed or external).

- Access: ○ free · ● owned · ⊠ quarantined. Publication: current · revoked (struck). Owner: managed · external.
- Quarantine names the occupied resource and the unresolved access evidence. A lease countdown is never a release time. A byte match, timeout, changed PID or new lock file never clears it.
- Kinds: program, corpus-writer, output, PDB, Wine, save, display, port, channel, storage.
