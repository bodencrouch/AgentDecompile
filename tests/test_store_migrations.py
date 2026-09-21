"""Schema versioning and the migration ledger for the corpus store.

Every test runs on a temporary SQLite file. The legacy fixture is the schema
the store had before the ledger existed; it is executed verbatim to build a
store at ``user_version = 0``.
"""

from __future__ import annotations

import multiprocessing
import re
import sqlite3
import threading
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import migrations, store

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).parent / "fixtures" / "store" / "legacy_schema_v0.sql"

# Python 3.14 defaults to a non-fork start method on Linux; the worker below
# is a module-level function, but fork keeps the test module import simple.
_FORK = multiprocessing.get_context("fork")


def _legacy_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(FIXTURE.read_text(encoding="utf-8"))
    con.commit()
    con.close()


def _ledger(path: Path) -> list[tuple]:
    con = sqlite3.connect(path)
    try:
        return con.execute(
            "SELECT version, name FROM schema_migration ORDER BY version"
        ).fetchall()
    finally:
        con.close()


def _sqlite_master(con: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    rows = con.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall()
    return [(r[0], r[1], r[2], re.sub(r"\s+", " ", r[3]).strip()) for r in rows]


def _table_infos(con: sqlite3.Connection) -> dict[str, list[tuple]]:
    names = sorted(
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    )
    return {
        name: sorted(tuple(r) for r in con.execute(f"PRAGMA table_info({name})"))
        for name in names
    }


def _pragma(con: sqlite3.Connection, name: str) -> int:
    return int(con.execute(f"PRAGMA {name}").fetchone()[0])


# --- registry ---------------------------------------------------------------


def test_registry_is_ordered_and_named() -> None:
    versions = [m.version for m in migrations.MIGRATIONS]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)
    assert versions[-1] == migrations.SCHEMA_VERSION
    names = [m.name for m in migrations.MIGRATIONS]
    assert len(set(names)) == len(names)
    assert migrations.MIGRATIONS[0].name == "baseline"


def test_registry_rejects_bad_order() -> None:
    bad = [
        migrations.Migration(2, "b", lambda con: None),
        migrations.Migration(1, "a", lambda con: None),
    ]
    with pytest.raises(AssertionError):
        migrations._check_registry(bad)
    dup = [
        migrations.Migration(1, "same", lambda con: None),
        migrations.Migration(2, "same", lambda con: None),
    ]
    with pytest.raises(AssertionError):
        migrations._check_registry(dup)


def test_statement_splitter_drops_pragmas_and_keeps_literals() -> None:
    script = (
        "-- leading note\nPRAGMA journal_mode=WAL;\n\nCREATE TABLE a(x TEXT DEFAULT 'p;q');\n"
        "-- trailing note\nCREATE INDEX i ON a(x)"
    )
    assert migrations._statements(script) == [
        "CREATE TABLE a(x TEXT DEFAULT 'p;q')",
        "CREATE INDEX i ON a(x)",
    ]


# --- fresh store ------------------------------------------------------------


def test_fresh_store_is_at_schema_version_with_one_ledger_row_per_migration(tmp_path: Path) -> None:
    db = tmp_path / "fresh.sqlite"
    con = store.connect(db)
    assert _pragma(con, "user_version") == migrations.SCHEMA_VERSION
    rows = migrations.ledger_rows(con)
    assert [(r["version"], r["name"]) for r in rows] == [
        (m.version, m.name) for m in migrations.MIGRATIONS
    ]
    for r in rows:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", r["applied_at"])
    # Golden: the table shapes a second connect must reproduce exactly.
    golden = _table_infos(con)
    assert set(golden) >= {"binary", "func", "match", "identity", "schema_migration"}
    assert "content_sha256" in {c[1] for c in golden["binary"]}
    assert "cfg_nodes" in {c[1] for c in golden["func"]}
    con.close()

    again = store.connect(db)
    assert _table_infos(again) == golden
    again.close()


def test_second_connect_runs_no_ddl_and_writes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "twice.sqlite"
    first = store.connect(db)
    before = (
        _pragma(first, "user_version"),
        _pragma(first, "schema_version"),
        _sqlite_master(first),
        first.execute("SELECT * FROM schema_migration ORDER BY version").fetchall(),
    )
    first.close()
    second = store.connect(db)
    after = (
        _pragma(second, "user_version"),
        _pragma(second, "schema_version"),
        _sqlite_master(second),
        second.execute("SELECT * FROM schema_migration ORDER BY version").fetchall(),
    )
    assert migrations.apply_pending(second) == []
    assert not second.in_transaction
    second.close()
    assert before == after


