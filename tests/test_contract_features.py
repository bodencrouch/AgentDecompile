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
    # b leaves entry EAX on one path, so its return is not a contract (tie triage window 3):
    # the classes are still reported, but only the receiver vetoes.
    assert [r["axis"] for r in result["reasons"]] == ["receiver"]
    assert result["axes"]["receiver"]["right"] == ("adjusted", 0x10)
    assert result["axes"]["return"]["left"] == "receiver" and result["axes"]["return"]["right"] == "unwritten"
    assert result["axes"]["return"]["status"] == "undetermined"
    assert result["axes"]["ret_cleanup"]["status"] == "same" and result["axes"]["callees"]["status"] == "same"


def test_required_46e240_vs_b_incompatible():
    result = contract_compatibility(_features("w46e240"), _features("b"))
    assert result["verdict"] == "incompatible"
    assert {r["axis"] for r in result["reasons"]} == {"receiver"}  # b's return is undetermined


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
    assert [r["axis"] for r in result["reasons"]] == ["receiver"]  # b's return is undetermined


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


# ---------------------------------------------------------------- push ecx local slot (tie triage)
#
# Real rows from the tie-triage packets (2026-09-27-tie-triage, -w2). Each fixture holds the
# Capstone rows of one body and the sha256 of the image span they cover. Row ids are the match
# ids the triage audited: 1003762 and 1003543 were false vetoes caused by MSVC's `push ecx`
# local-slot allocation; 1005025 read a receiver used as an index register as unused.

TRIAGE_BODIES = {
    "skip_gog": "gog_00413940",       # 1003762 source, SkipNewLines
    "skip_amz": "amazon_00633bd0",    # 1003762 target: push ecx at 0x633bd3, xor ecx,ecx at 0x633bd7
    "trails_gog": "gog_004015b0",     # 1003543 source: SPI 0x5e then 0x5d
    "trails_amz": "amazon_0040a080",  # 1003543/1003544 target: push ecx at 0x40a083
    "spi10_gog": "gog_00401610",      # 1003544 source: SPI 0x10 then 0x11 (wrong pair)
    "faction_gog": "gog_0052b3d0",    # 1005025 source
    "faction_amz": "amazon_007d7de4",  # 1005025 target: mov esi,ecx; test [edx+esi+0x3c],al
    "clear_gog": "gog_00409e70",      # 1004107 source: mov eax,ecx; zeroes rcv+0/4/8; ret (returns rcv)
    "clear_amz": "amazon_00741120",   # 1004107 target: mov eax,1; zeroes rcv+0x28..0x34; ret
    "zval_gog": "gog_0060bf20",       # 1009803 source, ComputeZValue: early exit leaves a global in EAX
    "zval_amz": "amazon_004c4c70",    # 1009803 target: early exit leaves entry EAX; fstp [esi+8]
}
TRIAGE_SHA = {
    "tie-triage": "8972699e1caa2213e2ce60c870b8acf683e19e31254ee6b517efb0622b73ca30",
    "tie-triage-w2": "82759d010d85fe909f63059dc757ff6b856d96588bfa8545da3740e5041bb24e",
    "tie-triage-w3": "0ce487c4ae54a43e6fb48b9c26efcb1186292705feae0646522395b6e2fe337a",
}
TRIAGE_SPAN_SHA = {
    "skip_gog": "f27861e43344", "skip_amz": "902cd87c0182", "trails_gog": "1f187e9fef2b",
    "trails_amz": "866e7ec2cb4c", "spi10_gog": "506c2cc7602b", "faction_gog": "a3f9d0ecec82",
    "faction_amz": "8dc6b837ce74", "clear_gog": "1e09d34a9de7", "clear_amz": "88390a1fbb41",
    "zval_gog": "978fd4cba2ba", "zval_amz": "8dc9f96b170e",
}


def _triage_fixture(key: str) -> dict:
    return json.loads((FIXTURES / f"{TRIAGE_BODIES[key]}.json").read_text())


def _triage(key: str) -> dict:
    fx = _triage_fixture(key)
    return extract_contract(listing_from_rows(fx["instructions"]), entry=fx["va"], size=fx["cacheSize"])


