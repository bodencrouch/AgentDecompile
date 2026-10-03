"""Connection ownership and transient-write classification for the corpus store."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from agentdecompile_recovery.corpus import migrations, store

pytestmark = pytest.mark.unit

_HASH = "ab" * 32
_EXPECTED_FAMILY = f"unclassified:{_HASH[:16]}"


def _stale_hashed_store(path: Path) -> Path:
    con = store.connect(path)
    con.execute(
        "INSERT INTO binary(id, repo_path, slug, content_sha256, recovery_family) "
        "VALUES (1, '/r/one', 'one', ?, 'unclassified:1')",
        (_HASH,),
    )
    con.commit()
    con.close()
    return path


def _family(path: Path) -> str | None:
    con = sqlite3.connect(path)
    try:
        row = con.execute("SELECT recovery_family FROM binary WHERE id=1").fetchone()
        return None if row is None else row[0]
    finally:
        con.close()


def test_connect_rolls_back_and_closes_after_initializer_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def recording_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        con = real_connect(*args, **kwargs)
        opened.append(con)
        return con

    def interrupted(con: sqlite3.Connection) -> None:
        con.execute("BEGIN")
        con.execute("CREATE TABLE unfinished(value TEXT)")
        raise KeyboardInterrupt("synthetic initializer interruption")

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    monkeypatch.setattr(migrations, "apply_pending", interrupted)

    with pytest.raises(KeyboardInterrupt, match="initializer interruption"):
        store.connect(tmp_path / "interrupted.sqlite")

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")

    check = real_connect(tmp_path / "interrupted.sqlite")
    try:
        assert check.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='unfinished'"
        ).fetchone() is None
    finally:
        check.close()


def test_connect_closes_even_when_failure_rollback_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingRollbackConnection:
        row_factory: Any = None
        in_transaction = True
        closed = False

        def execute(self, _sql: str):
            return self

        def fetchone(self):
            return (0,)

        def rollback(self) -> None:
            raise RuntimeError("synthetic rollback failure")

        def close(self) -> None:
            self.closed = True

    con = FailingRollbackConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda *_args, **_kwargs: con)
    monkeypatch.setattr(
        migrations,
        "apply_pending",
        lambda _con: (_ for _ in ()).throw(KeyboardInterrupt("synthetic interruption")),
    )

    with pytest.raises(RuntimeError, match="rollback failure"):
        store.connect(tmp_path / "rollback-fails.sqlite")
    assert con.closed is True


def test_sqlite_error_with_busy_locked_identifier_is_not_tolerated(tmp_path: Path) -> None:
    db = _stale_hashed_store(tmp_path / "broken.sqlite")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TRIGGER broken AFTER UPDATE ON binary BEGIN "
        "INSERT INTO no_such_busy_locked_table VALUES (1); END"
    )
    con.commit()

    with pytest.raises(sqlite3.OperationalError, match="no_such_busy_locked_table") as caught:
        store.backfill_recovery_family(con)
    sqlite_error = getattr(sqlite3, "SQLITE_ERROR", 1)
    assert getattr(caught.value, "sqlite_errorcode", sqlite_error) & 0xFF == sqlite_error
    assert not con.in_transaction
    con.close()
    assert _family(db) == "unclassified:1"


def test_python310_message_fallback_matches_only_complete_transient_messages() -> None:
    assert store._is_lock_or_readonly(sqlite3.OperationalError("database is locked"))
    assert store._is_lock_or_readonly(sqlite3.OperationalError("database table is locked: binary"))
    assert store._is_lock_or_readonly(sqlite3.OperationalError("attempt to write a readonly database"))
    assert not store._is_lock_or_readonly(
        sqlite3.OperationalError("no such table: no_such_busy_locked_table")
    )


def test_actual_busy_is_tolerated_without_stealing_transaction_ownership(tmp_path: Path) -> None:
    db = _stale_hashed_store(tmp_path / "busy.sqlite")
    holder = sqlite3.connect(db)
    holder.execute("BEGIN IMMEDIATE")
    waiter = sqlite3.connect(db, timeout=0.1)
    waiter.execute("PRAGMA busy_timeout=100")
    try:
        assert store.backfill_recovery_family(waiter) == 0
        assert not waiter.in_transaction
        assert _family(db) == "unclassified:1"
    finally:
        waiter.close()
        holder.rollback()
        holder.close()


def test_read_only_connect_skips_backfill_and_handle_remains_usable(tmp_path: Path) -> None:
    db = _stale_hashed_store(tmp_path / "readonly.sqlite")
    con = store.connect(db, read_only=True)
    try:
        assert not con.in_transaction
        assert con.execute("SELECT COUNT(*) FROM binary").fetchone()[0] == 1
        assert con.execute("SELECT recovery_family FROM binary").fetchone()[0] == "unclassified:1"
    finally:
        con.close()
    assert _family(db) == "unclassified:1"


def test_backfill_joins_and_preserves_caller_transaction(tmp_path: Path) -> None:
    db = _stale_hashed_store(tmp_path / "caller.sqlite")
    con = sqlite3.connect(db)
    con.execute("BEGIN IMMEDIATE")
    try:
        assert store.backfill_recovery_family(con) == 0
        assert con.in_transaction
        assert _family(db) == "unclassified:1"
        con.rollback()
        assert _family(db) == "unclassified:1"
    finally:
        if con.in_transaction:
            con.rollback()
        con.close()
