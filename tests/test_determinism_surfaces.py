"""Order-independence of the surfaces the determinism audit did not reach (D7).

Each test builds the same input in two different orders and requires the
same output. Fixtures are generic identifiers and plain integers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import block_inline, cross_place, store
from agentdecompile_recovery.corpus import ghidra_bulk as gb
from agentdecompile_recovery.corpus.correspondence import enrich_evidence
from agentdecompile_recovery.corpus.symbol_provenance import authentic_named_index

pytestmark = pytest.mark.unit


# --- symbol_provenance.authentic_named_index --------------------------------


def _named_funcs() -> dict[int, dict]:
    return {
        0x30: {"canon_key": "K", "name": "K", "name_origin": "stabs"},
        0x10: {"canon_key": "K", "name": "K", "name_origin": "stabs"},
        0x20: {"canon_key": "J", "name": "J", "name_origin": "export"},
        0x40: {"canon_key": "L", "name": "L", "name_origin": "matcher_inferred"},
    }


def test_authentic_named_index_is_input_order_independent() -> None:
    forward = _named_funcs()
    backward = dict(reversed(list(forward.items())))
    a = authentic_named_index(forward)
    b = authentic_named_index(backward)
    assert list(a.items()) == list(b.items())
    assert list(a) == ["J", "K"]
    assert a["K"] == [0x10, 0x30]
    assert "L" not in a


# --- correspondence.enrich_evidence ------------------------------------------


def test_enrich_evidence_sorts_dependencies_and_keeps_alternative_rank() -> None:
    deps_a = ["7:3", "7:1", "7:2"]
    deps_b = ["7:2", "7:3", "7:1"]
    ev_a = enrich_evidence({}, kind="callgraph", status="auto", dependencies=deps_a)
    ev_b = enrich_evidence({}, kind="callgraph", status="auto", dependencies=deps_b)
    assert ev_a["dependencies"] == ev_b["dependencies"] == ["7:1", "7:2", "7:3"]
    # ``alternatives`` is a ranked list (best first) supplied by the producer;
    # its order is a value, not an artefact of iteration, and must survive.
    ranked = [{"dst": 9, "score": 0.9}, {"dst": 2, "score": 0.8}]
    ev = enrich_evidence({}, status="ambiguous", alternatives=ranked, identity_claim=False)
    assert ev["alternatives"] == ranked


# --- block_inline.inline_hits ------------------------------------------------


def _fn(fid: int, hashes: list[str]) -> dict:
    return {"id": fid, "addr": fid, "n_instr": len(hashes) * 4, "block_hashes": hashes}


def _inline_case() -> tuple[list[dict], list[dict]]:
    missing = [
        _fn(3, ["b1", "b2"]),
        _fn(1, ["c1"]),
        _fn(2, ["d1", "d2", "d3"]),
    ]
    survivors = [
        _fn(30, ["b1", "b2", "b3", "b4"]),
        _fn(10, ["c1", "c2"]),
        _fn(11, ["c1", "c9"]),
        _fn(20, ["d1", "d2", "z1", "z2"]),
        _fn(21, ["d3", "z3", "z4", "z5"]),
    ]
    return missing, survivors


def test_inline_hits_is_input_order_independent() -> None:
    missing, survivors = _inline_case()
    forward = block_inline.inline_hits(missing, survivors)
    backward = block_inline.inline_hits(list(reversed(missing)), list(reversed(survivors)))
    assert forward == backward
    # Emission contract: total order on str(missing id), then host id, kind.
    ids = [h["missing_id"] for h in forward]
    assert ids == sorted(ids, key=str)
    assert {h["kind"] for h in forward} == {"inline", "clone", "split"}


# --- ghidra_bulk compile queue + receipt -------------------------------------


_FK_SCHEMA = """
CREATE TABLE func_knowledge (
    program TEXT NOT NULL,
    entry_hex TEXT NOT NULL,
    name TEXT,
    size INTEGER,
    decompiled TEXT{pk}
);
"""


def _tied_queue_rows() -> list[tuple[str, str, str, int, str]]:
    # Same decompiled length and size: the ORDER BY tie is the whole point.
    return [
        ("p", "00000030", "f3", 8, "int f(){}"),
        ("p", "00000010", "f1", 8, "int g(){}"),
        ("p", "00000020", "f2", 8, "int h(){}"),
        ("p", "00000040", "f4", 4, "int i(){}"),
    ]


def _write_kb(path: Path, rows, *, indexed: bool) -> None:
    con = sqlite3.connect(path)
    con.executescript(_FK_SCHEMA.format(pk=",\n    PRIMARY KEY (program, entry_hex)" if indexed else ""))
    con.executemany("INSERT INTO func_knowledge VALUES (?,?,?,?,?)", rows)
    con.commit()
    con.close()


# The real table carries PRIMARY KEY (program, entry_hex); a SEARCH on that
# index happens to visit ties in entry_hex order. A SCAN (no usable index, or
# a different plan after ANALYZE) visits them in insert order. Both plans
# must produce the same queue.
@pytest.mark.parametrize("indexed", [True, False])
def test_compile_queue_order_is_insert_and_plan_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, indexed: bool) -> None:
    rows = _tied_queue_rows()
    kb_a = tmp_path / "a.sqlite"
    kb_b = tmp_path / "b.sqlite"
    _write_kb(kb_a, rows, indexed=indexed)
    _write_kb(kb_b, list(reversed(rows)), indexed=indexed)
    monkeypatch.setattr(gb, "KB", kb_a)
    order_a = [r["entry_hex"] for r in gb.load_functions("p", None)]
    monkeypatch.setattr(gb, "KB", kb_b)
    order_b = [r["entry_hex"] for r in gb.load_functions("p", None)]
    assert order_a == order_b
    # Shortest-first stays the primary order; ties break on entry_hex.
    assert order_a == ["00000040", "00000010", "00000020", "00000030"]
    monkeypatch.setattr(gb, "KB", kb_a)
    sample_a = [r["entry_hex"] for r in gb.load_functions("p", 2)]
    monkeypatch.setattr(gb, "KB", kb_b)
    sample_b = [r["entry_hex"] for r in gb.load_functions("p", 2)]
    assert sample_a == sample_b == ["00000040", "00000010"]


def test_compile_receipt_ok_list_is_sorted(tmp_path: Path) -> None:
    dest = gb.write_compile_receipt(tmp_path, "p", ["00000030", "00000010", "00000020"])
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["ok"] == ["00000010", "00000020", "00000030"]


# --- cross_place glob order ----------------------------------------------------


def test_place_tree_glob_order_is_directory_order_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    out_root = tmp_path / "out"
    # Two source files claim the same address; the lexicographically first
    # one must win regardless of how the directory enumerates them.
    (src_dir / "a.c").write_text("/*\n * address: 0x00001000\n */\nint a(void) { return 1; }\n")
    (src_dir / "b.c").write_text("/*\n * address: 0x00001000\n */\nint b(void) { return 2; }\n")
    index = {0x1000: [(2, 0x2000, "dst_prog", "fn")]}
    monkeypatch.setattr(cross_place, "load_index", lambda _con, _bid: index)
    real_glob = Path.glob

    def reversed_glob(self, pattern):
        return iter(sorted(real_glob(self, pattern), reverse=True))

    monkeypatch.setattr(Path, "glob", reversed_glob)
    summary = cross_place.place_tree(src_dir, 1, out_root, con=None)
    assert summary["placed"] == 1
    assert "int a(void)" in (out_root / "dst_prog" / "fn_00002000.c").read_text()


# --- store.ensure_binary_columns ----------------------------------------------


def _binary_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(store.SCHEMA)
    con.execute("ALTER TABLE binary ADD COLUMN content_sha256 TEXT")
    con.executemany(
        "INSERT INTO binary (id, repo_path, slug, recovery_family) VALUES (?,?,?,?)",
        [(3, "r3", "s3", None), (1, "r1", "s1", ""), (2, "r2", "s2", "fam")],
    )
    con.commit()
    con.close()


def test_ensure_binary_columns_backfill_is_a_function_of_id(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    _binary_db(db)
    con = sqlite3.connect(db)
    store.ensure_binary_columns(con)
    con.commit()
    rows = con.execute("SELECT id, recovery_family FROM binary ORDER BY id").fetchall()
    con.close()
    assert rows == [(1, "unclassified:1"), (2, "fam"), (3, "unclassified:3")]


def test_ensure_binary_columns_tolerates_readonly_but_not_other_errors(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    _binary_db(db)
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    store.ensure_binary_columns(ro)  # read-only consumer must proceed
    assert ro.execute("SELECT recovery_family FROM binary WHERE id=3").fetchone() == (None,)
    ro.close()

    class _Con:
        def execute(self, sql, *args):
            if sql.startswith("PRAGMA"):
                return iter([(0, "content_sha256"), (1, "recovery_family")])
            if sql.startswith("SELECT"):
                class _Cur:
                    def fetchone(self):
                        return (1,)
                return _Cur()
            raise sqlite3.OperationalError("no such table: binary")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        store.ensure_binary_columns(_Con())
