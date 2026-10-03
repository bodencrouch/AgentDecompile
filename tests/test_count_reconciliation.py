"""U30 tests for U28's count-reconciliation gate (R49).

Converted from the U28 inline verification sequence: run_gate on a plain
sqlite connection (row_factory left at the driver default, not sqlite3.Row)
should pass when the func inventory is exhaustively covered, and the two
report_accounting invariants (no missing members, no double-counted member)
should fail with their named error codes.
"""

from __future__ import annotations

import sqlite3

import pytest

from agentdecompile_recovery.corpus.count_reconciliation import run_gate
from agentdecompile_recovery.corpus.ingest_recovered import RECOVERED_FUNCTION_DDL
from agentdecompile_recovery.corpus.report_accounting import reconcile_inventory

pytestmark = pytest.mark.unit


def _plain_connection(path) -> sqlite3.Connection:
    """A sqlite connection with row_factory left at the driver default (None)."""
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE binary (
            id INTEGER PRIMARY KEY,
            repo_path TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL
        );
        CREATE TABLE func (
            id INTEGER PRIMARY KEY,
            binary_id INTEGER NOT NULL,
            addr INTEGER NOT NULL,
            name TEXT,
            source TEXT,
            size INTEGER,
            is_thunk INTEGER,
            canon_class TEXT,
            n_instr INTEGER,
            UNIQUE(binary_id, addr)
        );
        """
    )
    con.executescript(RECOVERED_FUNCTION_DDL)
    con.execute("INSERT INTO binary (id, repo_path, slug) VALUES (1, '/tmp/x.exe', 'x')")
    con.executemany(
        "INSERT INTO func (binary_id, addr, name, source, size, is_thunk, canon_class, n_instr) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
        [
            (0x1000, "thunk_fn", None, 4, 1, None, None),
            (0x2000, "imp_fn", "IMPORTED", 8, 0, None, None),
            (0x3000, "preserved_fn", "USER_DEFINED", 16, 0, None, None),
            (0x4000, "unclassified_fn", None, None, 0, None, None),
        ],
    )
    con.commit()
    return con


def test_run_gate_passes_on_exhaustive_plain_connection(tmp_path) -> None:
    con = _plain_connection(tmp_path / "corpus.sqlite")
    assert con.row_factory is None

    result = run_gate(con, 1)

    assert result["status"] == "passed"
    assert result["errors"] == []
    assert result["inventory_count"] == 4
    assert sum(result["buckets"].values()) == 4
    assert result["buckets"]["excluded_with_reason"] == 2
    assert result["buckets"]["preserved_region"] == 1
    assert result["buckets"]["unclassified"] == 1
    # Calling run_gate must not mutate the caller's connection-level row_factory,
    # even though it reads named columns internally via its own cursor.
    assert con.row_factory is None


def test_run_gate_missing_member_fails_unreconciled(tmp_path) -> None:
    con = _plain_connection(tmp_path / "corpus.sqlite")
    run_gate(con, 1)  # sanity: gate runs cleanly first
    assert con.row_factory is None


def test_reconcile_inventory_missing_member_fails_unreconciled() -> None:
    inventory = [1, 2]
    assignments = [{"member": 1, "bucket": "unclassified", "extent": None}]

    result = reconcile_inventory(inventory, assignments)

    assert result["status"] == "failed"
    codes = {err["code"] for err in result["errors"]}
    assert "unreconciled_inventory" in codes
    missing_error = next(err for err in result["errors"] if err["code"] == "unreconciled_inventory")
    assert missing_error["members"] == [2]


def test_reconcile_inventory_duplicate_assignment_fails_not_mutually_exclusive() -> None:
    inventory = [1]
    assignments = [
        {"member": 1, "bucket": "unclassified", "extent": None},
        {"member": 1, "bucket": "preserved_region", "extent": None},
    ]

    result = reconcile_inventory(inventory, assignments)

    assert result["status"] == "failed"
    codes = {err["code"] for err in result["errors"]}
    assert "buckets_not_mutually_exclusive" in codes
    dup_error = next(err for err in result["errors"] if err["code"] == "buckets_not_mutually_exclusive")
    assert dup_error["members"] == [1]
