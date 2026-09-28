"""Integration: unique hash anchors and identical-image short-circuit via match_store."""

import sqlite3

from agentdecompile_recovery.corpus.fingerprint_hashes import attach_hashes
from agentdecompile_recovery.corpus.match_store import match_binaries
from agentdecompile_recovery.corpus.store import SCHEMA, ensure_func_columns


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    ensure_func_columns(con)
    return con


def _insert_binary(con, slug, *, content_sha256=None, md5=None):
    con.execute(
        "INSERT INTO binary(repo_path, slug, arch, bits, format, game, md5, content_sha256) VALUES (?,?,?,?,?,?,?,?)",
        (f"/tmp/{slug}", slug, "x86", 32, "PE", "g", md5, content_sha256),
    )
    return con.execute("SELECT id FROM binary WHERE slug=?", (slug,)).fetchone()[0]


def _insert_func(con, binary_id, addr, **fields):
    row = {
        "name": fields.get("name"),
        "canon_key": fields.get("canon_key"),
        "name_origin": fields.get("name_origin", "stabs"),
        "size": fields.get("size", 40),
        "is_thunk": 0,
        "n_instr": fields.get("n_instr", 20),
        "n_blocks": 3,
        "n_edges": 2,
        "back_edges": 0,
        "cyclomatic": 2,
        "n_callees": 0,
        "indirect_calls": 0,
        "data_refs": 0,
        "mnem": fields.get("mnem", {"MOV": 5, "RET": 1}),
        "strings": fields.get("strings", []),
        "consts": fields.get("consts", [7]),
        "ext_calls": [],
        "block_hashes": fields.get("block_hashes", ["deadbeef"]),
        "source": "IMPORTED",
        "param_count": 0,
    }
    row = attach_hashes(row)
    import json

    con.execute(
        """INSERT INTO func(
             binary_id, addr, name, canon_key, name_origin, size, is_thunk, n_instr,
             n_blocks, n_edges, back_edges, cyclomatic, n_callees, indirect_calls, data_refs,
             mnem, strings, consts, ext_calls, block_hashes,
             hash_reloc, hash_instr, hash_mnemonic, hash_raw, source, param_count
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            binary_id,
            addr,
            row["name"],
            row["canon_key"],
            row["name_origin"],
            row["size"],
            row["is_thunk"],
            row["n_instr"],
            row["n_blocks"],
            row["n_edges"],
            row["back_edges"],
            row["cyclomatic"],
            row["n_callees"],
            row["indirect_calls"],
            row["data_refs"],
            json.dumps(row["mnem"]),
            json.dumps(row["strings"]),
            json.dumps(row["consts"]),
            json.dumps(row["ext_calls"]),
            json.dumps(row["block_hashes"]),
            row["hash_reloc"],
            row["hash_instr"],
            row["hash_mnemonic"],
            row["hash_raw"],
            row["source"],
            row["param_count"],
        ),
    )


def test_identical_image_short_circuits():
    con = _db()
    digest = "a" * 64
    a = _insert_binary(con, "a", content_sha256=digest)
    b = _insert_binary(con, "b", content_sha256=digest)
    _insert_func(con, a, 0x1000, name="F", canon_key="F")
    _insert_func(con, b, 0x1000, name="F", canon_key="F")
    con.commit()
    res = match_binaries(con, a, b)
    assert res.get("short_circuit") == "identical_image"
    assert res["mapping"][0x1000] == 0x1000


def test_unique_hash_reloc_anchors():
    con = _db()
    a = _insert_binary(con, "a")
    b = _insert_binary(con, "b")
    _insert_func(con, a, 0x1000, name="X", canon_key=None, name_origin="matcher_inferred", consts=[99], mnem={"ADD": 4})
    _insert_func(con, b, 0x2000, name="Y", canon_key=None, name_origin="matcher_inferred", consts=[99], mnem={"ADD": 4})
    # distractor with different body
    _insert_func(con, a, 0x1100, name="Z", canon_key=None, consts=[1], mnem={"SUB": 2}, n_instr=10)
    _insert_func(con, b, 0x2100, name="W", canon_key=None, consts=[2], mnem={"XOR": 2}, n_instr=10)
    con.commit()
    res = match_binaries(con, a, b)
    assert res["mapping"].get(0x1000) == 0x2000


def test_matcher_inferred_symbol_does_not_seed():
    con = _db()
    a = _insert_binary(con, "a")
    b = _insert_binary(con, "b")
    _insert_func(
        con,
        a,
        0x1000,
        name="Same",
        canon_key="Same",
        name_origin="matcher_inferred",
        consts=[1],
        mnem={"NOP": 4},
        block_hashes=["aaaa"],
    )
    _insert_func(
        con,
        b,
        0x2000,
        name="Same",
        canon_key="Same",
        name_origin="matcher_inferred",
        consts=[2],
        mnem={"ADD": 4},
        block_hashes=["bbbb"],
    )
    con.commit()
    res = match_binaries(con, a, b)
    assert 0x1000 not in res["mapping"]
