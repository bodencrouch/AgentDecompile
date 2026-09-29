# CandidateAlignment

Matching drawn as the work: counterpart blocks from two builds aligned on recorded anchors, with the strings, references and anchors under comparison marked and named by their evidence channel. Candidate ≠ acceptance, and aligned ≠ equivalent.

**Use it** in three forms: **embedded in detail**, inside ReviewDetail for the focused review row (it drops its own header and follows the row after the settle); in the Compare workspace for a candidate pair; and in a Peek of a candidate edge (anchor-only, read from cache).

**Consumer provides** the two instances (entity @ build and address), the aligned blocks with their recorded anchor pairs, the evidence channel of each anchor, the difference hunks, alternatives with margin, and the edge state.

- Two wells side by side. Shared anchors are marked (underlined, bold `ink-strong`) on both sides and named in words for assistive technology ("shared anchor, rare ref").
- The evidence channel names each anchor: exact hash, relocation-normalized hash, rare ref, callee order, CFG, BSim, ABI. Alternatives and margin stay visible.
- **Claim boundaries** are written in the header: "candidate ≠ acceptance · aligned ≠ equivalent". Endpoints are named endpoints with their edge word, never "counterpart", until an acceptance event exists.
- **Linked cursor over anchors only.** On an anchor, the other well marks its partner. Between anchors it marks the nearest preceding anchor and says "rows between anchors are not paired". Nothing is paired by order or offset.
- **SplitCompare vocabulary.** Differing rows carry `±` plus the word "differs"; runs of equal rows collapse to "▸ 6 unchanged lines · 0041b21b–0041b22b · Expand", which expands in place in both wells.
- **Differences.** F7 / Shift+F7 step to the next or previous difference in both wells ("Difference 1 of 1: 0041b21b differs"); the Previous and Next difference buttons and the palette are the other paths.
- **Open both beside** opens both endpoints as a held pair in SplitCompare (in review, `o` re-points the Review held pair); the queue keeps focus and the selection does not change. On the static 8080 surface without split panes the button reads "Open beside (new window)" and opens the same link in a new window.
- The edge changes state only after its acceptance event. Candidate generation is not acceptance.

**Linking**

- **Publishes:** nothing; Open both beside writes `cmp` and two `hold` entries (a held pair) without changing the primary selection.
- **Follows:** the pair its host selects (the ReviewDetail row, a Compare pair), after the settle; holdable through Open both beside.
- **Targets rendered:** each endpoint → the Code Browser for that build, same entity, with `build`, address and its edge word (candidate or accepted) · a shared symbol anchor → the Code Browser at that symbol on that build · each alternative → its instance, with its margin · the edge → its receipt card when one exists.
- **Peek source:** the cached listing rows of both endpoints already read for this pair; nothing is decompiled or matched.
- **Absent copy:** "No aligned block on build-b." · "Not loaded · Enter to load build-b" · "no alternative within margin" · "candidate · no acceptance event yet" · "rows between anchors are not paired".
- **Target-size exception:** anchor links sit inside 18px code rows, at most one link per side per row (the code-well inline exception); buttons are 24px, 44px below 700px.

**Keyboard**

- F7 / Shift+F7 step differences in both wells; Enter or Space on "unchanged lines" expands it in both wells.
- Links follow the shared grammar: Enter goes, Shift+Enter on an endpoint opens it beside, Alt+↓ peeks, Shift+F10 opens the one link menu. Esc follows the one order in `keymap.json` `escapeOrder`.

**Accessibility**

- Each well is a labelled group ("build-a 0041b213, 6 rows"); shared anchors carry the hidden words "shared anchor, ‹channel›", differing rows the word "differs". The edge line style is `aria-hidden` beside its state word. A legend under the wells names ↔, ± and ▸ in words.
- Accessible View (Alt+F2, or the palette, Help menu and pane-header button) opens both wells as text with the words "anchor", "differs" and "unchanged".

**Removes switching:** it serves J07 (review a candidate match and check both endpoints, 8 → 0 plus one confirm), credited to U186 in the plan ledger.

## Behavior

- The cursor maps through anchors only; rows between anchors are not paired.
