# ReviewDetail

The master-detail form of MatchReview. The selected queue row expands in place, or opens in a detail pane beside the queue, with its CandidateAlignment, the IdentityEdge evidence channels and margin, the divergence components and the decision controls. Every decision carries the observed-basis token, and outcomes land on the row.

**Use it** for the cross-match review queue whenever a reviewer decides rows one at a time. Batch decisions stay in MatchReview's strip and ConfirmDialog. Both forms share one queue, one page cursor and one basis token.

**Consumer provides** the page of rows (match id, source and destination build and address, relation, divergence class, status and lifecycle, producing job) and, for the selected row: the aligned blocks with anchor channels; each evidence channel with its evidence and result; the margin and the next alternative; the divergence components with their address ranges; the observed-basis token and its read time; and, after a refusal, the basis change (each field's value when the reviewer looked and now).

- **In place or beside.** Below 860px of container width, the selected row expands in place: a detail row under it spanning every column, on `chassis`, continuing the row's 3px `accent` bar. At 860px and wider it may open in a detail pane to the right of the queue, behind a splitter (`splitter-rule`, 3:1 grip). Both forms show the same content in the same order. The in-place detail stays in view (sticky to the scroll container's width) when the queue scrolls sideways.
- **Content, in order.** A header with the match id, the divergence notation (framed `1↔1`, `1↔N` or dashed `≠`, plus words), the relation kind, both endpoints as typed links, the IdentityEdge mini line with its word, and the job that proposed it. Then CandidateAlignment (two `code-bg` wells; anchors underlined solid in `lane-identity-ink` with the words "anchor, ‹channel›"; "aligned ≠ equivalent"). Then the evidence channels table: exact hash, relocation-normalized hash, rare ref, callee order, BSim, ABI check, each with its evidence and a FactBadge word (BSim reads "similarity, not proof"). Then the margin in bold mono over the next alternative, which is a link. Then the divergence components with address ranges. Missing relation, components or channels read "unavailable" and are never fabricated.
- **Decisions.** The controls are a labelled group: the primary verb names the claim ("Accept as split (1↔N)…"), then "Reject…" and "Keep in review". Irreversible verbs open ConfirmDialog naming the exact target ("Accept split for match 18421? This cannot be undone here."). The group states the token it carries: "Carries basis 9f3c…a1e0, read 13:58:07."
- **Outcomes land on the row, after the terminal result.** A submitted decision shows nothing optimistic. On HTTP 202 the row's status becomes a compact lifecycle cell: "admitted › pending" (the current word in a dashed `line-control` chip) plus the job link. On the terminal result it becomes the edge mini plus its word ("accepted" solid, "rejected" struck) and the job link, and the detail's IdentityEdge changes only then. Terminal outcomes are announced once.
- **A refused decision is never replayed.** If the basis changed, the row reads "◷ refused · basis" and the detail shows an assertive `ad-notice caution`: "Decision refused: the basis changed since you looked. Nothing was applied." It names the decision that was not replayed. Below it, **What changed since you looked** is a table with the old and new basis ids and times, and one row per changed field: the old value struck in `ink-muted`, the new value in bold `ink-strong`, and a change word with a glyph (`±` changed, `+` added, `−` removed). Unchanged fields are summarized in one line. The decision controls return, carrying the new basis. The reviewer must decide again.
- **Review never gates progress.** Pending and refused rows block nothing else in the queue. j/k keep working.
- **Read-only until a verb is activated.** Expanding, moving between rows and opening beside read cached evidence only. The detail never runs matching, ABI checks or analysis.
- **Both surfaces.** The static 8080 surface uses the in-place form with the same sections, words and lifecycle cells. The full workspace adds the beside pane and the splitter. Both use the same decision endpoint and basis token.

**Linking**

