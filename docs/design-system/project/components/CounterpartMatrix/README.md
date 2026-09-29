# CounterpartMatrix

One logical entity across every build: counterparts, divergence class, locator status and facts, with unmatched builds left visibly absent.

**Use it** as the Compare workspace's primary view; the organizing relationship of the product. Its one-line **strip variant** is the CounterpartStrip under the view title in the Code Browser (see CounterpartStrip); below 700px the strip collapses into the breadcrumb's Build menu.

**Consumer provides** the logical entity, and per build: concrete address or absence, divergence class (1↔1, 1↔N, ≠), identity-edge state, locator status and facts.

- Rows are builds; the inspected build is the selected row. Bytes, ABI, addresses and edits stay per build.
- An absent counterpart is written "absent" in italics; a blank cell is never filled with a guess. Every counterpart link shows its edge word (accepted or candidate).
- **Cell grammar** (APG Grid with cell focus, as in ReadinessMatrix): Alt+↓ peeks the cell (ladder run, edge evidence or facts); **Enter** on a build switches the inspected build keeping the entity and, through backend alignment, the instruction position, then focuses the EntityBuildCard in the evidence rail with a back-link ("from CounterpartMatrix · build-c"); **Shift+Enter** opens SplitCompare with that build; Enter on a contested cell opens two held panes "contested · no winner".
- **Build-switch rule**: when the instruction has no mapping, "No instruction mapping for build-c; showing function start"; when the build has no counterpart, "build-d: no counterpart (absent); staying on build-a". Nothing is guessed. Alt+PageDown / Alt+PageUp step to the next or previous build with a counterpart from anywhere in the Code Browser.
- The fact column is the FactBadge strip: one button that opens a Peek.

**Linking**

- **Publishes:** `build` on Enter (one history stop, entity kept) · `cmp` on Shift+Enter (Open beside creates a Held pane) · `hold` for a contested pair.
- **Follows:** `entity` (the one logical entity) and `build` (the selected row); commit-on-Enter for the cells, cached rows follow after the settle. The matrix is not holdable; its Open-beside panes are.
- **Targets rendered:** address → the Code Browser for that build, same entity (counterpart), with its edge word · relation and identity → the IdentityEdge evidence and its receipt card · facts → a facts Peek whose facts link to receipts · build row header → that build's EntityBuildCard · ambiguous and contested locators → their ladder evidence; contested candidates as links marked "no winner". Cell names read "build-c: 00082f40, 1↔N, candidate, facts: compilation not run".
- **Peek source:** the stored identity edges, locator rows, ladder runs and fact rows for this entity; nothing is matched or decompiled.
- **Absent copy:** "absent" (italic, plain) · "unresolved" (plain) · "diverged — counterpart structurally different, possibly inlined/split" · "Not loaded. Open build-c to read it." · "No instruction mapping for build-c; showing function start" · "build-d: no counterpart (absent); staying on build-a".
- **Target-size exception:** none; cells are at least 24px (28px rows). With a coarse pointer each row adds one 44px row-menu button.

**Keyboard**

- APG Grid with cell focus: ←/→ cells, ↑/↓ builds, Home/End, Ctrl+Home/End, PageUp/PageDown. Enter goes, Shift+Enter opens beside, Alt+↓ peeks, Shift+F10 opens the one link menu. Alt+PageDown / Alt+PageUp step builds.

**Accessibility**

- `role="grid"` named "Counterparts of ‹entity›"; builds are row headers (`th scope="row"`). A build switch is announced once, politely ("Inspected build: build-c"), never while arrowing.

**Removes switching:** switching build tabs and re-finding the function to compare counterparts, and losing the instruction position on each switch (J01, J17, J26).
