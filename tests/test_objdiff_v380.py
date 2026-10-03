"""P2 parser regressions, authored but UNRUN. Reports here are schema fixtures,
not native checker qualification or emitted-region acceptance evidence.
"""
from __future__ import annotations

import copy
import json

import pytest

from agentdecompile_recovery.grid_lanes.objdiff_v380 import ReportError, parse_report
from agentdecompile_recovery.grid_lanes.parity_region import scan_region


CODE = b"\x31\xc0\xc3"
SYMBOL = "F_401000"


def emitted_report(left=CODE, right=None):
    """Explicit pinned schema fixture; opcode IDs are test values, not attestation."""
    right = left if right is None else right
    out = {}
    for side, code in (("left", left), ("right", right)):
        rows = []
        for token in scan_region(code):
            op = token["operation"]
            parts = [{"opcode": {"mnemonic": op, "opcode": {"xor": 1518, "ret": 662, "nop": 465, "inc": 279, "dec": 135}[op]}}]
            args = {"xor": 2, "inc": 1, "dec": 1, "ret": 0, "nop": 0}[op]
            for i in range(args):
                if i:
                    parts += [{"basic": ","}, {"basic": " "}]
                parts += [{"arg": {"opaque": "eax"}}]
            instruction = {"size": token["length"], "formatted": op + " " + ", ".join(["eax"] * args), "parts": parts}
            if token["offset"]:
                instruction["address"] = str(token["offset"])
            rows.append({"instruction": instruction, "arg_diff": [{} for _ in range(args)]})
        section = {"name": ".text", "kind": "SECTION_CODE", "size": str(len(code))}
        if side == "left":
            section["match_percent"] = 100
        out[side] = {"sections": [section], "symbols": [
            {"name": "[.text]", "kind": "SYMBOL_SECTION", "flags": {"local": True}},
            {"name": SYMBOL, "kind": "SYMBOL_FUNCTION", "size": str(len(code)), "flags": {"global": True, "size_inferred": True},
             "target_symbol": 1, "match_percent": 100, "instructions": rows},
        ]}
    return out


def parse(value, left=CODE, right=CODE, grade="matched"):
    raw = value if type(value) is bytes else json.dumps(value).encode()
    return parse_report(raw, SYMBOL, scan_region(left), scan_region(right), checker_grade=grade)


def test_omitted_zero_and_absent_right_percentage_are_native_defaults():
    report = emitted_report()
    normalized = parse(report)
    assert "match_percent" not in normalized["right"]["sections"][0]
    assert normalized["left"]["symbols"][1]["instructions"][0]["diff_kind"] == "DIFF_NONE"
    for side in ("left", "right"):
        report[side]["symbols"][1]["instructions"][0]["diff_kind"] = "DIFF_NONE"
        report[side]["symbols"][1]["instructions"][0]["instruction"]["address"] = "0"
    assert parse(report) == normalized
    assert parse(json.dumps(report, indent=3).encode()) == normalized


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop("right"),
    lambda r: r["left"]["symbols"][1].pop("match_percent"),
    lambda r: r["right"]["sections"][0].update(match_percent=100),
    lambda r: r["left"]["symbols"][1].update(target_symbol=0),
    lambda r: r["left"]["symbols"].append(copy.deepcopy(r["left"]["symbols"][1])),
    lambda r: r["left"]["symbols"][1].update(instructions=[]),
    lambda r: r["left"]["symbols"][1]["instructions"].pop(),
    lambda r: r["left"]["symbols"][1]["instructions"].__setitem__(0, {}),
    lambda r: r["left"]["symbols"][1]["instructions"][0]["instruction"].update(size=1),
    lambda r: r["left"]["symbols"][1]["instructions"][0]["instruction"].update(branch_dest="0"),
    lambda r: r["left"]["symbols"][1]["instructions"][0]["instruction"].update(line_number=0),
    lambda r: r["left"]["symbols"][1]["instructions"][0]["instruction"].update(relocation={}),
])
def test_coverage_association_and_present_zero_dependencies_refuse(mutation):
    report = emitted_report()
    mutation(report)
    with pytest.raises(ReportError):
        parse(report)


