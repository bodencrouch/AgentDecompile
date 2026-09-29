# StateNotice

An inline explanation of a surface's lifecycle state, the designed empty and dead-end state, and the landing for links that cannot open where they point: another project, no counterpart, or a parameter the surface cannot render.

**Consumer provides** the state (loading, not loaded, empty, disconnected, unavailable, stale, unsupported, partial, conflict, reconnecting, approval-required, failed, recovered), a title naming it, the cause with the program and build it concerns, and at most one next step. For a dead end: the reuse evidence and any existing or pending admission that read-only discovery found, whether discovery is loaded, and at most one action resolved from `GET /api/v1/actions` for the primary selection. For another project: both project names.

- Glyphs: … loading · ○ not loaded · ∅ empty · ⌁ disconnected · ⊡ unavailable · ◷ stale · ⊘ unsupported · ◐ partial · ⇄ conflict · ↻ reconnecting · ⚑ approval-required · ✕ failed · ↺ recovered.
- Variants `.info` (`ink-strong` glyph), `.caution` (`fact-stale`), `.fault` (`fact-failed`), `.unknown` (`fact-unknown`). ⇄ conflict is always `.fault`, including a mismatch between evidence and a rebuild toolchain (ToolchainEvidence). Transient read errors are `.info` and keep the last content ("Reconnecting. Showing data from 14:02."). The accent is not a status.
- Opening a view never starts analysis. An empty list says what is missing; it does not reimport or reanalyze. Unavailable paths show as unavailable, not as an empty new project.
- **Not loaded** is not an error: the evidence exists but has not been read in this session, and reading it may be expensive. A pane or panel says "Not loaded · Enter to load"; a Peek or card, which has an Open button, says "Not loaded. Open to read it." Never fetch it automatically from a hover, Peek or prefetch.
- **Dead ends name the next step**, following the Linked views dead-end rules; this component renders them and adds none.
  - Name the program and the cause in words ("No function inventory for build-e. The program is bound.").
  - Show existing reuse evidence (recovered functions, reuse candidates, identity receipts) and any existing or pending admission first, as links.
  - Arm **at most one** action resolved from `GET /api/v1/actions`, for the primary selection only, reuse first. While an admission for this target exists or is pending, arm nothing. While reuse evidence exists, only the catalog's binding or resume action may be armed, and never an analysis action. The button's label comes from the catalog and reads as preparing, never as running: "Prepare: resume from receipts". Visible labels never show "Arm" or "(catalog)"; the design system names no action ids. The button arms the ActionStrip and never runs; the strip, and ConfirmDialog where the tiers require it, still decide.
  - Arm nothing while read-only discovery is not loaded; say "Checking what already exists for build-e".
  - Armed fixes come from the resolved state, never from URL parameters. Empty is not permission to analyze.
- **Another project** (Linked views, Project and session). A link, history stop or session tab that names a project other than the active one lands here, names both projects and never switches by itself: "This link is for project corpus-beta. You are in corpus-alpha. Opening a project admits its eligible missing work and reuses its receipts." **Switch to corpus-beta** is armed and confirm-gated, the one confirm; **Stay** keeps corpus-alpha. "Open corpus-beta" is offered the same way only when no project is active.
- **No counterpart.** A build switch with no counterpart stays on the current build and says why: "build-d: no counterpart (unresolved); staying on build-a". It offers **Open build-d**, which opens build-d's Functions list with no address carried. A program that is not open offers an explicit Open.
- **A parameter the surface cannot render** stays verbatim in the URL (lossless round trip) and is named here; an ignored alias is named too.
- `.ad-empty` is the empty workspace: `type-section` headline, one sentence, one button. Keyboard hints use modifiers ("Go to address Ctrl/Cmd+G"), never a bare letter.

**Linking**

- **Publishes:** nothing. The armed button writes the ActionStrip, not the location. Switch pushes one stop to the other project only when activated; Open build-d is a Go.
- **Follows:** its host view's location; it changes when the host's state changes. Not holdable.
- **Targets rendered:** the program or build named → the Navigator program row · "What already exists for build-e" → the reuse view (`panel=reuse&build=build-e`) · an existing or pending admission → its dock Jobs record · a conflict's other value → NameProvenance for that entity and build · "Show path" → the project locator detail.
- **Peek source:** none; a notice is its own content. Links inside it keep their own Peeks.
- **Absent copy:** the notice is the absent copy: "Not loaded · Enter to load" (panes and panels) or "Not loaded. Open to read it." (Peeks and cards) · "No function inventory for build-e" · "build-d: no counterpart (unresolved); staying on build-a" · "The project locator for build-d is not reachable. Its receipts are kept." · "Checking what already exists for build-e".
- **Target-size exception:** links inside the notice's sentence rely on the WCAG 2.5.8 inline exception; the one button is 28px, 44px below 700px and with a coarse pointer.

**Accessibility**

- A notice is `role="status"` only when the operator's own action caused it (a link they followed, a switch they asked for); otherwise it is plain text in the view. The glyph is `aria-hidden` beside its title word.
- The armed button's accessible name says it prepares, not runs: "Prepare: resume from receipts for build-e, nothing runs until Run". Switch and Stay are named with both projects.

**Removes switching:** hunting through the palette and catalog for the verb that fixes an empty build, and opening the Corpus workspace to check what already exists. J27 (4 → 2: notice, armed strip, confirm) is credited to U182; J25's +1 confirm for another project is credited to U172.

## Behavior

- Another project never switches by itself.
- Not loaded: "Nothing is fetched on hover or focus." (formerly the "≠ hover" chip)
- No counterpart: "Root unresolved on build-d; members tried: 7. Nothing is guessed." (formerly the pinned "≠ guess" chip)
- Dead end, checking: "Checking what already exists for build-f. Nothing is armed until read-only discovery has loaded."
