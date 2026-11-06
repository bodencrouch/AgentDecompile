"""Named refusals for the keyed corpus verbs (attestation A5).

``export-hookpack``, ``verify-determinism``, ``logical-build`` and
``backfill`` share one refusal path: a missing basis, a build without a
usable ``content_sha256`` or a write lock held past ``busy_timeout`` is exit
2 with one named line on stderr, never a traceback. The content-hash line
carries a count and ``sha256(slug)[:12]`` per build, never a slug. Fixtures
are synthetic; every slug here is a made-up word.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import cli, logical, store
from agentdecompile_recovery.corpus.cli import main as corpus_main
from agentdecompile_recovery.corpus.determinism_basis import BasisError
from agentdecompile_recovery.corpus.extract import stamp_analyzer_identity

pytestmark = pytest.mark.unit

H1, H2 = "1" * 64, "2" * 64
FUNC_COLS = (
    "binary_id, addr, name, canon_key, canon_class, canon_method, canon_arity, "
    "name_origin, plate, signature, n_instr, n_blocks, cyclomatic, n_callees, strings, consts"
)
FUNCS = [
    (1, 0x2000, "run", "Widget::run", "Widget", "run", 1, "plate", "void Widget::run(int)", "void run(int)", 12, 3, 2, 1, "[]", "[]"),
    (2, 0x3000, "run", "Widget::run", "Widget", "run", 1, "plate", "void Widget::run(long)", "void run(long)", 12, 3, 2, 1, "[]", "[]"),
]


def _hashed(slug: str) -> str:
    return hashlib.sha256(slug.encode("utf-8")).hexdigest()[:12]


def _keyed_store(path: Path, *, hashes: tuple[str | None, str | None] = (H1, H2), stamp: bool = True) -> Path:
    """Two builds with one shared name; built once so identity rows exist."""
    con = store.connect(path)
    con.execute(
        "INSERT INTO binary(id, repo_path, slug, game, language_id, content_sha256) VALUES (1, '/a', 'alpha', 'g', 'l0', ?), (2, '/b', 'beta', 'g', 'l0', ?)",
        (H1, H2),
    )
    con.executemany(f"INSERT INTO func({FUNC_COLS}) VALUES ({','.join('?' * 16)})", FUNCS)
    con.commit()
    if stamp:
        stamp_analyzer_identity(con, analyzer_version="test-analyzer")
    logical.build(con)
    con.execute("UPDATE binary SET content_sha256=? WHERE id=1", (hashes[0],))
    con.execute("UPDATE binary SET content_sha256=? WHERE id=2", (hashes[1],))
    con.commit()
    con.close()
    # One more connect so the recovery_family backfill (D9) has already run
    # and committed; the verbs under test then never ask for the write lock
    # on connect, only where they write.
    store.connect(path).close()
    return path


def _counts(path: Path) -> dict[str, int]:
    con = sqlite3.connect(path)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("identity", "logical_function")}
    finally:
        con.close()


# --- the line ----------------------------------------------------------------


def test_refusal_line_names_the_class_and_hashes_the_builds() -> None:
    missing = logical.ContentHashError("binary.content_sha256 is NULL or blank for beta", kind="missing", slugs=["beta"])
    line = cli._refusal_line(missing)
    assert line == f"error: ContentHashError: content_sha256 missing for 1 build(s) [{_hashed('beta')}]; {logical.BACKFILL_HINT}"
    assert "beta" not in line
    dupe = logical.ContentHashError("shared: alpha, beta", kind="duplicate", slugs=["alpha", "beta"])
    line = cli._refusal_line(dupe)
    assert line.startswith(f"error: ContentHashError: content_sha256 shared by 2 build(s) [{_hashed('alpha')}, {_hashed('beta')}]")
    assert "alpha" not in line and "beta" not in line
    assert cli._refusal_line(BasisError("basis: analyzer.version is absent")) == "error: basis: analyzer.version is absent"
    assert cli._refusal_line(sqlite3.OperationalError("database is locked")).startswith("error: locked: database is locked")
    # Any other operational error is a real failure, not a refusal.
    assert cli._refusal_line(sqlite3.OperationalError("no such table: binary")) is None
    assert cli._refusal_line(ValueError("x")) is None


def test_run_keyed_verb_reraises_a_non_lock_operational_error() -> None:
    def boom():
        raise sqlite3.OperationalError("no such table: binary")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        cli._run_keyed_verb(boom)


# --- logical-build ------------------------------------------------------------


def test_logical_build_refuses_by_hashed_name_and_keeps_the_store(tmp_path: Path, capsys) -> None:
    db = _keyed_store(tmp_path / "c.sqlite", hashes=(H1, None))
    before = _counts(db)
    assert before["identity"] > 0
    assert corpus_main(["logical-build", "--db", str(db)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.strip().splitlines()
    assert lines == [f"error: ContentHashError: content_sha256 missing for 1 build(s) [{_hashed('beta')}]; {logical.BACKFILL_HINT}"]
    assert "beta" not in captured.err and "alpha" not in captured.err
    assert _counts(db) == before, "a refusal must not wipe identity or logical_function (A1)"


def test_logical_build_refuses_duplicate_hash_with_both_builds_hashed(tmp_path: Path, capsys) -> None:
    db = _keyed_store(tmp_path / "d.sqlite", hashes=(H1, H1))
    before = _counts(db)
    assert corpus_main(["logical-build", "--db", str(db)]) == 2
    err = capsys.readouterr().err
    assert f"content_sha256 shared by 2 build(s) [{_hashed('alpha')}, {_hashed('beta')}]" in err
    assert "alpha" not in err and "beta" not in err
    assert _counts(db) == before


def test_logical_build_reports_a_held_write_lock_as_locked(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _keyed_store(tmp_path / "l.sqlite")
    real_connect = store.connect

    def quick_connect(path, **kw):
        con = real_connect(path, **kw)
        con.execute("PRAGMA busy_timeout=300")  # the test's budget, not the store's
        return con

    monkeypatch.setattr(store, "connect", quick_connect)
    holder = sqlite3.connect(db)
    holder.execute("BEGIN IMMEDIATE")
    try:
        assert corpus_main(["logical-build", "--db", str(db)]) == 2
    finally:
        holder.rollback()
        holder.close()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: locked: database is locked")
    assert "Traceback" not in captured.err


# --- export-hookpack / verify-determinism -------------------------------------


def test_export_hookpack_refuses_by_hashed_name_and_writes_nothing(tmp_path: Path, capsys) -> None:
    db = _keyed_store(tmp_path / "e.sqlite", hashes=(H1, None))
    out = tmp_path / "pack.json"
    assert corpus_main(["export-hookpack", "--db", str(db), "--out", str(out)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"error: ContentHashError: content_sha256 missing for 1 build(s) [{_hashed('beta')}]; {logical.BACKFILL_HINT}"
    assert not out.exists()


def test_export_hookpack_checks_the_basis_before_touching_sites(tmp_path: Path, capsys) -> None:
    """A store with no basis refuses before the site loop reads identity or logical_function."""
    db = _keyed_store(tmp_path / "b.sqlite", stamp=False)
    out = tmp_path / "pack.json"
    seen: list[str] = []
    real_connect = store.connect

    def traced(path, **kw):
        con = real_connect(path, **kw)
        con.set_trace_callback(seen.append)
        return con

    from agentdecompile_recovery.corpus import export_hookpack as hp

    con = traced(db)
    with pytest.raises(BasisError):
        hp.export_hookpack(con, out)
    con.close()
    touched = [sql for sql in seen if "logical_function" in sql or "FROM identity" in sql]
    assert touched == [], touched
    assert not out.exists()
    assert corpus_main(["export-hookpack", "--db", str(db), "--out", str(out)]) == 2
    assert capsys.readouterr().err.startswith("error: basis: ")


def test_verify_determinism_refuses_by_hashed_name(tmp_path: Path, capsys) -> None:
    db = _keyed_store(tmp_path / "v.sqlite", hashes=(H1, None))
    assert corpus_main(["verify-determinism", "--db", str(db)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"error: ContentHashError: content_sha256 missing for 1 build(s) [{_hashed('beta')}]; {logical.BACKFILL_HINT}"


def test_keyed_verbs_still_succeed_on_a_keyed_store(tmp_path: Path, capsys) -> None:
    db = _keyed_store(tmp_path / "ok.sqlite")
    out = tmp_path / "pack.json"
    assert corpus_main(["logical-build", "--db", str(db)]) == 0
    assert json.loads(capsys.readouterr().out)["logical"] == 1
    assert corpus_main(["export-hookpack", "--db", str(db), "--out", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["sites"] == 1
    assert corpus_main(["verify-determinism", "--db", str(db)]) == 0
    assert json.loads(capsys.readouterr().out)["identical"] is True


# --- backfill -----------------------------------------------------------------


def test_backfill_unknown_pass_keeps_its_system_exit(tmp_path: Path) -> None:
    db = _keyed_store(tmp_path / "p.sqlite")
    with pytest.raises(SystemExit, match="unknown backfill pass"):
        corpus_main(["backfill", "--db", str(db), "--pass", "nope", "--receipts", str(tmp_path / "r")])


def test_backfill_reports_a_held_write_lock_as_locked(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _keyed_store(tmp_path / "bl.sqlite")
    from agentdecompile_recovery.corpus import backfill as bf

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(bf, "run", locked)
    assert corpus_main(["backfill", "--db", str(db), "--pass", "content_sha256", "--receipts", str(tmp_path / "r")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: locked: database is locked")
