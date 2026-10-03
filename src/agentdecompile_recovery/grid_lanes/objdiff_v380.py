"""Strict emitted DiffResult profile for pinned objdiff 3.8.0 (no checker execution).

Schema: encounter/objdiff@784a16740a8a67b835b752ab867e76347d8a9691,
objdiff-core/protos/diff.proto and src/bindings/diff.rs. This parser grants no
executable, implementation-closure, source, or runtime admission authority.
"""
from __future__ import annotations

import base64
import json
import math
import re
from typing import Callable

PROFILE = "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1"
POLICY = "coff-i386-register-leaf-v1"
UPSTREAM_COMMIT = "784a16740a8a67b835b752ab867e76347d8a9691"
ASSET_SHA256 = "bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81"
VERIFIER_ID = "parity:" + ASSET_SHA256
RAW_LIMIT = 4 << 20
FLAGS = ("global", "local", "weak", "common", "hidden", "ignored", "size_inferred")
ENUMS = {
    "SectionEnum": tuple("SECTION_" + s for s in ("UNKNOWN", "CODE", "DATA", "BSS", "COMMON")),
    "SymbolEnum": tuple("SYMBOL_" + s for s in ("UNKNOWN", "FUNCTION", "OBJECT", "SECTION")),
    "DiffEnum": tuple("DIFF_" + s for s in ("NONE", "REPLACE", "DELETE", "INSERT", "OP_MISMATCH", "ARG_MISMATCH")),
}
# '?' is optional, '!' required, '[]' repeated. Defaults model emitted pbjson,
# not its more permissive input decoder. Oneofs are independently enforced.
SCHEMA = {
    "DiffResult": {"left": "DiffObject!", "right": "DiffObject!"},
    "DiffObject": {"sections": "DiffSection[]", "symbols": "DiffSymbol[]"},
    "DiffSection": {"name": "str", "kind": "SectionEnum", "size": "u64", "address": "u64",
                    "match_percent": "percent?", "data_diff": "DataSegment[]", "reloc_diff": "DataRelocation[]"},
    "DiffSymbol": {"name": "str", "demangled_name": "str?", "address": "u64", "size": "u64",
                   "flags": "Flags?", "kind": "SymbolEnum", "target_symbol": "u32?", "match_percent": "percent?",
                   "instructions": "InstructionRow[]", "data_diff": "DataSegment[]"},
    "Flags": {k: "bool" for k in FLAGS},
    "InstructionRow": {"diff_kind": "DiffEnum", "instruction": "Instruction!", "arg_diff": "ArgDiff[]"},
    "Instruction": {"address": "u64", "size": "u32", "formatted": "str", "parts": "Part[]",
                    "relocation": "Relocation?", "branch_dest": "u64?", "line_number": "u32?"},
    "Part": {"basic": "str?", "opcode": "Opcode?", "arg": "Arg?", "separator": "bool?"},
    "Opcode": {"mnemonic": "str", "opcode": "u32"},
    "Arg": {"signed": "i64?", "unsigned": "u64?", "opaque": "str?", "reloc": "bool?", "branch_dest": "u64?"},
    "Relocation": {"type": "u32", "type_name": "str", "target_symbol": "u32", "addend": "i64"},
    "ArgDiff": {"diff_index": "u32?"},
    "DataSegment": {"kind": "DiffEnum", "data": "base64", "size": "u64"},
    "DataRelocation": {"relocation": "Relocation?", "kind": "DiffEnum", "start": "u64", "end": "u64"},
}


class ReportError(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(reason + ":" + detail)
        self.reason, self.detail = reason, detail


def _require(condition: bool, detail: str, reason: str = "report_schema_invalid") -> None:
    if not condition:
        raise ReportError(reason, detail)


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        _require(key not in out, "duplicate_key")
        out[key] = value
    return out


def _constant(value):
    raise ReportError("report_schema_invalid", "nonfinite_number")


def load_json(raw: bytes, *, limit: int = RAW_LIMIT, tick: Callable[[], None] = lambda: None, allow_null: bool = False):
    """Whole bounded JSON, rejecting duplicates/null/depth before schema decoding."""
    _require(type(raw) is bytes and len(raw) <= limit, "json_limit", "limit_exceeded")
    tick()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ReportError):
            raise
        raise ReportError("report_schema_invalid", "json") from exc
    stack = [(value, 0)]
    while stack:
        tick()
        item, depth = stack.pop()
        _require(depth <= 32 and (allow_null or item is not None), "depth_or_null")
        if type(item) is dict:
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, depth + 1) for v in item)
        elif type(item) is float:
            _require(math.isfinite(item), "nonfinite_number")
    return value


def _scalar(value, kind):
    if kind in ENUMS:
        _require(type(value) is str and value in ENUMS[kind], "enum")
    elif kind == "bool":
        _require(type(value) is bool, "boolean")
    elif kind == "u32":
        _require(type(value) is int and 0 <= value < 2**32, "u32")
    elif kind in ("u64", "i64"):
        _require(type(value) is str and re.fullmatch(r"0|[1-9][0-9]*|-?[1-9][0-9]*", value) is not None
                 and len(value) <= 20, kind)
        number = int(value)
        lo, hi = (0, 2**64) if kind == "u64" else (-2**63, 2**63)
        _require(lo <= number < hi, kind)
        return str(number)
    elif kind == "percent":
        _require(type(value) in (int, float) and 0 <= value <= 100 and math.isfinite(value), "percentage")
        return float(value)
    elif kind in ("str", "base64"):
        _require(type(value) is str, "string")
        try:
            _require(len(value.encode("utf-8")) <= (RAW_LIMIT if kind == "base64" else 4096), "string_limit")
            if kind == "base64":
                decoded = base64.b64decode(value, validate=True)
                _require(base64.b64encode(decoded).decode("ascii") == value, "base64")
        except (ValueError, UnicodeError) as exc:
            raise ReportError("report_schema_invalid", "string_encoding") from exc
    return value


