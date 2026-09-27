"""Schema helpers never commit a caller's work; read verbs never block on or
crash against a store they cannot write.

One test per fixed finding.  store.connect() commits only the maintenance it
opened itself; helpers that may run on a caller's connection join the caller's
transaction and leave COMMIT/ROLLBACK to it.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import time
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import stabs_link, store

pytestmark = pytest.mark.unit

_not_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file modes"
)


def _store(path: Path, family: str | None = "fam") -> Path:
    con = store.connect(path)
    con.execute("INSERT INTO binary (slug, repo_path, recovery_family) VALUES ('a', 'repoA', 'x')")
    con.commit()
    con.execute("UPDATE binary SET recovery_family=?", (family,))
    con.commit()
    con.close()
    return path


def _families(path: Path) -> list[str | None]:
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute("SELECT recovery_family FROM binary ORDER BY id")]
    finally:
        con.close()


def test_stabs_ensure_columns_never_commits_caller_work(tmp_path: Path) -> None:
    db = _store(tmp_path / "store.sqlite")
    con = sqlite3.connect(db)
    try:
        con.execute("INSERT INTO eval (run, metric, value) VALUES ('caller', 'm', 1.0)")
        stabs_link.ensure_columns(con)
        assert con.in_transaction is True
        con.rollback()
        assert con.execute("SELECT count(*) FROM eval").fetchone()[0] == 0
    finally:
        con.close()

    # With nothing pending the DDL autocommits: dashboard.workflow.merge_evidence
    # runs ensure_columns and then BEGIN IMMEDIATE on the same connection.
    con = store.connect(db)
    try:
        stabs_link.ensure_columns(con)
        assert con.in_transaction is False
        con.execute("BEGIN IMMEDIATE")
        con.rollback()
    finally:
        con.close()
    check = sqlite3.connect(db)
    try:
        cols = {r[1] for r in check.execute("PRAGMA table_info(func)")}
    finally:
        check.close()
    assert {"source_file", "object_file", "stabs_name", "stabs_type"} <= cols


@_not_root
def test_readonly_old_schema_store_opens_for_reads(tmp_path: Path) -> None:
    db = _store(tmp_path / "store.sqlite")
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
    ro = tmp_path / "ro.sqlite"
    shutil.copy(db, ro)
    ro.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        con = store.connect(ro)
        try:
            assert con.in_transaction is False
            assert con.execute("SELECT count(*) FROM binary").fetchone()[0] == 1
            assert con.execute("SELECT count(*) FROM match").fetchone()[0] == 0
        finally:
            con.close()
    finally:
        ro.chmod(0o644)


def test_pending_backfill_does_not_stall_connect_behind_a_writer(tmp_path: Path) -> None:
    db = _store(tmp_path / "store.sqlite", family=None)
    holder = sqlite3.connect(db, timeout=0)
    holder.execute("BEGIN IMMEDIATE")
    try:
        started = time.monotonic()
        con = store.connect(db)
        elapsed = time.monotonic() - started
        try:
            assert elapsed < 5, f"connect() waited {elapsed:.1f}s for a best-effort backfill"
            assert con.in_transaction is False
            assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
            assert con.execute("SELECT count(*) FROM binary").fetchone()[0] == 1
        finally:
            con.close()
    finally:
        holder.rollback()
        holder.close()
    assert _families(db) == [None]

    store.connect(db).close()
    assert _families(db) == ["unclassified:1"]
