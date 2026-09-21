from __future__ import annotations

from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.determinism_basis import BasisError, basis
from agentdecompile_recovery.corpus.export_hookpack import (
    export_hookpack,
    unique_window,
)
from agentdecompile_recovery.corpus.extract import stamp_analyzer_identity
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit


def _stamp(con) -> None:
    """Give every binary row the analyzer identity the basis refuses without."""
    con.execute("UPDATE binary SET language_id=COALESCE(language_id, 'x86:LE:32:default')")
    stamp_analyzer_identity(con, analyzer_version="test-analyzer")


def test_empty_store_refuses_without_a_basis(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite"
    out = tmp_path / "pack.json"
    with pytest.raises(BasisError, match="analyzer.version has no producer row"):
        export_hookpack(connect(db), out)
    assert not out.exists()


def test_one_logical_two_binaries_majority_signature(tmp_path: Path) -> None:
    con = connect(tmp_path / "c.sqlite")
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug'), (2, '/b', 'release')")
    _stamp(con)
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
    _stamp(con)
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
    _stamp(con)
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
    _stamp(con)
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
    _stamp(con)
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
    con = _two_logical_store(tmp_path / "c.sqlite", forward=True)
    export_hookpack(con, out)
    text = out.read_text(encoding="utf-8")
    pack = __import__("json").loads(text)
    assert text == __import__("json").dumps(pack, indent=2, sort_keys=True) + "\n"
    # The pack root carries the store's declared basis verbatim; its key set
    # is pinned in test_determinism_basis.
    assert pack["basis"] == basis(con)


# ------------------------------------------------------------- U1 identity

FIXTURES = Path(__file__).parent / "fixtures" / "hookpack"
HAY = b"\x90" * 64 + bytes.fromhex("535556578B7C2414") + b"\x90" * 64
HAY2 = b"\x90" * 64 + bytes.fromhex("8BFF558BEC83EC10") + b"\x90" * 64
_PAT = bytes.fromhex("535556578B7C2414") + b"\x90" * 24
HAY_DUP = b"\x90" * 64 + _PAT + _PAT


def _json(path: Path) -> dict:
    return __import__("json").loads(path.read_text(encoding="utf-8"))


def _identity_store(path: Path):
    con = connect(path)
    con.execute(
        "INSERT INTO binary(id, repo_path, slug, game, platform, format, arch, bits, image_base, content_sha256)"
        " VALUES (1, '/stored', 'zeta', 'g', 'pc', 'pe', 'x86', 32, 4194304, 'ab' || 'cd'),"
        "        (2, '/computed', 'alpha', 'g', 'pc', 'pe', 'x86', 32, NULL, NULL),"
        "        (3, '/nothing', 'mid', 'g', 'pc', 'elf', 'arm', 64, 65536, '')"
    )
    _stamp(con)
    con.commit()
    return con


def test_binaries_carry_identity_and_sha256_source(tmp_path: Path, monkeypatch) -> None:
    from agentdecompile_recovery.corpus import export_hookpack as hp

    images = {"/computed": HAY}
    monkeypatch.setattr(hp, "_raw_image", lambda repo: images.get(repo))
    out = tmp_path / "pack.json"
    hp.export_hookpack(_identity_store(tmp_path / "c.sqlite"), out)
    bins = _json(out)["binaries"]
    assert [b["slug"] for b in bins] == ["alpha", "mid", "zeta"]
    by_slug = {b["slug"]: b for b in bins}

    stored = by_slug["zeta"]
    assert stored["image_base"] == 4194304
    assert (stored["arch"], stored["bits"], stored["format"], stored["platform"]) == ("x86", 32, "pe", "pc")
    assert stored["sha256"] == "abcd"
    assert stored["sha256_source"] == "stored"

    computed = by_slug["alpha"]
    assert "image_base" not in computed
    assert computed["sha256"] == __import__("hashlib").sha256(HAY).hexdigest()
    assert computed["sha256_source"] == "computed"

    nothing = by_slug["mid"]
    assert nothing["image_base"] == 65536
    assert (nothing["arch"], nothing["bits"], nothing["format"]) == ("arm", 64, "elf")
    assert "sha256" not in nothing
    assert "sha256_source" not in nothing


# ------------------------------------------------------------- U2 windows


def _windows_store(path: Path):
    """Four builds of one site. Slugs are deliberately out of id order."""
    con = connect(path)
    con.execute(
        "INSERT INTO binary(id, repo_path, slug) VALUES"
        " (1, '/z', 'zeta'), (2, '/a', 'alpha'), (3, '/n', 'noimg'), (4, '/d', 'dup')"
    )
    _stamp(con)
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (7, 'Run', 'void Run()', 4)"
    )
    con.executemany(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (7, ?, 256, 1.0, 'a')",
        [(1,), (2,), (3,), (4,)],
    )
    con.executemany(
        "INSERT INTO func(binary_id, addr, name, signature, size) VALUES (?, 256, 'Run', 'void Run()', 16)",
        [(1,), (2,), (3,), (4,)],
    )
    con.commit()
    return con


