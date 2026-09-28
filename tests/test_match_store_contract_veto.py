"""End-to-end store matcher coverage for the opt-in calling-contract veto."""

from __future__ import annotations

import json
import pickle
import sqlite3

import pytest

from agentdecompile_recovery.corpus import match_store
from agentdecompile_recovery.corpus.fingerprint_hashes import attach_hashes
from agentdecompile_recovery.corpus.store import SCHEMA, ensure_func_columns

pytestmark = pytest.mark.unit

SRC_ADDR = 0x1000
BEST_ADDR = 0x2000
RUNNER_ADDR = 0x3000


def _db(candidate_addrs=(BEST_ADDR, RUNNER_ADDR), names=None):
    names = names or {}
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    ensure_func_columns(con)
    con.execute(
        "INSERT INTO binary(repo_path,slug,arch,bits,format,game) VALUES (?,?,?,?,?,?)",
        ("/synthetic/src", "src", "x86", 32, "PE", "g"),
    )
    src_id = con.execute("SELECT id FROM binary WHERE slug='src'").fetchone()[0]
    con.execute(
        "INSERT INTO binary(repo_path,slug,arch,bits,format,game) VALUES (?,?,?,?,?,?)",
        ("/synthetic/dst", "dst", "x86", 32, "PE", "g"),
    )
    dst_id = con.execute("SELECT id FROM binary WHERE slug='dst'").fetchone()[0]
    _insert_func(con, src_id, SRC_ADDR, "MOV", "src-block")
    for index, addr in enumerate(candidate_addrs, 1):
        _insert_func(con, dst_id, addr, f"ADD{index}", f"dst-block-{index}", names.get(addr))
    con.commit()
    return con, src_id, dst_id


