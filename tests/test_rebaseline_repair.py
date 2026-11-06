"""Store-repair edges of ``corpus rebaseline`` (review #7 and #9).

The package basis is monkeypatched to one of two synthetic objects, so a
test can move the "current" basis back and forth without touching the
real package constants.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import rebaseline as rb
from agentdecompile_recovery.corpus import store
from agentdecompile_recovery.corpus.determinism_basis import BasisError, basis_hash_of

pytestmark = pytest.mark.unit

BASIS_A = {"synthetic": "A"}
BASIS_B = {"synthetic": "B"}
HASH_A = basis_hash_of(BASIS_A)
HASH_B = basis_hash_of(BASIS_B)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "corpus.sqlite"
    con = store.connect(path)
    con.executemany(
        "INSERT INTO binary(id, repo_path, slug, recovery_family, analyzer_version, basis_hash,"
        " content_sha256) VALUES (?,?,?,?,?,?,?)",
        [
            (1, "/s/a.bin", "build-a", "fam", "77.0", HASH_A, "a" * 64),
            (2, "/s/b.bin", "build-b", "fam", "77.0", HASH_A, "b" * 64),
        ],
    )
    con.commit()
    con.close()
    return path


def _current(monkeypatch: pytest.MonkeyPatch, obj: dict) -> None:
    monkeypatch.setattr(rb, "package_basis", lambda _version: dict(obj))


def _hashes(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT basis_hash FROM binary")}
    finally:
        con.close()


def _ledger(path: Path) -> list[tuple]:
    con = sqlite3.connect(path)
    try:
        return con.execute(
            "SELECT old_basis_hash, new_basis_hash FROM basis_supersession ORDER BY id"
        ).fetchall()
    finally:
        con.close()


def _run(path: Path, receipts: Path, **kw) -> dict:
    con = store.connect(path)
    try:
        return rb.rebaseline(con, receipts_dir=receipts, **kw)
    finally:
        con.close()


# --- #7: A -> B -> A -> B ----------------------------------------------------


def test_oscillating_basis_does_not_wedge_the_store(db: Path, tmp_path: Path, monkeypatch) -> None:
    receipts = tmp_path / "receipts"
    sequence = [(BASIS_B, HASH_A, HASH_B), (BASIS_A, HASH_B, HASH_A), (BASIS_B, HASH_A, HASH_B), (BASIS_A, HASH_B, HASH_A)]
    for obj, old, new in sequence:
        _current(monkeypatch, obj)
        out = _run(db, receipts, reason=f"to {new[:8]}")
        assert out["status"] == "superseded", out
        assert (out["old_basis_hash"], out["new_basis_hash"]) == (old, new)
        assert _hashes(db) == {new}
        receipt = receipts / rb.RECEIPT_DIRNAME / f"{new[:16]}.json"
        assert hashlib.sha256(receipt.read_bytes()).hexdigest() == out["run"]["receipt_sha256"]
        assert _run(db, receipts)["status"] == "unchanged"

    # The ledger's latest row per pair is the latest supersession, so the
    # chain still reads in order: the newest row out of each hash is last.
    assert _run(db, receipts)["receipt"]["status"] == "present"
    ledger = _ledger(db)
    assert ledger[-1] == (HASH_B, HASH_A)
    assert ledger[-2] == (HASH_A, HASH_B)


def test_repeated_pair_without_a_later_supersession_still_refuses(db: Path, tmp_path: Path, monkeypatch) -> None:
    receipts = tmp_path / "receipts"
    _current(monkeypatch, BASIS_B)
    assert _run(db, receipts)["status"] == "superseded"
    # Something outside the verb put the old hash back. The ledger shows no
    # supersession out of B, so this is not an oscillation.
    con = sqlite3.connect(db)
    con.execute("UPDATE binary SET basis_hash=?", (HASH_A,))
    con.commit()
    con.close()
    with pytest.raises(BasisError, match="already recorded"):
        _run(db, receipts)
    assert _hashes(db) == {HASH_A}
    assert _ledger(db) == [(HASH_A, HASH_B)]


# --- #9: the receipt is durable before COMMIT ---------------------------------


def test_unusable_receipts_dir_leaves_rows_unstamped(db: Path, tmp_path: Path, monkeypatch) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    # A file where the verb's receipt directory must go.
    (receipts / rb.RECEIPT_DIRNAME).write_text("in the way\n", encoding="utf-8")
    _current(monkeypatch, BASIS_B)
    with pytest.raises(BasisError, match="receipt"):
        _run(db, receipts)
    assert _hashes(db) == {HASH_A}
    assert _ledger(db) == []


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory modes")
def test_read_only_receipts_dir_leaves_rows_unstamped(db: Path, tmp_path: Path, monkeypatch) -> None:
    receipts = tmp_path / "receipts"
    (receipts / rb.RECEIPT_DIRNAME).mkdir(parents=True)
    (receipts / rb.RECEIPT_DIRNAME).chmod(0o500)
    _current(monkeypatch, BASIS_B)
    try:
        with pytest.raises(BasisError, match="receipt"):
            _run(db, receipts)
    finally:
        (receipts / rb.RECEIPT_DIRNAME).chmod(0o700)
    assert _hashes(db) == {HASH_A}
    assert _ledger(db) == []
    assert list((receipts / rb.RECEIPT_DIRNAME).iterdir()) == []


def test_failed_receipt_flush_rolls_the_restamp_back(db: Path, tmp_path: Path, monkeypatch) -> None:
    receipts = tmp_path / "receipts"
    _current(monkeypatch, BASIS_B)

    def boom(_fd):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(rb.os, "fsync", boom)
    with pytest.raises(BasisError, match="receipt"):
        _run(db, receipts)
    monkeypatch.undo()
    assert _hashes(db) == {HASH_A}
    assert _ledger(db) == []
    assert not (receipts / rb.RECEIPT_DIRNAME / f"{HASH_B[:16]}.json").exists()
    leftovers = [p.name for p in (receipts / rb.RECEIPT_DIRNAME).iterdir()] if (receipts / rb.RECEIPT_DIRNAME).is_dir() else []
    assert leftovers == []


def test_rerun_reports_a_missing_receipt(db: Path, tmp_path: Path, monkeypatch) -> None:
    receipts = tmp_path / "receipts"
    _current(monkeypatch, BASIS_B)
    first = _run(db, receipts)
    path = Path(first["run"]["receipt_path"])
    path.unlink()
    again = _run(db, receipts)
    assert again["status"] == "unchanged"
    assert again["receipt"] == {
        "status": "missing",
        "path": str(path),
        "receipt_sha256": first["run"]["receipt_sha256"],
        "old_basis_hash": HASH_A,
        "new_basis_hash": HASH_B,
    }


def test_rerun_reports_a_receipt_that_does_not_match_the_ledger(db: Path, tmp_path: Path, monkeypatch) -> None:
    receipts = tmp_path / "receipts"
    _current(monkeypatch, BASIS_B)
    first = _run(db, receipts)
    path = Path(first["run"]["receipt_path"])
    path.write_text(json.dumps({"edited": True}), encoding="utf-8")
    again = _run(db, receipts)
    assert again["status"] == "unchanged"
    assert again["receipt"]["status"] == "mismatch"


def test_store_never_rebaselined_reports_no_receipt(db: Path, tmp_path: Path, monkeypatch) -> None:
    _current(monkeypatch, BASIS_A)
    out = _run(db, tmp_path / "receipts")
    assert out["status"] == "unchanged"
    assert out["receipt"] is None
