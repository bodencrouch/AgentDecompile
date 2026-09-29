# EvidenceRail

The resolution ladder as it actually ran for one entity on one build: members tried in family order, each with its reason, and any contested pair.

**Name note.** Despite its name, this component is the rail's **Ladder** section, not the rail region. The rail lists Ladder after Counterparts and shows it when the selected build's locator is not resolved. The rail's section list, order, per-viewer collapsed state and Expand all / Collapse all belong to 30-workstation-layout and the Workstation README.

**Use it** as the Ladder section of the evidence rail, in the ladder Peek of a locator or matrix cell, and as the target of every "member" and OutcomeTag link.

**Consumer provides** the ladder (A–F), each member's outcome and reason, the member used, the landed address with its identity-edge word, the terminal outcome, the run receipt, where the operator entered from (when opened from a matrix cell or a Peek, as entity and build), and for Explain the served `pipeline-model.json` revision.

- Same order and numbering as the ResolutionLadder in the diagrams and the `ladder-*` members in `pipeline-model.json`. An `<ol>`; the member that resolved carries `aria-current="step"`, the words "member used" and the 2px `ink-strong` now-frame. It is a status, so it never uses the selection fill or the accent bar.
- Untried members say "not tried (budget)", "not tried (resolved earlier)" or "not applicable"; never imply exhaustive failure.
- The terminal line is an OutcomeTag. An annotation is a claim, never resolved.
- **Following** (default): the section follows the primary entity and build after the settle, keeping its old content dimmed with "Loading ‹name›". **Kept**: an evidence section is kept, never held. The card's Keep button (`aria-pressed`; Shift+K only while focus is inside the card) keeps it in the rail labelled "Kept", with its entity, build and age. It never refreshes by itself and shows "◷ Basis changed since kept · Refresh" when its basis changes. On a kept card, Enter on a link goes; its footer says so.
- **Entered from**: opened from a matrix cell or Peek, the header carries a back-link named by entity and build ("← from ReadinessMatrix · ResourceRef::Resolve · build-c"). It returns to the same cell through the history row key; it never uses a row index.
- **Contested**: a contested terminal lists both evidenced addresses as candidate links, each carrying its build, with "contested · no winner". In the Code Browser that is one contested secondary pane; nothing is picked. **Compare candidates** opens the Compare workspace with two holds (`hold=addr:00452c10@build-d&hold=addr:00452e40@build-d`, within the limit of two), each pane labelled "candidate 1 of 2 · contested · no winner". Only the Compare workspace shows the split.
- **Explain** (an APG disclosure on the section) renders the ladder node from the backend-served `pipeline-model.json`, never the outline markdown. It is headed "From the pipeline design · model rev ‹8 hex›" with "Design description ≠ this item's evidence", in the context-hint claim tier (dotted frame, ClaimTier). The run above it is the evidence; Explain is design text.

**Linking**

- **Publishes:** a keep: Keep adds `keep=ladder:88@build-c` (replaceState). Compare candidates publishes `ws=compare` and two `hold` entries (push, as a workspace switch). Nothing else.
- **Follows:** `entity` and `build`, after the settle, keeping the old run dimmed with "Loading ‹name›". An evidence section is never holdable in the centre; it is keepable as a Kept card, which never refreshes by itself.
- **Targets rendered:** member → its pipeline-model node (`?node=ladder-A-3`) · resolved address → the counterpart in the Code Browser, with `build` and its edge word · contested pair → two address links marked "no winner", plus Compare candidates · run receipt → the receipt card · back-link → the entering matrix cell. Link names read "Ladder A step 3, callee_order, resolved, member used".
- **Peek source:** the stored ladder run for that entity × build; for Explain and a member's node Peek, the served `pipeline-model.json` at its revision.
- **Absent copy:** "not tried (budget)" · "not tried (resolved earlier)" · "not applicable" · "unresolved — never a silent zero" · "contested · no winner" · "Not loaded · Enter to load build-c's ladder run"
- **Target-size exception:** none; rows are 28px and every link and button is at least 24px. With a coarse pointer each ladder row carries one 44px row-menu button with the same link menu; there is no long-press.

**Keyboard**

- A list of rows in Tab order through their links; Enter goes, Alt+↓ peeks, Shift+F10 opens the one link menu; Shift+K presses Keep only while focus is inside the card. Explain toggles with Enter or Space and keeps focus.

**Accessibility**

- An `<ol>` in ladder order; the member used carries `aria-current="step"` and the words "member used". The header names entity and build. "Kept" and "Follows · as I move" are words with the sync icon, never color alone; the tier of Explain is the word "context hint", not only its dotted frame.

**Removes switching:** opening the readiness report and the diagram to learn which ladder member resolved an entity and why the others did not (J06, J33; counts in the plan ledger).

## Behavior

- A following card follows the selection as you move.
- On a kept card, Enter on a link goes.
