"""Ordering determinism for identity binding and call-graph propagation.

Ties are the common case: every propagated pair carries PROPAGATION_SCORE, so
the first-wins race in ``bind_identities`` must resolve on a total key, not on
SQLite scan order. The chosen key is dst-major (a recorded design decision):
``(-conf, dst_binary, dst_addr, logical_id, src_binary, src_addr)``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import store
from agentdecompile_recovery.corpus.callgraph_propagate import propagate_call_graph, unique_neighbor_matches
from agentdecompile_recovery.corpus.propagate import bind_identities

pytestmark = pytest.mark.unit

RUN = "v1"
SRC, DST = 1, 2

# Two sources in distinct logical functions both claim dst 0x100 at equal confidence.
SAME_DST_TIE = [
    (SRC, 0x10, DST, 0x100),
    (SRC, 0x20, DST, 0x100),
]
# One logical function seeded on two src addrs claims two different dst addrs.
SAME_LOGICAL_TIE = [
    (SRC, 0x30, DST, 0x200),
    (SRC, 0x40, DST, 0x300),
]


def _build(path: Path, matches: list[tuple[int, int, int, int]], identities: list[tuple[int, int, int]]):
    con = store.connect(path)
    con.executescript(
        """
        INSERT INTO binary(id, repo_path, slug) VALUES (1,'src/a','a'),(2,'dst/b','b');
        INSERT INTO logical_function(id, best_name) VALUES (1,'fn1'),(2,'fn2'),(3,'fn3');
        """
    )
    con.executemany(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (?,?,?,0.9,'seed')",
        identities,
    )
    for src_binary, src_addr, dst_binary, dst_addr in matches:
        con.execute("INSERT OR IGNORE INTO func(binary_id, addr, name) VALUES (?,?,?)", (src_binary, src_addr, f"s{src_addr:x}"))
        con.execute("INSERT OR IGNORE INTO func(binary_id, addr, name) VALUES (?,?,?)", (dst_binary, dst_addr, f"d{dst_addr:x}"))
        con.execute(
            "INSERT INTO match(run, src_binary, src_addr, dst_binary, dst_addr, score, margin, evidence, status)"
            " VALUES (?,?,?,?,?,1.0,1.0,'{}','auto')",
            (RUN, src_binary, src_addr, dst_binary, dst_addr),
        )
    con.commit()
    return con


def _snapshot(con) -> tuple[list[tuple], list[tuple]]:
    identity = [
        tuple(r) for r in con.execute(
            "SELECT logical_id, binary_id, addr, confidence, method FROM identity ORDER BY binary_id, addr"
        )
    ]
    demoted = [
        tuple(r) for r in con.execute(
            "SELECT src_binary, src_addr, dst_binary, dst_addr, status, evidence FROM match"
            " WHERE run=? AND status='review' ORDER BY src_binary, src_addr, dst_binary, dst_addr",
            (RUN,),
        )
    ]
    return identity, demoted


def _bind_with_order(tmp_path: Path, name: str, matches, identities):
    con = _build(tmp_path / f"{name}.sqlite", matches, identities)
    bind_identities(con, RUN)
    snap = _snapshot(con)
    con.close()
    return snap


def test_same_dst_tie_is_insert_order_invariant(tmp_path: Path) -> None:
    identities = [(1, SRC, 0x10), (2, SRC, 0x20)]
    forward = _bind_with_order(tmp_path, "fwd", SAME_DST_TIE, identities)
    reverse = _bind_with_order(tmp_path, "rev", list(reversed(SAME_DST_TIE)), list(reversed(identities)))
    assert forward == reverse


def test_same_dst_tie_picks_lowest_logical_id(tmp_path: Path) -> None:
    """Dst-major key: for one destination, the tie breaks on logical_id, then source."""
    identities = [(1, SRC, 0x10), (2, SRC, 0x20)]
    for name, order in (("fwd", SAME_DST_TIE), ("rev", list(reversed(SAME_DST_TIE)))):
        identity, demoted = _bind_with_order(tmp_path, name, order, identities)
        bound = [row for row in identity if row[1] == DST]
        assert bound == [(1, DST, 0x100, 1.0, f"match:{RUN}:auto")], name
        assert [(r[0], r[1], r[3]) for r in demoted] == [(SRC, 0x20, 0x100)], name
        assert json.loads(demoted[0][5])["reason"] == "logical_id_binary_conflict"


def test_same_logical_tie_is_insert_order_invariant(tmp_path: Path) -> None:
    identities = [(3, SRC, 0x30), (3, SRC, 0x40)]
    forward = _bind_with_order(tmp_path, "fwd", SAME_LOGICAL_TIE, identities)
    reverse = _bind_with_order(tmp_path, "rev", list(reversed(SAME_LOGICAL_TIE)), list(reversed(identities)))
    assert forward == reverse


def test_same_logical_tie_picks_lowest_dst_addr(tmp_path: Path) -> None:
    identities = [(3, SRC, 0x30), (3, SRC, 0x40)]
    for name, order in (("fwd", SAME_LOGICAL_TIE), ("rev", list(reversed(SAME_LOGICAL_TIE)))):
        identity, demoted = _bind_with_order(tmp_path, name, order, identities)
        bound = [row for row in identity if row[1] == DST]
        assert bound == [(3, DST, 0x200, 1.0, f"match:{RUN}:auto")], name
        assert [(r[1], r[3]) for r in demoted] == [(0x40, 0x300)], name
        assert json.loads(demoted[0][5])["conflicting_addr"] == 0x200


def test_logical_members_conflicting_addr_is_seed_order_invariant(tmp_path: Path) -> None:
    """A logical function already holding two addrs in the dst binary reports one stable conflicting_addr."""
    matches = [(SRC, 0x50, DST, 0x400)]
    seeds = [(3, SRC, 0x50), (3, DST, 0x410), (3, DST, 0x420)]
    forward = _bind_with_order(tmp_path, "fwd", matches, seeds)
    reverse = _bind_with_order(tmp_path, "rev", matches, list(reversed(seeds)))
    assert forward == reverse
    _identity, demoted = forward
    assert json.loads(demoted[0][5])["conflicting_addr"] == 0x420


def _two_parent_graph():
    # Anchors A->B and C->D. X is the unique pending callee of both A and C; Y likewise.
    src_callees = {"A": {"X"}, "C": {"X"}}
    dst_callees = {"B": {"Y"}, "D": {"Y"}}
    return src_callees, {}, dst_callees, {}


def test_dependencies_are_sorted_regardless_of_mapping_order() -> None:
    src_callees, src_callers, dst_callees, dst_callers = _two_parent_graph()
    eligible = {"A", "C", "X"}, {"B", "D", "Y"}
    seen = []
    for mapping in ({"A": "B", "C": "D"}, {"C": "D", "A": "B"}):
        added = propagate_call_graph(
            src_callees, src_callers, dst_callees, dst_callers, dict(mapping),
            src_eligible=eligible[0], dst_eligible=eligible[1], with_dependencies=True,
        )
        assert added[0][:3] == ("X", "Y", "callee")
        seen.append(added[0][3])
    assert seen[0] == seen[1] == ["A", "C"]


def test_propagation_kind_is_mapping_order_invariant() -> None:
    """The same pair proposed as callee by one anchor and caller by another keeps one kind."""
    src_callees = {"A": {"X"}}
    src_callers = {"C": {"X"}}
    dst_callees = {"B": {"Y"}}
    dst_callers = {"D": {"Y"}}
    kinds = []
    for mapping in ({"A": "B", "C": "D"}, {"C": "D", "A": "B"}):
        pairs = unique_neighbor_matches(
            src_callees, src_callers, dst_callees, dst_callers, mapping,
            src_eligible={"A", "C", "X"}, dst_eligible={"B", "D", "Y"},
        )
        assert [p[:2] for p in pairs] == [("X", "Y")]
        kinds.append(pairs[0][2])
    assert kinds[0] == kinds[1] == "callee"
