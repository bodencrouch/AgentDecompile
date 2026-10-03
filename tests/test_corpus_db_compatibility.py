"""Canonical schema admission and retained legacy routing (authored, not run)."""

from __future__ import annotations

import ast
import importlib
import sqlite3
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agentdecompile_recovery.corpus import db, migrations, store

pytestmark = pytest.mark.unit
CORPUS = Path(store.__file__).parent
FIXTURE = Path(__file__).parent / "fixtures" / "store" / "legacy_schema_v0.sql"


def test_public_compatibility_symbols_and_helpers(tmp_path):
    assert db.SCHEMA is store.SCHEMA
    assert db.j is store.j
    assert db.ensure_priority_index is store.ensure_priority_index
    assert db.j(None) is None
    assert db.j({"a": [1, 2]}) == '{"a":[1,2]}'
    assert db.DB_PATH == Path(db.__file__).resolve().parent.parent / "db" / "kotorxid.sqlite"
    con = store.connect(tmp_path / "helpers.sqlite")
    try:
        con.execute("DROP INDEX ix_func_priority_cover")
        db.ensure_priority_index(con)
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE name='ix_func_priority_cover'"
        ).fetchone()[0] == "ix_func_priority_cover"
    finally:
        con.close()


@pytest.mark.parametrize("as_string", [False, True])
@pytest.mark.parametrize("read_only", [False, True])
def test_explicit_paths_forward_unchanged_without_warning(tmp_path, monkeypatch, as_string, read_only):
    path = tmp_path / "selected.sqlite"
    selected = str(path) if as_string else path
    sentinel = object()
    connect = Mock(return_value=sentinel)
    monkeypatch.setattr(store, "connect", connect)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert db.connect(selected, read_only=read_only) is sentinel
    assert caught == []
    connect.assert_called_once_with(selected, read_only=read_only)


def test_omitted_path_warns_and_forwards_historical_existing_only(tmp_path, monkeypatch):
    historical = tmp_path / "historical.sqlite"
    store.connect(historical).close()
    monkeypatch.setattr(db, "DB_PATH", historical)
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_DB", str(tmp_path / "unrelated.sqlite"))
    canonical = store.connect
    spy = Mock(wraps=canonical)
    monkeypatch.setattr(store, "connect", spy)
    with pytest.warns(FutureWarning) as caught:
        con = db.connect()
    try:
        assert str(historical.resolve()) in str(caught[0].message)
        assert "no longer created" in str(caught[0].message)
        assert con.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION
    finally:
        con.close()
    spy.assert_called_once_with(historical, read_only=False, create=False)
    assert not (tmp_path / "unrelated.sqlite").exists()


@pytest.mark.parametrize("missing_parent", [False, True])
def test_implicit_missing_path_refuses_without_creating_parent(tmp_path, monkeypatch, missing_parent):
    historical = tmp_path / "missing-parent" / "db.sqlite" if missing_parent else tmp_path / "absent.sqlite"
    monkeypatch.setattr(db, "DB_PATH", historical)
    with pytest.warns(FutureWarning), pytest.raises(sqlite3.OperationalError):
        db.connect()
    assert not historical.exists()
    if missing_parent:
        assert not historical.parent.exists()


