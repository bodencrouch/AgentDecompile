"""One shape for recovered_function, whichever verb creates it first.

export-run-report used to create a narrow recovered_function (no binary_id,
no primary key) while ingest-recovered created the canonical one. Whichever
ran first won, and external-bridge then failed with ``no such column:
binary_id``. These tests pin the canonical shape and the additive upgrade of
stores that already hold the narrow shape.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import external_bridge
from agentdecompile_recovery.corpus.cli import main
from agentdecompile_recovery.corpus.export_run_report import build
from agentdecompile_recovery.corpus.ingest_recovered import ensure_recovered_schema
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit

# Verbatim copy of the narrow DDL export_run_report.py shipped before the fix.
# Kept as a literal so the upgrade test does not depend on current code.
OLD_NARROW_DDL = """
CREATE TABLE IF NOT EXISTS recovered_function (
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
    "program", "name", "addr", "size", "convention",
    "real_c", "logical_id", "path", "evidence", "machine_code",
)

# Rows the canonical constraints would reject (duplicate program/name, NULL
# path, NULL real_c) prove the upgrade never rebuilds or re-validates data.
NARROW_ROWS = [
    ("swkotor", "FUN_00401000", 0x401000, 16, "__stdcall", 1, 7, "/r/a.c", "ev-a", "c3"),
    ("swkotor", "FUN_00401000", 0x401000, 16, "__stdcall", 0, None, "/r/a2.c", None, "c390"),
    ("swkotor2", "FUN_00402000", 0x402000, 8, None, None, None, None, "ev-c", None),
]


def _cols(con) -> list[str]:
    return [row[1] for row in con.execute("PRAGMA table_info(recovered_function)")]


def _bridge(db: Path, out: Path) -> int:
    return main(["external-bridge", "--db", str(db), "--out-dir", str(out), "--reuse-only"])


def _export(db: Path, out: Path) -> int:
    return main(["export-run-report", "--db", str(db), "--out", str(out)])


def _ingest(db: Path, tmp: Path) -> int:
    (tmp / "rec").mkdir(exist_ok=True)
    (tmp / "cov").mkdir(exist_ok=True)
    return main([
        "ingest-recovered", "--db", str(db), "--recovered-dir", str(tmp / "rec"),
        "--coverage-dir", str(tmp / "cov"), "--out-dir", str(tmp / "ingest-out"),
    ])


def test_export_then_bridge_on_fresh_store(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    connect(db).close()
    assert _export(db, tmp_path / "r.json") == 0
    assert _bridge(db, tmp_path / "out") == 0
    con = sqlite3.connect(db)
    assert "binary_id" in _cols(con)


def test_bridge_then_export_on_fresh_store(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    connect(db).close()
    assert _bridge(db, tmp_path / "out") == 0
    assert _export(db, tmp_path / "r.json") == 0


def test_ingest_then_export_then_bridge_on_fresh_store(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    connect(db).close()
    assert _ingest(db, tmp_path) == 0
    assert _export(db, tmp_path / "r.json") == 0
    assert _bridge(db, tmp_path / "out") == 0


def test_every_creator_makes_the_canonical_shape(tmp_path: Path) -> None:
    ingest_db = tmp_path / "ingest.sqlite"
    con = connect(ingest_db)
    ensure_recovered_schema(con)
    canonical = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='recovered_function'"
    ).fetchone()[0]
    con.close()

    export_db = tmp_path / "export.sqlite"
    connect(export_db).close()
    assert _export(export_db, tmp_path / "r.json") == 0
    con = sqlite3.connect(export_db)
    created = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='recovered_function'"
    ).fetchone()[0]
    # A report verb must not start creating unrelated tables.
    assert con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='reuse_candidate'"
    ).fetchone() is None
    con.close()
    assert created == canonical


def _narrow_store(path: Path) -> None:
    con = connect(path)
    con.executescript(OLD_NARROW_DDL)
    con.executemany(
        f"INSERT INTO recovered_function ({', '.join(NARROW_COLUMNS)}) "
        f"VALUES ({', '.join('?' for _ in NARROW_COLUMNS)})",
        NARROW_ROWS,
    )
    con.commit()
    con.close()


def _narrow_snapshot(con) -> list[tuple]:
    return sorted(
        tuple(row)
        for row in con.execute(
            f"SELECT {', '.join(NARROW_COLUMNS)} FROM recovered_function"
        )
    )


