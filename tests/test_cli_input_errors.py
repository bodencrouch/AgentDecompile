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


def test_stabs_manifest_unknown_repo_path_reports_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "store.sqlite"
    store.connect(db).close()

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    out_dir = tmp_path / "out"

    rc = corpus_main(
        ["stabs-manifest", "nosuch", "--db", str(db), "--raw-dir", str(raw_dir), "--out-dir", str(out_dir)]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.err
    assert "error: not in database" in captured.err
    assert "nosuch" in captured.err
    assert captured.out == ""


def test_build_types_header_missing_table_reports_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    from agentdecompile_recovery.corpus import build_types_header as header
    monkeypatch.setattr(header, "basis", lambda _con: {"toolchain_identity_hash": "pinned:none"})
    db = tmp_path / "store.sqlite"
    con = store.connect(db)
    con.execute("INSERT INTO binary (repo_path, slug, arch, content_sha256) VALUES (?,?,?,?)", ("repoA", "slugA", "x86", "a" * 64))
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


def test_stabs_manifest_other_file_not_found_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A FileNotFoundError for something other than the raw image must not be
    reported as a raw-dir problem -- it isn't one. It should propagate so the
    caller sees the real cause instead of a misleading "check --raw-dir"."""
    db = tmp_path / "store.sqlite"
    con = store.connect(db)
    con.execute("INSERT INTO binary (repo_path, slug, arch) VALUES (?,?,?)", ("repoA", "slugA", "x86"))
    con.commit()
    con.close()

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "slugA").write_bytes(b"")  # raw image IS present
    out_dir = tmp_path / "out"

    import agentdecompile_recovery.corpus.machostabs as machostabs

    def boom(_path):
        raise FileNotFoundError("/elsewhere/dep.bin")

    monkeypatch.setattr(machostabs, "analyze", boom)

    with pytest.raises(FileNotFoundError, match="dep.bin"):
        corpus_main(
            ["stabs-manifest", "repoA", "--db", str(db), "--raw-dir", str(raw_dir), "--out-dir", str(out_dir)]
        )


def test_name_census_filename_less_not_found_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A FileNotFoundError with no filename attached can't be confirmed as
    the --db path, so it must propagate rather than being reported as a bad
    --db value."""
    db = tmp_path / "some.gbf"

    import agentdecompile_recovery.ghidra_db as ghidra_db

    def boom(_path):
        raise FileNotFoundError("some other file went missing")

    monkeypatch.setattr(ghidra_db, "open_program", boom)

    with pytest.raises(FileNotFoundError, match="some other file went missing"):
        recover_main(["name-census", "--db", str(db)])


def test_build_types_header_installed_empty_is_success_with_zero_types(tmp_path, capsys, monkeypatch):
    from agentdecompile_recovery.corpus import build_types_header as header, export_types
    from tests.test_corpus_type_schema import current
    db = tmp_path / 'empty-types.sqlite'
    con = current(db)
    export_types.insert_native_types(con, [])
    con.close()
    monkeypatch.setattr(header, 'basis', lambda _con: {'toolchain_identity_hash': 'pinned:none'})
    out = tmp_path / 'types.h'
    assert corpus_main(['build-types-header', '--db', str(db), '--repo-path', '/recipient', '--out', str(out)]) == 0
    captured = capsys.readouterr()
    assert 'Traceback' not in captured.err and 'error:' not in captured.err
    assert out.is_file() and out.with_name('types.h.manifest.json').is_file()