def test_implicit_deletion_race_uses_atomic_escaped_rw_open(tmp_path, monkeypatch):
    historical = tmp_path / "selected ?#% file.sqlite"
    store.connect(historical).close()
    monkeypatch.setattr(db, "DB_PATH", historical)
    real_connect = sqlite3.connect
    calls = []

    def remove_before_open(target, **kwargs):
        calls.append((target, kwargs))
        assert target == historical.resolve().as_uri() + "?mode=rw"
        assert kwargs == {"uri": True, "timeout": 30}
        historical.unlink()
        return real_connect(target, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", remove_before_open)
    with pytest.warns(FutureWarning), pytest.raises(sqlite3.OperationalError):
        db.connect()
    assert len(calls) == 1
    assert not historical.exists()


@pytest.mark.parametrize("create", [False, True])
def test_read_only_missing_path_never_creates(tmp_path, create):
    path = tmp_path / "absent-parent" / "absent.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        store.connect(path, read_only=True, create=create)
    assert not path.parent.exists()


def _schema_shape(con):
    return {
        row[0]: [tuple(col) for col in con.execute(f'PRAGMA table_info("{row[0]}")')]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    }


def test_explicit_fresh_and_known_v0_migrate_and_preserve_unknown_data(tmp_path):
    legacy = tmp_path / "legacy.sqlite"
    raw = sqlite3.connect(legacy)
    raw.executescript(FIXTURE.read_text(encoding="utf-8"))
    raw.execute("ALTER TABLE binary ADD COLUMN unknown_extension TEXT")
    raw.execute("CREATE TABLE extension_table(payload TEXT)")
    raw.execute("INSERT INTO extension_table VALUES ('keep me')")
    raw.executemany(
        "INSERT INTO binary(repo_path, slug, role, game, platform, unknown_extension) VALUES (?,?,?,?,?,?)",
        [("/unknown", "unknown", "future-role", "future-game", "future-platform", "keep"),
         ("/null", "null", None, None, None, None)],
    )
    raw.commit()
    raw.close()
    fresh = db.connect(tmp_path / "fresh.sqlite")
    migrated = db.connect(legacy)
    try:
        expected = [(m.version, m.name) for m in migrations.MIGRATIONS]
        for con in (fresh, migrated):
            assert con.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION
            assert [tuple(r) for r in con.execute(
                "SELECT version, name FROM schema_migration ORDER BY version"
            )] == expected
        for con in (fresh, migrated):
            store.require_stabs_schema(con)
            store.require_decomp_schema(con)
            assert store.decomp_read_state(con) is None
            assert con.execute("SELECT COUNT(*) FROM stabs_type").fetchone()[0] == 0
        fresh_shape, legacy_shape = _schema_shape(fresh), _schema_shape(migrated)
        legacy_shape.pop("extension_table")
        # ALTER positions differ when an extension precedes migration columns.
        def normalize(cols):
            return {tuple(col[1:]) for col in cols if col[1] != "unknown_extension"}

        assert {t: normalize(c) for t, c in fresh_shape.items()} == {
            t: normalize(c) for t, c in legacy_shape.items()
        }
        assert [tuple(r) for r in migrated.execute(
            "SELECT role, game, platform, unknown_extension, content_sha256, recovery_family "
            "FROM binary ORDER BY id"
        )] == [("future-role", "future-game", "future-platform", "keep", None, None),
               (None, None, None, None, None, None)]
        assert migrated.execute("SELECT payload FROM extension_table").fetchone()[0] == "keep me"
    finally:
        fresh.close()
        migrated.close()


def _instrument_admission(monkeypatch):
    opened, statements = [], []
    real_connect = sqlite3.connect

    class TracedConnection(sqlite3.Connection):
        close_count = 0

        def close(self):
            self.close_count += 1
            super().close()

    def traced(*args, **kwargs):
        con = real_connect(*args, factory=TracedConnection, **kwargs)
        con.set_trace_callback(statements.append)
        opened.append(con)
        return con

    monkeypatch.setattr(sqlite3, "connect", traced)
    migrate = Mock(side_effect=AssertionError("admission called migration"))
    backfill = Mock(side_effect=AssertionError("admission called backfill"))
    monkeypatch.setattr(migrations, "apply_pending", migrate)
    monkeypatch.setattr(store, "backfill_recovery_family", backfill)
    return opened, statements, migrate, backfill


def _assert_reader_only(statements, migrate, backfill):
    migrate.assert_not_called()
    backfill.assert_not_called()
    assert statements
    assert all(sql.lstrip().upper().startswith(("SELECT ", "PRAGMA BUSY_TIMEOUT=", "PRAGMA USER_VERSION", "PRAGMA TABLE_INFO(", "PRAGMA MAIN.TABLE_XINFO(")) for sql in statements)


def test_current_read_only_admission_never_attempts_backfill_or_writes(tmp_path, monkeypatch):
    path = tmp_path / "current ?#.sqlite"
    con = store.connect(path)
    con.execute(
        "INSERT INTO binary(repo_path,slug,content_sha256,recovery_family) VALUES ('/a','a',?,'unclassified:1')",
        ("ab" * 32,),
    )
    con.commit()
    assert all(r[0] is None for r in con.execute("SELECT basis_hash FROM schema_migration"))
    con.close()
    opened, statements, migrate, backfill = _instrument_admission(monkeypatch)
    ro = store.connect(path, read_only=True)
    try:
        assert ro.execute("SELECT recovery_family FROM binary").fetchone()[0] == "unclassified:1"
        assert not ro.in_transaction
        _assert_reader_only(statements, migrate, backfill)
    finally:
        ro.close()
    assert opened == [ro]
    assert ro.close_count == 1


@pytest.mark.parametrize("case", ["v0", "intermediate", "future", "no-ledger", "missing-entry", "wrong-version", "wrong-name", "malformed-columns", "ledger-view"])
def test_read_only_refuses_incompatible_version_or_ledger_and_closes(tmp_path, monkeypatch, case):
    path = tmp_path / "incompatible.sqlite"
    con = store.connect(path)
    if case in {"v0", "intermediate", "future"}:
        version = {"v0": 0, "intermediate": 1, "future": migrations.SCHEMA_VERSION + 1}[case]
        con.execute(f"PRAGMA user_version={version}")
    elif case == "no-ledger":
        con.execute("DROP TABLE schema_migration")
    elif case == "missing-entry":
        con.execute("DELETE FROM schema_migration WHERE version=1")
    elif case == "wrong-version":
        con.execute("UPDATE schema_migration SET version=100 WHERE version=1")
    elif case == "wrong-name":
        con.execute("UPDATE schema_migration SET name='unexpected' WHERE version=1")
    elif case == "ledger-view":
        con.execute("ALTER TABLE schema_migration RENAME TO ledger_data")
        con.execute("CREATE VIEW schema_migration AS SELECT * FROM ledger_data")
    else:
        con.execute("ALTER TABLE schema_migration RENAME COLUMN basis_hash TO unknown_basis")
    con.commit()
    con.close()
    opened, statements, migrate, backfill = _instrument_admission(monkeypatch)
    with pytest.raises(store.SchemaCompatibilityError) as caught:
        store.connect(path, read_only=True)
    message = str(caught.value)
    assert str(path.resolve()) in message
    assert "observed schema version" in message and "supported version" in message
    assert "8080" in message
    _assert_reader_only(statements, migrate, backfill)
    assert len(opened) == 1 and opened[0].close_count == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_future_writable_refuses_before_journal_or_migration_mutation(tmp_path, monkeypatch):
    path = tmp_path / "future.sqlite"
    raw_connect = sqlite3.connect
    raw = raw_connect(path)
    raw.execute(f"PRAGMA user_version={migrations.SCHEMA_VERSION + 1}")
    raw.execute("CREATE TABLE future_data(payload TEXT)")
    raw.execute("INSERT INTO future_data VALUES ('preserve')")
    raw.commit()
    raw.close()
    opened, statements, migrate, backfill = _instrument_admission(monkeypatch)
    with pytest.raises(store.SchemaCompatibilityError):
        db.connect(path)
    _assert_reader_only(statements, migrate, backfill)
    assert len(opened) == 1 and opened[0].close_count == 1
    check = raw_connect(path)
    try:
        assert check.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert check.execute("SELECT payload FROM future_data").fetchone()[0] == "preserve"
        assert check.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION + 1
    finally:
        check.close()


@pytest.mark.parametrize("failure", [sqlite3.OperationalError("no such table: unexpected"), KeyboardInterrupt("interrupted")])
def test_failed_later_migration_keeps_earlier_commit_and_closes(tmp_path, monkeypatch, failure):
    path = tmp_path / "partial.sqlite"
    real_apply, real_connect = migrations.apply_pending, sqlite3.connect
    opened = []

    def connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        opened.append(con)
        return con

    def first(con):
        con.execute("CREATE TABLE durable(payload TEXT)")
        con.execute("INSERT INTO durable VALUES ('committed')")

    def second(con):
        con.execute("CREATE TABLE unfinished(payload TEXT)")
        raise failure

    steps = [migrations.Migration(1, "first", first), migrations.Migration(2, "second", second)]
    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(migrations, "apply_pending", lambda con: real_apply(con, migrations=steps))
    with pytest.raises(type(failure), match=str(failure)):
        db.connect(path)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    check = real_connect(path)
    try:
        assert check.execute("SELECT payload FROM durable").fetchone() == ("committed",)
        assert check.execute("PRAGMA user_version").fetchone()[0] == 1
        assert check.execute("SELECT version,name FROM schema_migration").fetchall() == [(1, "first")]
        assert check.execute("SELECT 1 FROM sqlite_master WHERE name='unfinished'").fetchone() is None
    finally:
        check.close()


def test_unsupported_legacy_shape_fails_without_rebuilding(tmp_path):
    path = tmp_path / "unsupported.sqlite"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE func(unknown_field TEXT)")
    raw.execute("INSERT INTO func VALUES ('preserve')")
    raw.commit()
    raw.close()
    with pytest.raises(sqlite3.OperationalError):
        db.connect(path)
    raw = sqlite3.connect(path)
    try:
        assert raw.execute("SELECT * FROM func").fetchall() == [("preserve",)]
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        raw.close()


@pytest.mark.parametrize("module_name,entry", [
    ("export_mizuchi_db", "build"), ("export_mizuchi_db", "estimate"),
    ("export_mizuchi_db", "main"), ("package_binaries", "main"),
    ("materialize_binaries", "main"),
])
def test_inventory_consumers_request_read_only_before_work(monkeypatch, module_name, entry):
    module = importlib.import_module(f"agentdecompile_recovery.corpus.{module_name}")

    class AdmissionReached(Exception):
        pass

    # Stop at admission before knowledge-store access, artifact output or moves.
    connect = Mock(side_effect=AdmissionReached)
    monkeypatch.setattr(db, "connect", connect)
    monkeypatch.setattr(sys, "argv", [module_name, "--all"])
    if module_name == "package_binaries":
        monkeypatch.setattr(module, "OUT", SimpleNamespace(exists=lambda: False))
    elif module_name == "materialize_binaries":
        monkeypatch.setattr(module, "OUT", SimpleNamespace(is_dir=lambda: True))
    with pytest.raises(AdmissionReached):
        getattr(module, entry)("/selected") if entry == "build" else getattr(module, entry)()
    if module_name == "export_mizuchi_db":
        connect.assert_called_once_with(read_only=True)
    else:
        connect.assert_called_once_with(module.ROOT / "db" / "kotorxid.sqlite", read_only=True)


def test_schema_names_and_selected_db_routes_remain_distinct():
    # Read source rather than import dashboard/Ghidra consumers.
    package = ast.parse((CORPUS / "__init__.py").read_text())
    assert any(isinstance(n, ast.ImportFrom) and n.module == "contract" and
               any(a.name == "SCHEMA" for a in n.names) for n in package.body)
    for name in ("export_mizuchi_db", "package_binaries", "materialize_binaries", "name_precedence", "mizuchi_bridge"):
        tree = ast.parse((CORPUS / f"{name}.py").read_text())
        assert any(isinstance(n, ast.ImportFrom) and n.level == 1 and
                   any(a.name == "db" for a in n.names) for n in tree.body)
        if name in {"name_precedence", "mizuchi_bridge"}:
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and
                     isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and
                     n.func.value.id == "db" and n.func.attr == "connect"]
            assert calls and all(not c.keywords for c in calls)
    common = (CORPUS / "dashboard" / "common.py").read_text()
    tree = ast.parse(common)
    live_db = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "live_db")
    body = ast.get_source_segment(common, live_db)
    assert body.index("_RUNTIME_DB_PATH") < body.index("_saved_runtime_db_path()") < body.index('"AGENT_DECOMPILE_CORPUS_DB"')
    jobs = (CORPUS / "dashboard" / "actions" / "jobs.py").read_text()
    assert '(params or {}).get("db") or live_db()' in jobs
    assert 'filled["db"] = key' in jobs


