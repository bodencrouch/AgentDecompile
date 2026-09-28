# ContextPlacement

Context fusion results: puzzle pieces placed by address, left unplaced, conflicting or skipped, and proposed labels that are never applied silently.

**Consumer provides** each piece's kind (source dump, notes, JSON, GZF), its placement outcome with address when placed, and proposed labels with ready or conflict status.

- Pieces without a canonical address stay unplaced evidence; no guessed addresses.
- Conflicting names at the same address are all shown; nothing is auto-picked. Proposed ≠ applied.
- Context never increments proof; seeds stay advisory until compile and objdiff accept them.
