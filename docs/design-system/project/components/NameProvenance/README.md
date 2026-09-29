# NameProvenance

Per-field name precedence: the winning name, its tier, its origin, and every rejected alternative and conflict.

**Use it** as the evidence rail's **Why this name** section for the selection ("For ResourceRef::Resolve · build-a"), in a Peek on any name, and as the target of merge and placement conflict links.

**Consumer provides** the field, candidate names with tier, source build and witness (receipt), and the winner.

- Precedence: human annotation → debug info / STABS → authentic symbols → analysis names → placeholders. A placeholder never replaces a stronger name.
- Fusion is per field: the best donor may differ for every field. A human naming preference changes the display name, not physical-layout evidence.
- Rejected alternatives and conflicts stay visible; nothing authored is lost.
- There is no tooltip. On a name anywhere (EntityRow, the sticky function header, a breadcrumb), Alt+↓ opens a Peek of this section; the Peek names the winning tier, the donor build and the count of rejected alternatives in words.
- Rail-section form: a scope sentence header, the precedence table, and "Show all" linking to the full per-field view.

**Linking**

- **Publishes:** nothing. Choosing a name is an edit through the ActionStrip, never a click here.
- **Follows:** `entity` and `build`, after the settle. Keepable as a card (`keep=names:88@build-a`); a Kept card stays on its entity and build.
- **Targets rendered:** source build → the counterpart (entity @ build) in the Code Browser for that build, showing its edge word ("build-c · candidate") · witness → the receipt card that recorded it · analysis name → its address, with `build` · conflicting value → this section for that entity and build (the target of MergeReview and ContextPlacement conflict links) · "Show all fields" → the names panel (`ws=evidence&panel=names`).
- **Peek source:** Alt+↓ on a name anywhere reads the stored name-candidate rows and witness receipt headers.
- **Absent copy:** "none" for a tier with no candidate · "unresolved on build-d" (plain words) · "Not loaded. Open build-c to read its names." Never a guessed donor.
- **Target-size exception:** spacing: a Source cell may hold two short links separated by `·`; grid rows are 28px.

**Keyboard**

- APG Grid inside the section: arrows move cells, Enter follows the focused link, Alt+↓ peeks it, Shift+F10 reveals in.

**Accessibility**

- `role="grid"` named "Why this name, ResourceRef::Resolve, build-a"; the tier is the row header (`th scope="row"`). "winner" and "rejected" are words, not only row fill.

**Removes switching:** opening the Evidence workspace, the Compare workspace and the donor build to learn why a function has its name (J18, J31).
