"""Order-independence of the surfaces the determinism audit did not reach (D7).

Each test builds the same input in two different orders and requires the
same output. Fixtures are generic identifiers and plain integers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import block_inline, cross_place, propagate, store
from agentdecompile_recovery.corpus import ghidra_bulk as gb
from agentdecompile_recovery.corpus.correspondence import enrich_evidence
from agentdecompile_recovery.corpus.logical import ContentHashError
from agentdecompile_recovery.corpus.match_store import dependency_token, quarantined_source_tokens
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


# --- store.backfill_recovery_family (D9) --------------------------------------

# Synthetic image hashes; the family is 'unclassified:' + the first 16 hex.
HA = "a1" * 32
HC = "c3" * 32


def _binary_db(path: Path, rows=None) -> None:
    con = sqlite3.connect(path)
    con.executescript(store.SCHEMA)
    con.execute("ALTER TABLE binary ADD COLUMN content_sha256 TEXT")
    con.executemany(
        "INSERT INTO binary (id, repo_path, slug, recovery_family, content_sha256) VALUES (?,?,?,?,?)",
        rows if rows is not None else [(3, "r3", "s3", None, HC), (1, "r1", "s1", "", HA), (2, "r2", "s2", "fam", None)],
    )
    con.commit()
    con.close()


def _families(db: Path) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT id, recovery_family FROM binary ORDER BY id").fetchall()
    finally:
        con.close()


def test_recovery_family_backfill_is_a_function_of_content_hash(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    _binary_db(db)
    con = sqlite3.connect(db)
    store.ensure_binary_columns(con)
    con.commit()
    con.close()
    assert _families(db) == [(1, f"unclassified:{HA[:16]}"), (2, "fam"), (3, f"unclassified:{HC[:16]}")]


def test_recovery_family_backfill_is_insert_order_invariant(tmp_path: Path) -> None:
    """Same builds, opposite rowids: each build's family is the same string."""
    rows_a = [(1, "ra", "sa", None, HA), (2, "rc", "sc", None, HC)]
    rows_b = [(2, "ra", "sa", None, HA), (1, "rc", "sc", None, HC)]
    out = {}
    for name, rows in (("a", rows_a), ("b", rows_b)):
        db = tmp_path / f"{name}.sqlite"
        _binary_db(db, rows)
        con = sqlite3.connect(db)
        store.backfill_recovery_family(con)
        con.commit()
        out[name] = dict(con.execute("SELECT slug, recovery_family FROM binary").fetchall())
        con.close()
    assert out["a"] == out["b"] == {"sa": f"unclassified:{HA[:16]}", "sc": f"unclassified:{HC[:16]}"}


