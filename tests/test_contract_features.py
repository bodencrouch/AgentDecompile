"""Contract features on real byte rows (GOG/Amazon swkotor) and synthetic listings.

Fixtures under tests/fixtures/contract_features/ are copies of the byte and
instruction rows in two read-only evidence packets (contract-pairing and
amazon-remove-callers, 2026-09-27). Each fixture records its source sha256.
No database, image, decoder or network access happens here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.contract_features import (
    HARD_AXES,
    contract_compatibility,
    extract_contract,
    listing_from_rows,
    parse_cache_listing,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures" / "contract_features"
BODIES = {
    "a": "gog_00447fa0",          # GOG (a), operator=, receives M, returns M
    "w46e240": "gog_0046e240",    # GOG, receives M, returns M, list at N+0
    "a_prime": "amazon_0040ceb0",  # Amazon, receives M, returns M
    "b": "amazon_00412b50",       # Amazon (b), forms M = C+0x10, returns nothing
}
EVIDENCE_SHA = {
    "contract-pairing": "0d9974efa803a3d9156e2897d68f9d3b8cee85850e3c15ea73846b45dbbb530c",
    "amazon-remove-callers": "4c87df372e11ffbe8d5876d58993e829a1fa2b1955c1ebd9d82221150f4d76fd",
}


def _fixture(key: str) -> dict:
    return json.loads((FIXTURES / f"{BODIES[key]}.json").read_text())


def _features(key: str) -> dict:
    fx = _fixture(key)
    return extract_contract(listing_from_rows(fx["instructions"]), entry=fx["va"], size=fx["cacheSize"])


def _synthetic(rows: list[tuple[str, str]], base: int = 0x401000, size: int | None = -1) -> dict:
    listing, va = {}, base
    for hexbytes, text in rows:
        raw = bytes.fromhex(hexbytes)
        listing[va] = (raw, text)
        va += len(raw)
    return {"listing": listing, "entry": base, "size": (va - base) if size == -1 else size}


def _synthetic_features(rows, **kw) -> dict:
    body = _synthetic(rows, **{k: v for k, v in kw.items() if k in ("base", "size")})
    return extract_contract(body["listing"], entry=body["entry"], size=body["size"],
                            truncated=kw.get("truncated", False))


def _axes(result: dict) -> dict:
    return {name: result["axes"][name]["status"] for name in HARD_AXES}


# ---------------------------------------------------------------- fixtures


def test_fixtures_are_the_evidence_bytes():
    for key in BODIES:
        fx = _fixture(key)
        span = bytes.fromhex(fx["spanHex"])
        assert hashlib.sha256(span).hexdigest() == fx["spanSha256"]
        assert fx["source"]["evidenceSha256"] == EVIDENCE_SHA["contract-pairing"]
        covered = 0
        for row in fx["instructions"]:
            raw = bytes.fromhex(row["hex"])
            offset = row["va"] - fx["va"]
            assert span[offset:offset + len(raw)] == raw, hex(row["va"])
            covered += len(raw)
        assert covered == fx["cacheSize"] == len(span)
    assert _fixture("a_prime")["cacheRowSource"]["evidenceSha256"] == EVIDENCE_SHA["amazon-remove-callers"]


def test_verbatim_cache_row_and_capstone_decode_give_same_features():
    fx = _fixture("a_prime")
    row = fx["cacheRow"]
    assert row["asm"].startswith("# FUN_0040ceb0")  # header line kept verbatim
    from_cache = extract_contract(parse_cache_listing(row["asm"]), entry=int(row["entry_hex"], 16), size=row["size"])
    assert from_cache == _features("a_prime")
    for key in BODIES:
        fx = _fixture(key)
        intel = extract_contract(listing_from_rows(fx["capstoneRows"]), entry=fx["va"], size=fx["cacheSize"])
        assert intel == _features(key), key


# ---------------------------------------------------------------- features


def test_receiver_formation_per_body():
    expect = {
        "a": ("passthrough", 0, 0x447FA1),        # mov edi,ecx
        "w46e240": ("passthrough", 0, 0x46E242),  # mov edi,ecx
        "a_prime": ("passthrough", 0, 0x40CEB4),  # mov esi,ecx
        "b": ("adjusted", 0x10, 0x412B55),        # lea edi,[ecx+0x10]
    }
    for key, (form, k, site) in expect.items():
        receiver = _features(key)["receiver"]
        assert (receiver["form"], receiver["k"], receiver["formed_at"]) == (form, k, site), key
        assert receiver["determined"] is True


def test_return_contract_and_cleanup():
    for key in ("a", "w46e240", "a_prime"):
        f = _features(key)
        assert f["complete"] and f["return"]["class"] == "receiver", key
        assert f["return"]["eax_at_ret"] == ["rcv+0x0"]
        assert f["ret_cleanup"]["imm"] == [4]
    b = _features("b")
    assert b["return"]["class"] == "unwritten"
    assert "entry_eax" in b["return"]["eax_at_ret"]  # a path reaches ret 4 with EAX never written
    assert b["ret_cleanup"]["imm"] == [4]


def test_field_offsets_relative_to_receiver_and_argument():
    same_list = {"0x4": 1, "0x8": 3, "0xc": 1}
    assert _features("a")["field_offsets"] == {"arg1": same_list, "rcv": {"0x0": 2}}
    assert _features("a_prime")["field_offsets"] == {"arg1": same_list, "rcv": {"0x0": 2}}
    assert _features("w46e240")["field_offsets"] == {"arg1": {"0x0": 1, "0x4": 3, "0x8": 1}, "rcv": {"0x0": 2}}
    assert _features("b")["field_offsets"] == {"arg1": same_list, "rcv": {"0x10": 2}}


def test_callee_arity_cleanup_and_this_match_effect_table():
    # effectTable.removeThisOffset / nListBase were derived by hand in the evidence packet.
    remove_this = {"O+4": "[rcv+0x0]+0x4", "O+0": "[rcv+0x0]+0x0"}
    list_base = {"N+4": "arg1+0x4", "N+0": "arg1+0x0"}
    for key in ("a", "w46e240", "a_prime"):
        f, table = _features(key), _fixture(key)["effectTable"]
        assert f["callees_determined"]
        assert [(c["arity"], c["cleanup"]) for c in f["callees"]] == [(1, "callee"), (1, "callee")]
        assert f["callees"][0]["this"] == [remove_this[table["removeThisOffset"].split()[0]]], key
        assert f["callees"][1]["this"] == [list_base[table["nListBase"].split()[0]]], key
    b = _features("b")
    assert [(c["arity"], c["cleanup"]) for c in b["callees"]] == [(1, "callee"), (1, "callee")]
    assert b["callees"][0]["this"] == ["[rcv+0x10]+0x4"]  # O+4 of M = C+0x10


# ---------------------------------------------------------------- required pairs


def test_required_a_vs_40ceb0_compatible():
    result = contract_compatibility(_features("a"), _features("a_prime"))
    assert result["verdict"] == "compatible"
    assert _axes(result) == {name: "same" for name in HARD_AXES}
    assert result["reasons"] == [] and result["differences"] == []


def test_required_a_vs_b_incompatible_receiver_and_return():
    result = contract_compatibility(_features("a"), _features("b"))
    assert result["verdict"] == "incompatible"
    assert [r["axis"] for r in result["reasons"]] == ["receiver", "return"]
    assert result["axes"]["receiver"]["right"] == ("adjusted", 0x10)
    assert result["axes"]["return"]["left"] == "receiver" and result["axes"]["return"]["right"] == "unwritten"
    assert result["axes"]["ret_cleanup"]["status"] == "same" and result["axes"]["callees"]["status"] == "same"


def test_required_46e240_vs_b_incompatible():
    result = contract_compatibility(_features("w46e240"), _features("b"))
    assert result["verdict"] == "incompatible"
    assert {r["axis"] for r in result["reasons"]} == {"receiver", "return"}


def test_required_46e240_vs_a_compatible_with_offset_difference():
    result = contract_compatibility(_features("w46e240"), _features("a"))
    assert result["axes"]["receiver"]["status"] == "same"
    assert result["axes"]["return"]["status"] == "same"
    assert result["verdict"] == "compatible"
    offsets = [d for d in result["differences"] if d["kind"] == "field_offsets"]
    assert offsets == [{"kind": "field_offsets", "root": "arg1",
                        "only_left": {"0x0": 1, "0x4": 2}, "only_right": {"0x8": 2, "0xc": 1}}]
    this = [d for d in result["differences"] if d["kind"] == "callee_this"]
    assert [d["position"] for d in this] == [0, 1]


def test_same_build_b_vs_40ceb0_text_equal_core_is_incompatible():
    # The packet found the 26-instruction cores text-equal; struct/mnem cannot separate them.
    result = contract_compatibility(_features("b"), _features("a_prime"))
    assert result["verdict"] == "incompatible"
    assert [r["axis"] for r in result["reasons"]] == ["receiver", "return"]


def test_verdict_is_symmetric():
    keys = list(BODIES)
    for i, left in enumerate(keys):
        for right in keys[i:]:
            forward = contract_compatibility(_features(left), _features(right))
            backward = contract_compatibility(_features(right), _features(left))
            assert forward["verdict"] == backward["verdict"], (left, right)
            assert [r["axis"] for r in forward["reasons"]] == [r["axis"] for r in backward["reasons"]]


# ---------------------------------------------------------------- never fabricate

RETURNS_THIS = [("56", "PUSH ESI"), ("8bf1", "MOV ESI,ECX"), ("8bc6", "MOV EAX,ESI"),
                ("5e", "POP ESI"), ("c20400", "RET 0x4")]


def test_truncated_listing_is_unknown_even_against_itself():
    whole = _synthetic_features(RETURNS_THIS)
    cut = _synthetic_features(RETURNS_THIS, truncated=True)
    assert contract_compatibility(whole, whole)["verdict"] == "compatible"
    assert cut["complete"] is False and "listing_truncated" in cut["incomplete_reasons"]
    assert contract_compatibility(cut, cut)["verdict"] == "unknown"
    assert contract_compatibility(cut, whole)["verdict"] == "unknown"


def test_gap_or_missing_size_is_unknown():
    body = _synthetic(RETURNS_THIS)
    gap = dict(body["listing"])
    del gap[min(gap) + 3]  # drop MOV EAX,ESI; size still claims 9 bytes
    gapped = extract_contract(gap, entry=body["entry"], size=body["size"])
    assert gapped["complete"] is False
    assert any(r.startswith("gap_or_overlap") for r in gapped["incomplete_reasons"])
    no_size = extract_contract(body["listing"], entry=body["entry"], size=None)
    whole = _synthetic_features(RETURNS_THIS)
    for partial in (gapped, no_size):
        assert contract_compatibility(partial, whole)["verdict"] == "unknown"


def test_unmodelled_instruction_leaves_return_undetermined():
    rows = [("8bc1", "MOV EAX,ECX"), ("0fa2", "CPUID"), ("c20400", "RET 0x4")]
    f = _synthetic_features(rows)
    assert f["tracking_lost"] and f["return"]["class"] == "undetermined"
    assert contract_compatibility(f, f)["verdict"] == "unknown"
    ret8 = _synthetic_features(rows[:2] + [("c20800", "RET 0x8")])
    result = contract_compatibility(f, ret8)
    assert result["verdict"] == "incompatible"  # a determined hard axis still decides
    assert [r["axis"] for r in result["reasons"]] == ["ret_cleanup"]


def test_ret_cleanup_difference_is_incompatible():
    ret8 = RETURNS_THIS[:-1] + [("c20800", "RET 0x8")]
    result = contract_compatibility(_synthetic_features(RETURNS_THIS), _synthetic_features(ret8))
    assert result["verdict"] == "incompatible"
    assert result["reasons"] == [{"axis": "ret_cleanup", "left": [4], "right": [8]}]


def test_caller_cleanup_call_differs_from_callee_cleanup():
    head = [("56", "PUSH ESI"), ("8bf1", "MOV ESI,ECX"), ("6a01", "PUSH 0x1"), ("e800000000", "CALL FUN_x")]
    tail = [("8bc6", "MOV EAX,ESI"), ("5e", "POP ESI"), ("c3", "RET")]
    cdecl = _synthetic_features(head + [("83c404", "ADD ESP,0x4")] + tail)
    stdcall = _synthetic_features(head + tail)
    assert cdecl["callees"][0]["cleanup"] == "caller" and cdecl["callees"][0]["arity"] == 1
    assert stdcall["callees"][0]["cleanup"] == "callee" and stdcall["callees"][0]["arity"] == 1
    assert not cdecl["stack_faults"] and not stdcall["stack_faults"]
    result = contract_compatibility(cdecl, stdcall)
    assert result["verdict"] == "incompatible"
    assert [r["axis"] for r in result["reasons"]] == ["callees"]


def test_indirect_or_outbound_jump_is_unknown():
    indirect = _synthetic_features([("8bc1", "MOV EAX,ECX"), ("ffe0", "JMP EAX")])
    outbound = _synthetic_features([("8bc1", "MOV EAX,ECX"), ("e9fb0f0000", "JMP FUN_402000")])
    assert any(r.startswith("indirect_jump") for r in indirect["incomplete_reasons"])
    assert any(r.startswith("branch_leaves_listing") for r in outbound["incomplete_reasons"])
    whole = _synthetic_features(RETURNS_THIS)
    for f in (indirect, outbound):
        assert contract_compatibility(f, whole)["verdict"] == "unknown"
        assert contract_compatibility(f, f)["verdict"] == "unknown"


def test_missing_features_are_unknown():
    assert contract_compatibility(None, _features("a"))["verdict"] == "unknown"
    empty = extract_contract(None, entry=0x447FA0, size=81)
    assert empty["complete"] is False and empty["receiver"]["determined"] is False
    assert contract_compatibility(empty, _features("a"))["verdict"] == "unknown"


def test_callee_count_difference_is_reported_not_decided():
    # Builds inline differently; a count mismatch is a soft difference, not a veto.
    with_call = [("56", "PUSH ESI"), ("8bf1", "MOV ESI,ECX"), ("e800000000", "CALL FUN_x"),
                 ("8bc6", "MOV EAX,ESI"), ("5e", "POP ESI"), ("c20400", "RET 0x4")]
    result = contract_compatibility(_synthetic_features(with_call), _synthetic_features(RETURNS_THIS))
    assert result["verdict"] == "unknown"
    assert result["axes"]["callees"]["status"] == "undetermined"
    assert {"kind": "callee_count", "left": 1, "right": 0} in result["differences"]
