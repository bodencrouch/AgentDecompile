# OwnershipPanel

The resource-scoped ownership panel and the failover rule: which points serialize with one owner, and how an affected branch stops while siblings continue.

**Consumer provides** the lock rows and the failover rule lines. In the app's expanded form (a lock entered from the PipelineMap), also each lock's owner exactly as the backend reports it: managed or external, PID and start time, command summary, cwd and queued admissions.

- Lock glyph: 18×14 body in `lock` at `opacity-lock`, `radius-chip`, shackle at `stroke-lock`. Rows at a 24px pitch.
- Failover rule box: dashed `dash-failover` in `lock`.
- Caption: "Atomic resource-set admission; measured process-tree budgets and pressure; external owners remain external."
- The lock is always named in words beside the glyph; the salmon glyph is never the only carrier.
- Ownership is never inferred from job labels. An external owner is never offered kill or restart.

**Linking**

- **Publishes:** nothing. Diagram-only in the overview; in the app it never changes the selection and has no release, kill or restart verb.
- **Follows:** nothing in the diagram. The in-app expanded form follows the dock's resource filter (`dock=jobs&f=resource:…`).
- **Targets rendered:** in app renderings each lock row links to its pipeline node (`?node=lock-1`…`lock-5`) and the failover rule to `?node=failover-rule`; Enter on a lock in the PipelineMap opens the Jobs dock filtered by that resource key with this panel expanded, where the owning job links to its dock record (`job=`). In docs each row links to the outline anchor (`agentdecompile-recovery-pipeline.outline.md#lock-1`).
- **Absent copy:** "owner: unknown" and "process identity: not reported" when the backend does not report them; "free" when no owner holds the lock. Never a guessed owner.

**Accessibility**

- Rows are a list; each reads "lock, writes to one Ghidra program's analysis DB". The glyph SVG is `aria-hidden`. In the SVG each lock is a `<g id="lock-1">` and the outline is the primary accessible form.

**Removes switching:** opening the Jobs dock, the process list and the diagram to learn who holds a lock and what it serializes (J04, J28).
