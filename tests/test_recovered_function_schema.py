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