def _decode(value, name, tick):
    tick()
    if name not in SCHEMA:
        return _scalar(value, name)
    fields = SCHEMA[name]
    _require(type(value) is dict and not (set(value) - set(fields)), name + "_fields")
    if name in ("Part", "Arg"):
        _require(len(value) == 1, "oneof")
    out = {}
    for key, spec in fields.items():
        repeated = spec.endswith("[]")
        optional = spec.endswith("?")
        required = spec.endswith("!")
        typ = spec[:-2] if repeated else spec.rstrip("?!")
        if key not in value:
            if optional:
                continue
            _require(not required, name + "_missing_" + key, "report_incomplete")
            if repeated:
                out[key] = []
            elif typ in ENUMS:
                out[key] = ENUMS[typ][0]
            else:
                out[key] = {"str": "", "base64": "", "u64": "0", "i64": "0", "u32": 0, "bool": False}[typ]
        elif repeated:
            _require(type(value[key]) is list, name + "_array")
            out[key] = [_decode(v, typ, tick) for v in value[key]]
        else:
            out[key] = _decode(value[key], typ, tick)
    return out


def parse_report(raw: bytes, symbol: str, left_tokens: list[dict], right_tokens: list[dict], *,
                 checker_grade: str, tick: Callable[[], None] = lambda: None) -> dict:
    """Decode every supported field and establish both complete token coverages.

    Matching counterparts must agree in their complete normalized report shape.
    Mismatch counterparts retain distinct tokens, opcodes, text and diff markers;
    each still has exactly one row per actual token and a reciprocal function.
    """
    report = _decode(load_json(raw, tick=tick), "DiffResult", tick)
    _require(checker_grade in ("matched", "mismatched"), "checker_grade")
    matched = checker_grade == "matched"
    for side, tokens in (("left", left_tokens), ("right", right_tokens)):
        tick()
        obj = report[side]
        size = sum(token["length"] for token in tokens)
        _require(len(obj["sections"]) == 1 and len(obj["symbols"]) == 2, "object_coverage", "report_incomplete")
        section = obj["sections"][0]
        expected_section = {"name": ".text", "kind": "SECTION_CODE", "size": str(size), "address": "0",
                            "data_diff": [], "reloc_diff": []}
        if side == "left":
            _require("match_percent" in section, "section_percentage", "report_incomplete")
            expected_section["match_percent"] = section["match_percent"]
            _require(not matched or section["match_percent"] == 100, "section_match")
        _require(section == expected_section, "section_shape", "report_incomplete")
        local = {key: key == "local" for key in FLAGS}
        _require(obj["symbols"][0] == {"name": "[.text]", "address": "0", "size": "0", "flags": local,
                 "kind": "SYMBOL_SECTION", "instructions": [], "data_diff": []}, "section_symbol")
        function = obj["symbols"][1]
        global_flags = {key: key in ("global", "size_inferred") for key in FLAGS}
        _require(function.get("name") == symbol and function.get("kind") == "SYMBOL_FUNCTION"
                 and function.get("address") == "0" and function.get("size") == str(size)
                 and function.get("flags") == global_flags and function.get("target_symbol") == 1
                 and "demangled_name" not in function and function["data_diff"] == []
                 and "match_percent" in function, "function_binding", "report_incomplete")
        _require(not matched or function["match_percent"] == 100, "function_match")
        rows = function["instructions"]
        _require(bool(tokens) and len(rows) == len(tokens), "instruction_coverage", "report_incomplete")
        for row, token in zip(rows, tokens):
            tick()
            instruction = row["instruction"]
            _require(set(instruction) == {"address", "size", "formatted", "parts"}, "instruction_dependency")
            _require(instruction["address"] == str(token["offset"]) and instruction["size"] == token["length"],
                     "instruction_extent", "report_incomplete")
            parts, operation = instruction["parts"], token["operation"]
            argc = {"nop": 0, "xor": 2, "inc": 1, "dec": 1, "ret": 0}[operation]
            _require(bool(parts) and "opcode" in parts[0], "opcode")
            opcode = parts[0]["opcode"]
            _require(opcode["mnemonic"] == operation and 0 < opcode["opcode"] < 65535, "opcode")
            # Upstream's Intel formatter emits basic comma and space parts; a
            # separator oneof is equivalent ordinary formatting when true.
            args, text = [], operation + " "
            for part in parts[1:]:
                if "arg" in part:
                    _require(part["arg"] == {"opaque": "eax"}, "operand")
                    args.append("eax")
                    text += "eax"
                elif "basic" in part:
                    _require(part["basic"] in (" ", ",", ", "), "formatting")
                    text += part["basic"]
                elif "separator" in part:
                    _require(part["separator"] is True, "separator")
                    text += ", "
                else:
                    raise ReportError("report_schema_invalid", "extra_opcode")
            _require(len(args) == argc and text == operation + " " + ", ".join(args)
                     and instruction["formatted"] == text, "formatted_operands")
            _require(not matched or row["diff_kind"] == "DIFF_NONE", "instruction_diff")
            _require(len(row["arg_diff"]) in (0, argc), "argument_diff_shape")
            _require(not matched or all(not arg for arg in row["arg_diff"]), "argument_diff")
    if matched:
        # The sole supported left/right asymmetry is the code-section percentage.
        left, right = report["left"], report["right"]
        _require(left["symbols"] == right["symbols"], "counterpart_shape")
        _require({k: v for k, v in left["sections"][0].items() if k != "match_percent"} == right["sections"][0],
                 "counterpart_section")
    return report
