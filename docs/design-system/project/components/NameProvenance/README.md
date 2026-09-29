# NameProvenance

Per-field name precedence: the winning name, its tier, its origin, and every rejected alternative and conflict.

**Use it** as the evidence rail's **Why this name** section for the selection ("For ResourceRef::Resolve · build-a"), in a Peek on any name, and as the target of merge and placement conflict links.

**Consumer provides** the field, candidate names with tier, source build and witness (receipt), and the winner.

- Precedence: human annotation → debug info / STABS → authentic symbols → analysis names → placeholders. A placeholder never replaces a stronger name.
- Fusion is per field: the best donor may differ for every field. A human naming preference changes the display name, not physical-layout evidence.
- Rejected alternatives and conflicts stay visible; nothing authored is lost.
- There is no tooltip. On a name anywhere (EntityRow, the Code Browser's one composite header in the Views toolbar row, a breadcrumb), Alt+↓ opens a Peek of this section; the Peek names the winning tier, the donor build and the count of rejected alternatives in words. The composite header shows the winning tier as a word beside the function name.
- **Witnesses and knowledge.** A debug-info (STABS) candidate names its witness as a receipt link. A knowledge entry about the entity is not a precedence tier: it sits below the table, outside the precedence order, labelled with its own ClaimTier ("context hint"), so it can never read as a candidate name.
- **Conflicts** from MergeReview and ContextPlacement land here for that entity and build in the active project. The Peek reads cached name rows only, and a proposed label is never applied by following a link.
- Rail-section form: a scope sentence header, the precedence table, and "Show all" linking to the full per-field view.

**Analysis sub-tiers.** Two named sub-tiers sit inside "analysis" (guideline 20):
- "analysis · Function ID": a Function ID hash match (FunctionIdManager). It ranks above placeholders, below debug info and authentic symbols, and is always a candidate.
- "analysis · imported SARIF": names from a SARIF file whose hash matches the build (DebugInfoImport). They rank below debug info.

A PDB whose identity (GUID and age) does not match the build is a hypothesis, and its names rank with analysis names, never with debug info. A weaker import never overwrites a stronger name: the stronger value stays, and the imported one is listed as a rejected alternative.

**Linking**

- **Publishes:** nothing. Choosing a name is an edit (InlineRename in place for one target, the ActionStrip for a batch), never a click here.
- **Follows:** `entity` and `build`, after the settle. Keepable as a card (`keep=names:88@build-a`); a Kept card stays on its entity and build.
- **Targets rendered:** source build → the counterpart (entity @ build) in the Code Browser for that build, showing its edge word ("build-c · candidate") · witness (STABS, annotation) → the receipt card that recorded it · analysis name → its address, with `build` · knowledge entry → its context piece's receipt card · conflicting value → this section for that entity and build (the target of MergeReview and ContextPlacement conflict links) · "Show all fields" → the names panel (`ws=evidence&panel=names`).
- **Peek source:** Alt+↓ on a name anywhere reads the stored name-candidate rows and witness receipt headers; nothing is fetched or re-fused.
- **Absent copy:** "none" for a tier with no candidate · "unresolved on build-d" (plain words) · "Not loaded. Open build-c to read its names." Never a guessed donor.
- **Target-size exception:** spacing: a Source cell may contain two short links separated by `·`; grid rows are 28px. With a coarse pointer each grid row carries one 44px row-menu button with the same link menu; there is no long-press.

**Keyboard**

- APG Grid inside the section: arrows move cells, Enter follows the focused link, Alt+↓ peeks it, Shift+F10 opens the one link menu. Shift+K keeps the section as a card only while focus is inside it (the Keep button, `aria-pressed`).

**Accessibility**

- `role="grid"` named "Why this name, ResourceRef::Resolve, build-a"; the tier is the row header (`th scope="row"`). "winner" and "rejected" are words; the winner never borrows the selection fill or the accent, which mark only the focused row.

**Removes switching:** opening the Evidence workspace, the Compare workspace and the donor build to learn why a function has its name (J18, J31).
