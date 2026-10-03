"""Tests for workbench.py's static-chain cross-build matrix (U8/U43/AE6).

Builds a synthetic corpus database through the real store helpers
(``agentdecompile_recovery.corpus.store.connect``) so the schema, including
the match_review control tables that ``cross_build_matrix``/``pair_matches``
pin a transaction against, is exactly what production code produces --
nothing here hand-rolls a parallel schema. No dependence on
/home/brunner56/agentdecompile-nvme paths: everything lives under tmp_path.
"""

from __future__ import annotations

import json
import sqlite3

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdecompile_recovery.corpus import store
from agentdecompile_recovery.corpus.dashboard import function_evidence
from agentdecompile_recovery.corpus.dashboard.router import create_dashboard_router
from agentdecompile_recovery.corpus.dashboard.workbench import (
    cross_build_matrix,
    function_detail,
    pair_matches,
)

pytestmark = pytest.mark.unit


def _setup_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    db = tmp_path / "corpus.sqlite"
    con = store.connect(db)
    con.close()
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_DB", str(db))
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_WORK_DIR", str(tmp_path / "work"))
    return db


def _insert_binary(con: sqlite3.Connection, *, repo_path: str, slug: str, arch: str = "x86",
                    bits: int = 32, func_count: int = 1, recovery_family: str | None = None,
                    content_sha256: str | None = None) -> int:
    cur = con.execute(
        "INSERT INTO binary (repo_path, slug, arch, bits, func_count, recovery_family, content_sha256) "
        "VALUES (?,?,?,?,?,?,?)",
        (repo_path, slug, arch, bits, func_count, recovery_family, content_sha256),
    )
    con.commit()
    return int(cur.lastrowid)


def _insert_match(con: sqlite3.Connection, *, src_binary: int, dst_binary: int,
                   src_addr: int = 0x1000, dst_addr: int = 0x1000, evidence: dict | None = None) -> int:
    cur = con.execute(
        "INSERT INTO match (run, src_binary, src_addr, dst_binary, dst_addr, score, evidence, status) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("run1", src_binary, src_addr, dst_binary, dst_addr, 1.0, json.dumps(evidence or {}), "accepted"),
    )
    con.commit()
    return int(cur.lastrowid)


def test_matrix_cell_ran_vs_not_scheduled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = _setup_db(monkeypatch, tmp_path)
    con = store.connect(db)
    try:
        # A and B share a recovery family and arch group: the spanning-forest
        # scheduler connects them, and a recorded match row makes the cell "ran".
        a = _insert_binary(con, repo_path=str(tmp_path / "a"), slug="a", func_count=5, recovery_family="fam1")
        b = _insert_binary(con, repo_path=str(tmp_path / "b"), slug="b", func_count=3, recovery_family="fam1")
        # C sits in its own family with no partner, so no pair touching it is
        # ever scheduled and (absent any match rows) it stays "not-scheduled".
        c = _insert_binary(con, repo_path=str(tmp_path / "c"), slug="c", func_count=1, recovery_family="fam2")
        _insert_match(con, src_binary=min(a, b), dst_binary=max(a, b), evidence={"primary_channel": "S", "bsim": 1})
    finally:
        con.close()

    result = cross_build_matrix([a, b, c])
    assert result["ok"] is True
    cells = {frozenset((cell["srcSlug"], cell["dstSlug"])): cell for cell in result["cells"]}

    ab_cell = cells[frozenset(("a", "b"))]
    assert ab_cell["state"] == "ran"
    assert ab_cell["schedule"]["selected"] is True

    for pair in (("a", "c"), ("b", "c")):
        cell = cells[frozenset(pair)]
        assert cell["state"] == "not-scheduled"
        assert cell["schedule"]["selected"] is False
        assert cell["reason"] == "pair_not_selected" or cell["schedule"]["reason"] == (
            "pair_outside_spanning_forest_and_hub_anchor_set"
        )


def test_matrix_include_tiers_missing_basis_stays_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = _setup_db(monkeypatch, tmp_path)
    con = store.connect(db)
    try:
        # Neither binary carries a content_sha256, so there is no report basis
        # to build tier counts from.
        a = _insert_binary(con, repo_path=str(tmp_path / "a"), slug="a", recovery_family="fam1")
        b = _insert_binary(con, repo_path=str(tmp_path / "b"), slug="b", recovery_family="fam1")
    finally:
        con.close()

    result = cross_build_matrix([a, b], include_tiers=True)
    assert result["ok"] is True
    cell = result["cells"][0]
    for side in ("src", "dst"):
        tiers = cell["tiers"][side]
        # Explicit refusal, never an invented zero/placeholder count.
        assert tiers["ok"] is False
        assert tiers["reason"] == "binary_content_identity_required"
        assert "tiers" not in tiers


