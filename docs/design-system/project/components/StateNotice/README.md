# StateNotice

An inline explanation of a surface's lifecycle state, and the designed empty state.

**Consumer provides** the state (loading, not loaded, empty, disconnected, unavailable, stale, unsupported, partial, conflict, reconnecting, approval-required, failed, recovered), a title naming it, the cause, and at most one next action.

- Glyphs: … loading · ○ not loaded · ∅ empty · ⌁ disconnected · ⊡ unavailable · ◷ stale · ⊘ unsupported · ◐ partial · ⇄ conflict · ↻ reconnecting · ⚑ approval-required · ✕ failed · ↺ recovered.
- Variants `.info` (`accent`), `.caution` (`fact-stale`), `.fault` (`fact-failed`), `.unknown` (`fact-unknown`). Transient read errors are `.info` and keep the last content.
- Opening a view never starts analysis. An empty list says what is missing; it does not reimport or reanalyze. Unavailable paths show as unavailable, not as an empty new project.
- `.ad-empty` is the empty workspace: `type-section` headline, one sentence, one button.
- **Not loaded** is not an error: the evidence exists but has not been read in this session, and reading it may be expensive. Say "Not loaded. Open to read it." and never fetch it automatically from a hover, peek or prefetch.
