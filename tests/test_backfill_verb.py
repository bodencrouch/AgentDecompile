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
    assert with_image["result"] == {"content_sha256": digest}
    assert with_image["binary"]["id"] == 1
    no_image = json.loads(after_first["content_sha256/slug-build-b.json"])
    assert no_image["key"] == {"pass": "content_sha256", "identity": "build-b"}
    assert no_image["result"] == {"reason": "no_raw_image"}
    assert no_image["raw_image"] is None
    for body in after_first.values():
        text = body.decode("utf-8")
        assert "applied_at" not in text and "timestamp" not in text
        assert body == (json.dumps(json.loads(text), sort_keys=True, indent=2) + "\n").encode()

    con = store.connect(fixture_db)
    second = backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    con.close()
    assert second["passes"]["content_sha256"]["counts"] == {
        "updated": 0, "unchanged": 0, "skipped": 0, "resumed": 2,
    }
    assert [e["status"] for e in second["passes"]["content_sha256"]["binaries"]] == ["resumed", "resumed"]
    assert _receipts(receipts) == after_first
    assert _content_sha(fixture_db) == [(1, digest), (2, None)]


def test_no_resume_rewrites_identical_receipts(fixture_db: Path, tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    con = store.connect(fixture_db)
    backfill.run(con, ["content_sha256"], receipts_dir=receipts)
    before = _receipts(receipts)
    third = backfill.run(con, ["content_sha256"], receipts_dir=receipts, resume=False)
    con.close()
    assert third["passes"]["content_sha256"]["counts"] == {
        "updated": 0, "unchanged": 1, "skipped": 1, "resumed": 0,
    }
    assert _receipts(receipts) == before


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
        "updated": 1, "unchanged": 0, "skipped": 0, "resumed": 1,
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
    assert resumed["passes"]["content_sha256"]["counts"]["resumed"] == 2

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
