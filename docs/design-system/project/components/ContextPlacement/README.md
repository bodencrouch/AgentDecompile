# ContextPlacement

Context fusion results: puzzle pieces placed by address, left unplaced, conflicting or skipped, and proposed labels that are never applied silently; conflicts reviewed master-detail.

**Consumer provides** each piece's kind (source dump, notes, JSON, GZF), its placement outcome with build and address when placed, and proposed labels with ready or conflict status and every competing name.

- Pieces without a canonical address stay unplaced evidence; no guessed addresses.
- Conflicting names at the same address are all shown; nothing is auto-picked. Proposed ≠ applied.
- **Master-detail**: the focused conflict row shows the proposed labels side by side with a Peek of the placed piece's listing, inline or in the rail. Applying a label goes through the ActionStrip.
- Context never increments proof; seeds stay advisory until compile and objdiff accept them.

**Linking**

- **Publishes:** nothing; Enter on a placed address goes (one history stop) and the ActionStrip applies labels.
- **Follows:** `project` and the placement record; the detail follows the focused row after the settle. Not holdable.
- **Targets rendered:** a placed address → the Code Browser at that build and address · a conflict → the placed address and NameProvenance for that entity and build · a proposed label → its NameProvenance row · the piece → its source file view in words · "project locked" → the lock's node and owner job.
- **Peek source:** Alt+↓ on a placed address reads the cached listing at that address; on a conflict, the stored name candidates.
- **Absent copy:** "unplaced · no address" (plain) · "skipped · project locked" · "2 names disagree · not applied".
- **Target-size exception:** none; rows are 28px.

**Keyboard**

- A grid with row focus: ↑/↓ rows, → opens the inline detail, ← closes; Enter follows the focused link; Alt+↓ peeks.

**Accessibility**

- The piece is the row header; placement and label states are words ("conflict", "ready"), never color alone. The detail is a labelled region.

**Removes switching:** opening the placed address, the names view and the piece file separately to resolve a proposed-label conflict (J32).