def test_narrow_store_upgrades_additively_and_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "narrow.sqlite"
    _narrow_store(db)
    con = connect(db)
    assert "binary_id" not in _cols(con)
    before_cols = _cols(con)
    before = _narrow_snapshot(con)

    ensure_recovered_schema(con)
    ensure_recovered_schema(con)

    after_cols = _cols(con)
    assert after_cols.count("binary_id") == 1
    # Existing columns keep their order; the new one is appended.
    assert after_cols[: len(before_cols)] == before_cols
    assert after_cols[len(before_cols):] == ["binary_id"]
    assert _narrow_snapshot(con) == before
    assert con.execute(
        "SELECT COUNT(*) FROM recovered_function WHERE binary_id IS NOT NULL"
    ).fetchone()[0] == 0

    recovered = external_bridge.load_recovered(con)
    assert len(recovered) == len(NARROW_ROWS)
    assert all(rec["binary_id"] is None for rec in recovered)
    con.close()


def test_narrow_store_survives_export_then_bridge(tmp_path: Path) -> None:
    db = tmp_path / "narrow.sqlite"
    _narrow_store(db)
    con = connect(db)
    before = _narrow_snapshot(con)
    con.close()

    assert _export(db, tmp_path / "r.json") == 0
    assert _export(db, tmp_path / "r2.json") == 0
    assert _bridge(db, tmp_path / "out") == 0

    con = connect(db)
    assert _narrow_snapshot(con) == before
    assert _cols(con).count("binary_id") == 1
    report = build(con)
    assert len(report["results"]) == len(NARROW_ROWS)
    con.close()


def test_narrow_store_upgraded_by_bridge_alone(tmp_path: Path) -> None:
    db = tmp_path / "narrow.sqlite"
    _narrow_store(db)
    assert _bridge(db, tmp_path / "out") == 0
    con = connect(db)
    assert "binary_id" in _cols(con)
    assert len(_narrow_snapshot(con)) == len(NARROW_ROWS)
    con.close()


def test_canonical_store_gets_no_alter(tmp_path: Path) -> None:
    db = tmp_path / "wide.sqlite"
    con = connect(db)
    ensure_recovered_schema(con)
    con.close()
    con = connect(db)
    seen: list[str] = []
    con.set_trace_callback(seen.append)
    ensure_recovered_schema(con)
    con.set_trace_callback(None)
    assert not [sql for sql in seen if "ALTER" in sql.upper()]
    con.close()


# --- Narrow tables: rebuild when empty, unique index when safe --------------

from agentdecompile_recovery.corpus import db as legacy_db  # noqa: E402
from agentdecompile_recovery.corpus import mizuchi_bridge  # noqa: E402
from agentdecompile_recovery.corpus.ingest_recovered import (  # noqa: E402
    apply_seed_promotions,
    ensure_recovered_function,
)

UNIQUE_ROWS = [
    ("swkotor", "FUN_00401000", 0x401000, 16, "__stdcall", 1, 7, "/r/a.c", "ev-a", "c3"),
    ("swkotor2", "FUN_00402000", 0x402000, 8, None, 0, None, "/r/b.c", "ev-b", "90"),
]

PROMOTION = {
    "program": "swkotor", "binary_id": 3, "addr": 0x401000, "name": "FUN_00401000",
    "size": 16, "convention": None, "machine_code": "c3", "real_c": 1,
    "logical_id": 7, "path": "/r/seed.c", "evidence": "seed-validation-byte-exact:x",
}


def _plain_narrow(path: Path, rows: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.executescript(OLD_NARROW_DDL)
    con.executemany(
        f"INSERT INTO recovered_function ({', '.join(NARROW_COLUMNS)}) "
        f"VALUES ({', '.join('?' for _ in NARROW_COLUMNS)})",
        rows,
    )
    con.commit()
    con.close()


def _open(path: Path, **kw) -> sqlite3.Connection:
    con = sqlite3.connect(path, **kw)
    con.row_factory = sqlite3.Row
    return con


def _master(con) -> list[tuple]:
    return sorted(
        tuple(row)
        for row in con.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE tbl_name='recovered_function'"
        )
    )


def _info(con) -> dict[str, tuple[int, int]]:
    """column -> (notnull, pk)"""
    return {
        row[1]: (row[3], row[5])
        for row in con.execute("PRAGMA table_info(recovered_function)")
    }


def _canonical_sql(tmp_path: Path) -> str:
    con = _open(tmp_path / "canonical.sqlite")
    ensure_recovered_function(con)
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='recovered_function'"
    ).fetchone()[0]
    con.close()
    return sql


