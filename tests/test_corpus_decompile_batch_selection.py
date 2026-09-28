from __future__ import annotations

import sqlite3

from agentdecompile_recovery.corpus.cli import select_decompile_batch_pending
from agentdecompile_recovery.corpus.decompile_text import CTEXT_SCHEMA


def _connections() -> tuple[sqlite3.Connection, sqlite3.Connection]:
    store = sqlite3.connect(":memory:")
    store.execute(
        "CREATE TABLE func (binary_id INTEGER, addr INTEGER, n_instr INTEGER, size INTEGER)"
    )
    store.executemany(
        "INSERT INTO func VALUES (1, ?, ?, ?)",
        [(0x1000, 4, 8), (0x2000, 4, 8), (0x3000, 0, 8), (0x4000, 4, 0)],
    )
    ctext = sqlite3.connect(":memory:")
    ctext.executescript(CTEXT_SCHEMA)
    ctext.executemany(
        "INSERT INTO ctext(repo_path, addr, ok, signature, code) VALUES ('repo', ?, ?, NULL, NULL)",
        [(0x1000, 1), (0x2000, 0)],
    )
    return store, ctext


def test_cli_store_selection_retries_only_failed_rows_when_requested() -> None:
    store, ctext = _connections()
    by_addr = {0x1000: object(), 0x2000: object(), 0x5000: object()}

    want, done, pending = select_decompile_batch_pending(
        by_addr, ctext, "repo", store_con=store, binary_id=1, min_instr=1
    )
    assert want == [0x1000, 0x2000]
    assert done == {0x1000, 0x2000}
    assert pending == []

    want, done, pending = select_decompile_batch_pending(
        by_addr,
        ctext,
        "repo",
        store_con=store,
        binary_id=1,
        min_instr=1,
        retry_failed=True,
    )
    assert want == [0x1000, 0x2000]
    assert done == {0x1000}
    assert pending == [0x2000]