def test_apply_pending_hot_path_never_opens_a_transaction(tmp_path: Path) -> None:
    db = tmp_path / "hot.sqlite"
    store.connect(db).close()
    con = sqlite3.connect(db)
    seen: list[str] = []
    con.set_trace_callback(seen.append)
    assert migrations.apply_pending(con) == []
    assert seen == ["PRAGMA user_version"]
    con.close()


# --- legacy store -----------------------------------------------------------


def test_legacy_store_migrates_to_the_fresh_shape(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite"
    _legacy_db(legacy)
    raw = sqlite3.connect(legacy)
    assert _pragma(raw, "user_version") == 0
    assert "content_sha256" not in {r[1] for r in raw.execute("PRAGMA table_info(binary)")}
    raw.close()

    con = store.connect(legacy)
    assert _pragma(con, "user_version") == migrations.SCHEMA_VERSION
    assert _ledger(legacy) == [(m.version, m.name) for m in migrations.MIGRATIONS]
    migrated_master = _sqlite_master(con)
    migrated_infos = _table_infos(con)
    con.close()

    fresh = store.connect(tmp_path / "fresh.sqlite")
    assert _sqlite_master(fresh) == migrated_master
    assert _table_infos(fresh) == migrated_infos
    fresh.close()


def test_legacy_store_keeps_its_rows(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite"
    _legacy_db(legacy)
    raw = sqlite3.connect(legacy)
    raw.executemany(
        "INSERT INTO binary(id, repo_path, slug, recovery_family) VALUES (?,?,?,?)",
        [(1, "/r/one", "one", "fam"), (2, "/r/two", "two", None)],
    )
    raw.execute("INSERT INTO func(binary_id, addr, name) VALUES (1, 4096, 'entry')")
    raw.commit()
    raw.close()

    con = store.connect(legacy)
    con.commit()
    rows = con.execute("SELECT id, slug, recovery_family FROM binary ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [(1, "one", "fam"), (2, "two", "unclassified:2")]
    assert con.execute("SELECT count(*) FROM func").fetchone()[0] == 1
    con.close()


# --- read-only connections -------------------------------------------------


def test_read_only_connect_to_migrated_store_writes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "migrated.sqlite"
    store.connect(db).close()
    ro = store.connect(db, read_only=True)
    assert _pragma(ro, "user_version") == migrations.SCHEMA_VERSION
    assert migrations.apply_pending(ro) == []
    assert not ro.in_transaction
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute("INSERT INTO eval(run) VALUES ('x')")
    ro.close()


def test_read_only_connect_to_legacy_store_raises(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite"
    _legacy_db(legacy)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        store.connect(legacy, read_only=True)
    # Nothing was recorded by the failed attempt.
    raw = sqlite3.connect(legacy)
    assert _pragma(raw, "user_version") == 0
    assert not raw.execute(
        "SELECT 1 FROM sqlite_master WHERE name='schema_migration'"
    ).fetchone()
    raw.close()


def _with_noop_v2() -> list[migrations.Migration]:
    return migrations.MIGRATIONS + [
        migrations.Migration(migrations.SCHEMA_VERSION + 1, "noop_probe", lambda con: None)
    ]


def test_pending_migration_is_tolerated_on_read_only_once_ledger_exists(tmp_path: Path) -> None:
    db = tmp_path / "ledgered.sqlite"
    store.connect(db).close()
    ro = store.connect(db, read_only=True)
    # A future step that this handle cannot apply: another writer will.
    assert migrations.apply_pending(ro, migrations=_with_noop_v2()) == []
    assert not ro.in_transaction
    assert _pragma(ro, "user_version") == migrations.SCHEMA_VERSION
    ro.close()


def test_pending_migration_is_tolerated_when_lock_is_busy(tmp_path: Path) -> None:
    db = tmp_path / "busy.sqlite"
    store.connect(db).close()
    holder = sqlite3.connect(db)
    holder.execute("BEGIN IMMEDIATE")
    waiter = sqlite3.connect(db, timeout=0.2)
    waiter.execute("PRAGMA busy_timeout=200")
    assert migrations.apply_pending(waiter, migrations=_with_noop_v2()) == []
    assert not waiter.in_transaction
    holder.rollback()
    holder.close()
    # Once the lock is free the same handle applies the step.
    applied = migrations.apply_pending(waiter, migrations=_with_noop_v2())
    assert [m.name for m in applied] == ["noop_probe"]
    assert _pragma(waiter, "user_version") == migrations.SCHEMA_VERSION + 1
    assert [r["name"] for r in migrations.ledger_rows(waiter)][-1] == "noop_probe"
    waiter.close()


def test_failed_migration_rolls_back_as_one_transaction(tmp_path: Path) -> None:
    db = tmp_path / "atomic.sqlite"
    store.connect(db).close()

    def half_then_fail(con: sqlite3.Connection) -> None:
        con.execute("CREATE TABLE probe_half(x)")
        raise sqlite3.OperationalError("no such table: synthetic")

    bad = migrations.MIGRATIONS + [
        migrations.Migration(migrations.SCHEMA_VERSION + 1, "half", half_then_fail)
    ]
    con = sqlite3.connect(db)
    with pytest.raises(sqlite3.OperationalError, match="synthetic"):
        migrations.apply_pending(con, migrations=bad)
    assert not con.in_transaction
    assert _pragma(con, "user_version") == migrations.SCHEMA_VERSION
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='probe_half'").fetchone()
    assert [r["version"] for r in migrations.ledger_rows(con)] == [
        m.version for m in migrations.MIGRATIONS
    ]
    con.close()


# --- concurrency -----------------------------------------------------------


def test_second_writer_rechecks_version_under_the_lock(tmp_path: Path) -> None:
    """Deterministic version of the two-process race.

    Writer A holds the write lock mid-migration; writer B blocks on its own
    BEGIN IMMEDIATE. When A commits, B must see version 1 and skip instead
    of applying the baseline a second time.
    """
    legacy = tmp_path / "race.sqlite"
    _legacy_db(legacy)
    a_inside = threading.Event()
    release_a = threading.Event()
    outcome: dict[str, object] = {}

    def gated_baseline(con: sqlite3.Connection) -> None:
        migrations._baseline(con)
        a_inside.set()
        assert release_a.wait(30)

    registry_a = [migrations.Migration(1, "baseline", gated_baseline)]

    def writer_a() -> None:
        con = sqlite3.connect(legacy, timeout=30)
        outcome["a"] = [m.name for m in migrations.apply_pending(con, migrations=registry_a)]
        con.close()

    def writer_b() -> None:
        con = sqlite3.connect(legacy, timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        outcome["b"] = [m.name for m in migrations.apply_pending(con)]
        outcome["b_version"] = _pragma(con, "user_version")
        con.close()

    ta = threading.Thread(target=writer_a)
    ta.start()
    assert a_inside.wait(30)
    tb = threading.Thread(target=writer_b)
    tb.start()
    tb.join(timeout=1)
    assert tb.is_alive(), "B should be blocked on the write lock while A is mid-migration"
    release_a.set()
    ta.join(timeout=30)
    tb.join(timeout=30)
    assert outcome["a"] == ["baseline"]
    assert outcome["b"] == []
    assert outcome["b_version"] == migrations.SCHEMA_VERSION
    assert _ledger(legacy) == [(1, "baseline")]


def _connect_worker(db: str, barrier, result_path: str) -> None:
    barrier.wait()
    try:
        con = store.connect(db)
        version = int(con.execute("PRAGMA user_version").fetchone()[0])
        con.close()
        Path(result_path).write_text(f"ok {version}", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 -- reported to the parent as text
        Path(result_path).write_text(f"error {exc!r}", encoding="utf-8")


def test_two_processes_migrate_the_same_legacy_store_once(tmp_path: Path) -> None:
    legacy = tmp_path / "shared.sqlite"
    _legacy_db(legacy)
    barrier = _FORK.Barrier(2)
    results = [tmp_path / "a.txt", tmp_path / "b.txt"]
    procs = [
        _FORK.Process(target=_connect_worker, args=(str(legacy), barrier, str(out)))
        for out in results
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
    assert all(p.exitcode == 0 for p in procs)
    texts = [out.read_text(encoding="utf-8") for out in results]
    assert texts == [f"ok {migrations.SCHEMA_VERSION}"] * 2, texts
    assert _ledger(legacy) == [(m.version, m.name) for m in migrations.MIGRATIONS]
