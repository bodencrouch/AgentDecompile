"""The report, bridge, and ingest paths share the current recovered schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import external_bridge
from agentdecompile_recovery.corpus.export_run_report import build
from agentdecompile_recovery.corpus.ingest_recovered import (
    RECOVERED_FUNCTION_ADDED_COLUMNS,
    ensure_recovered_function,
    ensure_recovered_schema,
)

pytestmark = pytest.mark.unit

OLD_NARROW_DDL = """
CREATE TABLE recovered_function (
    program TEXT,
    name TEXT,
    addr INTEGER,
    size INTEGER,
    convention TEXT,
    real_c INTEGER,
    logical_id INTEGER,
    path TEXT,
    evidence TEXT,
    machine_code TEXT
)
"""

NARROW_COLUMNS = (
    "program",
    "name",
    "addr",
    "size",
    "convention",
    "real_c",
    "logical_id",
    "path",
    "evidence",
    "machine_code",
)


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def _columns(con: sqlite3.Connection) -> list[str]:
    return [str(row[1]) for row in con.execute("PRAGMA table_info(recovered_function)")]


def _key(con: sqlite3.Connection) -> list[str]:
    info = list(con.execute("PRAGMA table_info(recovered_function)"))
    return [str(row[1]) for row in sorted(info, key=lambda row: row[5]) if row[5]]


def _narrow_store(path: Path, rows: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.executescript(OLD_NARROW_DDL)
    if rows:
        con.executemany(
            f"INSERT INTO recovered_function ({', '.join(NARROW_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in NARROW_COLUMNS)})",
            rows,
        )
    con.commit()
    con.close()


def test_report_and_bridge_share_current_shape(tmp_path: Path) -> None:
    con = _connect(tmp_path / "store.sqlite")
    report = build(con)
    assert report["results"] == []
    assert external_bridge.load_recovered(con) == []
    expected = {column for column, _declaration in RECOVERED_FUNCTION_ADDED_COLUMNS}
    assert expected <= set(_columns(con))
    assert con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reuse_candidate'"
    ).fetchone() is None
    con.close()


def test_ingest_schema_adds_reuse_table_without_changing_recovered_shape(tmp_path: Path) -> None:
    con = _connect(tmp_path / "store.sqlite")
    ensure_recovered_function(con)
    before = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='recovered_function'"
    ).fetchone()[0]
    ensure_recovered_schema(con)
    after = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='recovered_function'"
    ).fetchone()[0]
    assert before == after
    assert con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reuse_candidate'"
    ).fetchone() is not None
    con.close()


def test_empty_narrow_table_is_rebuilt_with_current_candidate_key(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite"
    _narrow_store(path, [])
    con = _connect(path)
    ensure_recovered_function(con)
    assert _key(con) == ["program", "name", "binary_id", "addr", "path", "source_sha256"]
    assert not con.in_transaction
    con.close()


def test_nonconforming_narrow_rows_are_preserved_additively(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    rows = [
        ("swkotor", "FUN_401000", 0x401000, 16, None, 1, 7, "/r/a.c", "ev", "c3"),
        ("swkotor", "FUN_401000", 0x401000, 16, None, None, None, None, None, None),
    ]
    _narrow_store(path, rows)
    con = _connect(path)
    ensure_recovered_function(con)
    assert con.execute("SELECT COUNT(*) FROM recovered_function").fetchone()[0] == 2
    assert {column for column, _declaration in RECOVERED_FUNCTION_ADDED_COLUMNS} <= set(_columns(con))
    assert _key(con) == []
    con.close()


def test_upgrade_joins_caller_transaction(tmp_path: Path) -> None:
    path = tmp_path / "caller.sqlite"
    _narrow_store(path, [])
    con = _connect(path)
    con.execute("CREATE TABLE caller_note(value TEXT)")
    con.commit()
    con.execute("INSERT INTO caller_note VALUES ('pending')")
    before = _columns(con)
    ensure_recovered_function(con)
    assert con.in_transaction
    con.rollback()
    assert _columns(con) == before
    assert con.execute("SELECT COUNT(*) FROM caller_note").fetchone()[0] == 0
    con.close()


def test_canonical_fast_path_takes_no_write_lock(tmp_path: Path) -> None:
    path = tmp_path / "canonical.sqlite"
    con = _connect(path)
    ensure_recovered_function(con)
    con.close()

    holder = sqlite3.connect(path)
    holder.execute("BEGIN IMMEDIATE")
    try:
        reader = _connect(path)
        ensure_recovered_function(reader)
        assert not reader.in_transaction
        reader.close()
    finally:
        holder.rollback()
        holder.close()