def test_unrelated_ledger_sql_error_propagates_unchanged_and_closes(tmp_path, monkeypatch):
    path = tmp_path / "sql-error.sqlite"
    store.connect(path).close()
    real_connect = sqlite3.connect
    failure = sqlite3.OperationalError("synthetic ledger I/O failure")
    opened = []

    class BrokenLedgerConnection(sqlite3.Connection):
        close_count = 0

        def execute(self, sql, *args, **kwargs):
            if sql.startswith("SELECT version, name FROM"):
                raise failure
            return super().execute(sql, *args, **kwargs)

        def close(self):
            self.close_count += 1
            super().close()

    def connect(*args, **kwargs):
        con = real_connect(*args, factory=BrokenLedgerConnection, **kwargs)
        opened.append(con)
        return con

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(sqlite3.OperationalError) as caught:
        store.connect(path, read_only=True)
    assert caught.value is failure
    assert len(opened) == 1 and opened[0].close_count == 1


def test_malformed_sqlite_propagates_database_error_and_closes(tmp_path, monkeypatch):
    path = tmp_path / "malformed.sqlite"
    path.write_bytes(b"This is not a SQLite database" * 20)
    opened, statements, migrate, backfill = _instrument_admission(monkeypatch)
    with pytest.raises(sqlite3.DatabaseError):
        store.connect(path, read_only=True)
    assert len(opened) == 1 and opened[0].close_count == 1
    migrate.assert_not_called()
    backfill.assert_not_called()


