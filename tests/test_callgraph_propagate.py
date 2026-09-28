from agentdecompile_recovery.corpus.callgraph_propagate import (
    absorb_anchors,
    propagate_call_graph,
    record_pairs,
    unique_index_anchors,
    unique_neighbor_matches,
)
from agentdecompile_recovery.corpus.match_engine import candidate_margin, match_binaries
from agentdecompile_recovery.corpus.match_islands import unique_structural_pairs
from agentdecompile_recovery.corpus.propagate import persist_status


def _fn(fid, *, strings=(), callees=(), callers=(), n_instr=20, n_blocks=4, cyclomatic=2, canon_key=None, mnem=None, name_origin=None):
    row = {
        "id": fid,
        "addr": fid,
        "name": fid,
        "strings": list(strings),
        "callee_addrs": list(callees),
        "caller_addrs": list(callers),
        "n_instr": n_instr,
        "n_blocks": n_blocks,
        "cyclomatic": cyclomatic,
        "n_callees": len(callees),
        "canon_key": canon_key,
    }
    if canon_key and name_origin is None:
        name_origin = "stabs"
    if name_origin is not None:
        row["name_origin"] = name_origin
    if mnem is not None:
        row["mnem"] = mnem
    return row


META = {"arch": "x86", "bits": 32, "format": "PE", "game": "g"}


def test_unique_callee_of_an_anchor_is_a_match():
    mapping = {"A": "B"}
    pairs = unique_neighbor_matches(
        {"A": {"X"}},
        {},
        {"B": {"Y"}},
        {},
        mapping,
        src_eligible={"A", "X"},
        dst_eligible={"B", "Y"},
    )
    assert pairs == [("X", "Y", "callee")]


def test_two_unmatched_callees_are_not_guessed():
    pairs = unique_neighbor_matches(
        {"A": {"X", "Z"}},
        {},
        {"B": {"Y", "W"}},
        {},
        {"A": "B"},
        src_eligible={"A", "X", "Z"},
        dst_eligible={"B", "Y", "W"},
    )
    assert pairs == []


def test_conflicting_proposals_are_dropped():
    mapping = {"A": "B", "C": "D"}
    pairs = unique_neighbor_matches(
        {"A": {"X"}, "C": {"X"}},
        {},
        {"B": {"Y"}, "D": {"Z"}},
        {},
        mapping,
        src_eligible={"A", "C", "X"},
        dst_eligible={"B", "D", "Y", "Z"},
    )
    assert pairs == []


def test_propagation_walks_a_call_chain():
    mapping = {"A": "B"}
    added = propagate_call_graph(
        {"A": {"X"}, "X": {"P"}},
        {},
        {"B": {"Y"}, "Y": {"Q"}},
        {},
        mapping,
        src_eligible={"A", "X", "P"},
        dst_eligible={"B", "Y", "Q"},
    )
    assert mapping == {"A": "B", "X": "Y", "P": "Q"}
    assert [pair[:2] for pair in added] == [("X", "Y"), ("P", "Q")]


def test_unique_string_then_callee_propagation():
    left = [
        _fn("A", strings=["Failed to allocate heap"], callees=["X"]),
        _fn("X"),
    ]
    right = [
        _fn("B", strings=["Failed to allocate heap"], callees=["Y"]),
        _fn("Y"),
    ]
    hits = match_binaries(left, right, left_meta=META, right_meta=META)
    by_left = {row["left_id"]: row for row in hits}
    assert by_left["A"]["status"] == "auto"
    assert by_left["X"]["right_id"] == "Y"
    assert by_left["X"]["kind"] == "callgraph"
    assert by_left["X"]["signals"]["propagation_kind"] == "callee"


def test_unique_symbol_then_caller_propagation():
    left = [
        _fn("Inner", canon_key="Game::SaveSlot", callers=["Outer"]),
        _fn("Outer"),
    ]
    right = [
        _fn("Inner2", canon_key="Game::SaveSlot", callers=["Outer2"]),
        _fn("Outer2"),
    ]
    hits = match_binaries(left, right, left_meta=META, right_meta=META)
    by_left = {row["left_id"]: row for row in hits}
    assert by_left["Inner"]["kind"] == "anchor"
    assert by_left["Outer"]["right_id"] == "Outer2"
    assert by_left["Outer"]["signals"]["propagation_kind"] == "caller"


