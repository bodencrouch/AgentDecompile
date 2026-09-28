# LocatorGlyph

Where one entity lands in one build: the closed locator status set, with observed status on its own axis.

**Consumer provides** per entity × build the status (`resolved`, `pinned`, `degraded`, `ambiguous`, `unresolved`, `contested`), the member used or reason, and `observed_status` separately.

- ● resolved(member) `ink-strong` · ◎ pinned(member) `address`, labelled `module_rva` or `section_offset` (non-portable) · ◑ degraded(member, reason) and ⋯ ambiguous `fact-stale` · ◌ unresolved `fact-unknown` · ⇉ contested `fact-failed`.
- Contested means two locators land on different addresses in one build, both with evidence, and there is no winner.
- `observed_status` follows a thin rule and never overwrites pack status. Display order: contested, unresolved, ambiguous, pinned, degraded, resolved.
