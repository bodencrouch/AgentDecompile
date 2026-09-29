# WorkflowControl

The one pipeline control: pause or resume write admission for the active project, with a disclosure that says exactly what pausing stops, what drains and which lanes it does not own.

**Consumer provides** the project name, the admission state from real owner and lock state, and the backend's reported pause scope: the node ids it covers (write admission is `gate-0`), the lanes it does not own with their ownership (`lane-C`, `lane-E`), the admitted jobs that would drain, and any external jobs. When the backend does not report a scope, it provides nothing and the control says so.

- There is no Start. Opening a project, adding binaries or resuming admits eligible missing work by itself; reopening admits nothing that already has a receipt.
- **Pause new work** stops new write admission and drains what was already admitted. Its description reads "Stops starting new jobs; jobs already started finish". It is not cancel and never reports "safe-paused" or "Paused" until the drain is confirmed.
- **Visible words.** The state words are "Starting new work" · "Pausing · ‹n› job finishing" · "Paused"; the paused button reads **Resume new work**. Docs keep the term admission; the control never shows it.
- **What this pauses** is an APG Disclosure beside the toolbar, outside its roving set. It holds one sentence composed from the backend's reported scope, never hand-written and never from a fixed stage range, for example: "Pausing stops starting new jobs ([gate 0]) for corpus-alpha; jobs already started finish; lanes [C] and [E] are separately owned and keep running." When no scope is reported it says "Scope not reported". Below the sentence: the admitted jobs that would drain (job links), what is not controlled here, and the external jobs that stay visible. Node links in the sentence are links, never controls.
- The Pause new work button's `aria-describedby` carries a one-line summary of that sentence.
- The control disclaims runtime reuse, distributed workers and read-only indexing; they show beside it as plain chips with liveness words, without start or stop verbs.
- A pre-existing external job stays visible and blocks duplicate admission. No per-stage Run buttons anywhere; pipeline nodes are links, never Run buttons.
- **Narrow.** Below 700px the control wraps and collapses to its state glyph and word: ▸ while running ("▸ Starting new work"), ❙❙ only when paused ("❙❙ Paused"); its disclosure keeps the scope sentence, the drain state and the disclaimed lanes as dashed chips. The header keeps the project name and a wrapping scope sentence. Never a Start.

**Linking**

- **Publishes:** nothing. Pause and Resume arm the one catalog action this control owns and confirm it; they never change the location.
- **Follows:** `project` (the admission scope is the active project) and its owner and lock state. Not holdable.
- **Targets rendered:** write admission → `?node=gate-0` · each separately owned lane → `?node=lane-C`, `?node=lane-E` · each admitted and each external job → its dock Jobs record. Node ids come only from the backend's scope and exist in `pipeline-model.json`. Link names read "Pipeline node lane-C, runtime reuse, separately owned".
- **Peek source:** Alt+↓ on a node link reads the PipelineMap's cached counts and lock owner and the node's model text; on a job, the stored job record as of the dock's last read.
- **Absent copy:** "Scope not reported" · "New work state unknown · owner not reported" · "external owner · not controlled here" · "Pausing · 1 job finishing" (never "safe-paused" or "Paused" before the drain is confirmed).
- **Target-size exception:** node and job links sit inline in the scope sentence and rely on the WCAG 2.5.8 inline exception; the control's buttons are 28px, 44px below 700px and with a coarse pointer.

**Keyboard**

- APG Toolbar: one tab stop; ←/→ move between its controls; Enter or Space activates. The What this pauses disclosure button follows the toolbar in Tab order, and the links in its sentence follow the button.
- The disclosure never moves focus when it opens. Esc follows the one Esc order in the Keymap section.

**Accessibility**

- The toolbar is named by its scope ("New work for corpus-alpha"); its state is text, not only the glyph. A drain completing is announced once, politely.
- The disclosure reflows at 320×256; family, gate and ownership are words.

**Removes switching:** J29 (pause or resume admission and understand what it drains and which lanes it does not own) goes from 4 switches to 1: the disclosure beside the control, credited to U181.