@pytest.mark.parametrize("value", [True, "100", "NaN", float("nan"), float("inf"), -1, 101, None, 10**200])
def test_percentage_exact_type_range_and_finite(value):
    report = emitted_report()
    report["left"]["symbols"][1]["match_percent"] = value
    with pytest.raises(ReportError):
        parse(report)


@pytest.mark.parametrize("field,value", [
    ("size", 2.0), ("size", True), ("size", "2"), ("size", 2**32),
    ("address", "00"), ("address", "-0"), ("address", "18446744073709551616"),
    ("address", 0), ("address", "0e0"), ("address", " 0"), ("address", "+0"),
    ("unknown", 1), ("lineNumber", 1),
])
def test_instruction_scalar_and_unknown_fields(field, value):
    report = emitted_report()
    report["left"]["symbols"][1]["instructions"][0]["instruction"][field] = value
    with pytest.raises(ReportError):
        parse(report)


@pytest.mark.parametrize("parts", [[], [{}], [{"opcode": {}}], [{"opcode": {"mnemonic": "xor", "opcode": 0}}],
    [{"arg": {"signed": "0"}}], [{"arg": {"opaque": "eax", "unsigned": "0"}}],
    [{"opcode": {"mnemonic": "xor", "opcode": 1518}, "basic": "xor"}], None])
def test_parts_empty_oneof_opcode_and_extra_operands(parts):
    report = emitted_report()
    report["left"]["symbols"][1]["instructions"][0]["instruction"]["parts"] = parts
    with pytest.raises(ReportError):
        parse(report)


@pytest.mark.parametrize("raw", [b'{"left":{},"left":{},"right":{}}', b'{"x":NaN}', b'{}{}', b'[]', b'\xff',
                                  b'[' * 33 + b'0' + b']' * 33])
def test_whole_json_duplicate_keys_encoding_and_depth(raw):
    with pytest.raises(ReportError):
        parse(raw)


@pytest.mark.parametrize("change", [
    {"diff_kind": 0}, {"diff_kind": "NONE"}, {"diff_kind": "DIFF_FUTURE"},
    {"arg_diff": [{"diff_index": False}, {}]}, {"arg_diff": [{}, {}, {}]},
])
def test_diff_enum_and_arg_shapes(change):
    report = emitted_report()
    report["left"]["symbols"][1]["instructions"][0].update(change)
    with pytest.raises(ReportError):
        parse(report)


def test_invalid_base64_rejected_even_in_unsupported_data_row():
    report = emitted_report()
    report["left"]["sections"][0]["data_diff"] = [{"data": "YQ", "size": "1"}]
    with pytest.raises(ReportError, match="string_encoding|base64"):
        parse(report)


def test_counterpart_opcode_and_full_part_shape_must_match():
    report = emitted_report()
    report["right"]["symbols"][1]["instructions"][0]["instruction"]["parts"][0]["opcode"]["opcode"] += 1
    with pytest.raises(ReportError, match="counterpart_shape"):
        parse(report)


def test_supported_complete_mismatch_and_xor_encoding_alias():
    left, right = b"\x31\xc0\x40\xc3", b"\x31\xc0\x48\xc3"
    report = emitted_report(left, right)
    report["left"]["sections"][0]["match_percent"] = 75
    for side in ("left", "right"):
        report[side]["symbols"][1]["match_percent"] = 75
        report[side]["symbols"][1]["instructions"][1]["diff_kind"] = "DIFF_REPLACE"
    parsed = parse(report, left, right, "mismatched")
    assert parsed["left"]["symbols"][1]["instructions"][1]["diff_kind"] == "DIFF_REPLACE"
    # Parser equality alone never proves these different region bytes equal.
    assert parse(emitted_report(CODE, b"\x33\xc0\xc3"), CODE, b"\x33\xc0\xc3")
    assert CODE != b"\x33\xc0\xc3"