def test_triage_fixtures_are_the_evidence_bytes():
    for key in TRIAGE_BODIES:
        fx = _triage_fixture(key)
        assert fx["source"]["evidenceSha256"] in TRIAGE_SHA.values(), key
        span = b"".join(bytes.fromhex(row["hex"]) for row in fx["instructions"])
        assert len(span) == fx["cacheSize"], key
        assert hashlib.sha256(span).hexdigest() == fx["spanSha256"], key
        assert fx["spanSha256"].startswith(TRIAGE_SPAN_SHA[key]), key
        at = {row["va"]: row["hex"] for row in fx["instructions"]}
        cursor = fx["va"]
        for row in fx["instructions"]:
            assert row["va"] == cursor, hex(row["va"])
            cursor += len(bytes.fromhex(row["hex"]))
        for hand in fx["handRows"]:  # the bytes the triage verified against the image
            assert at[hand["va"]] == hand["hex"], (key, hex(hand["va"]))
    assert {_triage_fixture(k)["source"]["evidenceSha256"] for k in ("faction_gog", "faction_amz")} \
        == {TRIAGE_SHA["tie-triage-w2"]}


def test_1003762_push_ecx_is_a_local_slot_not_a_receiver_use():
    amz = _triage("skip_amz")
    assert amz["complete"] and not amz["stack_faults"]
    assert amz["receiver"]["push_slots"] == {"0x633bd3": "local_slot"}
    assert (amz["receiver"]["form"], amz["receiver"]["determined"]) == ("unused", True)
    result = contract_compatibility(_triage("skip_gog"), amz)
    assert result["verdict"] != "incompatible"
    assert result["axes"]["receiver"]["status"] == "same"
    assert result["axes"]["ret_cleanup"]["status"] == "same"  # both ret 8


def test_1003543_push_ecx_is_not_a_fifth_argument():
    amz = _triage("trails_amz")
    assert amz["receiver"]["push_slots"] == {"0x40a083": "local_slot"}
    assert [(c["arity"], c["cleanup"]) for c in amz["callees"]] == [(4, "callee"), (4, "callee")]
    assert amz["callees_determined"]
    for left, right in (("trails_gog", "trails_amz"), ("trails_amz", "trails_gog")):
        result = contract_compatibility(_triage(left), _triage(right))
        # Both bodies end in a call with no further EAX write, so return is undetermined
        # (eax_left_by_a_callee) rather than compatible: the tail call could return through
        # ST0, which the body-only scan cannot see. Never compatible, only never vetoed.
        assert result["verdict"] != "incompatible", (left, right)
        assert result["axes"]["return"]["status"] == "undetermined"
        assert result["axes"]["callees"]["status"] == "same"
        assert result["axes"]["receiver"]["status"] == "same"


def test_1003544_wrong_pair_is_not_vetoed_by_the_artifact():
    # SPI 0x10/0x11 against 0x5e/0x5d: same calling contract, different constants. The old
    # veto came from the push-ecx artifact; the contract cannot see the constants, and a
    # never-vetoed verdict never promotes a row.
    result = contract_compatibility(_triage("spi10_gog"), _triage("trails_amz"))
    # Both bodies end in a call with no further EAX write, so return is undetermined
    # (eax_left_by_a_callee) rather than compatible; the fix's job is only to not veto.
    assert result["verdict"] != "incompatible"
    assert result["axes"]["return"]["status"] == "undetermined"


def test_1005025_receiver_used_as_index_register():
    amz = _triage("faction_amz")
    receiver = amz["receiver"]
    assert (receiver["form"], receiver["k"], receiver["formed_at"]) == ("passthrough", 0, 0x7D7DED)
    for left, right in (("faction_gog", "faction_amz"), ("faction_amz", "faction_gog")):
        result = contract_compatibility(_triage(left), _triage(right))
        assert result["verdict"] == "incompatible"  # still vetoed, now only on real axes
        # The source leaves entry EAX on a path, so return is undetermined; ret 0xc vs ret 8 decides.
        assert [r["axis"] for r in result["reasons"]] == ["ret_cleanup"]
        assert result["axes"]["receiver"]["status"] == "same"


