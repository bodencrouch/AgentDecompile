from __future__ import annotations

from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.export_hookpack import (
    FORMAT,
    export_hookpack,
    unique_window,
)
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit


def test_empty_store_writes_empty_sites(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite"
    out = tmp_path / "pack.json"
    summary = export_hookpack(connect(db), out)
    assert summary["sites"] == 0
    pack = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert pack["format"] == FORMAT
    assert pack["sites"] == {}


def test_one_logical_two_binaries_majority_signature(tmp_path: Path) -> None:
    con = connect(tmp_path / "c.sqlite")
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug'), (2, '/b', 'release')")
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (9, 'RunScript', 'void RunScript()', 2)"
    )
    con.execute("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (9, 1, 100, 1.0, 'stabs'), (9, 2, 200, 0.8, 'engine')")
    con.execute(
        "INSERT INTO func(binary_id, addr, name, signature) VALUES (1, 100, 'RunScript', 'void RunScript()'), (2, 200, 'FUN_200', 'void RunScript()')"
    )
    con.commit()
    out = tmp_path / "pack.json"
    export_hookpack(con, out)
    pack = __import__("json").loads(out.read_text(encoding="utf-8"))
    site = pack["sites"]["RunScript"]
    assert site["logical_id"] == 9
    assert site["signature"]["kind"] == "shared"
    assert {i["binary"] for i in site["instances"]} == {"debug", "release"}
    assert {i["addr"] for i in site["instances"]} == {100, 200}


def test_missing_signature_is_kind_none(tmp_path: Path) -> None:
    con = connect(tmp_path / "c.sqlite")
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug')")
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (3, 'Anon', NULL, 1)"
    )
    con.execute("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (3, 1, 50, 1.0, 'engine')")
    con.execute("INSERT INTO func(binary_id, addr, name, signature) VALUES (1, 50, 'FUN_50', NULL)")
    con.commit()
    out = tmp_path / "pack.json"
    export_hookpack(con, out)
    pack = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert pack["sites"]["Anon"]["signature"]["kind"] == "none"


def test_shared_members_win_over_stale_best(tmp_path: Path) -> None:
    con = connect(tmp_path / "c.sqlite")
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug'), (2, '/b', 'release')")
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) "
        "VALUES (4, 'Split', 'void Old()', 2)"
    )
    con.execute(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence, method) "
        "VALUES (4, 1, 10, 1.0, 'stabs'), (4, 2, 20, 0.8, 'engine')"
    )
    con.execute(
        "INSERT INTO func(binary_id, addr, name, signature) "
        "VALUES (1, 10, 'Split', 'void Split()'), (2, 20, 'FUN_20', 'void Split()')"
    )
    con.commit()
    out = tmp_path / "pack.json"
    export_hookpack(con, out)
    pack = __import__("json").loads(out.read_text(encoding="utf-8"))
    sig = pack["sites"]["Split"]["signature"]
    assert sig["kind"] == "shared"
    assert sig["value"] == "void Split()"


def test_unique_window_omits_non_unique() -> None:
    hay = b"\x90" * 64 + bytes.fromhex("535556578B7C2414") + b"\x90" * 64
    assert unique_window(hay, 64, 32) == bytes.fromhex("535556578B7C2414")
    pat = bytes.fromhex("535556578B7C2414") + b"\x90" * 24
    assert unique_window(pat + pat, 0, 32) is None


def test_export_copies_unique_bytes_from_image(tmp_path: Path, monkeypatch) -> None:
    from agentdecompile_recovery.corpus import export_hookpack as hp

    hay = b"\x90" * 64 + bytes.fromhex("535556578B7C2414") + b"\x90" * 64
    monkeypatch.setattr(hp, "_raw_image", lambda repo: hay)
    monkeypatch.setattr(hp, "_file_offset", lambda image, addr: 64)
    con = connect(tmp_path / "c.sqlite")
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug')")
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (3, 'Run', 'void Run()', 1)"
    )
    con.execute("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (3, 1, 256, 1.0, 'stabs')")
    con.execute(
        "INSERT INTO func(binary_id, addr, name, signature, size) VALUES (1, 256, 'Run', 'void Run()', 16)"
    )
    con.commit()
    out = tmp_path / "pack.json"
    hp.export_hookpack(con, out)
    pack = __import__("json").loads(out.read_text(encoding="utf-8"))
    site = pack["sites"]["Run"]
    assert site["expected_bytes"] == "535556578B7C2414"
    assert site["instances"][0]["expected_bytes"] == "535556578B7C2414"


def _two_logical_store(path: Path, *, forward: bool):
    """Same content, opposite insertion order: rows that are not rowid-aliased
    (identity) come back in insertion order without an ORDER BY."""
    con = connect(path)
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug'), (2, '/b', 'release')")
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) "
        "VALUES (1, 'Tick', NULL, 3), (2, 'Tick', NULL, 1)"
    )
    identities = [(1, 1, 100, 0.9, 'a'), (1, 1, 300, 0.9, 'a'), (1, 2, 200, 0.9, 'a'), (2, 2, 400, 0.9, 'a')]
    funcs = [
        (1, 100, 'Tick', 'void Tick(int)'),
        (1, 300, 'Tick', 'void Tick(long)'),
        (2, 200, 'FUN_200', 'void Tick(int)'),
        (2, 400, 'FUN_400', 'void Tick(char)'),
    ]
    if not forward:
        identities.reverse()
        funcs.reverse()
    con.executemany("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (?,?,?,?,?)", identities)
    con.executemany("INSERT INTO func(binary_id, addr, name, signature) VALUES (?,?,?,?)", funcs)
    con.commit()
    return con


def test_export_is_insertion_order_independent(tmp_path: Path) -> None:
    export_hookpack(_two_logical_store(tmp_path / "f.sqlite", forward=True), tmp_path / "f.json")
    export_hookpack(_two_logical_store(tmp_path / "r.sqlite", forward=False), tmp_path / "r.json")
    assert (tmp_path / "f.json").read_bytes() == (tmp_path / "r.json").read_bytes()


def test_shared_best_name_never_overwrites_a_site(tmp_path: Path) -> None:
    out = tmp_path / "pack.json"
    export_hookpack(_two_logical_store(tmp_path / "c.sqlite", forward=True), out)
    pack = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert sorted(pack["sites"]) == ["Tick__1", "Tick__2"]
    assert pack["sites"]["Tick__1"]["logical_id"] == 1
    assert pack["sites"]["Tick__2"]["logical_id"] == 2
    assert [i["addr"] for i in pack["sites"]["Tick__1"]["instances"]] == [100, 300, 200]


def test_preferred_signature_breaks_count_ties_by_value() -> None:
    from agentdecompile_recovery.corpus.export_hookpack import _preferred_signature

    ab = _preferred_signature(None, ["void A()", "void B()"])
    ba = _preferred_signature(None, ["void B()", "void A()"])
    assert ab == ba
    assert ab["value"] == "void B()"
    assert ab["kind"] == "majority"


def test_pack_is_serialized_with_sorted_keys_and_basis(tmp_path: Path) -> None:
    out = tmp_path / "pack.json"
    export_hookpack(_two_logical_store(tmp_path / "c.sqlite", forward=True), out)
    text = out.read_text(encoding="utf-8")
    pack = __import__("json").loads(text)
    assert text == __import__("json").dumps(pack, indent=2, sort_keys=True) + "\n"
    assert pack["basis"]["algorithm_version"] == "phase0.1"
    assert set(pack["basis"]) == {
        "decoder", "algorithm_version", "masking_rule_version", "threshold_params", "corpus_manifest_hash",
    }
