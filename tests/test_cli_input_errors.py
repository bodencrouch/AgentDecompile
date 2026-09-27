"""Bad-input cases for four CLI verbs report a clean error, not a traceback.

Each verb previously let a library exception (KeyError, FileNotFoundError,
sqlite3.OperationalError) propagate straight out of ``main()``. The dispatch
layer now catches the specific exception for that input case and reports it
the way sibling verbs in the same file already do.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import store
from agentdecompile_recovery.corpus.cli import main as corpus_main
from agentdecompile_recovery.cli import main as recover_main

pytestmark = pytest.mark.unit


def test_evaluate_pair_missing_binaries_reports_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "store.sqlite"
    store.connect(db).close()

    rc = corpus_main(["evaluate-pair", "--db", str(db), "--src", "nope", "--dst", "nope2"])

    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.err
    assert "error:" in captured.err
    assert "nope" in captured.err
    assert captured.out == ""


def test_stabs_manifest_missing_raw_image_reports_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "store.sqlite"
    con = store.connect(db)
    con.execute("INSERT INTO binary (repo_path, slug, arch) VALUES (?,?,?)", ("repoA", "slugA", "x86"))
    con.commit()
    con.close()

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    out_dir = tmp_path / "out"

    rc = corpus_main(
        ["stabs-manifest", "repoA", "--db", str(db), "--raw-dir", str(raw_dir), "--out-dir", str(out_dir)]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.err
    assert "error:" in captured.err
    assert "slugA" in captured.err
    assert captured.out == ""


def test_build_types_header_missing_table_reports_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "store.sqlite"
    con = store.connect(db)
    con.execute("INSERT INTO binary (repo_path, slug, arch) VALUES (?,?,?)", ("repoA", "slugA", "x86"))
    con.commit()
    con.close()

    out = tmp_path / "types.h"

    rc = corpus_main(["build-types-header", "--db", str(db), "--repo-path", "repoA", "--out", str(out)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.err
    assert "error:" in captured.err
    assert "ghidra_type" in captured.err
    assert captured.out == ""


def test_name_census_missing_db_reports_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.gbf"

    rc = recover_main(["name-census", "--db", str(missing)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.err
    assert '"error"' in captured.err
    assert "nope.gbf" in captured.err
    assert captured.out == ""