- Publishes `page` (the match-id cursor) and the selected match through the location. Selecting a row uses replaceState, not a history stop. Open beside publishes `ws=compare&sp=‹build›` for the pair.
- Follows the queue selection, never the Code Browser selection. j/k change the detail's row. Nothing else does.
- Renders both endpoints, component ranges and the alternative as address links (Code Browser for that build), the logical id (CounterpartMatrix), job ids (dock Jobs record), and basis ids (ProvenanceStamp detail and what changed since).
- An absent destination reads "absent", and missing relation or components read "unavailable". Neither is a link.

**Keyboard**

- The queue is an APG Grid with one tab stop. ↑/↓ or **j/k** move the selected row. The detail follows at once, because it reads cached evidence, and stays open. j/k also work while focus is inside the detail (it is part of the grid's composite), except in text fields. Focus stays on the equivalent control in the new row's detail, or returns to the row. The keys can be remapped or turned off, and Previous row and Next row are 24px buttons with `aria-keyshortcuts="k"` and `"j"`.
- **Enter** on a row goes to its detail: the row expands in place, or its detail fills the beside pane. Enter again collapses it. **Tab** from the selected row moves into its detail's links and controls, and on out of the grid. **Esc** inside the detail returns focus to the row without collapsing it.
- **x** or **Space** checks a row for a MatchReview batch. **o** (`review.open`) opens both endpoints in SplitCompare beside the queue; Shift+Enter on an endpoint link opens only that endpoint beside. **d** (`review.decide`) arms Decide: for the checked set when there is one, otherwise for the selected row, by moving focus to the detail's primary decision button. **.** repeats the armed decision on the focused row. Keys only arm; every decision still goes through ConfirmDialog.
- **F8 / Shift+F8**: when the review queue is the active worklist, they move to the next or previous row from anywhere, and the detail follows. **Ctrl/Cmd+Alt+3** is the Review layout preset. **Alt+↓** on any address peeks it. **Shift+F10** opens the row menu: Open beside, Peek source, Peek destination, Copy link.
- Decision buttons open ConfirmDialog with focus on Cancel. Esc cancels, and focus returns to the decision button.

**Accessibility**

- The queue is `role="grid"` with `aria-rowcount`. The selected row has `aria-selected="true"`, `aria-expanded` and `aria-controls` pointing to the detail. The detail is a `section` labelled "Match 18421". In the beside form the pane is labelled the same way and the splitter is a focusable `separator` with `aria-valuenow`, `aria-valuemin` and `aria-valuemax`.
- The decision controls are a `group` labelled "Decision for match 18421". The basis sentence is visible text, not a tooltip.
- Status cells are glyph plus word ("admitted › pending", "accepted", "rejected", "◷ refused · basis"). Edge lines and glyphs are `aria-hidden` next to their words.
- WCAG 4.1.3: terminal outcomes are announced once in the polite region ("Match 18420 accepted, job 5cf1"). A refusal is assertive because it blocks the action in hand. Pending states and polls announce nothing.
- WCAG 3.2.2: moving rows never submits, confirms or navigates. WCAG 2.2.1: pending decisions never expire, and a refusal waits for the reviewer.
- The change table uses `del` and `ins` with visible change words, so the change is never carried by strikethrough alone. WCAG 2.5.8: controls are 24px, and 44px below 700px, including row checkboxes.

**Removes switching:**

- Review one candidate match. Before: queue → Compare workspace for the alignment → Evidence workspace for channels and margin → back to the queue to decide, 3 switches per row. After: 0; the detail expands in place, and j moves to the next row.
- Recover from a refused decision. Before: an error, a page refresh that loses the place, finding the row again, and reopening its evidence, 3 switches. After: 0; the basis change is shown in place and you decide again.
- Confirm an outcome. Before: the Jobs dock to watch the job, then back to the queue, 2 switches. After: 0; the outcome lands on the row.
- Look at the full alignment. Before: 1 switch to Compare, which loses the queue position. After: Shift+Enter opens it beside the queue, 0 switches.
