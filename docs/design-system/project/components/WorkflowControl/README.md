# WorkflowControl

The one pipeline control: pause or resume admission for the active project, with a scope sentence that says exactly what it drains and which lanes it does not own.

**Consumer provides** the scope name, the admission state from real owner and lock state, the accepted jobs that pausing would drain, the stages it admits into, the separately owned lanes to surface, and any external jobs.

- There is no Start. Opening a project, adding binaries or resuming admits eligible missing work by itself; reopening admits nothing that already has a receipt.
- Pause stops admitting into this scope and drains what it accepted. It is not cancel and never reports "safe-paused" until the drain is confirmed.
- **Scope sentence** beside the control, whose nouns are pipeline node links: "Pausing drains admission for [stages 1–8]; [lanes C] and [E] are separately owned." It is generated from the model and the backend's owner state, never hand-written.
- **What this pauses**: an APG disclosure listing the accepted jobs that would drain (job links), what is not controlled here, and the external jobs that stay visible.
- The control disclaims runtime reuse, distributed workers and read-only indexing; show them beside it (dashed chips) without start or stop verbs.
- A pre-existing external job stays visible and blocks duplicate admission. No per-stage Run buttons anywhere; nodes are links, never Run buttons.

**Linking**

- **Publishes:** nothing. Pause and Resume are the one catalog action this control arms; they never change the location.
- **Follows:** `project` (the admission scope is the active project) and its owner and lock state; not holdable.
- **Targets rendered:** "stages 1–8" → `?node=main-pipeline` · each lane → `?node=lane-C`, `?node=lane-E` · stage 0's gate → `?node=gate-0` · each owned job and each external job → its dock Jobs record · the scope's lock → its node (`?node=lock-2`). Link names read "Pipeline node lane-C, runtime reuse, separately owned".
- **Peek source:** Alt+↓ on a node link reads the PipelineMap's cached counts and lock owner; on a job, the stored job record.
- **Absent copy:** "Admission state unknown · owner not reported" · "external owner · not controlled here" · "Pausing · draining 1 accepted job" (never "safe-paused" before the drain is confirmed).
- **Target-size exception:** inline: node links sit in the scope sentence; the control button is 28px.

**Keyboard**

- APG Toolbar: one tab stop, ←/→ between Pause and What this pauses; Enter or Space activates. Links in the sentence are in Tab order after the toolbar.

**Accessibility**

- The control is named by its scope ("Admission for corpus-alpha"); its state is text, not only the glyph. The disclosure keeps focus on its button. A drain completing is announced once, politely.

**Removes switching:** opening the pipeline map, the Jobs dock and the lane views to learn what Pause will drain and what it does not own (J29).