@pytest.mark.parametrize("damage", [
    "ALTER TABLE func DROP COLUMN stabs_name",
    "ALTER TABLE func DROP COLUMN stabs_type",
    "DROP INDEX ix_func_srcfile",
    "DROP INDEX ix_stabs_type_bin",
    "DROP INDEX ix_stabs_type_src",
    "DROP TABLE stabs_type",
])
def test_read_only_current_v11_requires_stabs_postcondition(tmp_path, monkeypatch, damage):
    path = tmp_path / "incomplete-v11.sqlite"
    con = store.connect(path)
    con.execute(damage)
    con.commit()
    con.close()
    opened, statements, migrate, backfill = _instrument_admission(monkeypatch)
    with pytest.raises(store.SchemaCompatibilityError, match="STABS schema required"):
        store.connect(path, read_only=True)
    _assert_reader_only(statements, migrate, backfill)
    assert opened[0].close_count == 1


def test_actual_v9_read_only_refuses_without_upgrading(tmp_path, monkeypatch):
    path = tmp_path / "actual-v9.sqlite"
    con = sqlite3.connect(path)
    migrations.apply_pending(con, target=9)
    con.close()
    opened, statements, migrate, backfill = _instrument_admission(monkeypatch)
    with pytest.raises(store.SchemaCompatibilityError, match="observed schema version 9"):
        store.connect(path, read_only=True)
    _assert_reader_only(statements, migrate, backfill)
    assert opened[0].close_count == 1
