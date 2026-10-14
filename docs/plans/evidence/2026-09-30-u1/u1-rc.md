| id | predicate (≤16 words) | status | file:line opened | missing clause (≤16 words) |
|---|---|---|---|---|
| RC-01 | Corrupted reconstructed addend must fail independent linked-image check | partial | coff_fixup_roundtrip.py:223-277 | Comparator only used in tests, not wired as pipeline accept/reject gate |
| RC-02 | Discarded compiled replacement earns zero source contribution despite fallback bytes | implemented | source_contribution.py:432-477 ("intentionally_discarded", winner selection) | none found |
| RC-03 | Same logical family allowed; incompatible held-out sibling replacement refused | partial | correspondence.py:18,63-105 (status bands, ambiguity_group, allows_identity_binding) | Did not open behavior-change (x+1→x+2) refusal path itself |
| RC-04 | Entity/physical multiplicity retained; no invented standalone address for folded/inline | partial | logical.py:1-40 (identity layer from name evidence) | Did not open folded-body / inline-only / split-region handling code |
| RC-05 | Per-check outcomes retained separately; compile/ReAgent GREEN never promotes other facts | absent | grep only (contract_features.py, features.py hits) | No function opened proving scoped, non-promoting fact isolation |
| RC-06 | Affected result stale on dependency change; unrelated local compile stays valid | implemented | recipient_acceptance.py:104-166 (`_intact`, stale outcome, rootSets granularity) | none found |
| RC-07 | Same accepted state under shuffled discovery/worker order; tied ambiguity unresolved | partial | determinism_harness.py:211-227 (`run_cascade`, order-independent pair fixing) | Did not open `compare_dumps`/`run_harness` full replay-equality assertions |
| RC-08 | Presence passes, identity fails via wrong-label bytes; unrelated binding stays usable | implemented | operation_contract.py:110-150 (`bind_operations` sha256 identity check) | none found |
| RC-09 | Supported original-code operation binds via identity/ABI independent of source-floor status | implemented | operation_contract.py:1-9,110-150 | none found |
| RC-10 | Explicit terminal reason (absent/inlined/unsupported/budget-limited); no forced match | partial | matching_status.py:108-129 (explicit status enum: out-of-text, asm-floor, absent, etc.) | No distinct "inlined" or "budget_limited" terminal reason found |
