# ReviewDetail

The master-detail form of MatchReview. The selected queue row expands in place, or opens in a detail pane beside the queue, with its CandidateAlignment, the match record, the IdentityEdge evidence channels and margin, the divergence components and the decision controls. Every decision carries the observed-basis token, and outcomes land on the row. Its named part **BasisDelta** is the refusal summary, shared by the page and the per-row table.

**Use it** for the cross-match review queue (`ws=compare&panel=review`) whenever a reviewer reads rows one at a time. Batch decisions stay in MatchReview's ActionStrip and ConfirmDialog. Both forms share one queue, one page cursor and one basis token.

**Consumer provides** the page of rows (match id, source and destination build and address, relation, divergence class, status and lifecycle, producing job) and, for the selected row: the U17 match record in its order (relation, divergence_class, components, thresholds_version, producing_channel, reason); the aligned blocks with anchor channels; each evidence channel with its evidence and result; the margin and the next alternative; the divergence components with their address ranges; the observed-basis token and its read time; and, after a refusal, the basis change (each field's value when the reviewer looked and now, and which rows changed, are new or left the page).

- **In place or beside, never in the rail.** Below 860px of container width, the selected row expands in place: a detail row under it spanning every column, on `chassis`, continuing the row's 3px `accent` bar. At 860px and wider it may open in a detail pane to the right of the queue, behind a splitter. Both forms show the same content in the same order.
- **Follows after the settle.** Moving rows (↑/↓, j/k) moves focus at once; the detail follows after the 200ms `settle-delay`, like every following pane (35), and drops late reads for superseded rows.
- **Content, in order.** A header with the match id, the divergence notation (framed `1↔1`, `1↔N` or `≠`, plus words), the relation kind, both endpoints as typed links with the edge word (candidate or accepted), the IdentityEdge mini line with its word, and the job that proposed it. Then CandidateAlignment (embedded variant: two `code-bg` wells; anchors underlined solid in `lane-identity-ink` with the words "anchor, ‹channel›"; "candidate ≠ acceptance · aligned ≠ equivalent"). Then the **match record**: the U17 fields in U17 order, relation, divergence_class, components, thresholds_version, producing_channel, reason, each "unavailable" where missing and never fabricated. Then the evidence channels table (exact hash, relocation-normalized hash, rare ref, callee order, BSim, ABI check, each with its evidence and a FactBadge word; BSim reads "similarity, not proof"). Then the margin in bold mono over the next alternative, which is a link. Then the divergence components with address ranges.
- **Differences.** F7 and Shift+F7 step the alignment's anchors and highlights ("Difference 2 of 9: 0041b240 differs"); the Previous and Next difference buttons are the other path.
- **The Review held pair.** `o` opens both endpoints beside as a held pair in SplitCompare and re-points the same pair slot for every later row; it never adds holds. The pair's header shows "candidate ≠ acceptance · aligned ≠ equivalent", the divergence notation, and the edge state as of the hold with its read time. After the decision's terminal result it reads "◷ Basis changed since held · Refresh". The pair reads cache only, and says "Not loaded. Open to read it." where the program is not open.
- **Decisions.** The controls are a labelled group: the primary verb names the claim ("Accept as split (1↔N)…"), then "Reject…" and "Keep in review". Irreversible verbs open ConfirmDialog naming the exact target ("Accept split for match 18421? This cannot be undone here."). The group states the token it carries: "Carries basis 9f3c…a1e0, read 13:58:07."
- **Outcomes land on the row, after the terminal result.** A submitted decision shows nothing optimistic and announces nothing on pending. On HTTP 202 the row's OutcomeCell becomes "admitted › pending" (the current word in a dashed `line-control` chip) plus the job link. On the terminal result it becomes the edge mini plus its word ("accepted" solid, "rejected" struck) and the job link, and the detail's IdentityEdge changes only then. Terminal outcomes are announced once.
- **BasisDelta: a refused decision is never replayed.** After a stale-basis refusal of a batch:
  - The page shows the assertive line "Decision refused: basis changed. 2 rows changed and were unchecked; nothing was applied. F8 steps them after Step changed rows." with the old and new basis ids and times.
  - Kept: the page cursor, the scroll anchored on the focused match id, and focus on the invoker.
  - Unchanged rows keep their check. Changed rows are unchecked and marked "± changed since you looked", with field old → new in the detail's **What changed since you looked** table (`del`/`ins` plus a change word). New rows are marked "+ new since you looked".
  - Rows that left the page go into a separate collapsed group, "Left this page since you looked (N) · basis 9f3c… read 13:58". They are historical, cannot be checked or decided, and show match-id links only.
  - **Changed only** is a session-local filter button. After a reload it reads "Changes since the previous basis are not available; all rows need re-reading."
  - **Step changed rows** makes the changed rows the active worklist explicitly, with an announcement; then F8 steps them. The active worklist is never replaced silently.
  - Deciding again needs a new ConfirmDialog that names the new count.
- **Review never gates progress.** Pending and refused rows block nothing else in the queue. j/k keep working.
- **Read-only until a verb is activated.** Expanding, moving between rows and opening beside read cached evidence only. The detail never runs matching, ABI checks or analysis.
- **Both surfaces.** The static 8080 `wb-review` surface uses the in-place form with the same U17 object, the BasisDelta summary and OutcomeCell. It opens the held pair as a new window ("Open beside (new window)"). The full workspace adds the beside pane and the splitter. Both use the same decision endpoint and basis token.

**Linking**

- **Publishes:** `page` (the match-id cursor) with replaceState on row moves; Enter on an endpoint link is Go (one stop). `o` re-points the Review held pair: two `hold` entries in the Compare workspace, replaced, never added (replaceState). "Changed only" is session-local view state, never in the URL.
- **Follows:** the queue selection after the settle, never the Code Browser selection. Not holdable; the held pair is.
- **Targets rendered:** both endpoints, component ranges and the alternative as address links (the Code Browser for that build, with the edge word) · the logical id (Compare with the CounterpartMatrix) · job ids (dock Jobs record) · basis ids (ProvenanceStamp detail and what changed since) · match ids in the left-the-page group (`page=`).
- **Peek source:** Alt+↓ on an endpoint reads its cached listing lines; on a job, the stored job record. The detail reads stored review rows and cached listings only.
- **Absent copy:** destination "absent" (plain) · "unavailable" for missing U17 fields · "Not loaded. Open to read it." · "left this page since you looked" · "Changes since the previous basis are not available; all rows need re-reading."
- **Target-size exception:** none; controls are 24px, 44px below 700px, including row checkboxes; with a coarse pointer each row has one 44px row-menu button carrying the link menu.

**Keyboard**

- The queue is an APG Grid (a checkable, row-selection grid) with one tab stop. ↑/↓ or **j/k** move the selected row; the detail follows after the settle and stays open. Previous row and Next row are 24px buttons with `aria-keyshortcuts="k"` and `"j"`.
- **Enter** on a row expands its detail in place, or fills the beside pane; Enter again collapses it. There are no →/← open and close keys. **Tab** from the selected row moves into its detail's links and controls, and on out of the grid.
- **x** or **Space** checks a row; **Shift+↑/↓** and **Shift+j/k** extend the checked range. Ctrl/Cmd-click toggles a row and Shift-click extends the range, including on the match-id or name link (35 grid modifier precedence); Open beside there is Shift+Enter or the menu, and typeahead starts with `/`.
- **o** (`review.open`) re-points the held pair. **d** (`review.decide`) arms Decide for the checked set when there is one, otherwise for the selected row, by moving focus to the detail's primary decision button. **.** arms or repeats the armed decision on the focused row; it never posts. Every decision still goes through ConfirmDialog.
- **F7 / Shift+F7** step the alignment's differences. **F8 / Shift+F8** step the active worklist from anywhere (after Step changed rows, the changed rows). **g then 3** is the Review layout preset. **Alt+↓** on any address peeks it. **Shift+F10** opens the one link menu.
- Esc follows the one order in `keymap.json` `escapeOrder`; inside the detail it returns focus to the row without collapsing it. A history move cancels an open ConfirmDialog, and nothing is replayed.

**Accessibility**

- The queue is `role="grid"` with `aria-rowcount`. The selected row has `aria-selected="true"`, `aria-expanded` and `aria-controls` pointing to the detail. The detail is a `section` labelled "Match 18421". In the beside form the splitter is a focusable `separator` with `aria-valuenow`, `aria-valuemin` and `aria-valuemax`.
- The decision controls are a `group` labelled "Decision for match 18421". The basis sentence is visible text, not a tooltip.
- Status cells are glyph plus word ("admitted › pending", "accepted", "rejected", "± changed since you looked", "+ new since you looked"). Edge lines and glyphs are `aria-hidden` next to their words. The change table uses `del` and `ins` with visible change words, so the change is never carried by strikethrough alone.
- WCAG 4.1.3: terminal outcomes are announced once in the polite region ("Match 18420 accepted, job 5cf1"). The refusal line is assertive because it blocks the action in hand. Pending states and polls announce nothing.
- WCAG 3.2.2: moving rows never submits, confirms or navigates. WCAG 2.2.1: pending decisions never expire, and a refusal waits for the reviewer.

**Removes switching** (counts from the plan ledger):

- J07 review a candidate match and check both endpoints before deciding: 8 → 0, plus one modal confirm per decision and one Review preset per session (U186).
- J08 recover from a refused decision: 4 → 1, the new confirm; only changed rows are re-read (U186).

**Parity extension (2026-09-29): manual match (X07)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): X07)