def test_ghidra_local_names_resolve_like_frame_offsets():
    # Transliteration, not a cache row: the tie-triage packets hold no cache asm. [ebp - 4]
    # in an ebp frame is rendered by Ghidra as [EBP + local_8] (entry ESP - 8).
    for key in ("skip_amz", "trails_amz"):
        fx = _triage_fixture(key)
        rows = [dict(r, text=r["text"].replace("[ebp - 4]", "[EBP + local_8]")) for r in fx["instructions"]]
        assert rows != fx["instructions"]
        named = extract_contract(listing_from_rows(rows), entry=fx["va"], size=fx["cacheSize"])
        assert named == _triage(key), key


# Guards: the fix must not stop seeing a receiver that really is pushed or reloaded.

def _receiver(f: dict) -> tuple:
    return f["receiver"]["form"], f["receiver"]["determined"]


def test_push_ecx_passed_to_a_call_stays_a_receiver_use():
    f = _synthetic_features([("51", "PUSH ECX"), ("e800000000", "CALL FUN_x"), ("c3", "RET")])
    assert _receiver(f) == ("passthrough", True)
    assert f["receiver"]["push_slots"] == {"0x401000": "use"}
    assert [(c["arity"], c["cleanup"]) for c in f["callees"]] == [(1, "callee")]


def test_push_ecx_reloaded_as_a_spill_stays_a_receiver_use():
    rows = [("55", "PUSH EBP"), ("8bec", "MOV EBP,ESP"), ("51", "PUSH ECX"), ("33c9", "XOR ECX,ECX"),
            ("8b45fc", "MOV EAX,dword ptr [EBP + -0x4]"), ("8be5", "MOV ESP,EBP"), ("5d", "POP EBP"), ("c3", "RET")]
    f = _synthetic_features(rows)
    assert _receiver(f) == ("passthrough", True)
    assert f["return"]["class"] == "receiver"


def test_push_ecx_float_argument_keeps_arity():
    rows = [("51", "PUSH ECX"), ("d91c24", "FSTP dword ptr [ESP]"), ("e800000000", "CALL FUN_x"), ("c3", "RET")]
    f = _synthetic_features(rows)
    assert [(c["arity"], c["cleanup"]) for c in f["callees"]] == [(1, "callee")]
    assert f["receiver"]["determined"] is True and f["receiver"]["form"] == "passthrough"


def test_push_ecx_with_lost_stack_or_unresolved_access_is_undetermined():
    lost = _synthetic_features([("51", "PUSH ECX"), ("03e0", "ADD ESP,EAX"), ("c3", "RET")])
    unresolved = _synthetic_features([("51", "PUSH ECX"), ("8a442401", "MOV AL,byte ptr [ESP + 0x1]"),
                                      ("83c404", "ADD ESP,0x4"), ("c3", "RET")])
    for f in (lost, unresolved):
        assert f["receiver"]["form"] is None and f["receiver"]["determined"] is False
        assert contract_compatibility(f, f)["axes"]["receiver"]["status"] == "undetermined"


def test_push_ecx_out_parameter_is_undetermined_and_not_an_argument():
    # push ecx; call f(&local) while the pushed value is still there: the callee may read it.
    # xor ecx,ecx: the call's ECX is not the receiver, so only the push decides the receiver.
    rows = [("55", "PUSH EBP"), ("8bec", "MOV EBP,ESP"), ("51", "PUSH ECX"), ("33c9", "XOR ECX,ECX"),
            ("8d45fc", "LEA EAX,[EBP + -0x4]"),
            ("50", "PUSH EAX"), ("e800000000", "CALL FUN_x"), ("8b45fc", "MOV EAX,dword ptr [EBP + -0x4]"),
            ("8be5", "MOV ESP,EBP"), ("5d", "POP EBP"), ("c3", "RET")]
    f = _synthetic_features(rows)
    assert f["receiver"]["push_slots"] == {"0x401003": "undecided"}
    assert f["receiver"]["determined"] is False
    assert [(c["arity"], c["cleanup"]) for c in f["callees"]] == [(1, "callee")]
    assert f["return"]["class"] == "other"  # the callee may have written the local


def test_pop_ecx_after_call_leaves_arity_undetermined():
    # MSVC frees a cdecl argument or a push-ecx local with pop ecx; the arity cannot be told.
    rows = [("51", "PUSH ECX"), ("6a01", "PUSH 0x1"), ("e800000000", "CALL FUN_x"), ("59", "POP ECX"),
            ("59", "POP ECX"), ("c3", "RET")]
    f = _synthetic_features(rows)
    assert f["callees"][0]["arity"] is None and f["callees_determined"] is False


