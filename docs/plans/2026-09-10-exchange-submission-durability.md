# Exchange submission durability follow-up

## Context

A read-only review of the donated-compute branch found three coupled defects in
the exchange store: unverified candidate artifacts can be pruned before any
coordinator consumes them, submit receipts are globally scoped, and a failed
snapshot write lets a later replay report success without first becoming
durable. The exchange still has no resolver or acknowledgement API, so this
change must not invent one merely to make retention bounded.

## Constraints

- A remote submission remains a proposal; no result may be promoted without
  the coordinator's independent verification gate.
- Keep the on-disk state readable across this correction. Legacy receipts that
  lack enough identity to safely replay must not be trusted as receipts.
- Preserve the existing lease/fence boundary and public route shapes.
- Do not add a process-wide lock, change `CONTEXT_LOCK`, or start a server.

## Task 1: Make submitted proposals and idempotency durable

Owner: exchange store.

1. Retain `awaiting-verification` units until a future coordinator-side
   acknowledgement/resolution flow exists; continue retention pruning only for
   genuinely failed work and remove receipts belonging to pruned units.
2. Scope a submit receipt to its worker and bind its replay to the original
   lease/unit identity as well as artifact/verdict content. A key collision
   from another worker, or reuse on another unit, must not acknowledge work.
3. Make initial submit and matching replay wait for durable snapshot success
   before returning an accepted response. A failed write must be retryable and
   the successful retry must survive a new store loading the state file.
4. Add regression tests for each case, then run the exchange store test file,
   scoped lint, and whitespace validation.

## Verification

Run only the focused store test module unless a new failure requires narrower
diagnosis:

```bash
PYTHONPATH=src python -m pytest tests/test_exchange_store.py -q --tb=short --show-capture=no
```

Also run `ruff check --select F,I` on changed Python files and `git diff --check`.
