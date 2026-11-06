"""The backfill frame and its one shipped pass, ``content_sha256``.

Fixture: a store with two synthetic binaries. One has a raw image on disk
(resolved through the same configured path ``raw_image_path`` uses); the
other has none.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import backfill, store
from agentdecompile_recovery.corpus.cli import main as corpus_main

pytestmark = pytest.mark.unit

WITH_IMAGE = "/synthetic/build-a/image.bin"
WITHOUT_IMAGE = "/synthetic/build-b/image.bin"
IMAGE_BYTES = bytes(range(256)) * 4


def _raw_slug(repo_path: str) -> str:
    # Mirrors ghidra_bulk.raw_image_path: leading slash dropped, '/' -> '__'.
    return repo_path.strip("/").replace("/", "__")


@pytest.fixture
def fixture_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / _raw_slug(WITH_IMAGE)).write_bytes(IMAGE_BYTES)
    monkeypatch.setenv("AGENT_DECOMPILE_EXTRACT_RAW", str(raw_dir))
    from agentdecompile_recovery.corpus import ghidra_bulk

    monkeypatch.setattr(ghidra_bulk, "EXTRACT_RAW", None)
    assert ghidra_bulk.raw_image_path(WITH_IMAGE) == raw_dir / _raw_slug(WITH_IMAGE)

    db = tmp_path / "corpus.sqlite"
    con = store.connect(db)
    con.executemany(
        "INSERT INTO binary(id, repo_path, slug, recovery_family) VALUES (?,?,?,?)",
        [(1, WITH_IMAGE, "build-a", "fam"), (2, WITHOUT_IMAGE, "build-b", "fam")],
    )
    con.commit()
    con.close()
    return db


def _content_sha(db: Path) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT id, content_sha256 FROM binary ORDER BY id").fetchall()
    finally:
        con.close()


def _receipts(receipts: Path) -> dict[str, bytes]:
    return {str(p.relative_to(receipts)): p.read_bytes() for p in sorted(receipts.rglob("*.json"))}


def test_registry_ships_content_sha256() -> None:
    assert "content_sha256" in backfill.PASSES
    step = backfill.PASSES["content_sha256"]
    assert step.name == "content_sha256"
    assert step.needs_raw_image is True


def test_unknown_pass_is_rejected(fixture_db: Path, tmp_path: Path) -> None:
    con = store.connect(fixture_db)
    with pytest.raises(ValueError, match="unknown backfill pass: nope"):
        backfill.run(con, ["nope"], receipts_dir=tmp_path / "r")
    con.close()


def test_content_sha256_pass_runs_then_resumes(fixture_db: Path, tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    digest = hashlib.sha256(IMAGE_BYTES).hexdigest()
    assert _content_sha(fixture_db) == [(1, None), (2, None)]

    con = store.connect(fixture_db)
    first = backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    con.close()
    report = first["passes"]["content_sha256"]
    assert report["counts"] == {"updated": 1, "unchanged": 0, "skipped": 1, "resumed": 0}
    assert report["binaries"] == [
        {"id": 1, "slug": "build-a", "status": "updated"},
        {"id": 2, "slug": "build-b", "status": "skipped", "reason": "no_raw_image"},
    ]
    assert _content_sha(fixture_db) == [(1, digest), (2, None)]

    after_first = _receipts(receipts)
    assert sorted(after_first) == [
        f"content_sha256/{digest}.json",
        "content_sha256/slug-build-b.json",
    ]
    with_image = json.loads(after_first[f"content_sha256/{digest}.json"])
    assert with_image["key"] == {"pass": "content_sha256", "identity": digest}
    assert with_image["status"] == "updated"
    assert with_image["result"] == {"content_sha256": digest}
    assert with_image["binary"]["id"] == 1
    no_image = json.loads(after_first["content_sha256/slug-build-b.json"])
    assert no_image["key"] == {"pass": "content_sha256", "identity": "build-b"}
    assert no_image["status"] == "skipped"
    assert no_image["result"] == {"reason": "no_raw_image"}
    assert no_image["raw_image"] is None
    for body in after_first.values():
        text = body.decode("utf-8")
        assert "applied_at" not in text and "timestamp" not in text
        assert body == (json.dumps(json.loads(text), sort_keys=True, indent=2) + "\n").encode()

    con = store.connect(fixture_db)
    second = backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    con.close()
    # The skipped pair is retried (its input may have appeared); the
    # rewrite is byte-identical because the inputs did not change.
    assert second["passes"]["content_sha256"]["counts"] == {
        "updated": 0, "unchanged": 0, "skipped": 1, "resumed": 1,
    }
    assert [e["status"] for e in second["passes"]["content_sha256"]["binaries"]] == ["resumed", "skipped"]
    assert _receipts(receipts) == after_first
    assert _content_sha(fixture_db) == [(1, digest), (2, None)]


def test_no_resume_rewrites_completed_receipt_status(fixture_db: Path, tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    con = store.connect(fixture_db)
    backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    before = _receipts(receipts)
    third = backfill.run(con, ["content_sha256"], receipts_dir=receipts, resume=False)
    con.close()
    assert third["passes"]["content_sha256"]["counts"] == {
        "updated": 0, "unchanged": 1, "skipped": 1, "resumed": 0,
    }
    after = _receipts(receipts)
    assert after != before
    digest = hashlib.sha256(IMAGE_BYTES).hexdigest()
    assert json.loads(after[f"content_sha256/{digest}.json"])["status"] == "unchanged"
    assert after["content_sha256/slug-build-b.json"] == before["content_sha256/slug-build-b.json"]


def test_changed_image_gets_a_new_receipt_and_a_new_digest(fixture_db: Path, tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    con = store.connect(fixture_db)
    backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    raw_dir = Path(os.environ["AGENT_DECOMPILE_EXTRACT_RAW"])
    replaced = IMAGE_BYTES[::-1]
    (raw_dir / _raw_slug(WITH_IMAGE)).write_bytes(replaced)
    again = backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    con.close()
    assert again["passes"]["content_sha256"]["counts"] == {
        "updated": 1, "unchanged": 0, "skipped": 1, "resumed": 0,
    }
    new_digest = hashlib.sha256(replaced).hexdigest()
    assert _content_sha(fixture_db)[0] == (1, new_digest)
    assert (receipts / "content_sha256" / f"{new_digest}.json").is_file()


def test_cli_backfill_verb_prints_sorted_json(fixture_db: Path, tmp_path: Path, capsys) -> None:
    receipts = tmp_path / "receipts"
    rc = corpus_main([
        "backfill", "--db", str(fixture_db), "--pass", "content_sha256", "--receipts", str(receipts),
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert out == json.dumps(parsed, sort_keys=True)
    assert parsed["passes"]["content_sha256"]["counts"]["updated"] == 1
    assert parsed["passes"]["content_sha256"]["counts"]["skipped"] == 1

    rc = corpus_main([
        "backfill", "--db", str(fixture_db), "--pass", "content_sha256", "--receipts", str(receipts),
    ])
    assert rc == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["passes"]["content_sha256"]["counts"] == {
        "updated": 0, "unchanged": 0, "skipped": 1, "resumed": 1,
    }

    rc = corpus_main([
        "backfill", "--db", str(fixture_db), "--pass", "content_sha256", "--receipts", str(receipts),
        "--no-resume",
    ])
    assert rc == 0
    fresh = json.loads(capsys.readouterr().out)
    assert fresh["passes"]["content_sha256"]["counts"] == {
        "updated": 0, "unchanged": 1, "skipped": 1, "resumed": 0,
    }


def test_cli_backfill_rejects_unknown_pass(fixture_db: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="unknown backfill pass"):
        corpus_main([
            "backfill", "--db", str(fixture_db), "--pass", "nope", "--receipts", str(tmp_path / "r"),
        ])


# --- analyzer_identity pass -------------------------------------------------


def _identity(db: Path) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute(
            "SELECT id, analyzer_version, processor_spec_hash, basis_hash, basis_source FROM binary ORDER BY id"
        ).fetchall()
    finally:
        con.close()


@pytest.fixture
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "install"
    (root / "Ghidra").mkdir(parents=True)
    (root / "Ghidra" / "application.properties").write_text("application.version=77.0\n", encoding="utf-8")
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(root))
    return root


def test_registry_ships_analyzer_identity() -> None:
    step = backfill.PASSES["analyzer_identity"]
    assert step.name == "analyzer_identity"
    assert step.needs_raw_image is False


def test_analyzer_identity_fills_only_null_rows_and_resumes(fixture_db: Path, tmp_path: Path, install: Path) -> None:
    from agentdecompile_recovery.corpus.determinism_basis import basis_hash_for, processor_spec_hash_for
    from agentdecompile_recovery.corpus.extract import stamp_analyzer_identity

    receipts = tmp_path / "receipts"
    con = store.connect(fixture_db)
    con.execute("UPDATE binary SET language_id='x86:LE:32:default' WHERE id=1")
    con.execute("UPDATE binary SET language_id='arm:LE:32:v7' WHERE id=2")
    # Row 1 was stamped at ingest under an older analyzer; the pass must keep it.
    stamp_analyzer_identity(con, analyzer_version="70.1", binary_ids=[1])
    con.commit()
    summary = backfill.run(con, ["analyzer_identity"], receipts_dir=receipts)
    con.close()
    report = summary["passes"]["analyzer_identity"]
    assert report["counts"] == {"updated": 1, "unchanged": 1, "skipped": 0, "resumed": 0}
    assert _identity(fixture_db) == [
        (1, "70.1", processor_spec_hash_for("x86:LE:32:default"), basis_hash_for("70.1"), "ingest"),
        (2, "77.0", processor_spec_hash_for("arm:LE:32:v7"), basis_hash_for("77.0"), "backfill"),
    ]
    body = json.loads((receipts / "analyzer_identity" / "slug-build-b.json").read_text(encoding="utf-8"))
    assert body["result"] == {
        "analyzer_version": "77.0",
        "processor_spec_hash": processor_spec_hash_for("arm:LE:32:v7"),
        "basis_hash": basis_hash_for("77.0"),
        "basis_source": "backfill",
    }
    assert body["raw_image"] is None or body["raw_image"].endswith(_raw_slug(WITHOUT_IMAGE))

    con = store.connect(fixture_db)
    again = backfill.run(con, ["analyzer_identity"], receipts_dir=receipts)
    assert again["passes"]["analyzer_identity"]["counts"] == {
        "updated": 0, "unchanged": 0, "skipped": 0, "resumed": 2,
    }
    fresh = backfill.run(con, ["analyzer_identity"], receipts_dir=receipts, resume=False)
    con.close()
    assert fresh["passes"]["analyzer_identity"]["counts"] == {
        "updated": 0, "unchanged": 2, "skipped": 0, "resumed": 0,
    }


def test_analyzer_identity_fills_a_partially_null_row(fixture_db: Path, tmp_path: Path, install: Path) -> None:
    from agentdecompile_recovery.corpus.determinism_basis import basis_hash_for, processor_spec_hash_for

    con = store.connect(fixture_db)
    con.execute("UPDATE binary SET language_id='x86:LE:32:default', analyzer_version='70.1' WHERE id=1")
    con.execute("UPDATE binary SET language_id='x86:LE:32:default' WHERE id=2")
    con.commit()
    backfill.run(con, ["analyzer_identity"], receipts_dir=tmp_path / "r")
    con.close()
    rows = _identity(fixture_db)
    # The recorded version wins; only the NULL columns were derived from it.
    assert rows[0] == (1, "70.1", processor_spec_hash_for("x86:LE:32:default"), basis_hash_for("70.1"), "backfill")
    assert rows[1] == (2, "77.0", processor_spec_hash_for("x86:LE:32:default"), basis_hash_for("77.0"), "backfill")


def test_analyzer_identity_skips_without_an_install_or_language(
    fixture_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    con = store.connect(fixture_db)
    con.execute("UPDATE binary SET language_id='x86:LE:32:default'")
    con.commit()
    summary = backfill.run(con, ["analyzer_identity"], receipts_dir=tmp_path / "r")
    report = summary["passes"]["analyzer_identity"]
    assert report["counts"] == {"updated": 0, "unchanged": 0, "skipped": 2, "resumed": 0}
    assert {e["reason"] for e in report["binaries"]} == {"no_install"}
    assert _identity(fixture_db) == [(1, None, None, None, None), (2, None, None, None, None)]

    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(tmp_path / "missing"))
    con.execute("UPDATE binary SET language_id=NULL WHERE id=2")
    con.commit()
    (tmp_path / "missing" / "Ghidra").mkdir(parents=True)
    (tmp_path / "missing" / "Ghidra" / "application.properties").write_text("application.version=77.0\n")
    summary = backfill.run(con, ["analyzer_identity"], receipts_dir=tmp_path / "r", resume=False)
    con.close()
    report = summary["passes"]["analyzer_identity"]
    assert report["counts"] == {"updated": 1, "unchanged": 0, "skipped": 1, "resumed": 0}
    assert report["binaries"][1] == {"id": 2, "slug": "build-b", "status": "skipped", "reason": "no_language_id"}
    assert "unknown" not in json.dumps(_identity(fixture_db))


def test_cli_backfill_analyzer_identity(fixture_db: Path, tmp_path: Path, install: Path) -> None:
    con = store.connect(fixture_db)
    con.execute("UPDATE binary SET language_id='x86:LE:32:default'")
    con.commit()
    con.close()
    rc = corpus_main([
        "backfill", "--db", str(fixture_db), "--pass", "analyzer_identity", "--receipts", str(tmp_path / "r"),
    ])
    assert rc == 0
    from agentdecompile_recovery.corpus.determinism_basis import basis_hash_for

    assert {r[3] for r in _identity(fixture_db)} == {basis_hash_for("77.0")}


# --- resume honours the receipt's status (review #5/#8) ----------------------


def test_skipped_receipt_is_not_resumed_once_the_install_appears(
    fixture_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts = tmp_path / "r"
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    con = store.connect(fixture_db)
    con.execute("UPDATE binary SET language_id='x86:LE:32:default'")
    con.commit()
    first = backfill.run(con, ["analyzer_identity"], receipts_dir=receipts)
    assert first["passes"]["analyzer_identity"]["counts"]["skipped"] == 2
    body = json.loads((receipts / "analyzer_identity" / "slug-build-b.json").read_text(encoding="utf-8"))
    assert body["status"] == "skipped"
    assert body["result"] == {"reason": "no_install"}

    root = tmp_path / "install"
    (root / "Ghidra").mkdir(parents=True)
    (root / "Ghidra" / "application.properties").write_text("application.version=77.0\n", encoding="utf-8")
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(root))
    # Default resume=True: a skipped receipt must not stand in for the work.
    second = backfill.run(con, ["analyzer_identity"], receipts_dir=receipts)
    assert second["passes"]["analyzer_identity"]["counts"] == {
        "updated": 2, "unchanged": 0, "skipped": 0, "resumed": 0,
    }
    from agentdecompile_recovery.corpus.determinism_basis import basis_hash_for

    assert {r[3] for r in _identity(fixture_db)} == {basis_hash_for("77.0")}
    third = backfill.run(con, ["analyzer_identity"], receipts_dir=receipts)
    con.close()
    assert third["passes"]["analyzer_identity"]["counts"] == {
        "updated": 0, "unchanged": 0, "skipped": 0, "resumed": 2,
    }


def test_resume_reruns_when_the_row_no_longer_satisfies_the_pass(fixture_db: Path, tmp_path: Path) -> None:
    receipts = tmp_path / "r"
    con = store.connect(fixture_db)
    backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    digest = hashlib.sha256(IMAGE_BYTES).hexdigest()
    body = json.loads((receipts / "content_sha256" / f"{digest}.json").read_text(encoding="utf-8"))
    assert body["status"] == "updated"
    # The row lost its hash after the receipt was written (a restore, a
    # hand edit, another store sharing this receipts dir).
    con.execute("UPDATE binary SET content_sha256=NULL WHERE id=1")
    con.commit()
    again = backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    con.close()
    counts = again["passes"]["content_sha256"]["counts"]
    assert counts["updated"] == 1 and counts["resumed"] == 0
    assert _content_sha(fixture_db)[0] == (1, digest)


def test_receipt_without_status_is_rerun(fixture_db: Path, tmp_path: Path, install: Path) -> None:
    receipts = tmp_path / "r"
    con = store.connect(fixture_db)
    con.execute("UPDATE binary SET language_id='x86:LE:32:default'")
    con.commit()
    backfill.run(con, ["analyzer_identity"], receipts_dir=receipts)
    # A receipt from before the status field existed: same key, no status.
    path = receipts / "analyzer_identity" / "slug-build-b.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy.pop("status")
    path.write_text(json.dumps(legacy), encoding="utf-8")
    again = backfill.run(con, ["analyzer_identity"], receipts_dir=receipts)
    con.close()
    assert again["passes"]["analyzer_identity"]["counts"] == {
        "updated": 0, "unchanged": 1, "skipped": 0, "resumed": 1,
    }
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "unchanged"
