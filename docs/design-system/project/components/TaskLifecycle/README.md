# TaskLifecycle

A task's position in its lifecycle rail, with terminal and side states.

**Consumer provides** the current state, prior states and, for terminals and side states, the reason.

- Rail: proposed → waiting → ready → admitted → running → awaiting_acceptance → accepted. Done steps on `pane`, current outlined in `accent`.
- Terminals: ✕ negative, ⊘ unsupported, ⊗ cancelled. Side states (dashed): ↻ retry_wait, ∅ budget_exhausted.
- Resource occupancy is not a negative result. Terminal task counts never define objective completion.