def test_instance_windows_are_carried_and_labelled(tmp_path: Path, monkeypatch) -> None:
    from agentdecompile_recovery.corpus import export_hookpack as hp

    images = {"/z": HAY, "/a": HAY2, "/n": None, "/d": HAY_DUP}
    monkeypatch.setattr(hp, "_raw_image", lambda repo: images[repo])
    monkeypatch.setattr(hp, "_file_offset", lambda image, addr, load_base=None: 64)
    out = tmp_path / "pack.json"
    hp.export_hookpack(_windows_store(tmp_path / "c.sqlite"), out)
    site = _json(out)["sites"]["Run"]
    by_slug = {i["binary"]: i for i in site["instances"]}

    assert by_slug["zeta"]["expected_bytes"] == "535556578B7C2414"
    assert by_slug["alpha"]["expected_bytes"] == "8BFF558BEC83EC10"
    assert "window" not in by_slug["zeta"]
    assert by_slug["noimg"] == {**by_slug["noimg"], "window": "no_image"}
    assert "expected_bytes" not in by_slug["noimg"]
    assert by_slug["dup"]["window"] == "not_unique"
    assert "expected_bytes" not in by_slug["dup"]

    assert "expected_bytes" not in site
    assert site["expected_bytes_agreement"] == {"hits": 1, "of": 2}
    assert site["instance_windows"] == [
        {"binary": "alpha", "expected_bytes": "8BFF558BEC83EC10"},
        {"binary": "zeta", "expected_bytes": "535556578B7C2414"},
    ]


def test_site_expected_bytes_rule_unchanged_when_all_agree(tmp_path: Path, monkeypatch) -> None:
    from agentdecompile_recovery.corpus import export_hookpack as hp

    monkeypatch.setattr(hp, "_raw_image", lambda repo: HAY)
    monkeypatch.setattr(hp, "_file_offset", lambda image, addr, load_base=None: 64)
    con = connect(tmp_path / "c.sqlite")
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug'), (2, '/b', 'release')")
    _stamp(con)
    con.execute("INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (3, 'Run', 'void Run()', 2)")
    con.execute("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (3, 1, 256, 1.0, 'a'), (3, 2, 256, 1.0, 'a')")
    con.commit()
    out = tmp_path / "pack.json"
    hp.export_hookpack(con, out)
    site = _json(out)["sites"]["Run"]
    assert site["expected_bytes"] == "535556578B7C2414"
    assert site["expected_bytes_agreement"] == {"hits": 2, "of": 2}
    assert [w["binary"] for w in site["instance_windows"]] == ["debug", "release"]


def test_unmapped_address_with_image_is_not_unique(tmp_path: Path, monkeypatch) -> None:
    """An image whose mapper cannot place the VA has no unique window either."""
    from agentdecompile_recovery.corpus import export_hookpack as hp

    monkeypatch.setattr(hp, "_raw_image", lambda repo: HAY)
    monkeypatch.setattr(hp, "_file_offset", lambda image, addr, load_base=None: None)
    out = tmp_path / "pack.json"
    hp.export_hookpack(_policy_store(tmp_path / "c.sqlite"), out)
    site = _json(out)["sites"]["Plain"]
    assert site["instances"][0]["window"] == "not_unique"
    assert "expected_bytes" not in site["instances"][0]
    assert site["instance_windows"] == []


