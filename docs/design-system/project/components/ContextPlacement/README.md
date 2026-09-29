# ContextPlacement

Context fusion results: puzzle pieces placed by address, left unplaced, conflicting or skipped, and proposed labels that are never applied silently; conflicts reviewed master-detail.

**Consumer provides** each piece's kind (source dump, notes, JSON, GZF), its placement outcome (placed, unplaced, conflict, skipped) with build and address when placed, and proposed labels with ready or conflict status and every competing name, all within the active project.

- Pieces without a canonical address stay unplaced evidence; no guessed addresses.
- **Master-detail** (the ReviewDetail pattern): the focused conflict row drives a detail, inline below 860px or beside at 860px and wider. It shows the proposed labels and the project's current name side by side, the proposed ones in the context-hint claim tier, with **nothing pre-picked**. Proposed ≠ applied.
- The detail's Peek of the placed piece's listing reads the cached listing only; it never decompiles or loads a program.
- **Applying a label is an edit**: InlineRename in place for one target (Enter confirms in its own editor), or the ActionStrip plus ConfirmDialog for a batch of rows. Following a link never applies a label.
- Context never increments proof; seeds stay advisory until compile and objdiff accept them. Imported context notes are context-hint pieces; a viewer's own mark notes are not context and never enter fusion.

**Linking**

- **Publishes:** nothing. Enter on a placed address goes (one history stop); labels change only through InlineRename or the ActionStrip.
- **Follows:** `project` and the placement record; the detail follows the focused row after the settle and reads cache only. Not holdable.
- **Targets rendered:** links resolve only inside the active project. A placed address → the Code Browser at that build and address (always with `build`) · a conflict → NameProvenance for that entity and build, as a cache-only Peek or the rail's "Why this name" · "project locked" → the lock's node and its owner job. An item that exists only in another project is words ("in corpus-beta · not open"), never a link; any link that names another project lands on 35's cross-project StateNotice (Switch armed and confirm-gated, Stay) and never opens it.
- **Peek source:** Alt+↓ on a placed address reads the cached listing at that address; on a conflict, the stored name candidates. Nothing is fetched or re-fused.
- **Absent copy:** "unplaced · no address" (plain) · "skipped · project locked" · "2 names disagree · not applied" · "in corpus-beta · not open" · "Not loaded · Enter to load build-a"
- **Target-size exception:** none; rows are 28px and links and buttons at least 24px, 44px below 700px. With a coarse pointer each row carries one 44px row-menu button with the same link menu; there is no long-press.

**Keyboard**

- An APG Grid with row focus: ↑/↓ rows, → opens the inline detail, ← closes it; Enter follows the focused link; Alt+↓ peeks; F2 on a conflict row opens InlineRename for that target. Links follow the linked-views grammar.

**Accessibility**

- The piece is the row header; placement and label states are words ("conflict", "ready"), never color alone. The detail is a labelled region. The context-hint tier is a word, not only a dotted frame.

**Removes switching:** opening the placed address, the names view and the piece file separately to resolve a proposed-label conflict (J32, credited to UX-01; counts in the plan ledger).