Ghidra's Version Tracking offers Create Manual Match, Create And Accept Manual Match and Create And Apply Manual Match between the function under the cursor in two tools. Here only the first exists: a manual match proposes a candidate identity edge that enters this queue for review. It never accepts and never applies markup.

- **Where.** **New manual match…** in the queue header and the palette; **Match with…** in the link menu of a function in the Code Browser, which fills the source side; and, from the Review held pair or two SplitCompare panes, **Match these two…**, which fills both sides from the panes' functions.
- **Anatomy.** A form in the detail position (in place or beside, as for a row):
  1. **Source**: a build chooser and a function picker over the stored function index of that build (name, address, signature), with the filter **Only functions without an accepted counterpart on the other build** on by default.
  2. **Destination**: the same, for a different build. The same build on both sides is refused: "A match joins two builds; choose a different destination build."
  3. **Relation**: one_to_one (default), clone, inline, thunk, split, fold, region or unroll, with the divergence class left "unavailable" until a check runs.
  4. **Reason** (required): the evidence you cite, in words ("build-b folds FUN_0041c880 into FUN_0041c940; same body bytes after relocation"). It becomes the edge's reason field.
  5. What exists already, read from stored edges only: "A match already exists between these: match 18424 · rejected · Open match 18424" (Ghidra's Select Existing Match), or "FUN_0041c880 on build-a already has an accepted counterpart on build-b. A second edge makes this 1↔N; choose split or fold, or review the existing edge."
- **Propose.** **Propose manual edge…** opens ConfirmDialog: "Propose a manual identity edge between FUN_0041c880 on build-a and FUN_0041c940 on build-b? It enters review as a candidate; nothing is accepted." The primary button is **Propose edge**. It posts the catalog's identity-decision write with the decision "manual match" and the cited reason, carrying the observed basis token like every decision here.
- **What it becomes.** After the terminal result, a new queue row (match 18426) with:
  - the edge drawn dashed in `lane-identity-ink`, the word "candidate", and the evidence level "hypothesis (manual)" with "basis: manual · cited by you: ‹reason›";
  - evidence channels read "manual · no channel run", and the ABI check "○ not run";
  - producing_channel `manual` and the author (by you, by agent or external).
  Until then the form shows the OutcomeCell words (pending, running) and nothing optimistic.
- **Never auto-accepts.** Accepting is a later, separate decision on that row, with its own ConfirmDialog and basis token, exactly as for a matcher's candidate. The form has no Accept or Apply button, and says so: "A manual match is a candidate. Accept it later from its row; nothing is applied to either program." Propagation along it is possible only after acceptance, through PropagationTransfer.
- **Keyboard.** `review.manualMatch` (no default key) opens the form. Tab moves source, destination, relation, reason, Cancel, Propose. The function pickers are APG comboboxes with a listbox; typeahead filters by name or address.
- **Accessibility.** The form is a `section` named "New manual match". The existing-edge line is a polite status message when it appears. The ConfirmDialog is an `alertdialog`. The new row is announced once, after the terminal result: "Manual match 18426 proposed, candidate, job b7e2."
- **One writer.** The write is to the identity database, not to a program, so program locks do not block it; a refused basis follows BasisDelta as for every decision.

## Behavior

- A decision carries its basis; "The outcome lands on this row after the terminal result; 202 shows as pending. Nothing is shown before that."
- Candidate alignment keys (formerly visible "F7 anchors · o held pair" chips): F7 steps the anchors and highlights; o re-points the Review held pair.
- Refused batch: "Kept: the page cursor, the scroll on match 18425 and focus on Decide. Unchanged rows keep their check."
- Manual match: "A manual match is a candidate. Accept it later from its row"; "nothing is applied to either program." (formerly the "≠ applied" chip)
