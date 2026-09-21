"""Determinism of the store-backed matcher and the feature cosine (Phase 0 D4/D5).

Rules under test: no set/dict iteration order reaches a persisted or compared
value; every first-wins pick has a total key ending in addresses; persisted
floats are rounded to a fixed precision.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys

from agentdecompile_recovery.corpus import propagate
from agentdecompile_recovery.corpus.fingerprint_hashes import attach_hashes
from agentdecompile_recovery.corpus.match_engine import cosine, score_features
from agentdecompile_recovery.corpus.match_store import match_binaries
from agentdecompile_recovery.corpus.store import connect

SRC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src"


# --- D5: cosine() -----------------------------------------------------------


def _vector_pairs(n: int = 64) -> list[tuple[str, float]]:
    return [(f"op{i:02d}", 1.0 / (i + 3)) for i in range(n)]


def _other_vector(pairs: list[tuple[str, float]]) -> dict[str, float]:
    return {k: math.pi * (i + 1) / 10 for i, (k, _) in enumerate(pairs)}


def test_cosine_is_insertion_order_invariant():
    pairs = _vector_pairs()
    forward = dict(pairs)
    backward = dict(reversed(pairs))
    other = _other_vector(pairs)
    assert repr(cosine(forward, other)) == repr(cosine(backward, other))
    assert repr(cosine(other, forward)) == repr(cosine(other, backward))


_SUBPROCESS_SNIPPET = """
import math
from agentdecompile_recovery.corpus.match_engine import cosine
pairs = [(f"op{i:02d}", 1.0 / (i + 3)) for i in range(64)]
a = dict(pairs)
b = {k: math.pi * (i + 1) / 10 for i, (k, _) in enumerate(pairs)}
print(repr(cosine(a, b)))
"""


def _cosine_in_subprocess(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(SRC_DIR)}
    out = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SNIPPET],
        env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_cosine_is_hash_seed_invariant_across_processes():
    assert _cosine_in_subprocess("1") == _cosine_in_subprocess("2")


class _AccessLog(dict):
    """dict whose key lookups are recorded, to observe iteration order."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen: list = []

    def get(self, key, default=None):
        self.seen.append(key)
        return super().get(key, default)


def test_cosine_visits_keys_in_sorted_order():
    pairs = _vector_pairs()
    a = _AccessLog(reversed(pairs))
    b = _AccessLog(_other_vector(pairs))
    cosine(a, b)
    assert a.seen == sorted(a.seen)
    assert b.seen == sorted(b.seen)


# --- D4: match_store greedy cascade -----------------------------------------


def _insert_binary(con, slug: str) -> int:
    con.execute(
        "INSERT INTO binary(repo_path, slug, arch, bits, format, game) VALUES (?,?,?,?,?,?)",
        (f"/fixture/{slug}", slug, "x86", 32, "PE", "g"),
    )
    return int(con.execute("SELECT id FROM binary WHERE slug=?", (slug,)).fetchone()[0])


