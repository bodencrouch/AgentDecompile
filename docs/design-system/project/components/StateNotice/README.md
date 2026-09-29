# StateNotice

An inline explanation of a surface's lifecycle state, and the designed empty and dead-end state.

**Consumer provides** the state (loading, not loaded, empty, disconnected, unavailable, stale, unsupported, partial, conflict, reconnecting, approval-required, failed, recovered), a title naming it, the cause with the program and build it concerns, and at most one next action; for a dead end, the one catalog verb that would fix it and a link to what already exists.

- Glyphs: … loading · ○ not loaded · ∅ empty · ⌁ disconnected · ⊡ unavailable · ◷ stale · ⊘ unsupported · ◐ partial · ⇄ conflict · ↻ reconnecting · ⚑ approval-required · ✕ failed · ↺ recovered.
- Variants `.info` (`ink-strong` glyph), `.caution` (`fact-stale`), `.fault` (`fact-failed`), `.unknown` (`fact-unknown`). Transient read errors are `.info` and keep the last content. The accent is not a status.
- Opening a view never starts analysis. An empty list says what is missing; it does not reimport or reanalyze. Unavailable paths show as unavailable, not as an empty new project.
- **Dead ends name the next step.** An empty or unbound view names the program and the cause ("No function inventory in the corpus store for build-e. The Ghidra program is bound.") and offers exactly one button that **arms** the matching catalog verb (extract-inventory or program_binding) in the ActionStrip, pre-bound to that build. It never runs it: the strip and ConfirmDialog still decide. A "What already exists for build-e" link shows reuse evidence (recovered functions, reuse candidates, identity receipts) first. Empty is not permission to analyze.
- `.ad-empty` is the empty workspace: `type-section` headline, one sentence, one button. Keyboard hints use modifiers ("Go to address Ctrl/Cmd+G"), never a bare letter.
- **Not loaded** is not an error: the evidence exists but has not been read in this session, and reading it may be expensive. Say "Not loaded. Open to read it." and never fetch it automatically from a hover, peek or prefetch.

**Linking**

- **Publishes:** nothing. The armed button writes the ActionStrip, not the location.
- **Follows:** its host view's location; it changes when the host's state changes. Not holdable.
- **Targets rendered:** the program or build named → the Code Browser or Navigator binding for that build · "What already exists for build-e" → the evidence reuse panel for that build (`ws=evidence&panel=reuse&build=build-e`) · a conflict's other value → NameProvenance for that entity and build · "Show path" → the project locator detail.
- **Peek source:** none; a notice is its own content.
- **Absent copy:** the notice is the absent copy: "Not loaded. Open to read it." · "No function inventory in the corpus store for build-e. The Ghidra program is bound." · "The project locator for build-d is not reachable. Its receipts are kept."
- **Target-size exception:** none; the one button is 28px and links sit in the sentence (inline).

**Accessibility**

- A notice is `role="status"` only when the operator's own action caused it; otherwise it is plain text in the view. The glyph is `aria-hidden` beside its title word. The armed button's name says it arms, not runs ("Arm extract-inventory for build-e").

**Removes switching:** hunting through the palette and the catalog for the verb that fixes an empty build, and opening the Evidence workspace to check what already exists (J27).