def _insert_func(con, binary_id, addr, mnemonic, block_hash, name=None):
    row = attach_hashes({
        "mnem": {mnemonic: 20},
        "consts": [addr],
        "block_hashes": [block_hash],
        "n_instr": 20,
        "size": 40,
    })
    con.execute(
        """INSERT INTO func(
             binary_id,addr,name,name_origin,size,is_thunk,n_instr,n_blocks,n_edges,
             back_edges,cyclomatic,n_callees,indirect_calls,data_refs,mnem,strings,
             consts,ext_calls,block_hashes,hash_reloc,hash_instr,hash_mnemonic,
             hash_raw,source,param_count
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            binary_id, addr, name or f"sub_{addr:x}", "matcher_inferred", row["size"], 0,
            row["n_instr"], 3, 2, 0, 2, 0, 0, 0, json.dumps(row["mnem"]), "[]",
            json.dumps(row["consts"]), "[]", json.dumps(row["block_hashes"]),
            row["hash_reloc"], row["hash_instr"], row["hash_mnemonic"],
            row["hash_raw"], "IMPORTED", 0,
        ),
    )


def _install_controlled_fuzzy(monkeypatch, scores):
    monkeypatch.setattr(
        match_store,
        "candidate_pairs",
        lambda _sa, _sb, src_addr, _mapping: set(scores) if src_addr == SRC_ADDR else set(),
    )
    monkeypatch.setattr(match_store, "unique_structural_pairs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(match_store, "leftover_inlines", lambda *_args, **_kwargs: [])

    def score(_left, right, **_kwargs):
        return scores[right["addr"]], {
            "strings": 1.0,
            "primary_channel": "X",
            "_content": 1.0,
        }

    monkeypatch.setattr(match_store, "score_features", score)


def _install_contracts(monkeypatch, differing_axes):
    """Control the extractor verdict per target.

    ``differing_axes`` maps dst addr to the list of hard axes that differ
    ([] means compatible, None means features unavailable). This keeps the
    matcher tests independent of the pinned extractor revision.
    """

    def compat(left, right):
        axes = differing_axes.get(right["dst"]) if right else None
        if left is None or axes is None:
            return {"verdict": "unknown", "reasons": [], "differences": [], "axes": {}, "notes": []}
        return {
            "verdict": "incompatible" if axes else "compatible",
            "reasons": [{"axis": axis, "left": 0, "right": 1} for axis in axes],
            "differences": [],
            "axes": {},
            "notes": [],
        }

    monkeypatch.setattr(match_store, "contract_compatibility", compat)

    def loader(side, addr):
        if side == "src":
            return {"src": addr}
        return {"dst": addr} if differing_axes.get(addr) is not None else None

    return loader


def _run(con, src_id, dst_id, loader=None):
    kwargs = {} if loader is None else {"contract_features": loader}
    return match_store.match_binaries(con, src_id, dst_id, rounds=1, **kwargs)["results"].get(SRC_ADDR)


def test_ret_cleanup_difference_in_tie_window_demotes_best_keeps_margin_and_alternatives(monkeypatch):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.90, RUNNER_ADDR: 0.87})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: ["ret_cleanup"], RUNNER_ADDR: []})
    con, src_id, dst_id = _db()

    before = _run(con, src_id, dst_id)
    after = _run(con, src_id, dst_id, loader)

    assert before["dst"] == BEST_ADDR
    assert after["dst"] == RUNNER_ADDR
    assert after["margin"] == before["margin"] == 0.03
    assert after["status"] == "review"
    assert after["evidence"]["identity_claim"] is False
    contract = after["evidence"]["contract"]
    assert contract["promoted"] is True
    assert [(row["dst"], row["contract"], row["veto"]) for row in contract["window"]] == [
        (BEST_ADDR, "incompatible", "ret_cleanup"),
        (RUNNER_ADDR, "compatible", None),
    ]
    assert {alt["dst"] for alt in after["evidence"]["alternatives"]} == {BEST_ADDR, RUNNER_ADDR}


@pytest.mark.parametrize("axis", ["receiver", "return", "callees"])
def test_non_ret_cleanup_axis_does_not_veto_a_tie(monkeypatch, axis):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.90, RUNNER_ADDR: 0.87})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: [axis], RUNNER_ADDR: []})
    con, src_id, dst_id = _db()

    result = _run(con, src_id, dst_id, loader)

    assert result["dst"] == BEST_ADDR
    contract = result["evidence"]["contract"]
    assert contract["verdict"] == "incompatible"
    assert contract["reasons"] == [axis]
    assert contract["veto"] is None
    assert contract["promoted"] is False


@pytest.mark.parametrize("axis", ["receiver", "return", "callees"])
def test_non_ret_cleanup_axis_does_not_block_verification(monkeypatch, axis):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.95})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: [axis]})
    con, src_id, dst_id = _db((BEST_ADDR,))

    baseline = _run(con, src_id, dst_id)
    with_axis = _run(con, src_id, dst_id, loader)

    assert baseline["evidence"]["status_band"] == "verified"
    assert with_axis["dst"] == BEST_ADDR
    assert with_axis["evidence"]["status_band"] == "verified"
    assert with_axis["evidence"]["identity_claim"] is True
    assert with_axis["evidence"]["contract"]["reasons"] == [axis]


def test_ret_cleanup_difference_blocks_verification_of_single_candidate(monkeypatch):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.95})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: ["ret_cleanup", "receiver"]})
    con, src_id, dst_id = _db((BEST_ADDR,))

    baseline = _run(con, src_id, dst_id)
    vetoed = _run(con, src_id, dst_id, loader)

    assert baseline["evidence"]["status_band"] == "verified"
    assert baseline["evidence"]["identity_claim"] is True
    assert vetoed["dst"] == BEST_ADDR
    assert vetoed["status"] == "review"
    assert vetoed["evidence"]["identity_claim"] is False
    assert vetoed["evidence"]["contract"]["veto"] == "ret_cleanup"
    assert vetoed["evidence"]["contract"]["vetoed_best"] is True


def test_every_tied_candidate_vetoed_keeps_original_best_at_review(monkeypatch):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.90, RUNNER_ADDR: 0.87})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: ["ret_cleanup"], RUNNER_ADDR: ["ret_cleanup"]})
    con, src_id, dst_id = _db()

    result = _run(con, src_id, dst_id, loader)

    assert result["dst"] == BEST_ADDR
    assert result["margin"] == 0.03
    assert result["status"] == "review"
    assert result["evidence"]["contract"]["vetoed_best"] is True
    assert {alt["dst"] for alt in result["evidence"]["alternatives"]} == {BEST_ADDR, RUNNER_ADDR}


def test_unwind_target_best_in_tie_loses_even_without_features(monkeypatch):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.90, RUNNER_ADDR: 0.87})
    # No features for either target: the hard negative is name-based.
    loader = _install_contracts(monkeypatch, {})
    con, src_id, dst_id = _db(names={BEST_ADDR: "Unwind@0081d40e"})

    before = _run(con, src_id, dst_id)
    after = _run(con, src_id, dst_id, loader)

    assert before["dst"] == BEST_ADDR
    assert after["dst"] == RUNNER_ADDR
    assert after["status"] == "review"
    assert after["margin"] == before["margin"]
    contract = after["evidence"]["contract"]
    assert contract["verdict"] == "unknown"
    assert contract["hard_negatives"] == [{"dst": BEST_ADDR, "score": 0.9, "veto": "unwind_target"}]
    assert any(alt.get("veto") == "unwind_target" for alt in after["evidence"]["alternatives"])


def test_unwind_target_outside_tie_window_is_still_never_chosen(monkeypatch):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.99, RUNNER_ADDR: 0.60})
    loader = _install_contracts(monkeypatch, {RUNNER_ADDR: []})
    con, src_id, dst_id = _db(names={BEST_ADDR: "Unwind@0081d40e"})

    result = _run(con, src_id, dst_id, loader)

    assert result["dst"] == RUNNER_ADDR
    assert result["status"] == "review"
    assert result["evidence"]["identity_claim"] is False


def test_sole_unwind_candidate_that_verifies_on_baseline_produces_no_row(monkeypatch):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.95})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: []})
    con, src_id, dst_id = _db((BEST_ADDR,), names={BEST_ADDR: "Unwind@0081d40e"})

    baseline = _run(con, src_id, dst_id)
    after = _run(con, src_id, dst_id, loader)

    assert baseline["evidence"]["status_band"] == "verified"
    assert after is None


def test_compatible_never_changes_a_review_row(monkeypatch):
    # A tie at review stays exactly where it was when both targets are compatible.
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.90, RUNNER_ADDR: 0.87})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: [], RUNNER_ADDR: []})
    con, src_id, dst_id = _db()

    before = _run(con, src_id, dst_id)
    after = _run(con, src_id, dst_id, loader)

    assert after["dst"] == before["dst"] == BEST_ADDR
    assert after["score"] == before["score"]
    assert after["margin"] == before["margin"]
    assert after["status"] == before["status"] == "review"
    assert after["evidence"]["identity_claim"] is False
    assert after["evidence"]["contract"]["verdict"] == "compatible"
    assert {alt["dst"] for alt in after["evidence"]["alternatives"]} == {BEST_ADDR, RUNNER_ADDR}


def test_veto_promoted_runner_up_never_verifies_even_when_scores_would(monkeypatch):
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.99, RUNNER_ADDR: 0.98})
    loader = _install_contracts(monkeypatch, {BEST_ADDR: ["ret_cleanup"], RUNNER_ADDR: []})
    monkeypatch.setattr(match_store, "allows_verify", lambda *_a, **_k: True)
    monkeypatch.setattr(match_store, "_passes", lambda *_a, **_k: True)
    con, src_id, dst_id = _db()

    result = _run(con, src_id, dst_id, loader)

    assert result["dst"] == RUNNER_ADDR
    assert result["status"] == "review"
    assert result["evidence"]["identity_claim"] is False
    assert result["evidence"]["contract"]["promoted"] is True


def test_contract_features_none_is_byte_identical_to_omitting_it(monkeypatch):
    # Every opt-in feature would fire here: a ret_cleanup veto is available and
    # the best target is an Unwind@ funclet. None must ignore all of it.
    _install_controlled_fuzzy(monkeypatch, {BEST_ADDR: 0.90, RUNNER_ADDR: 0.87})
    _install_contracts(monkeypatch, {BEST_ADDR: ["ret_cleanup"], RUNNER_ADDR: []})
    con, src_id, dst_id = _db(names={BEST_ADDR: "Unwind@0081d40e"})

    omitted = match_store.match_binaries(con, src_id, dst_id, rounds=1)
    explicit_none = match_store.match_binaries(con, src_id, dst_id, rounds=1, contract_features=None)

    assert pickle.dumps(explicit_none, protocol=5) == pickle.dumps(omitted, protocol=5)
    row = omitted["results"][SRC_ADDR]
    assert row["dst"] == BEST_ADDR
    assert "contract" not in row["evidence"]