def _insert_func(con, binary_id: int, addr: int, **fields) -> None:
    row = {
        "name": fields.get("name", f"sub_{addr:x}"),
        "canon_key": None,
        "name_origin": "matcher_inferred",
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
    con.execute(
        """INSERT INTO func(
             binary_id, addr, name, canon_key, name_origin, size, is_thunk, n_instr,
             n_blocks, n_edges, back_edges, cyclomatic, n_callees, indirect_calls, data_refs,
             mnem, strings, consts, ext_calls, block_hashes,
             hash_reloc, hash_instr, hash_mnemonic, hash_raw, source, param_count
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            binary_id, addr, row["name"], row["canon_key"], row["name_origin"], row["size"],
            row["is_thunk"], row["n_instr"], row["n_blocks"], row["n_edges"], row["back_edges"],
            row["cyclomatic"], row["n_callees"], row["indirect_calls"], row["data_refs"],
            json.dumps(row["mnem"]), json.dumps(row["strings"]), json.dumps(row["consts"]),
            json.dumps(row["ext_calls"]), json.dumps(row["block_hashes"]),
            row["hash_reloc"], row["hash_instr"], row["hash_mnemonic"], row["hash_raw"],
            row["source"], row["param_count"],
        ),
    )


TIE_SOURCES = (0x1000, 0x2000)
TIE_DEST = 0x3000
SRC_FEATURES = {"consts": [0x1234, 0x5678], "mnem": {"MOV": 5, "ADD": 3, "RET": 1}, "strings": ["fmt"]}
# Near-match, not identical: the pair scores below 1.0 with an unrounded float,
# and the shared string/const keys are not unique so no anchor stage claims it.
DST_FEATURES = {
    "consts": [0x1234, 0x5678], "strings": ["fmt"], "mnem": {"MOV": 6, "ADD": 2, "RET": 1, "SUB": 2},
    "n_instr": 23, "size": 46, "block_hashes": ["feedface"],
}


def _tie_fixture(tmp_path: pathlib.Path, name: str, src_order: tuple[int, ...]):
    """Two identical source functions tie exactly for one destination.

    Planner statistics are set so every ``func`` index looks non-selective and
    an unordered ``SELECT ... WHERE binary_id=?`` becomes a rowid scan (insert
    order).  With fresh statistics the planner happens to walk the
    ``(binary_id, addr)`` index and hides insert-order dependence; the matcher
    must not depend on that plan (``ANALYZE`` legitimately changes it).
    """
    con = connect(tmp_path / f"{name}.db")
    src = _insert_binary(con, "src")
    dst = _insert_binary(con, "dst")
    for addr in src_order:
        _insert_func(con, src, addr, **SRC_FEATURES)
    _insert_func(con, dst, TIE_DEST, **DST_FEATURES)
    con.commit()
    con.execute("ANALYZE")
    con.execute("UPDATE sqlite_stat1 SET stat=? WHERE tbl='func'", (" ".join(["1000000"] * 6),))
    con.execute("ANALYZE sqlite_schema")
    con.commit()
    plan = " ".join(str(row[3]) for row in con.execute("EXPLAIN QUERY PLAN SELECT addr, name, mnem FROM func WHERE binary_id=?", (src,)))
    assert plan.startswith("SCAN func"), plan
    return con, src, dst


def _persisted_rows(con) -> list[tuple]:
    return sorted(
        tuple(row) for row in con.execute(
            "SELECT src_addr, dst_addr, score, margin, status, relation FROM match"
        )
    )


def _run(tmp_path, name, src_order):
    con, src, dst = _tie_fixture(tmp_path, name, src_order)
    res = match_binaries(con, src, dst)
    propagate.run_pair(con, "/fixture/src", "/fixture/dst", note="t", run="r")
    winners = sorted(res["mapping"].items())
    return winners, _persisted_rows(con), res


def test_tied_sources_resolve_identically_regardless_of_insert_order(tmp_path):
    winners_a, rows_a, res_a = _run(tmp_path, "a", TIE_SOURCES)
    winners_b, rows_b, _ = _run(tmp_path, "b", tuple(reversed(TIE_SOURCES)))
    # The fixture is a genuine tie: both sources score identically for the destination.
    sa, sb = res_a["src"], res_a["dst"]
    scores = {addr: score_features(sa.funcs[addr], sb.funcs[TIE_DEST], same_arch=True)[0] for addr in TIE_SOURCES}
    assert len(set(scores.values())) == 1, scores
    assert winners_a == [(min(TIE_SOURCES), TIE_DEST)]
    assert winners_a == winners_b
    assert rows_a == rows_b


def test_persisted_scores_are_rounded_to_four_places(tmp_path):
    _, rows, res = _run(tmp_path, "r", TIE_SOURCES)
    assert rows and all(0.0 < row[2] < 1.0 for row in rows), rows
    for src_addr, dst_addr, score, margin, *_ in rows:
        assert score == round(score, 4), (src_addr, score)
        assert margin == round(margin, 4), (src_addr, margin)
    for result in res["results"].values():
        assert result["score"] == round(result["score"], 4)
        assert result["margin"] == round(result["margin"], 4)