# ---------------------------------------------------------------- return axis (tie triage window 3)
#
# 1009803 was a false veto on `return` alone: both bodies return through `fstp [esi+8]` and
# neither returns EAX. The return axis may veto only when every ret writes EAX with a value of
# the function's own and the body has no x87 instruction; otherwise it is undetermined.


def test_triage_w3_fixtures_come_from_window_3():
    assert {_triage_fixture(k)["source"]["evidenceSha256"] for k in ("zval_gog", "zval_amz")} \
        == {TRIAGE_SHA["tie-triage-w3"]}
    assert {_triage_fixture(k)["source"]["evidenceSha256"] for k in ("clear_gog", "clear_amz")} \
        == {TRIAGE_SHA["tie-triage"]}
    for key in ("zval_gog", "zval_amz", "clear_gog", "clear_amz"):
        assert _triage_fixture(key)["handRows"], key


def test_1009803_x87_return_is_not_vetoed_on_eax():
    for key in ("zval_gog", "zval_amz"):
        f = _triage(key)
        assert f["complete"] and not f["tracking_lost"], key
        assert f["return"]["determined"] is False, key
        assert "x87" in f["return"]["undetermined_reasons"], key
    assert "eax_not_written_on_a_path" in _triage("zval_amz")["return"]["undetermined_reasons"]
    for left, right in (("zval_gog", "zval_amz"), ("zval_amz", "zval_gog")):
        result = contract_compatibility(_triage(left), _triage(right))
        assert result["verdict"] != "incompatible", (left, right)
        assert result["axes"]["return"]["status"] == "undetermined"
        assert result["axes"]["ret_cleanup"]["status"] == "same"  # both ret 0x10


def test_1004107_return_written_on_every_path_still_vetoes():
    src, dst = _triage("clear_gog"), _triage("clear_amz")
    assert (src["return"]["class"], src["return"]["determined"]) == ("receiver", True)
    assert (dst["return"]["class"], dst["return"]["determined"]) == ("other", True)
    for left, right in (("clear_gog", "clear_amz"), ("clear_amz", "clear_gog")):
        result = contract_compatibility(_triage(left), _triage(right))
        assert result["verdict"] == "incompatible"
        assert [r["axis"] for r in result["reasons"]] == ["return"]


def test_x87_body_leaves_return_undetermined_even_when_eax_is_written():
    plain = _synthetic_features([("8bc1", "MOV EAX,ECX"), ("c3", "RET")])
    x87 = _synthetic_features([("8bc1", "MOV EAX,ECX"), ("d9e8", "FLD1"), ("d95904", "FSTP dword ptr [ECX + 0x4]"),
                               ("c3", "RET")])
    assert (plain["return"]["class"], plain["return"]["determined"]) == ("receiver", True)
    assert x87["return"]["class"] == "receiver" and x87["return"]["determined"] is False
    assert x87["return"]["undetermined_reasons"] == ["x87"]
    other = _synthetic_features([("b801000000", "MOV EAX,0x1"), ("c3", "RET")])
    assert contract_compatibility(plain, other)["verdict"] == "incompatible"
    assert contract_compatibility(x87, other)["axes"]["return"]["status"] == "undetermined"


def test_eax_unwritten_on_one_path_leaves_return_undetermined():
    rows = [("85c9", "TEST ECX,ECX"), ("7402", "JZ LAB_x"), ("8bc1", "MOV EAX,ECX"), ("c3", "RET")]
    f = _synthetic_features(rows)
    assert f["return"]["class"] == "unwritten" and f["return"]["determined"] is False
    assert f["return"]["undetermined_reasons"] == ["eax_not_written_on_a_path"]
    returns_this = _synthetic_features([("8bc1", "MOV EAX,ECX"), ("c3", "RET")])
    assert contract_compatibility(f, returns_this)["axes"]["return"]["status"] == "undetermined"


def test_eax_left_by_a_callee_leaves_return_undetermined():
    # A void function whose last act is a call leaves the callee's EAX (or ST0) behind.
    f = _synthetic_features([("e800000000", "CALL FUN_x"), ("c3", "RET")])
    assert f["return"]["class"] == "callee_result" and f["return"]["determined"] is False
    assert f["return"]["undetermined_reasons"] == ["eax_left_by_a_callee"]
