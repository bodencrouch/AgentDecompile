"""store.connect() must return with no transaction open.

The recovery_family backfill used to run an UPDATE inside connect() and never
commit it, so every verb that only read held SQLite's write lock for its whole
run, and the backfill (plus any ALTER that ran after it) was discarded at close.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import time
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import store
from agentdecompile_recovery.corpus.cli import main as corpus_main

pytestmark = pytest.mark.unit

_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "REPLACE", "ALTER", "DROP")


def _unclassified_store(path: Path) -> Path:
    """A store holding two binaries whose recovery_family predates the catalog."""
    con = store.connect(path)
    con.execute("INSERT INTO binary (slug, repo_path) VALUES ('a', 'repoA')")
    con.execute("INSERT INTO binary (slug, repo_path) VALUES ('b', 'repoB')")
    con.commit()
    con.execute("UPDATE binary SET recovery_family=NULL")
    con.commit()
    con.close()
    return path


def _families(path: Path) -> list[str | None]:
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute("SELECT recovery_family FROM binary ORDER BY id")]
    finally:
        con.close()


def test_connect_commits_backfill_and_leaves_no_transaction(tmp_path: Path) -> None:
    db = _unclassified_store(tmp_path / "store.sqlite")

    con = store.connect(db)
    try:
        assert con.in_transaction is False
        # Visible from an independent connection while the first is still open.
        assert _families(db) == ["unclassified:1", "unclassified:2"]
    finally:
        con.close()


def test_open_connection_does_not_hold_the_write_lock(tmp_path: Path) -> None:
    db = _unclassified_store(tmp_path / "store.sqlite")

    holder = store.connect(db)
    other = sqlite3.connect(db, timeout=0.2)
    try:
        started = time.monotonic()
        other.execute("BEGIN IMMEDIATE")
        other.execute("INSERT INTO eval (run, metric, value) VALUES ('r', 'm', 1.0)")
        other.commit()
        assert time.monotonic() - started < 0.2
    finally:
        other.close()
        holder.close()


def test_connect_persists_alters_that_run_after_the_backfill(tmp_path: Path) -> None:
    """ensure_match_columns runs after the backfill; its ALTERs must persist too."""
    db = _unclassified_store(tmp_path / "store.sqlite")
    legacy = sqlite3.connect(db)
    legacy.executescript(
        """
        DROP TABLE match;
        CREATE TABLE match (
            id INTEGER PRIMARY KEY, run TEXT,
            src_binary INTEGER, src_addr INTEGER,
            dst_binary INTEGER, dst_addr INTEGER,
            score REAL, margin REAL, evidence TEXT, status TEXT
        );
        """
    )
    legacy.close()

    store.connect(db).close()

    check = sqlite3.connect(db)
    try:
        cols = {r[1] for r in check.execute("PRAGMA table_info(match)")}
    finally:
        check.close()
    assert {"relation", "src_end", "dst_end"} <= cols
    assert _families(db) == ["unclassified:1", "unclassified:2"]


def test_two_read_verbs_in_one_process_both_succeed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression guard: sequential verbs through the CLI in one interpreter."""
    db = _unclassified_store(tmp_path / "store.sqlite")

    assert corpus_main(["evaluate-pair", "--db", str(db), "--src", "repoA", "--dst", "repoB"]) == 0
    assert corpus_main(["export-run-report", "--db", str(db), "--out", str(tmp_path / "report.json")]) == 0
    capsys.readouterr()

    probe = sqlite3.connect(db, timeout=0.2)
    try:
        probe.execute("BEGIN IMMEDIATE")
        probe.rollback()
    finally:
        probe.close()
    assert _families(db) == ["unclassified:1", "unclassified:2"]


def _readonly(path: Path) -> None:
    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file modes")
def test_readonly_maintained_store_opens(tmp_path: Path) -> None:
    """Regression guard: a fully maintained store needs no writes to open."""
    db = tmp_path / "store.sqlite"
    con = store.connect(db)
    con.execute("INSERT INTO binary (slug, repo_path, recovery_family) VALUES ('a', 'repoA', 'fam')")
    con.commit()
    con.close()
    _readonly(db)
    try:
        con = store.connect(db)
        try:
            assert con.in_transaction is False
            assert con.execute("SELECT count(*) FROM binary").fetchone()[0] == 1
        finally:
            con.close()
    finally:
        db.chmod(0o644)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file modes")
def test_readonly_unclassified_store_opens_without_open_transaction(tmp_path: Path) -> None:
    """The backfill cannot write; its failed UPDATE must not leave a transaction open."""
    db = _unclassified_store(tmp_path / "store.sqlite")
    _readonly(db)
    try:
        con = store.connect(db)
        try:
            assert con.in_transaction is False
            assert con.execute("SELECT count(*) FROM binary").fetchone()[0] == 2
        finally:
            con.close()
    finally:
        db.chmod(0o644)


def test_second_connect_issues_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _unclassified_store(tmp_path / "store.sqlite")
    statements: list[str] = []
    real_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        con.set_trace_callback(statements.append)
        return con

    monkeypatch.setattr(sqlite3, "connect", traced_connect)

    store.connect(db).close()
    assert any(s.lstrip().upper().startswith("UPDATE") for s in statements)

    statements.clear()
    con = store.connect(db)
    try:
        writes = [s for s in statements if s.lstrip().upper().startswith(_WRITE_VERBS)]
        assert writes == []
        assert con.total_changes == 0
        assert con.in_transaction is False
    finally:
        con.close()
