from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import determinism_basis as db_mod
from agentdecompile_recovery.corpus.cli import build_parser, main as corpus_main
from agentdecompile_recovery.corpus.export_hookpack import export_hookpack
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit


def _store(path: Path, rows):
    con = connect(path)
    con.executemany(
        "INSERT INTO binary(id, repo_path, slug, content_sha256, md5, language_id) VALUES (?,?,?,?,?,?)", rows
    )
    con.commit()
    return con


ROWS = [
    (1, "/a", "alpha", "ff" * 32, "aa" * 16, "x86:LE:32:default"),
    (2, "/b", "beta", None, "bb" * 16, "x86:LE:32:default"),
    (3, "/c", "gamma", "", "", None),
]


def test_manifest_hash_sorted_with_fallbacks(tmp_path: Path) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    expected = hashlib.sha256("\n".join(sorted(["ff" * 32, "bb" * 16, "gamma"])).encode()).hexdigest()
    assert db_mod.corpus_manifest_hash(con) == expected
    reverse = _store(tmp_path / "r.sqlite", list(reversed(ROWS)))
    assert db_mod.basis(con) == db_mod.basis(reverse)


def test_basis_shape_without_ghidra(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    con = _store(tmp_path / "c.sqlite", ROWS)
    b = db_mod.basis(con)
    assert b["decoder"].startswith("ghidra-analysis/unknown+")
    assert b["decoder"] != "ghidra-analysis/unknown+unknown"
    assert b["algorithm_version"] == "phase0.1"
    assert b["masking_rule_version"] == "none"
    assert b["threshold_params"] == {}
    empty = connect(tmp_path / "e.sqlite")
    assert db_mod.basis(empty)["decoder"] == "ghidra-analysis/unknown+unknown"


def test_first_diff_path() -> None:
    assert db_mod.first_diff_path({"a": 1}, {"a": 1}) == ""
    assert db_mod.first_diff_path({"a": {"b": [1, 2]}}, {"a": {"b": [1, 3]}}) == "$.a.b[1]"
    assert db_mod.first_diff_path({"a": 1}, {"a": 1, "z": 2}) == "$.z"


def test_verify_determinism_verb(tmp_path: Path, monkeypatch, capsys) -> None:
    subs = build_parser()._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert "verify-determinism" in subs
    db = tmp_path / "c.sqlite"
    con = _store(db, ROWS)
    con.execute("INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (1, 'Run', 'void Run()', 1)")
    con.execute("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (1, 1, 16, 1.0, 'a')")
    con.commit()
    assert corpus_main(["verify-determinism", "--db", str(db)]) == 0
    assert '"identical": true' in capsys.readouterr().out

    calls = []

    def flaky(con, out):
        calls.append(out)
        export_hookpack(con, out)
        if len(calls) == 2:
            text = out.read_text(encoding="utf-8").replace('"logical_id": 1', '"logical_id": 2')
            out.write_text(text, encoding="utf-8")

    result = db_mod.verify_export(db, flaky)
    assert result == {"identical": False, "diff": "$.sites.Run.logical_id"}
