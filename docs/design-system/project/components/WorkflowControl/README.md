# WorkflowControl

The one pipeline control: pause or resume admission for the active project.

**Consumer provides** the scope (project name), the current admission state, and what pausing will drain.

- There is no Start. Admission begins on its own when a project is opened, binaries are added or work resumes, and reopening admits nothing that already has a receipt.
- Pause stops admitting new work into this project and drains what it already accepted. It is not cancel, and it claims nothing over lanes it does not own (runtime reuse, distributed workers, read-only indexing).
- The state cell names what is happening in words ("Admitting · 2 owned jobs" / "Draining 1 job"). No per-stage Run buttons anywhere.
