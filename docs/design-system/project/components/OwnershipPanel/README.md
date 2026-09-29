# OwnershipPanel

The resource-scoped ownership panel and the failover rule: which points serialize with one owner, and how an affected branch stops while siblings continue.

**Consumer provides** the lock rows and the failover rule lines. In the app's expanded form (a lock entered from the PipelineMap), also each lock's owner exactly as the backend reports it: managed or external, PID and start time, command summary, cwd and queued admissions.

- Lock glyph: 18×14 body in `lock` at `opacity-lock`, `radius-chip`, shackle at `stroke-lock`. Rows at a 24px pitch.
- Failover rule box: dashed `dash-failover` in `lock`.
- Caption: "Atomic resource-set admission; measured process-tree budgets and pressure; external owners remain external."
- The lock is always named in words beside the glyph; the salmon glyph is never the only carrier.
- Ownership is never inferred from job labels. An external owner is never offered kill or restart. An external owner with no job record reads "external · no job", with its process identity as reported, else "unknown".
- The app form is also the owner-and-resource field of a FailureRecord (inline, as reported).

**Linking**

- **Publishes:** nothing. It has no release, kill or restart verb, and never changes the selection.
- **Follows:** print form: nothing. App form: the Jobs dock's resource filter (`dock=jobs&f=resource:lock-3`), commit-on-Enter: Enter on a lock in the PipelineMap pushes one stop to that filter with this panel expanded, and the primary selection does not move. Not holdable.
- **Targets rendered:** each lock row → its pipeline node (`?node=lock-1`…`lock-5`) · failover rule → `?node=failover-rule` · the owning job → its dock Jobs record (`job=`) · each queued admission → its job record. In docs the rows link to the outline anchors (`agentdecompile-recovery-pipeline.outline.md#lock-1`). Link names read "Lock lock-3, compiler outputs and Wine context, owned by job 77c0, external".
- **Peek source:** Alt+↓ on a lock row reads the stored lock and job records exactly as the backend reported them (owner kind, PID and start time, command summary, cwd, queued admissions).
- **Absent copy:** "owner: unknown" · "process identity: not reported" · "external · no job" · "free" when nothing owns the lock. Never a guessed owner.
- **Target-size exception:** none; rows are 24px and each row's link spans its label. With a coarse pointer each lock row in the app form carries one 44px row-menu button with the same link menu; there is no long-press.

**Accessibility**

- Rows are a list; each reads "lock, writes to one Ghidra program's analysis DB". The glyph SVG is `aria-hidden`. In the SVG each lock is a `<g id="lock-1">` and the outline is the primary accessible form.

**Removes switching:** opening the Jobs dock, the process list and the diagram to learn who owns a lock and what it serializes (J04, J28).