def test_recovery_family_rowid_form_is_rewritten_to_the_hash_form(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    _binary_db(db, [(1, "r1", "s1", "unclassified:1", HA), (2, "r2", "s2", "unclassified:7", HC), (3, "r3", "s3", "unclassified:custom", HC)])
    con = sqlite3.connect(db)
    assert store.backfill_recovery_family(con) == 0
    con.commit()
    con.close()
    # Only the exact rowid form ('unclassified:' || id) is a placeholder; other
    # values are user data and stay.
    assert _families(db) == [(1, f"unclassified:{HA[:16]}"), (2, "unclassified:7"), (3, "unclassified:custom")]


def test_recovery_family_without_content_hash_stays_null_and_is_counted(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    _binary_db(db, [(1, "r1", "s1", None, None), (2, "r2", "s2", "", "  "), (3, "r3", "s3", None, HC)])
    con = sqlite3.connect(db)
    assert store.backfill_recovery_family(con) == 2
    con.commit()
    # Idempotent: the count is the same on the next connect and nothing else moves.
    assert store.backfill_recovery_family(con) == 2
    con.commit()
    con.close()
    assert _families(db) == [(1, None), (2, ""), (3, f"unclassified:{HC[:16]}")]


def test_ensure_binary_columns_tolerates_readonly_but_not_other_errors(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    _binary_db(db)
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    store.ensure_binary_columns(ro)  # read-only consumer must proceed
    assert ro.execute("SELECT recovery_family FROM binary WHERE id=3").fetchone() == (None,)  # row 3 has a hash; the write was refused, not the read
    ro.close()

    class _Con:
        # The backfill owns its write and asks whether a transaction is open;
        # none is, so it will BEGIN itself and hit the synthetic error there.
        in_transaction = False

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


# --- match_store dependency tokens (A3) ---------------------------------------


def test_dependency_token_is_the_hash_prefix_and_addr() -> None:
    assert dependency_token(HA, 0x1000) == f"{HA[:16]}:4096"
    assert dependency_token(f"  {HA}  ", 7) == f"{HA[:16]}:7"


def test_dependency_token_refuses_a_hashless_build_by_hashed_name() -> None:
    for blank in (None, "", "   "):
        with pytest.raises(ContentHashError) as info:
            dependency_token(blank, 1, slug="s1")
        assert info.value.kind == "missing"
        assert info.value.slugs == ["s1"]


def _match_store(path: Path, *, src_hash: str | None) -> sqlite3.Connection:
    con = store.connect(path)
    con.execute(
        "INSERT INTO binary(id, repo_path, slug, content_sha256) VALUES (1, '/s', 'src', ?), (2, '/d', 'dst', ?)",
        (src_hash, HC),
    )
    con.execute("INSERT INTO logical_function(id, best_name) VALUES (1, 'parent'), (2, 'child')")
    con.execute("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (1, 1, 16, 0.9, 'seed'), (2, 1, 32, 0.9, 'seed')")
    con.executemany(
        "INSERT INTO func(binary_id, addr, name) VALUES (?,?,?)",
        [(1, 16, "p"), (1, 32, "c"), (2, 256, "P"), (2, 512, "C")],
    )
    quarantined = json.dumps(enrich_evidence({}, kind="anchor", status="ambiguous", identity_claim=False, quarantine=True))
    dependent = json.dumps(enrich_evidence({}, kind="callgraph", status="auto", dependencies=[dependency_token(src_hash or HA, 16)]))
    con.executemany(
        "INSERT INTO match(run, src_binary, src_addr, dst_binary, dst_addr, score, margin, evidence, status)"
        " VALUES ('r', 1, ?, 2, ?, 1.0, 1.0, ?, ?)",
        [(16, 256, quarantined, "review"), (32, 512, dependent, "auto")],
    )
    con.commit()
    return con


def test_quarantined_source_tokens_use_the_producer_token(tmp_path: Path) -> None:
    con = _match_store(tmp_path / "q.sqlite", src_hash=HA)
    assert quarantined_source_tokens(con, "r") == {f"{HA[:16]}:16"}
    assert quarantined_source_tokens(con, "other") == set()


def test_quarantined_source_tokens_refuse_a_hashless_source(tmp_path: Path) -> None:
    con = _match_store(tmp_path / "q.sqlite", src_hash=None)
    with pytest.raises(ContentHashError) as info:
        quarantined_source_tokens(con, "r")
    assert info.value.slugs == ["src"]


def test_bind_identities_sees_a_quarantined_parent_through_the_hash_token(tmp_path: Path) -> None:
    """The consumer intersects the same token the producer persisted; a rowid token on either side would bind the child."""
    con = _match_store(tmp_path / "b.sqlite", src_hash=HA)
    assert propagate.bind_identities(con, "r") == 0
    assert con.execute("SELECT COUNT(*) FROM identity WHERE binary_id=2").fetchone()[0] == 0
    # Lift the quarantine and the same child binds.
    con.execute("UPDATE match SET evidence='{}', status='auto' WHERE src_addr=16")
    con.commit()
    assert propagate.bind_identities(con, "r") == 2