def test_router_cross_build_matrix_accepts_slugs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Regression: the route used to read only binary_ids and silently drop slugs."""
    db = _setup_db(monkeypatch, tmp_path)
    con = store.connect(db)
    try:
        a = _insert_binary(con, repo_path=str(tmp_path / "a"), slug="only-a", recovery_family="fam1")
        b = _insert_binary(con, repo_path=str(tmp_path / "b"), slug="only-b", recovery_family="fam1")
    finally:
        con.close()

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app)

    response = client.get("/dashboard/api/workbench/cross-build-matrix", params={"slugs": "only-a,only-b"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    slugs = {row["slug"] for row in payload["binaries"]}
    assert slugs == {"only-a", "only-b"}
    assert {b_id for b_id in (a, b)} <= {row["id"] for row in payload["binaries"]}


def test_pair_matches_uses_typed_columns_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = _setup_db(monkeypatch, tmp_path)
    con = store.connect(db)
    try:
        a = _insert_binary(con, repo_path=str(tmp_path / "a"), slug="a")
        b = _insert_binary(con, repo_path=str(tmp_path / "b"), slug="b")
        match_id = _insert_match(con, src_binary=a, dst_binary=b)
        con.execute("UPDATE match SET kind=?, confidence=?, algorithm=? WHERE id=?",
                    ("exact", 0.9, "S", match_id))
        con.commit()
        # Sanity: this corpus db really does carry the typed columns.
        cols = {row[1] for row in con.execute("PRAGMA table_info(match)")}
        assert {"kind", "confidence", "algorithm"} <= cols
    finally:
        con.close()

    result = pair_matches(a, b)
    assert result["ok"] is True
    assert len(result["matches"]) == 1
    row = result["matches"][0]
    assert row["kind"] == "exact"
    assert row["confidence"] == pytest.approx(0.9)
    assert row["algorithm"] == "S"


def test_pair_matches_falls_back_to_evidence_json_without_typed_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = _setup_db(monkeypatch, tmp_path)
    con = store.connect(db)
    try:
        a = _insert_binary(con, repo_path=str(tmp_path / "a"), slug="a")
        b = _insert_binary(con, repo_path=str(tmp_path / "b"), slug="b")
        _insert_match(con, src_binary=a, dst_binary=b,
                      evidence={"kind": "fuzzy", "confidence": 0.5, "primary_channel": "K"})
        # Simulate a pre-U13 corpus db that never got the typed columns.
        con.execute("DROP INDEX IF EXISTS ix_match_algorithm_confidence")
        for column in ("kind", "confidence", "algorithm"):
            con.execute(f"ALTER TABLE match DROP COLUMN {column}")
        con.commit()
        cols = {row[1] for row in con.execute("PRAGMA table_info(match)")}
        assert not ({"kind", "confidence", "algorithm"} & cols)
    finally:
        con.close()

    result = pair_matches(a, b)
    assert result["ok"] is True
    assert len(result["matches"]) == 1
    row = result["matches"][0]
    assert row["kind"] == "fuzzy"
    assert row["confidence"] == pytest.approx(0.5)
    assert row["algorithm"] == "K"


def test_function_detail_exposes_comments_for_listing_column(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """function_detail must surface the recorded-evidence `comments` list
    (what the Listing comment column renders) when a complete observation
    is already on disk -- no corpus db or live Ghidra connection needed."""
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_WORK_DIR", str(tmp_path / "work"))

    payload = {
        "name": "sub_1000",
        "signature": "int sub_1000(void)",
        "views": {
            "decompile": {"decompilation": "int sub_1000(void) { return 1; }"},
            "disassemble": {"instructions": [{"address": "0x1000", "mnemonic": "ret", "bytes": "c3"}]},
        },
        "comments": [{"address": "0x1000", "type": "pre", "text": "entry"}],
    }
    function_evidence.record({"functionIdentifier": "0x1000", "programPath": "", "locator": ""},
                              "get-function", payload)

    result = function_detail("demo-slug", "0x1000", locator="", program="")
    assert result["ok"] is True
    assert result["comments"] == [{"address": "0x1000", "type": "pre", "text": "entry"}]
