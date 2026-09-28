# WorkflowControl

The one pipeline control: pause or resume admission for the active project, with its scope and the lanes it does not own.

**Consumer provides** the scope name, the admission state from real owner and lock state, what pausing would drain, and the separately owned lanes to surface.

- There is no Start. Opening a project, adding binaries or resuming admits eligible missing work by itself; reopening admits nothing that already has a receipt.
- Pause stops admitting into this scope and drains what it accepted. It is not cancel and never reports "safe-paused" until the drain is confirmed.
- The control disclaims runtime reuse, distributed workers and read-only indexing; show them beside it (dashed chips) without start or stop verbs.
- A pre-existing external job stays visible and blocks duplicate admission. No per-stage Run buttons anywhere.
