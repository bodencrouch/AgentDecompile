# EvidenceRail

The resolution ladder as it actually ran for one entity on one build: members tried in family order, each with its reason, and any contested pair.

**Use it** as a section of the evidence rail, in the ladder Peek of a locator or matrix cell, and as the target of every "member" and OutcomeTag link.

**Consumer provides** the ladder (A–F), each member's outcome and reason, the member used, the landed address, the terminal outcome, and where the operator entered from (when it was opened from a matrix cell or a Peek).

- Same order and numbering as the ResolutionLadder in the diagrams. The member that resolved is the current step (`aria-current="step"`, selection fill plus the 3px bar).
- Untried members say "not tried (budget)" or "not applicable"; never imply exhaustive failure.
- The terminal line is an OutcomeTag. An annotation is a claim, never resolved.
- **Following** (default): the card follows the primary entity and build after the settle delay, keeping its old content dimmed with "Loading ‹name›". **Kept**: K keeps the card in the rail labelled "Kept", with its entity, build and age; it never refreshes by itself and shows "◷ Basis changed since kept · Refresh" when its basis changes.
- **Entered from**: opened from a matrix cell or Peek, the header carries a back-link ("from ReadinessMatrix · row 12 · build-c").
- **Contested split form**: a contested terminal shows both addresses with "contested · no winner"; Enter opens both as held panes.

**Linking**

- **Publishes:** nothing. K adds the card to the URL as `keep=ladder:88@build-c`.
- **Follows:** `entity` and `build`, after the settle, keeping the old run dimmed with "Loading ‹name›". Not holdable in the centre; keepable as a Kept card, which never refreshes by itself.
- **Targets rendered:** member → its pipeline node (`?node=ladder-A-3`), whose Explain text opens in place · resolved address → the counterpart in the Code Browser, with `build` and its edge word · contested pair → two address links marked "no winner" · run receipt → the receipt card · back-link → the entering matrix row and column. Link names read "Ladder A step 3, callee_order, resolved".
- **Peek source:** the stored ladder run for that entity × build and the node's generated outline text.
- **Absent copy:** "not tried (budget)" · "not tried (resolved earlier)" · "not applicable" · "unresolved — never a silent zero" · "Not loaded. Open build-c to read its ladder run."
- **Target-size exception:** none; rows are 28px.

**Keyboard**

- A list of rows in Tab order through their links; Enter goes, Alt+↓ peeks, K keeps the card, Shift+F10 reveals in.

**Accessibility**

- An `<ol>` in ladder order; the member used carries `aria-current="step"` and the words "member used". The header names entity and build; "Kept" and "Following" are words with the sync icon, never color alone.

**Removes switching:** opening the readiness report and the diagram to learn which ladder member resolved an entity and why the others did not (J06, J33).