def test_stored_sha256_never_reads_the_image(tmp_path: Path, monkeypatch) -> None:
    from agentdecompile_recovery.corpus import export_hookpack as hp

    reads: list[str] = []

    def spy(repo):
        reads.append(repo)
        return None

    monkeypatch.setattr(hp, "_raw_image", spy)
    hp.export_hookpack(_identity_store(tmp_path / "c.sqlite"), tmp_path / "pack.json")
    # /stored has a hash; /computed and /nothing (blank hash) are the only reads.
    assert sorted(reads) == ["/computed", "/nothing"]


def test_site_without_any_window_has_no_agreement(tmp_path: Path) -> None:
    out = tmp_path / "pack.json"
    export_hookpack(_two_logical_store(tmp_path / "c.sqlite", forward=True), out)
    site = _json(out)["sites"]["Tick__1"]
    assert "expected_bytes_agreement" not in site
    assert site["instance_windows"] == []
    assert all(i["window"] == "no_image" for i in site["instances"])


# ------------------------------------------------------------- U3 policy


def _policy_store(path: Path):
    con = connect(path)
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1, '/a', 'debug')")
    _stamp(con)
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES"
        " (9, 'RunScript', 'void RunScript()', 1), (10, 'SlotTable', NULL, 1), (11, 'Plain', NULL, 1)"
    )
    con.executemany(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (?, 1, ?, 1.0, 'a')",
        [(9, 100), (10, 200), (11, 300)],
    )
    con.commit()
    return con


def test_site_policy_defaults_without_file(tmp_path: Path) -> None:
    out = tmp_path / "pack.json"
    export_hookpack(_policy_store(tmp_path / "c.sqlite"), out)
    pack = _json(out)
    for site in pack["sites"].values():
        assert site["kind"] == "detour"
        assert site["required"] is False
        assert "offset" not in site and "size" not in site
        assert "adapter_key" not in site and "aliases" not in site
    assert "policy_unmatched" not in pack
    assert "policy_hashes" not in pack


def test_site_policy_file_applies_kind_required_and_field(tmp_path: Path) -> None:
    out = tmp_path / "pack.json"
    export_hookpack(_policy_store(tmp_path / "c.sqlite"), out, site_policy=FIXTURES / "site_policy.json")
    pack = _json(out)
    run = pack["sites"]["RunScript"]
    assert (run["kind"], run["required"]) == ("call", True)
    assert "offset" not in run
    slot = pack["sites"]["SlotTable"]
    assert (slot["kind"], slot["required"], slot["offset"], slot["size"]) == ("field", True, 16, 4)
    plain = pack["sites"]["Plain"]
    assert (plain["kind"], plain["required"]) == ("detour", False)
    assert pack["policy_unmatched"] == {"sites": ["Ghost"], "adapter_keys": []}
    assert pack["policy_hashes"]["site_policy"] == __import__("hashlib").sha256(
        (FIXTURES / "site_policy.json").read_bytes()
    ).hexdigest()
    assert pack["policy_hashes"]["adapter_map"] is None


def test_site_policy_rejects_invalid_kind(tmp_path: Path) -> None:
    from agentdecompile_recovery.corpus.hookpack_policy import load_site_policy

    p = tmp_path / "policy.json"
    p.write_text('{"sites": {"X": {"kind": "trampoline"}}}', encoding="utf-8")
    with pytest.raises(ValueError, match="kind"):
        load_site_policy(p)


def test_site_policy_rejects_field_on_non_field_kind(tmp_path: Path) -> None:
    from agentdecompile_recovery.corpus.hookpack_policy import load_site_policy

    p = tmp_path / "policy.json"
    p.write_text('{"sites": {"X": {"kind": "call", "field": {"offset": 0, "size": 4}}}}', encoding="utf-8")
    with pytest.raises(ValueError, match="field"):
        load_site_policy(p)


