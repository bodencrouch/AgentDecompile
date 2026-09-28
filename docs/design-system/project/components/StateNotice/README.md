# StateNotice

An inline explanation of a surface's lifecycle state, and the designed empty state.

**Consumer provides** the state (loading, empty, disconnected, unavailable, stale, unsupported, partial, conflict, reconnecting, approval-required, failed, recovered), a title naming it, the cause, and at most one next action.

- Glyphs: … loading · ∅ empty · ⌁ disconnected · ⊡ unavailable · ◷ stale · ⊘ unsupported · ◐ partial · ⇄ conflict · ↻ reconnecting · ⚑ approval-required · ✕ failed · ↺ recovered.
- Variants `.info` (`accent`), `.caution` (`fact-stale`), `.fault` (`fact-failed`), `.unknown` (`fact-unknown`). Transient read errors are `.info` and keep the last content.
- Opening a view never starts analysis. An empty list says what is missing; it does not reimport or reanalyze. Unavailable paths show as unavailable, not as an empty new project.
- `.ad-empty` is the empty workspace: `type-section` headline, one sentence, one button.
