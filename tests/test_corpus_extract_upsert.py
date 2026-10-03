"""``extract.upsert_binary`` never clears a stored build identity.

``binary.content_sha256`` is the cascade tie-break key (D8) and the input to
the ``recovery_family`` hash form (D9). The backfill pass writes it from the
raw image; ``upsert_binary`` only stores a digest a caller hands it and must
never overwrite a stored one with NULL, nor silently replace it.

Fixtures are synthetic: repo paths under ``tmp_path``, digests are repeated
hex bytes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import store
from agentdecompile_recovery.corpus.extract import upsert_binary

pytestmark = pytest.mark.unit

ANALYZER = "11.4.1"
LANG = "x86:LE:32:default"
DIGEST_A = "aa" * 32
DIGEST_B = "bb" * 32


def _binary(con: sqlite3.Connection, repo_path: str) -> dict:
    cur = con.execute("SELECT * FROM binary WHERE repo_path=?", (repo_path,))
    names = [d[0] for d in cur.description]
    row = cur.fetchone()
    assert row is not None, repo_path
    return dict(zip(names, tuple(row)))


def _stamp(con: sqlite3.Connection, repo_path: str) -> tuple:
    row = _binary(con, repo_path)
    return (row["analyzer_version"], row["processor_spec_hash"], row["basis_hash"], row["basis_source"])


@pytest.fixture
def con(tmp_path: Path, monkeypatch) -> sqlite3.Connection:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    handle = store.connect(tmp_path / "c.sqlite")
    yield handle
    handle.close()


# --- (a) a backfilled digest survives a digest-less upsert ------------------


def test_backfilled_digest_survives_an_upsert_without_one(con) -> None:
    bid = upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG, "analyzer_version": ANALYZER})
    # The backfill pass is the digest writer (a plain UPDATE, not the upsert).
    con.execute("UPDATE binary SET content_sha256=? WHERE id=?", (DIGEST_A, bid))
    con.commit()
    assert upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG, "analyzer_version": ANALYZER}) == bid
    assert _binary(con, "/x")["content_sha256"] == DIGEST_A


def test_an_empty_digest_does_not_clear_a_stored_one(con) -> None:
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": DIGEST_A, "language_id": LANG})
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": "", "language_id": LANG})
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": "  ", "language_id": LANG})
    assert _binary(con, "/x")["content_sha256"] == DIGEST_A


# --- (b) a different digest refuses unless reidentification is explicit -----


def test_a_different_digest_refuses_and_names_both(con) -> None:
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": DIGEST_A, "language_id": LANG})
    with pytest.raises(ValueError) as info:
        upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": DIGEST_B, "language_id": LANG})
    text = str(info.value)
    assert "x" in text and DIGEST_A[:12] in text and DIGEST_B[:12] in text
    assert "allow_reidentify" in text
    assert _binary(con, "/x")["content_sha256"] == DIGEST_A


def test_a_different_digest_is_accepted_with_allow_reidentify(con) -> None:
    bid = upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": DIGEST_A, "language_id": LANG})
    assert (
        upsert_binary(
            con, repo_path="/x", slug="x", meta={"content_sha256": DIGEST_B, "language_id": LANG}, allow_reidentify=True
        )
        == bid
    )
    assert _binary(con, "/x")["content_sha256"] == DIGEST_B


def test_the_same_digest_in_another_case_is_not_a_change(con) -> None:
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": DIGEST_A, "language_id": LANG})
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": " " + DIGEST_A.upper() + " ", "language_id": LANG})
    assert _binary(con, "/x")["content_sha256"] == DIGEST_A


# --- (c) fewer facts never erase measured facts -----------------------------


def test_an_upsert_with_fewer_facts_keeps_measured_facts(con) -> None:
    full = {
        "content_sha256": DIGEST_A,
        "language_id": LANG,
        "arch": "x86",
        "bits": 32,
        "format": "Portable Executable (PE)",
        "md5": "cd" * 16,
        "image_base": 0x400000,
        "analyzer_version": ANALYZER,
    }
    bid = upsert_binary(con, repo_path="/x", slug="x", meta=full)
    assert upsert_binary(con, repo_path="/x", slug="x", meta={"analyzer_version": ANALYZER}) == bid
    row = _binary(con, "/x")
    assert row["image_base"] == 0x400000
    assert row["arch"] == "x86"
    assert row["bits"] == 32
    assert row["format"] == "Portable Executable (PE)"
    assert row["md5"] == "cd" * 16
    assert row["language_id"] == LANG
    assert row["content_sha256"] == DIGEST_A


def test_a_fuller_upsert_still_updates_measured_facts(con) -> None:
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG, "image_base": 0x400000, "bits": 32})
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG, "image_base": 0x10000000, "bits": 64})
    row = _binary(con, "/x")
    assert row["image_base"] == 0x10000000
    assert row["bits"] == 64


# --- (d) recovery_family: NULL at insert, hash form once a digest exists ----


def test_new_build_family_is_null_without_a_digest_and_hash_form_with_one(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    db = tmp_path / "c.sqlite"
    con = store.connect(db)
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG})
    upsert_binary(con, repo_path="/y", slug="y", meta={"language_id": LANG, "content_sha256": DIGEST_B})
    con.close()
    # The store's per-connect backfill derives the family from the digest.
    con = store.connect(db)
    try:
        assert _binary(con, "/x")["recovery_family"] is None
        assert _binary(con, "/y")["recovery_family"] == "unclassified:" + DIGEST_B[:16]
    finally:
        con.close()


def test_family_backfills_from_a_digest_a_later_pass_supplies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    db = tmp_path / "c.sqlite"
    con = store.connect(db)
    bid = upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG})
    con.execute("UPDATE binary SET content_sha256=? WHERE id=?", (DIGEST_A, bid))
    con.commit()
    con.close()
    con = store.connect(db)
    try:
        assert _binary(con, "/x")["recovery_family"] == "unclassified:" + DIGEST_A[:16]
    finally:
        con.close()


def test_a_derived_family_survives_a_prepare_round_trip(con) -> None:
    """The dashboard reads the stored family back into meta; the store's hash
    form must not be rewritten to a slug placeholder on the way through."""
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG, "content_sha256": DIGEST_A})
    store.backfill_recovery_family(con)
    con.commit()
    derived = _binary(con, "/x")["recovery_family"]
    assert derived == "unclassified:" + DIGEST_A[:16]
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG, "recovery_family": derived})
    assert _binary(con, "/x")["recovery_family"] == derived
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG})
    assert _binary(con, "/x")["recovery_family"] == derived


def test_an_operator_family_is_kept_and_can_be_set(con) -> None:
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG, "recovery_family": "fam"})
    assert _binary(con, "/x")["recovery_family"] == "fam"
    upsert_binary(con, repo_path="/x", slug="x", meta={"language_id": LANG})
    assert _binary(con, "/x")["recovery_family"] == "fam"


# --- (e) upsert_binary never derives a digest from the repo path ------------


def test_upsert_never_writes_a_digest_it_did_not_receive(con, tmp_path: Path) -> None:
    image = tmp_path / "image.bin"
    image.write_bytes(b"\x7fELF" + bytes(range(256)) * 4)
    upsert_binary(con, repo_path=str(image), slug="image", meta={"language_id": LANG})
    assert _binary(con, str(image))["content_sha256"] is None


# --- (f) a refused upsert changes nothing, including the analyzer stamp -----


def test_a_refused_upsert_leaves_the_row_and_its_stamp_unchanged(con) -> None:
    meta = {"content_sha256": DIGEST_A, "language_id": LANG, "analyzer_version": ANALYZER, "image_base": 0x400000}
    upsert_binary(con, repo_path="/x", slug="x", meta=meta)
    # Settle the store's own per-connect family backfill first so the only
    # writer left in the refused call would be upsert_binary itself.
    store.backfill_recovery_family(con)
    con.commit()
    before = _binary(con, "/x")
    assert before["analyzer_version"] == ANALYZER and before["basis_source"] == "ingest"
    with pytest.raises(ValueError):
        upsert_binary(
            con,
            repo_path="/x",
            slug="x",
            meta={"content_sha256": DIGEST_B, "language_id": LANG, "analyzer_version": "11.4.2", "image_base": 0x500000},
        )
    assert _binary(con, "/x") == before
    assert con.in_transaction is False