def test_empty_narrow_table_is_rebuilt_canonical(tmp_path: Path) -> None:
    db_path = tmp_path / "empty-narrow.sqlite"
    _plain_narrow(db_path, [])
    con = _open(db_path)
    ensure_recovered_function(con)
    info = _info(con)
    assert info["program"] == (1, 1) and info["name"] == (1, 2)
    assert info["real_c"][0] == 1 and info["path"][0] == 1
    assert con.execute(
        "SELECT sql FROM sqlite_master WHERE name='recovered_function'"
    ).fetchone()[0] == _canonical_sql(tmp_path)
    assert not con.in_transaction

    apply_seed_promotions(con, [PROMOTION])
    apply_seed_promotions(con, [PROMOTION])
    assert con.execute("SELECT COUNT(*) FROM recovered_function").fetchone()[0] == 1
    con.close()


def test_nonempty_narrow_table_keeps_rows_and_gets_unique_index(tmp_path: Path) -> None:
    db_path = tmp_path / "narrow-rows.sqlite"
    _plain_narrow(db_path, UNIQUE_ROWS)
    con = _open(db_path)
    ensure_recovered_function(con)
    assert _narrow_snapshot(con) == sorted(UNIQUE_ROWS)
    assert "binary_id" in _info(con)
    assert all(pk == 0 for _nn, pk in _info(con).values())
    assert con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='ux_recovered_program_name'"
    ).fetchone() is not None

    apply_seed_promotions(con, [PROMOTION])
    apply_seed_promotions(con, [PROMOTION])
    assert con.execute("SELECT COUNT(*) FROM recovered_function").fetchone()[0] == 2
    con.close()


def test_narrow_table_with_duplicates_keeps_rows_and_no_index(tmp_path: Path) -> None:
    db_path = tmp_path / "narrow-dups.sqlite"
    _plain_narrow(db_path, NARROW_ROWS)
    con = _open(db_path)
    ensure_recovered_function(con)
    assert _narrow_snapshot(con) == sorted(NARROW_ROWS)
    assert "binary_id" in _info(con)
    assert con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='ux_recovered_program_name'"
    ).fetchone() is None
    con.close()


@pytest.mark.parametrize("rows", [[], UNIQUE_ROWS, NARROW_ROWS], ids=["empty", "unique", "dups"])
def test_narrow_upgrade_is_idempotent(tmp_path: Path, rows: list[tuple]) -> None:
    db_path = tmp_path / "narrow.sqlite"
    _plain_narrow(db_path, rows)
    con = _open(db_path)
    ensure_recovered_function(con)
    first = (_master(con), _narrow_snapshot(con))
    ensure_recovered_function(con)
    ensure_recovered_function(con)
    assert (_master(con), _narrow_snapshot(con)) == first
    con.close()


def _canonical_store(path: Path) -> None:
    con = _open(path)
    ensure_recovered_function(con)
    apply_seed_promotions(con, [PROMOTION])
    con.close()


def test_canonical_store_needs_no_write_access(tmp_path: Path) -> None:
    db_path = tmp_path / "wide.sqlite"
    _canonical_store(db_path)
    db_path.chmod(0o444)
    try:
        con = _open(db_path)
        ensure_recovered_function(con)
        assert len(external_bridge.load_recovered(con)) == 1
        assert len(mizuchi_bridge.load_recovered(con)) == 1
        con.close()
    finally:
        db_path.chmod(0o644)


def test_canonical_store_takes_no_write_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "wide.sqlite"
    _canonical_store(db_path)
    holder = sqlite3.connect(db_path)
    holder.execute("BEGIN IMMEDIATE")
    try:
        con = _open(db_path, timeout=0.1)
        ensure_recovered_function(con)
        assert len(external_bridge.load_recovered(con)) == 1
        assert len(mizuchi_bridge.load_recovered(con)) == 1
        assert not con.in_transaction
        con.close()
    finally:
        holder.rollback()
        holder.close()


def test_mizuchi_load_recovered_on_store_without_table(tmp_path: Path) -> None:
    con = legacy_db.connect(tmp_path / "legacy.sqlite")
    assert mizuchi_bridge.load_recovered(con) == []
    con.close()


def test_mizuchi_load_recovered_on_narrow_store(tmp_path: Path) -> None:
    db_path = tmp_path / "narrow.sqlite"
    _plain_narrow(db_path, UNIQUE_ROWS)
    con = _open(db_path)
    recovered = mizuchi_bridge.load_recovered(con)
    assert len(recovered) == len(UNIQUE_ROWS)
    assert all(rec["binary_id"] is None for rec in recovered)
    con.close()


# --- The upgrade never commits or rolls back a caller's transaction ---------

from agentdecompile_recovery.corpus import ingest_recovered  # noqa: E402