def test_site_policy_rejects_unknown_key_by_name(tmp_path: Path) -> None:
    from agentdecompile_recovery.corpus.hookpack_policy import load_site_policy

    p = tmp_path / "policy.json"
    p.write_text('{"sites": {"X": {"kind": "call", "priority": 3}}}', encoding="utf-8")
    with pytest.raises(ValueError, match="priority"):
        load_site_policy(p)
    p.write_text('{"defaults": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="defaults"):
        load_site_policy(p)


def test_policy_lookup_prefers_suffixed_key_then_base(tmp_path: Path) -> None:
    p = tmp_path / "policy.json"
    p.write_text(
        '{"sites": {"Tick": {"kind": "call"}, "Tick__2": {"kind": "reference", "required": true}}}',
        encoding="utf-8",
    )
    out = tmp_path / "pack.json"
    export_hookpack(_two_logical_store(tmp_path / "c.sqlite", forward=True), out, site_policy=p)
    pack = _json(out)
    assert pack["sites"]["Tick__1"]["kind"] == "call"
    assert pack["sites"]["Tick__2"]["kind"] == "reference"
    assert pack["sites"]["Tick__2"]["required"] is True
    assert pack["policy_unmatched"]["sites"] == []


# --------------------------------------------------------- U1b adapter map


def test_adapter_map_emits_keys_and_sorted_aliases(tmp_path: Path) -> None:
    out = tmp_path / "pack.json"
    export_hookpack(_policy_store(tmp_path / "c.sqlite"), out, adapter_map=FIXTURES / "adapter_map.json")
    pack = _json(out)
    run = pack["sites"]["RunScript"]
    assert run["adapter_key"] == "script.run"
    assert run["aliases"] == ["ExecScript", "RunScript", "run_script"]
    slot = pack["sites"]["SlotTable"]
    assert slot["adapter_key"] == "slot.table"
    assert "aliases" not in slot
    assert "adapter_key" not in pack["sites"]["Plain"]
    assert pack["policy_unmatched"] == {"sites": [], "adapter_keys": ["Phantom"]}
    assert pack["policy_hashes"]["site_policy"] is None
    assert pack["policy_hashes"]["adapter_map"] == __import__("hashlib").sha256(
        (FIXTURES / "adapter_map.json").read_bytes()
    ).hexdigest()


def test_adapter_map_collision_raises_with_both_site_keys(tmp_path: Path) -> None:
    from agentdecompile_recovery.corpus.hookpack_policy import load_adapter_map

    p = tmp_path / "map.json"
    p.write_text('{"keys": {"B": "same.key", "A": "same.key", "C": "other"}}', encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_adapter_map(p)
    msg = str(info.value)
    assert "same.key" in msg and "'A'" in msg and "'B'" in msg and "'C'" not in msg


def test_adapter_map_fallback_collision_raises_at_export(tmp_path: Path) -> None:
    p = tmp_path / "map.json"
    p.write_text('{"keys": {"Tick": "tick.adapter"}}', encoding="utf-8")
    with pytest.raises(ValueError) as info:
        export_hookpack(_two_logical_store(tmp_path / "c.sqlite", forward=True), tmp_path / "pack.json", adapter_map=p)
    msg = str(info.value)
    assert "Tick__1" in msg and "Tick__2" in msg


# ------------------------------------------------------------ determinism


def test_export_with_policy_and_map_is_byte_identical(tmp_path: Path) -> None:
    from functools import partial

    from agentdecompile_recovery.corpus.determinism_basis import verify_export

    db = tmp_path / "c.sqlite"
    con = _policy_store(db)
    con.close()
    export = partial(
        export_hookpack, site_policy=FIXTURES / "site_policy.json", adapter_map=FIXTURES / "adapter_map.json"
    )
    assert verify_export(db, export) == {"identical": True, "diff": ""}


def test_export_with_windows_is_insertion_order_independent(tmp_path: Path, monkeypatch) -> None:
    from agentdecompile_recovery.corpus import export_hookpack as hp

    monkeypatch.setattr(hp, "_raw_image", lambda repo: HAY)
    monkeypatch.setattr(hp, "_file_offset", lambda image, addr, load_base=None: 64)
    hp.export_hookpack(_two_logical_store(tmp_path / "f.sqlite", forward=True), tmp_path / "f.json")
    hp.export_hookpack(_two_logical_store(tmp_path / "r.sqlite", forward=False), tmp_path / "r.json")
    assert (tmp_path / "f.json").read_bytes() == (tmp_path / "r.json").read_bytes()
    site = _json(tmp_path / "f.json")["sites"]["Tick__1"]
    assert [w["binary"] for w in site["instance_windows"]] == ["debug", "debug", "release"]