def test_absorb_keeps_the_first_anchor():
    base = {"A": "B"}
    absorb_anchors(base, {"A": "Z", "C": "D"})
    assert base == {"A": "B", "C": "D"}


def test_structural_island_matches_unique_spp_and_cfg():
    left = [
        _fn("A", strings=["Failed to allocate heap"], n_blocks=3, cyclomatic=2),
        _fn(
            "Island",
            n_blocks=8,
            cyclomatic=4,
            mnem={"mov": 10, "xor": 3, "ret": 1},
        ),
    ]
    left[1]["n_edges"] = 10
    right = [
        _fn("B", strings=["Failed to allocate heap"], n_blocks=3, cyclomatic=2),
        _fn(
            "Island2",
            n_blocks=8,
            cyclomatic=4,
            mnem={"movl": 10, "eor": 3, "ret": 1},
        ),
        _fn("Decoy", n_blocks=50, cyclomatic=20, mnem={"mov": 200}),
    ]
    right[1]["n_edges"] = 10
    right[2]["n_edges"] = 80
    hits = match_binaries(left, right, left_meta=META, right_meta=META, tier="verify")
    by_left = {row["left_id"]: row for row in hits}
    assert by_left["Island"]["right_id"] == "Island2"
    assert by_left["Island"]["kind"] == "structural"


def test_inline_review_when_blocks_are_contained():
    left = [
        _fn("A", strings=["Failed to allocate heap"]),
        {**_fn("Tiny"), "block_hashes": ["blk-a", "blk-b"]},
    ]
    right = [
        {**_fn("B", strings=["Failed to allocate heap"]), "block_hashes": ["blk-a", "blk-b", "blk-c"]},
    ]
    hits = match_binaries(left, right, left_meta=META, right_meta=META, tier="verify")
    inline = next(row for row in hits if row.get("kind") == "inline")
    assert inline["left_id"] == "Tiny"
    assert inline["right_id"] == "B"


def test_conflicting_unique_keys_do_not_anchor():
    mapping = unique_index_anchors(
        {"name": ["A"], "other": ["A"]},
        {"name": ["B"], "other": ["C"]},
        src_eligible={"A"},
        dst_eligible={"B", "C"},
    )
    assert mapping == {}


def test_empty_mnem_is_not_a_structural_island():
    src = [_fn("Island", n_blocks=8, cyclomatic=4)]
    src[0]["n_edges"] = 10
    dst = [_fn("Island2", n_blocks=8, cyclomatic=4)]
    dst[0]["n_edges"] = 10
    assert unique_structural_pairs(src, dst, id_of=lambda fn: fn["id"]) == []


def test_record_pairs_upgrades_scored_miss():
    results = {
        "X": {
            "dst": "WRONG",
            "score": 0.4,
            "status": "unresolved",
            "kind": "identity",
        }
    }
    added = record_pairs(results, [("X", "Y", "callee")], pair_class="same_platform")
    assert added == 1
    assert results["X"]["dst"] == "Y"
    assert results["X"]["kind"] == "callgraph"
    assert results["X"]["status"] == "auto"


def test_missing_n_instr_is_not_eligible():
    left = [_fn("A", strings=["Failed to allocate heap"], n_instr=None)]
    right = [_fn("B", strings=["Failed to allocate heap"], n_instr=None)]
    assert match_binaries(left, right, left_meta=META, right_meta=META) == []


def test_persist_status_keeps_structural_verify():
    result = {
        "score": 0.8,
        "margin": 1.0,
        "kind": "structural",
        "status": "verify",
        "evidence": {"_content": 2},
    }
    assert persist_status(result, "same_platform", None, None) == "verify"


def test_candidate_margin_sole_uses_score():
    assert candidate_margin(0.71, 0.0, 1) == 0.71
    assert abs(candidate_margin(0.71, 0.50, 2) - 0.21) < 1e-12
