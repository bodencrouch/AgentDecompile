# StateNotice

An inline explanation of a surface's lifecycle state, and the designed empty state.

**Consumer provides** the state (loading, empty, disconnected, unavailable, stale, unsupported, partial, conflict, reconnecting, approval-required, failed, recovered), a one-line title, the cause, and at most one next action.

- Variants by glyph and token: `.info` (`accent`), `.caution` (`fact-caution`), `.fault` (`fact-failed`), `.unknown` (`fact-unknown`). The title always names the state in words.
- Keep the last received content beneath a stale or reconnecting notice. Transient read errors are `.info`, not alarms.
- Opening a view never starts analysis. An empty list says what is missing and offers the explicit action; it does not re-import or re-analyze.
- `.ad-empty` is the empty workspace: `section` headline, one sentence, one button. No illustration.
