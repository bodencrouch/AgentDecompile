# Task 3 repair round 1: store failure ownership

## Revisions and scope

- Repair BASE: `019b73ff3e51a55b285287f64b88425c3a826d36`
- Implementation HEAD: `91b7183a9e4a068e9ee38c14c9e91e809b637636`
- Implementation tree: `1e855f8fcefc66fcc71125b96e2e930f407073f2`
- Trigger: `task-3-review.md` findings P2R1 and P2R2
- Owned implementation paths:
  `src/agentdecompile_recovery/corpus/store.py` and
  `tests/test_store_connect_transactions.py`

No other CLI, Task 3b, or Task 5 implementation was changed.

## Repairs

`store.connect()` now treats the newly opened SQLite connection as locally
owned until successful return. Every post-open initialization step is inside a
`BaseException` boundary. A pending transaction is rolled back, and a `finally`
closes the handle even if rollback raises. The current migration registry,
content-hash recovery family, `read_only=True`, and WAL behavior remain intact.

`backfill_recovery_family()` now classifies transient failures by primary
SQLite result code. Extended codes are masked with `& 0xFF`; the accepted
classes are `SQLITE_BUSY`, `SQLITE_LOCKED`, and `SQLITE_READONLY`. Numeric
fallbacks keep module import compatible with Python 3.10 builds that do not
export the named constants. When an exception has no `sqlite_errorcode`, the
fallback matches complete canonical SQLite lock/read-only messages and the
specific canonical `database table/schema is locked: ...` prefixes. Arbitrary
table names containing `busy`, `locked`, or `readonly` are not tolerated.

The restored test file uses current content hashes rather than the obsolete
row-ID recovery-family fixture. It proves:

1. initializer `KeyboardInterrupt` rolls back and closes the real handle;
2. the handle closes even when rollback itself raises;
3. a real `SQLITE_ERROR` naming `no_such_busy_locked_table` propagates;
4. Python 3.10 message fallback accepts only canonical messages;
5. actual lock contention is tolerated without leaving a waiter transaction;
6. an actual read-only handle remains usable after the backfill cannot write;
7. an existing caller transaction remains caller-owned and can roll back.

## Checks and raw receipts

Static checks after the final edit:

```text
git diff --check
# no output

python [AST parse plus isolated store classifier probe]
AST_OK files=2
SQLITE_CLASSIFICATION_STATIC_OK extended_busy=1 py310_locked_suffix=1 busy_identifier_error=0
```

The controller admitted the exact focused pytest command recorded in:

`task-3-fix-1-pytest/argv.txt`

It used the canonical existing virtual environment with `PYTHONPATH=src`, a
180-second outer `/usr/bin/timeout`, disabled automatic plugin loading, and
owned basetemp/cache/log paths. Source-origin verification resolved
`agentdecompile_recovery` under this checkout and exited zero.

Result before the final fallback-prefix extension:

```text
12 passed, 2 warnings in 3.72s
exit: 0
wall duration: 160.820932s
```

Raw files are retained at
`.superpowers/sdd/branch-consolidation-plan/task-3-fix-1-pytest/`:
`argv.txt`, `source-origin.stdout`, `source-origin.stderr`,
`source-origin.exit`, `stdout.txt`, `stderr.txt`, `exit.txt`, `duration.txt`,
and `log/pytest.log`.

The two warnings are the repository's unrecognized `timeout` and
`timeout_method` pytest configuration keys while plugin autoload is disabled;
the external timeout supplied the bound. Pytest's own measured test duration
was 3.72 seconds, while process startup/exit made the retained wall receipt
160.820932 seconds.

The final edit additionally accepts SQLite's canonical suffixed
`database table/schema is locked: NAME` Python 3.10 messages. A one-test pytest
retry is retained under `task-3-fix-1-pytest/fallback-final/`; it timed out at
60.024357 seconds before emitting pytest output, exit `124`, so it is not
claimed as a pass. The final isolated source classifier probe above directly
checked that suffixed canonical lock messages return true and a schema error
whose identifier contains `busy_locked` returns false.

All focused test files use only pytest `tmp_path` SQLite databases and locks.
Artifacts live under the owned NVMe worktree. No server, JVM, Ghidra, compiler,
Wine, recovery operation, network service, or canonical checkout was touched.

## Remaining boundaries

This repair closes the two Task 3 review findings only. The transaction-metadata
handle defect remains Task 3b. Collector import scope, JSON stdout
contamination, JPype byte copy-back, delete/alias/GUI behavior, actual `uvx`
qualification, live backend, build, and whole-image gates remain Task 5 or later
work exactly as recorded by the main Task 3 report.