STORE_SHAPES = ["empty-narrow", "narrow-rows", "missing"]


def _shaped_store(path: Path, shape: str) -> None:
    if shape == "empty-narrow":
        _plain_narrow(path, [])
    elif shape == "narrow-rows":
        _plain_narrow(path, UNIQUE_ROWS)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE caller_note (v TEXT)")
    con.commit()
    con.close()


def _notes(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM caller_note").fetchone()[0]
    finally:
        con.close()


def _shape(con) -> list[tuple]:
    return list(con.execute("PRAGMA table_info(recovered_function)"))


@pytest.mark.parametrize("shape", STORE_SHAPES)
def test_caller_rollback_survives_ensure(tmp_path: Path, shape: str) -> None:
    db_path = tmp_path / "s.sqlite"
    _shaped_store(db_path, shape)
    con = _open(db_path)
    before = _shape(con)
    con.execute("INSERT INTO caller_note VALUES ('pending')")
    assert con.in_transaction
    ensure_recovered_function(con)
    assert con.in_transaction
    con.rollback()
    assert _notes(db_path) == 0
    # The upgrade joined the caller's transaction, so it rolled back with it.
    assert _shape(con) == before
    con.close()


@pytest.mark.parametrize("shape", STORE_SHAPES)
def test_caller_commit_keeps_rows_and_upgrade(tmp_path: Path, shape: str) -> None:
    db_path = tmp_path / "s.sqlite"
    _shaped_store(db_path, shape)
    con = _open(db_path)
    con.execute("INSERT INTO caller_note VALUES ('kept')")
    ensure_recovered_function(con)
    con.commit()
    con.close()
    assert _notes(db_path) == 1
    con = _open(db_path)
    assert "binary_id" in _info(con)
    if shape != "narrow-rows":
        assert _info(con)["program"] == (1, 1)
    else:
        assert _narrow_snapshot(con) == sorted(UNIQUE_ROWS)
    con.close()


@pytest.mark.parametrize("shape", STORE_SHAPES)
def test_failed_upgrade_inside_caller_transaction(
    tmp_path: Path, shape: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "s.sqlite"
    _shaped_store(db_path, shape)
    monkeypatch.setattr(
        ingest_recovered, "RECOVERED_FUNCTION_DDL",
        ingest_recovered.RECOVERED_FUNCTION_DDL + ";\nCREATE BOGUS STATEMENT",
    )
    monkeypatch.setattr(
        ingest_recovered, "RECOVERED_FUNCTION_ADDED_COLUMNS",
        (("binary_id", "INTEGER"), ("bogus", "NOT A )) TYPE")),
    )
    con = _open(db_path)
    before = _shape(con)
    con.execute("INSERT INTO caller_note VALUES ('pending')")
    with pytest.raises(sqlite3.OperationalError):
        ensure_recovered_function(con)
    assert con.in_transaction
    assert _shape(con) == before
    assert con.execute("SELECT COUNT(*) FROM caller_note").fetchone()[0] == 1
    con.rollback()
    assert _notes(db_path) == 0
    con.close()


@pytest.mark.parametrize("shape", STORE_SHAPES)
def test_failed_upgrade_without_caller_transaction_rolls_back(
    tmp_path: Path, shape: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "s.sqlite"
    _shaped_store(db_path, shape)
    original_ddl = ingest_recovered.RECOVERED_FUNCTION_DDL
    original_cols = ingest_recovered.RECOVERED_FUNCTION_ADDED_COLUMNS
    monkeypatch.setattr(
        ingest_recovered, "RECOVERED_FUNCTION_DDL",
        original_ddl + ";\nCREATE BOGUS STATEMENT",
    )
    monkeypatch.setattr(
        ingest_recovered, "RECOVERED_FUNCTION_ADDED_COLUMNS",
        (("binary_id", "INTEGER"), ("bogus", "NOT A )) TYPE")),
    )
    con = _open(db_path)
    before = _shape(con)
    rows = len(_narrow_snapshot(con)) if before else 0
    assert not con.in_transaction
    with pytest.raises(sqlite3.OperationalError):
        ensure_recovered_function(con)
    assert not con.in_transaction
    assert _shape(con) == before
    if before:
        assert len(_narrow_snapshot(con)) == rows

    monkeypatch.setattr(ingest_recovered, "RECOVERED_FUNCTION_DDL", original_ddl)
    monkeypatch.setattr(ingest_recovered, "RECOVERED_FUNCTION_ADDED_COLUMNS", original_cols)
    ensure_recovered_function(con)
    assert "binary_id" in _info(con)
    assert len(_narrow_snapshot(con)) == rows
    con.close()
