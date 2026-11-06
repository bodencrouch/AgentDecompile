"""Shared dependency-closed x86-64 byte decoders."""
from __future__ import annotations

from typing import Any


def strip_alignment_padding(data: bytes) -> bytes:
    end = len(data)
    while end > 0 and data[end - 1] in {0x90, 0xCC}:
        end -= 1
    return data[:end]


X86_64_THREE_ARGS_ARITHMETIC_PATTERNS: dict[bytes, tuple[str, str, str]] = {
    b"\x8d\x04\x37\x01\xd0\xc3": ("add-add", "a + b + c", "lea-eax-rdi-rsi-add-eax-edx-ret"),
    b"\x29\xf7\x8d\x04\x17\xc3": ("sub-add", "a - b + c", "sub-edi-esi-lea-eax-rdi-rdx-ret"),
    b"\x89\xf8\x01\xd6\x29\xf0\xc3": ("sub-sum", "a - b - c", "mov-eax-edi-add-esi-edx-sub-eax-esi-ret"),
    b"\x89\xd0\x01\xf7\x29\xf8\xc3": ("sub-sum-reversed", "c - (a + b)", "mov-eax-edx-add-edi-esi-sub-eax-edi-ret"),
    b"\x0f\xaf\xfe\x8d\x04\x17\xc3": ("mul-add", "a * b + c", "imul-edi-esi-lea-eax-rdi-rdx-ret"),
    b"\x89\xf8\x0f\xaf\xc6\x29\xd0\xc3": ("mul-sub", "a * b - c", "mov-eax-edi-imul-eax-esi-sub-eax-edx-ret"),
    b"\x89\xd0\x0f\xaf\xfe\x29\xf8\xc3": ("sub-mul", "c - a * b", "mov-eax-edx-imul-edi-esi-sub-eax-edi-ret"),
}


def decode_x86_64_three_args_arithmetic(data: bytes) -> dict[str, str] | None:
    body = strip_alignment_padding(data)
    decoded = X86_64_THREE_ARGS_ARITHMETIC_PATTERNS.get(body)
    if decoded is None:
        return None
    suffix, expression, pattern = decoded
    return {"suffix": suffix, "expression": expression, "pattern": pattern}


X86_64_THREE_ARGS_BITWISE_OPS: dict[int, tuple[str, str]] = {
    0x21: ("and", "&"),
    0x09: ("or", "|"),
    0x31: ("xor", "^"),
}


def decode_x86_64_three_args_bitwise(data: bytes) -> dict[str, str] | None:
    body = strip_alignment_padding(data)
    if len(body) != 7 or body[:2] != b"\x89\xf8" or body[3] != 0xF0 or body[5:] != b"\xd0\xc3":
        return None
    first = X86_64_THREE_ARGS_BITWISE_OPS.get(body[2])
    second = X86_64_THREE_ARGS_BITWISE_OPS.get(body[4])
    if first is None or second is None:
        return None
    expression = f"(a {first[1]} b) {second[1]} c"
    return {
        "suffix": f"{first[0]}-{second[0]}",
        "expression": expression,
        "pattern": f"mov-eax-edi-{first[0]}-eax-esi-{second[0]}-eax-edx-ret",
    }


X86_64_THREE_ARGS_SELECT_OPS: dict[bytes, tuple[str, str, str, str, str]] = {
    b"\x89\xd0\x39\xf7\x0f\x42\xc7\xc3": ("uint-select-lt", "unsigned int", "a < b ? a : c", "cmovb", "mov-eax-edx-cmp-edi-esi-cmovb-eax-edi-ret"),
    b"\x89\xd0\x39\xf7\x0f\x43\xc7\xc3": ("uint-select-ge", "unsigned int", "a < b ? c : a", "cmovae", "mov-eax-edx-cmp-edi-esi-cmovae-eax-edi-ret"),
    b"\x89\xd0\x39\xf7\x0f\x47\xc7\xc3": ("uint-select-gt", "unsigned int", "a > b ? a : c", "cmova", "mov-eax-edx-cmp-edi-esi-cmova-eax-edi-ret"),
    b"\x89\xd0\x39\xf7\x0f\x46\xc7\xc3": ("uint-select-le", "unsigned int", "a > b ? c : a", "cmovbe", "mov-eax-edx-cmp-edi-esi-cmovbe-eax-edi-ret"),
    b"\x89\xd0\x39\xf7\x0f\x4c\xc7\xc3": ("int-select-lt", "int", "a < b ? a : c", "cmovl", "mov-eax-edx-cmp-edi-esi-cmovl-eax-edi-ret"),
    b"\x89\xd0\x39\xf7\x0f\x4d\xc7\xc3": ("int-select-ge", "int", "a < b ? c : a", "cmovge", "mov-eax-edx-cmp-edi-esi-cmovge-eax-edi-ret"),
    b"\x89\xd0\x39\xf7\x0f\x4f\xc7\xc3": ("int-select-gt", "int", "a > b ? a : c", "cmovg", "mov-eax-edx-cmp-edi-esi-cmovg-eax-edi-ret"),
    b"\x89\xd0\x39\xf7\x0f\x4e\xc7\xc3": ("int-select-le", "int", "a > b ? c : a", "cmovle", "mov-eax-edx-cmp-edi-esi-cmovle-eax-edi-ret"),
}


def decode_x86_64_three_args_select(data: bytes) -> dict[str, str] | None:
    body = strip_alignment_padding(data)
    decoded = X86_64_THREE_ARGS_SELECT_OPS.get(body)
    if decoded is None:
        return None
    suffix, value_type, expression, cmov, pattern = decoded
    return {
        "suffix": suffix,
        "valueType": value_type,
        "expression": expression,
        "cmov": cmov,
        "pattern": pattern,
    }


X86_64_THREE_ARGS_ARITHMETIC64_PATTERNS: dict[bytes, tuple[str, str, str]] = {
    b"\x48\x8d\x04\x37\x48\x01\xd0\xc3": ("add-add64", "a + b + c", "lea-rax-rdi-rsi-add-rax-rdx-ret"),
    b"\x48\x29\xf7\x48\x8d\x04\x17\xc3": ("sub-add64", "a - b + c", "sub-rdi-rsi-lea-rax-rdi-rdx-ret"),
    b"\x48\x89\xf8\x48\x01\xd6\x48\x29\xf0\xc3": ("sub-sum64", "a - b - c", "mov-rax-rdi-add-rsi-rdx-sub-rax-rsi-ret"),
    b"\x48\x89\xd0\x48\x01\xf7\x48\x29\xf8\xc3": ("sub-sum-reversed64", "c - (a + b)", "mov-rax-rdx-add-rdi-rsi-sub-rax-rdi-ret"),
    b"\x48\x0f\xaf\xfe\x48\x8d\x04\x17\xc3": ("mul-add64", "a * b + c", "imul-rdi-rsi-lea-rax-rdi-rdx-ret"),
    b"\x48\x89\xf8\x48\x0f\xaf\xc6\x48\x29\xd0\xc3": ("mul-sub64", "a * b - c", "mov-rax-rdi-imul-rax-rsi-sub-rax-rdx-ret"),
    b"\x48\x89\xd0\x48\x0f\xaf\xfe\x48\x29\xf8\xc3": ("sub-mul64", "c - a * b", "mov-rax-rdx-imul-rdi-rsi-sub-rax-rdi-ret"),
}


def decode_x86_64_three_args_arithmetic64(data: bytes) -> dict[str, str] | None:
    body = strip_alignment_padding(data)
    decoded = X86_64_THREE_ARGS_ARITHMETIC64_PATTERNS.get(body)
    if decoded is None:
        return None
    suffix, expression, pattern = decoded
    return {"suffix": suffix, "expression": expression, "pattern": pattern}


X86_64_THREE_ARGS_BITWISE64_OPS: dict[bytes, tuple[str, str]] = {
    b"\x48\x21\xf0": ("and", "&"),
    b"\x48\x09\xf0": ("or", "|"),
    b"\x48\x31\xf0": ("xor", "^"),
}


X86_64_THREE_ARGS_BITWISE64_OPS_SECOND: dict[bytes, tuple[str, str]] = {
    b"\x48\x21\xd0": ("and", "&"),
    b"\x48\x09\xd0": ("or", "|"),
    b"\x48\x31\xd0": ("xor", "^"),
}


def decode_x86_64_three_args_bitwise64(data: bytes) -> dict[str, str] | None:
    body = strip_alignment_padding(data)
    if len(body) != 10 or body[:3] != b"\x48\x89\xf8" or body[9:] != b"\xc3":
        return None
    first = X86_64_THREE_ARGS_BITWISE64_OPS.get(body[3:6])
    second = X86_64_THREE_ARGS_BITWISE64_OPS_SECOND.get(body[6:9])
    if first is None or second is None:
        return None
    expression = f"(a {first[1]} b) {second[1]} c"
    return {
        "suffix": f"{first[0]}-{second[0]}64",
        "expression": expression,
        "pattern": f"mov-rax-rdi-{first[0]}-rax-rsi-{second[0]}-rax-rdx-ret",
    }


X86_64_THREE_ARGS_SELECT64_OPS: dict[bytes, tuple[str, str, str, str, str]] = {
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x42\xc7\xc3": ("uint64-select-lt", "unsigned long long", "a < b ? a : c", "cmovb", "mov-rax-rdx-cmp-rdi-rsi-cmovb-rax-rdi-ret"),
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x43\xc7\xc3": ("uint64-select-ge", "unsigned long long", "a < b ? c : a", "cmovae", "mov-rax-rdx-cmp-rdi-rsi-cmovae-rax-rdi-ret"),
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x47\xc7\xc3": ("uint64-select-gt", "unsigned long long", "a > b ? a : c", "cmova", "mov-rax-rdx-cmp-rdi-rsi-cmova-rax-rdi-ret"),
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x46\xc7\xc3": ("uint64-select-le", "unsigned long long", "a > b ? c : a", "cmovbe", "mov-rax-rdx-cmp-rdi-rsi-cmovbe-rax-rdi-ret"),
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x4c\xc7\xc3": ("int64-select-lt", "long long", "a < b ? a : c", "cmovl", "mov-rax-rdx-cmp-rdi-rsi-cmovl-rax-rdi-ret"),
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x4d\xc7\xc3": ("int64-select-ge", "long long", "a < b ? c : a", "cmovge", "mov-rax-rdx-cmp-rdi-rsi-cmovge-rax-rdi-ret"),
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x4f\xc7\xc3": ("int64-select-gt", "long long", "a > b ? a : c", "cmovg", "mov-rax-rdx-cmp-rdi-rsi-cmovg-rax-rdi-ret"),
    b"\x48\x89\xd0\x48\x39\xf7\x48\x0f\x4e\xc7\xc3": ("int64-select-le", "long long", "a > b ? c : a", "cmovle", "mov-rax-rdx-cmp-rdi-rsi-cmovle-rax-rdi-ret"),
}


def decode_x86_64_three_args_select64(data: bytes) -> dict[str, str] | None:
    body = strip_alignment_padding(data)
    decoded = X86_64_THREE_ARGS_SELECT64_OPS.get(body)
    if decoded is None:
        return None
    suffix, value_type, expression, cmov, pattern = decoded
    return {
        "suffix": suffix,
        "valueType": value_type,
        "expression": expression,
        "cmov": cmov,
        "pattern": pattern,
    }


def format_x86_64_two_args_affine_expression(coeff_a: int, coeff_b: int, immediate: int) -> str:
    terms: list[str] = []
    if coeff_a == 1:
        terms.append("a")
    elif coeff_a > 1:
        terms.append(f"{coeff_a}u * a")
    if coeff_b == 1:
        terms.append("b")
    elif coeff_b > 1:
        terms.append(f"{coeff_b}u * b")
    if immediate:
        terms.append(f"0x{immediate:02x}u")
    return " + ".join(terms)


def decode_x86_64_two_args_affine_lea(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) < 4 or body[:2] != b"\x8d\x04":
        return None
    sib = body[2]
    scale = 1 << ((sib >> 6) & 0x03)
    index = (sib >> 3) & 0x07
    base = sib & 0x07
    register_names = {0x07: "a", 0x06: "b"}
    if base not in register_names or index not in register_names:
        return None
    coeffs = {"a": 0, "b": 0}
    coeffs[register_names[base]] += 1
    coeffs[register_names[index]] += scale
    immediate = 0
    suffix = "scaled"
    if len(body) == 4 and body[3] == 0xC3:
        pass
    elif len(body) == 6 and body[3:6] == b"\x01\xf8\xc3":
        coeffs["a"] += 1
        suffix = "scaled-add-a"
    elif len(body) == 7 and body[3:5] == b"\x83\xc0" and body[6] == 0xC3:
        immediate = body[5]
        if immediate == 0:
            return None
        suffix = "scaled-add-imm8"
    else:
        return None
    coeff_a = coeffs["a"]
    coeff_b = coeffs["b"]
    if coeff_a == 1 and coeff_b == 1 and immediate == 0:
        return None
    if coeff_a == 0 or coeff_b == 0:
        return None
    return {
        "suffix": suffix,
        "coeffA": coeff_a,
        "coeffB": coeff_b,
        "immediate": immediate,
        "expression": format_x86_64_two_args_affine_expression(coeff_a, coeff_b, immediate),
        "pattern": f"lea-eax-sib-0x{sib:02x}{'-add-eax-edi' if suffix == 'scaled-add-a' else '-add-eax-imm8' if suffix == 'scaled-add-imm8' else ''}-ret",
    }


def format_x86_64_two_args_affine_expression64(coeff_a: int, coeff_b: int, immediate: int) -> str:
    terms: list[str] = []
    if coeff_a == 1:
        terms.append("a")
    elif coeff_a > 1:
        terms.append(f"{coeff_a}ull * a")
    if coeff_b == 1:
        terms.append("b")
    elif coeff_b > 1:
        terms.append(f"{coeff_b}ull * b")
    if immediate:
        terms.append(f"0x{immediate:02x}ull")
    return " + ".join(terms)


def decode_x86_64_two_args_affine_lea64(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) < 5 or body[:3] != b"\x48\x8d\x04":
        return None
    sib = body[3]
    scale = 1 << ((sib >> 6) & 0x03)
    index = (sib >> 3) & 0x07
    base = sib & 0x07
    register_names = {0x07: "a", 0x06: "b"}
    if base not in register_names or index not in register_names:
        return None
    coeffs = {"a": 0, "b": 0}
    coeffs[register_names[base]] += 1
    coeffs[register_names[index]] += scale
    immediate = 0
    suffix = "scaled64"
    if len(body) == 5 and body[4] == 0xC3:
        pass
    elif len(body) == 8 and body[4:8] == b"\x48\x01\xf8\xc3":
        coeffs["a"] += 1
        suffix = "scaled-add-a64"
    elif len(body) == 9 and body[4:7] == b"\x48\x83\xc0" and body[8] == 0xC3:
        immediate = body[7]
        if immediate == 0:
            return None
        suffix = "scaled-add-imm8-64"
    else:
        return None
    coeff_a = coeffs["a"]
    coeff_b = coeffs["b"]
    if coeff_a == 1 and coeff_b == 1 and immediate == 0:
        return None
    if coeff_a == 0 or coeff_b == 0:
        return None
    return {
        "suffix": suffix,
        "coeffA": coeff_a,
        "coeffB": coeff_b,
        "immediate": immediate,
        "expression": format_x86_64_two_args_affine_expression64(coeff_a, coeff_b, immediate),
        "pattern": f"lea-rax-sib-0x{sib:02x}{'-add-rax-rdi' if suffix == 'scaled-add-a64' else '-add-rax-imm8' if suffix == 'scaled-add-imm8-64' else ''}-ret",
    }


X86_64_ARG_CONST_MIN_MAX_CMOV: dict[int, tuple[str, str, str, str, bool]] = {
    0x42: ("uint-min", "<", "unsigned int", "cmovb", False),
    0x43: ("uint-max", ">", "unsigned int", "cmovae", True),
    0x4C: ("int-min", "<", "int", "cmovl", False),
    0x4D: ("int-max", ">", "int", "cmovge", True),
}


def decode_x86_64_arg_const_min_max(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) != 12 or body[:2] != b"\x83\xff" or body[3] != 0xB8 or body[8] != 0x0F or body[10:12] != b"\xc7\xc3":
        return None
    decoded = X86_64_ARG_CONST_MIN_MAX_CMOV.get(body[9])
    if decoded is None:
        return None
    suffix, operator, value_type, cmov, compare_is_exclusive_upper = decoded
    compare_immediate = body[2]
    constant = int.from_bytes(body[4:8], "little", signed=False)
    if compare_is_exclusive_upper:
        if compare_immediate == 0:
            return None
        expected_constant = compare_immediate - 1
    else:
        expected_constant = compare_immediate
    if constant != expected_constant:
        return None
    if value_type == "int" and constant > 0x7F:
        return None
    return {
        "suffix": suffix,
        "operator": operator,
        "valueType": value_type,
        "returnType": value_type,
        "constant": constant,
        "compareImmediate": compare_immediate,
        "cmov": cmov,
        "pattern": f"cmp-edi-imm8-mov-eax-imm32-{cmov}-eax-edi-ret",
    }


def decode_x86_64_arg_bitmask_bool(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if body == b"\x89\xf8\x83\xe0\x01\xc3":
        return {
            "predicate": "nonzero",
            "operator": "!=",
            "mask": 0x00000001,
            "pattern": "mov-eax-edi-and-eax-1-ret",
        }
    if body == b"\x89\xf8\xf7\xd0\x83\xe0\x01\xc3":
        return {
            "predicate": "zero",
            "operator": "==",
            "mask": 0x00000001,
            "pattern": "mov-eax-edi-not-eax-and-eax-1-ret",
        }
    if len(body) == 9 and body[:3] == b"\x89\xf8\xc1" and body[3] == 0xE8 and body[5:8] == b"\x83\xe0\x01" and body[8] == 0xC3:
        shift = body[4]
        if not 1 <= shift <= 31:
            return None
        return {
            "predicate": "nonzero",
            "operator": "!=",
            "mask": 1 << shift,
            "shift": shift,
            "pattern": "mov-eax-edi-shr-eax-imm8-and-eax-1-ret",
        }
    if len(body) == 10 and body[:3] == b"\x31\xc0\x40" and body[3] == 0xF6 and body[4] == 0xC7 and body[6] == 0x0F and body[8:] == b"\xc0\xc3":
        mask = body[5]
        setcc_opcode = body[7]
        if mask == 0:
            return None
        if setcc_opcode == 0x94:
            predicate = "zero"
            operator = "=="
            setcc = "sete"
        elif setcc_opcode == 0x95:
            predicate = "nonzero"
            operator = "!="
            setcc = "setne"
        else:
            return None
        return {
            "predicate": predicate,
            "operator": operator,
            "mask": mask,
            "byteMask": mask,
            "setcc": setcc,
            "pattern": f"xor-eax-test-dil-imm8-{setcc}-al-ret",
        }
    if len(body) == 12 and body[:2] == b"\x31\xc0" and body[2:4] == b"\xf7\xc7" and body[8] == 0x0F and body[10:] == b"\xc0\xc3":
        mask = int.from_bytes(body[4:8], "little", signed=False)
        setcc_opcode = body[9]
        if mask == 0:
            return None
        if setcc_opcode == 0x94:
            predicate = "zero"
            operator = "=="
            setcc = "sete"
        elif setcc_opcode == 0x95:
            predicate = "nonzero"
            operator = "!="
            setcc = "setne"
        else:
            return None
        return {
            "predicate": predicate,
            "operator": operator,
            "mask": mask,
            "setcc": setcc,
            "pattern": f"xor-eax-test-edi-imm32-{setcc}-al-ret",
        }
    return None


def decode_x86_64_arg64_bitmask_bool(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if body == b"\x48\x89\xf8\x83\xe0\x01\xc3":
        return {
            "predicate": "nonzero",
            "operator": "!=",
            "mask": 0x0000000000000001,
            "pattern": "mov-rax-rdi-and-eax-1-ret",
        }
    if len(body) == 10 and body[:3] == b"\x48\x89\xf8" and body[3:5] == b"\xc1\xe8" and body[6:9] == b"\x83\xe0\x01" and body[9] == 0xC3:
        shift = body[5]
        if not 1 <= shift <= 31:
            return None
        return {
            "predicate": "nonzero",
            "operator": "!=",
            "mask": 1 << shift,
            "shift": shift,
            "pattern": "mov-rax-rdi-shr-eax-imm8-and-eax-1-ret",
        }
    if len(body) == 11 and body[:3] == b"\x48\x89\xf8" and body[3:6] == b"\x48\xc1\xe8" and body[7:10] == b"\x83\xe0\x01" and body[10] == 0xC3:
        shift = body[6]
        if not 32 <= shift <= 63:
            return None
        return {
            "predicate": "nonzero",
            "operator": "!=",
            "mask": 1 << shift,
            "shift": shift,
            "pattern": "mov-rax-rdi-shr-rax-imm8-and-eax-1-ret",
        }
    if len(body) == 10 and body[:3] == b"\x31\xc0\x40" and body[3] == 0xF6 and body[4] == 0xC7 and body[6] == 0x0F and body[8:] == b"\xc0\xc3":
        mask = body[5]
        setcc_opcode = body[7]
        if mask == 0:
            return None
        if setcc_opcode == 0x94:
            predicate = "zero"
            operator = "=="
            setcc = "sete"
        elif setcc_opcode == 0x95:
            predicate = "nonzero"
            operator = "!="
            setcc = "setne"
        else:
            return None
        return {
            "predicate": predicate,
            "operator": operator,
            "mask": mask,
            "byteMask": mask,
            "requiresWidthHint": True,
            "setcc": setcc,
            "pattern": f"xor-eax-test-dil-imm8-{setcc}-al-ret",
        }
    if len(body) == 12 and body[:2] == b"\x31\xc0" and body[2:4] == b"\xf7\xc7" and body[8] == 0x0F and body[10:] == b"\xc0\xc3":
        mask = int.from_bytes(body[4:8], "little", signed=False)
        setcc_opcode = body[9]
        if mask == 0:
            return None
        if setcc_opcode == 0x94:
            predicate = "zero"
            operator = "=="
            setcc = "sete"
        elif setcc_opcode == 0x95:
            predicate = "nonzero"
            operator = "!="
            setcc = "setne"
        else:
            return None
        return {
            "predicate": predicate,
            "operator": operator,
            "mask": mask,
            "requiresWidthHint": True,
            "setcc": setcc,
            "pattern": f"xor-eax-test-edi-imm32-{setcc}-al-ret",
        }
    return None


def decode_x86_64_arg_udiv_pow2(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 5 and body == b"\x89\xf8\xd1\xe8\xc3":
        return {"shift": 1, "divisor": 2, "pattern": "mov-eax-edi-shr-eax-one-ret"}
    if len(body) == 6 and body[:3] == b"\x89\xf8\xc1" and body[3] == 0xE8 and body[5] == 0xC3:
        shift = body[4]
        if not 2 <= shift <= 31:
            return None
        return {"shift": shift, "divisor": 1 << shift, "pattern": "mov-eax-edi-shr-eax-imm8-ret"}
    return None


def decode_x86_64_arg_urem_pow2(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) != 6 or body[:3] != b"\x89\xf8\x83" or body[3] != 0xE0 or body[5] != 0xC3:
        return None
    mask = body[4]
    if mask <= 1:
        return None
    divisor = mask + 1
    if divisor & (divisor - 1):
        return None
    return {
        "shift": divisor.bit_length() - 1,
        "divisor": divisor,
        "mask": mask,
        "pattern": "mov-eax-edi-and-eax-pow2-minus-one-ret",
    }


X86_64_ARG_UDIV_MAGIC_OPS: dict[tuple[int, int], tuple[int, str]] = {
    (0xAAAAAAAB, 0x21): (3, "mov-ecx-edi-mov-eax-magic-imul-rax-rcx-shr-rax-33-ret"),
    (0xCCCCCCCD, 0x22): (5, "mov-ecx-edi-mov-eax-magic-imul-rax-rcx-shr-rax-34-ret"),
    (0xCCCCCCCD, 0x23): (10, "mov-ecx-edi-mov-eax-magic-imul-rax-rcx-shr-rax-35-ret"),
}


def decode_x86_64_arg_udiv_magic(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) != 16 or body[:2] != b"\x89\xf9" or body[2] != 0xB8 or body[7:11] != b"\x48\x0f\xaf\xc1" or body[11:14] != b"\x48\xc1\xe8" or body[15] != 0xC3:
        return None
    multiplier = int.from_bytes(body[3:7], "little", signed=False)
    shift = body[14]
    decoded = X86_64_ARG_UDIV_MAGIC_OPS.get((multiplier, shift))
    if decoded is None:
        return None
    divisor, pattern = decoded
    return {"divisor": divisor, "multiplier": multiplier, "shift": shift, "pattern": pattern}


X86_64_ARG_UREM_MAGIC_OPS: dict[bytes, tuple[int, str, int, str]] = {
    bytes.fromhex("89f889f9baabaaaaaa480fafd148c1ea218d0c5229c8c3"): (3, "0xaaaaaaab", 33, "mov-eax-edi-mov-ecx-edi-mov-edx-magic-imul-rdx-rcx-shr-rdx-33-lea-ecx-rdx-rdx2-sub-eax-ecx-ret"),
    bytes.fromhex("89f889f9bacdcccccc480fafd148c1ea228d0c9229c8c3"): (5, "0xcccccccd", 34, "mov-eax-edi-mov-ecx-edi-mov-edx-magic-imul-rdx-rcx-shr-rdx-34-lea-ecx-rdx-rdx4-sub-eax-ecx-ret"),
    bytes.fromhex("89f889f9bacdcccccc480fafd148c1ea2301d28d0c9229c8c3"): (10, "0xcccccccd", 35, "mov-eax-edi-mov-ecx-edi-mov-edx-magic-imul-rdx-rcx-shr-rdx-35-add-edx-edx-lea-ecx-rdx-rdx4-sub-eax-ecx-ret"),
}


def decode_x86_64_arg_urem_magic(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    decoded = X86_64_ARG_UREM_MAGIC_OPS.get(body)
    if decoded is None:
        return None
    divisor, multiplier, shift, pattern = decoded
    return {
        "divisor": divisor,
        "multiplier": multiplier,
        "shift": shift,
        "pattern": pattern,
    }


def decode_x86_64_arg_sdiv_pow2(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if body == b"\x89\xf8\xc1\xe8\x1f\x01\xf8\xd1\xf8\xc3":
        return {
            "shift": 1,
            "divisor": 2,
            "bias": 1,
            "pattern": "mov-eax-edi-shr-eax-31-add-eax-edi-sar-eax-one-ret",
        }
    if len(body) == 12 and body[:2] == b"\x8d\x47" and body[3:8] == b"\x85\xff\x0f\x49\xc7" and body[8:10] == b"\xc1\xf8" and body[11] == 0xC3:
        bias = body[2]
        shift = body[10]
        if not 2 <= shift <= 7:
            return None
        if bias != (1 << shift) - 1:
            return None
        return {
            "shift": shift,
            "divisor": 1 << shift,
            "bias": bias,
            "pattern": "lea-eax-rdi-bias-test-edi-edi-cmovns-eax-edi-sar-eax-imm8-ret",
        }
    return None


def decode_x86_64_arg_srem_pow2(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if body == b"\x89\xf8\x89\xf9\xc1\xe9\x1f\x01\xf9\x83\xe1\xfe\x29\xc8\xc3":
        return {
            "shift": 1,
            "divisor": 2,
            "bias": 1,
            "mask": "0xfffffffe",
            "pattern": "mov-eax-edi-mov-ecx-edi-shr-ecx-31-add-ecx-edi-and-ecx-neg2-sub-eax-ecx-ret",
        }
    if len(body) == 16 and body[:2] == b"\x89\xf8" and body[2:4] == b"\x8d\x48" and body[5:10] == b"\x85\xff\x0f\x49\xcf" and body[10:12] == b"\x83\xe1" and body[13:] == b"\x29\xc8\xc3":
        bias = body[4]
        mask_byte = body[12]
        if bias == 0:
            return None
        divisor = bias + 1
        if divisor & (divisor - 1):
            return None
        shift = divisor.bit_length() - 1
        if not 2 <= shift <= 7:
            return None
        if mask_byte != ((256 - divisor) & 0xFF):
            return None
        return {
            "shift": shift,
            "divisor": divisor,
            "bias": bias,
            "mask": f"0xffffff{mask_byte:02x}",
            "pattern": "mov-eax-edi-lea-ecx-rax-bias-test-edi-edi-cmovns-ecx-edi-and-ecx-negdivisor-sub-eax-ecx-ret",
        }
    return None


X86_64_ARG_SDIV_MAGIC_OPS: dict[bytes, tuple[int, str, int, str]] = {
    bytes.fromhex("4863c74869c0565555554889c148c1e93f48c1e82001c8c3"): (3, "0x55555556", 32, "movsxd-rax-edi-imul-rax-rax-magic-mov-rcx-rax-shr-rcx-63-shr-rax-32-add-eax-ecx-ret"),
    bytes.fromhex("4863c74869c0676666664889c148c1e93f48c1f82101c8c3"): (5, "0x66666667", 33, "movsxd-rax-edi-imul-rax-rax-magic-mov-rcx-rax-shr-rcx-63-sar-rax-33-add-eax-ecx-ret"),
    bytes.fromhex("4863c74869c0676666664889c148c1e93f48c1f82201c8c3"): (10, "0x66666667", 34, "movsxd-rax-edi-imul-rax-rax-magic-mov-rcx-rax-shr-rcx-63-sar-rax-34-add-eax-ecx-ret"),
}


def decode_x86_64_arg_sdiv_magic(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    decoded = X86_64_ARG_SDIV_MAGIC_OPS.get(body)
    if decoded is None:
        return None
    divisor, multiplier, shift, pattern = decoded
    return {
        "divisor": divisor,
        "multiplier": multiplier,
        "shift": shift,
        "pattern": pattern,
    }


X86_64_ARG_SREM_MAGIC_OPS: dict[bytes, tuple[int, str, int, str]] = {
    bytes.fromhex("4863c74869c8565555554889ca48c1ea3f48c1e92001d18d0c4929c8c3"): (3, "0x55555556", 32, "movsxd-rax-edi-imul-rcx-rax-magic-mov-rdx-rcx-shr-rdx-63-shr-rcx-32-add-ecx-edx-lea-ecx-rcx-rcx2-sub-eax-ecx-ret"),
    bytes.fromhex("4863c74869c8676666664889ca48c1ea3f48c1f92101d18d0c8929c8c3"): (5, "0x66666667", 33, "movsxd-rax-edi-imul-rcx-rax-magic-mov-rdx-rcx-shr-rdx-63-sar-rcx-33-add-ecx-edx-lea-ecx-rcx-rcx4-sub-eax-ecx-ret"),
    bytes.fromhex("4863c74869c8676666664889ca48c1ea3f48c1f92201d101c98d0c8929c8c3"): (10, "0x66666667", 34, "movsxd-rax-edi-imul-rcx-rax-magic-mov-rdx-rcx-shr-rdx-63-sar-rcx-34-add-ecx-edx-add-ecx-ecx-lea-ecx-rcx-rcx4-sub-eax-ecx-ret"),
}


def decode_x86_64_arg_srem_magic(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    decoded = X86_64_ARG_SREM_MAGIC_OPS.get(body)
    if decoded is None:
        return None
    divisor, multiplier, shift, pattern = decoded
    return {
        "divisor": divisor,
        "multiplier": multiplier,
        "shift": shift,
        "pattern": pattern,
    }


def decode_x86_64_arg_bswap32(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if body == b"\x89\xf8\x0f\xc8\xc3":
        return {"pattern": "mov-eax-edi-bswap-eax-ret"}
    return None


def decode_x86_64_arg_bswap64(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if body == b"\x48\x89\xf8\x48\x0f\xc8\xc3":
        return {"pattern": "mov-rax-rdi-bswap-rax-ret"}
    return None


def decode_x86_64_arg_rotate(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 5 and body[:2] == b"\x89\xf8" and body[2] == 0xD1 and body[4] == 0xC3:
        if body[3] == 0xC0:
            return {"direction": "left", "count": 1, "encoding": "rol", "pattern": "mov-eax-edi-rol-eax-one-ret"}
        if body[3] == 0xC8:
            return {"direction": "right", "count": 1, "encoding": "ror", "pattern": "mov-eax-edi-ror-eax-one-ret"}
    if len(body) == 6 and body[:2] == b"\x89\xf8" and body[2] == 0xC1 and body[3] == 0xC0 and body[5] == 0xC3:
        count = body[4]
        if not 1 <= count <= 31:
            return None
        if count > 16:
            return {"direction": "right", "count": 32 - count, "encoding": "rol", "encodedCount": count, "pattern": "mov-eax-edi-rol-eax-imm8-ret"}
        return {"direction": "left", "count": count, "encoding": "rol", "encodedCount": count, "pattern": "mov-eax-edi-rol-eax-imm8-ret"}
    return None


def decode_x86_64_arg64_rotate(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 7 and body[:3] == b"\x48\x89\xf8" and body[3:5] == b"\x48\xd1" and body[6] == 0xC3:
        if body[5] == 0xC0:
            return {"direction": "left", "count": 1, "encoding": "rol", "pattern": "mov-rax-rdi-rol-rax-one-ret"}
        if body[5] == 0xC8:
            return {"direction": "right", "count": 1, "encoding": "ror", "pattern": "mov-rax-rdi-ror-rax-one-ret"}
    if len(body) == 8 and body[:3] == b"\x48\x89\xf8" and body[3:6] == b"\x48\xc1\xc0" and body[7] == 0xC3:
        count = body[6]
        if not 1 <= count <= 63:
            return None
        if count > 32:
            return {"direction": "right", "count": 64 - count, "encoding": "rol", "encodedCount": count, "pattern": "mov-rax-rdi-rol-rax-imm8-ret"}
        return {"direction": "left", "count": count, "encoding": "rol", "encodedCount": count, "pattern": "mov-rax-rdi-rol-rax-imm8-ret"}
    return None


X86_64_ARG_IMM8_BINARY_OPS: dict[int, tuple[str, str]] = {
    0xE0: ("and", "&"),
    0xC8: ("or", "|"),
    0xF0: ("xor", "^"),
}


X86_64_ARG_ACCUM_IMM32_BINARY_OPS: dict[int, tuple[str, str]] = {
    0x25: ("and", "&"),
    0x0D: ("or", "|"),
    0x35: ("xor", "^"),
}


def decode_x86_64_arg_imm8_binary_op(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 4 and body[:2] == b"\x8d\x47" and body[3] == 0xC3:
        raw_immediate = body[2]
        signed_immediate = raw_immediate if raw_immediate < 0x80 else raw_immediate - 0x100
        if signed_immediate == 0:
            return None
        suffix = "add" if signed_immediate > 0 else "sub"
        operator = "+" if signed_immediate > 0 else "-"
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": abs(signed_immediate),
            "rawImmediate": raw_immediate,
            "signedImmediate": signed_immediate,
            "immediateBits": 8,
            "pattern": "lea-eax-rdi-disp8-ret",
        }
    if len(body) == 7 and body[:2] == b"\x8d\x87" and body[6] == 0xC3:
        raw_immediate = int.from_bytes(body[2:6], "little", signed=False)
        signed_immediate = int.from_bytes(body[2:6], "little", signed=True)
        if signed_immediate == 0:
            return None
        suffix = "add" if signed_immediate > 0 else "sub"
        operator = "+" if signed_immediate > 0 else "-"
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": abs(signed_immediate),
            "rawImmediate": raw_immediate,
            "signedImmediate": signed_immediate,
            "immediateBits": 32,
            "pattern": "lea-eax-rdi-disp32-ret",
        }
    if len(body) == 6 and body[:3] == b"\x89\xf8\x83" and body[5] == 0xC3:
        decoded = X86_64_ARG_IMM8_BINARY_OPS.get(body[3])
        if decoded is None:
            return None
        raw_immediate = body[4]
        if raw_immediate > 0x7F:
            return None
        suffix, operator = decoded
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": raw_immediate,
            "rawImmediate": raw_immediate,
            "signedImmediate": raw_immediate,
            "immediateBits": 8,
            "pattern": "mov-eax-edi-op-eax-imm8-ret",
        }
    if len(body) == 8 and body[:2] == b"\x89\xf8" and body[7] == 0xC3:
        decoded = X86_64_ARG_ACCUM_IMM32_BINARY_OPS.get(body[2])
        if decoded is None:
            return None
        raw_immediate = int.from_bytes(body[3:7], "little", signed=False)
        if raw_immediate == 0 and decoded[0] in {"or", "xor"}:
            return None
        suffix, operator = decoded
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": raw_immediate,
            "rawImmediate": raw_immediate,
            "signedImmediate": int.from_bytes(body[3:7], "little", signed=True),
            "immediateBits": 32,
            "pattern": "mov-eax-edi-accum-op-eax-imm32-ret",
        }
    return None


X86_64_ARG_IMM32_BINARY64_OPS: dict[int, tuple[str, str]] = {
    0x25: ("and", "&"),
    0x0D: ("or", "|"),
    0x35: ("xor", "^"),
}


def decode_x86_64_arg_imm32_binary_op64(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 5 and body[:3] == b"\x48\x8d\x47" and body[4] == 0xC3:
        raw_immediate = body[3]
        signed_immediate = int.from_bytes(body[3:4], "little", signed=True)
        if signed_immediate == 0:
            return None
        suffix = "add" if signed_immediate > 0 else "sub"
        operator = "+" if signed_immediate > 0 else "-"
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": abs(signed_immediate),
            "rawImmediate": raw_immediate,
            "signedImmediate": signed_immediate,
            "immediateBits": 8,
            "pattern": "lea-rax-rdi-disp8-ret",
        }
    if len(body) == 8 and body[:3] == b"\x48\x8d\x87" and body[7] == 0xC3:
        raw_immediate = int.from_bytes(body[3:7], "little", signed=False)
        signed_immediate = int.from_bytes(body[3:7], "little", signed=True)
        if signed_immediate == 0:
            return None
        suffix = "add" if signed_immediate > 0 else "sub"
        operator = "+" if signed_immediate > 0 else "-"
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": abs(signed_immediate),
            "rawImmediate": raw_immediate,
            "signedImmediate": signed_immediate,
            "immediateBits": 32,
            "pattern": "lea-rax-rdi-disp32-ret",
        }
    if len(body) == 10 and body[:3] == b"\x48\x89\xf8" and body[3] == 0x48 and body[9] == 0xC3:
        decoded = X86_64_ARG_IMM32_BINARY64_OPS.get(body[4])
        if decoded is None or decoded[0] == "and":
            return None
        raw_immediate = int.from_bytes(body[5:9], "little", signed=False)
        if raw_immediate == 0:
            return None
        suffix, operator = decoded
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": raw_immediate,
            "rawImmediate": raw_immediate,
            "signedImmediate": int.from_bytes(body[5:9], "little", signed=True),
            "immediateBits": 32,
            "pattern": "mov-rax-rdi-rex-accum-op-rax-imm32-ret",
        }
    if len(body) == 9 and body[:3] == b"\x48\x89\xf8" and body[8] == 0xC3:
        decoded = X86_64_ARG_IMM32_BINARY64_OPS.get(body[3])
        if decoded is None or decoded[0] != "and":
            return None
        raw_immediate = int.from_bytes(body[4:8], "little", signed=False)
        suffix, operator = decoded
        return {
            "suffix": suffix,
            "operator": operator,
            "immediate": raw_immediate,
            "rawImmediate": raw_immediate,
            "signedImmediate": int.from_bytes(body[4:8], "little", signed=True),
            "immediateBits": 32,
            "pattern": "mov-rax-rdi-and-eax-imm32-ret",
        }
    return None


def decode_x86_64_arg_narrow_imm8_compare(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 10 and body[:3] == b"\x31\xc0\x40" and body[3] == 0x80 and body[4] == 0xFF and body[6] == 0x0F and body[8:] == b"\xc0\xc3":
        width = 8
        immediate = body[5]
        setcc_opcode = body[7]
    elif len(body) == 10 and body[:3] == b"\x31\xc0\x66" and body[3] == 0x83 and body[4] == 0xFF and body[6] == 0x0F and body[8:] == b"\xc0\xc3":
        width = 16
        immediate = body[5]
        setcc_opcode = body[7]
    else:
        return None
    if setcc_opcode in X86_64_UNSIGNED_COMPARE_SETCC:
        suffix, operator, setcc = X86_64_UNSIGNED_COMPARE_SETCC[setcc_opcode]
        signed = False
    elif setcc_opcode in X86_64_SIGNED_COMPARE_SETCC:
        suffix, operator, setcc = X86_64_SIGNED_COMPARE_SETCC[setcc_opcode]
        signed = True
    else:
        return None
    cast_type = {
        (8, False): "unsigned char",
        (8, True): "signed char",
        (16, False): "unsigned short",
        (16, True): "short",
    }[(width, signed)]
    value_type = "int" if signed else "unsigned int"
    expression_immediate = immediate if not signed or immediate < 0x80 else immediate - 0x100
    return {
        "suffix": suffix,
        "operator": operator,
        "setcc": setcc,
        "width": width,
        "signed": signed,
        "castType": cast_type,
        "valueType": value_type,
        "immediate": expression_immediate,
        "rawImmediate": immediate,
        "pattern": f"xor-eax-cmp-{'dil' if width == 8 else 'di'}-imm8-setcc-al-ret",
    }


def decode_x86_64_arg_narrow_movzx_imm8_compare(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 13 and body[:8] == b"\x40\x0f\xb6\xcf\x31\xc0\x83\xf9" and body[9] == 0x0F and body[11:] == b"\xc0\xc3":
        width = 8
        immediate = body[8]
        setcc_opcode = body[10]
        movzx = "movzx-ecx-dil"
    elif len(body) == 12 and body[:7] == b"\x0f\xb7\xcf\x31\xc0\x83\xf9" and body[8] == 0x0F and body[10:] == b"\xc0\xc3":
        width = 16
        immediate = body[7]
        setcc_opcode = body[9]
        movzx = "movzx-ecx-di"
    else:
        return None
    decoded = X86_64_UNSIGNED_COMPARE_SETCC.get(setcc_opcode)
    if decoded is None:
        return None
    suffix, operator, setcc = decoded
    if suffix not in {"lt", "ge"}:
        return None
    cast_type = "unsigned char" if width == 8 else "unsigned short"
    return {
        "suffix": suffix,
        "operator": operator,
        "setcc": setcc,
        "width": width,
        "castType": cast_type,
        "valueType": "unsigned int",
        "rawImmediate": immediate,
        "pattern": f"{movzx}-xor-eax-cmp-ecx-imm8-setcc-al-ret",
    }


def decode_x86_64_arg_imm8_compare(data: bytes, *, signed: bool) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    immediate_bits = 0
    raw_immediate = 0
    immediate = 0
    setcc_offset = 0
    if len(body) == 9 and body[:4] == b"\x31\xc0\x83\xff" and body[5] == 0x0F and body[7:] == b"\xc0\xc3":
        immediate_bits = 8
        raw_immediate = body[4]
        immediate = raw_immediate if raw_immediate < 0x80 else (raw_immediate - 0x100 if signed else raw_immediate | 0xFFFFFF00)
        setcc_offset = 6
        pattern = "xor-eax-cmp-edi-imm8-setcc-al-ret"
    elif len(body) == 12 and body[:4] == b"\x31\xc0\x81\xff" and body[8] == 0x0F and body[10:] == b"\xc0\xc3":
        immediate_bits = 32
        raw_immediate = int.from_bytes(body[4:8], "little", signed=False)
        immediate = int.from_bytes(body[4:8], "little", signed=signed)
        setcc_offset = 9
        pattern = "xor-eax-cmp-edi-imm32-setcc-al-ret"
    else:
        return None
    rules = X86_64_SIGNED_COMPARE_SETCC if signed else X86_64_UNSIGNED_COMPARE_SETCC
    decoded = rules.get(body[setcc_offset])
    if decoded is None:
        return None
    suffix, operator, setcc = decoded
    return {
        "suffix": suffix,
        "operator": operator,
        "setcc": setcc,
        "immediate": immediate,
        "rawImmediate": raw_immediate,
        "immediateBits": immediate_bits,
        "pattern": pattern,
    }


def normalize_x86_64_arg_imm8_compare_operator(
    operator: str,
    immediate: int,
    *,
    signed: bool,
) -> tuple[str, int]:
    if operator not in {"<=", ">"}:
        return operator, immediate

    overflow_limit = 0x7FFFFFFF if signed else 0xFFFFFFFF
    if immediate >= overflow_limit:
        return operator, immediate

    next_immediate = immediate + 1
    if operator == "<=" and immediate < overflow_limit:
        return "<", next_immediate
    if operator == ">" and immediate < overflow_limit:
        return ">=", next_immediate
    return operator, immediate


X86_64_UNSIGNED_COMPARE_SETCC: dict[int, tuple[str, str, str]] = {
    0x92: ("lt", "<", "setb"),
    0x93: ("ge", ">=", "setae"),
    0x94: ("eq", "==", "sete"),
    0x95: ("ne", "!=", "setne"),
    0x96: ("le", "<=", "setbe"),
    0x97: ("gt", ">", "seta"),
}


X86_64_SIGNED_COMPARE_SETCC: dict[int, tuple[str, str, str]] = {
    0x9C: ("lt", "<", "setl"),
    0x9D: ("ge", ">=", "setge"),
    0x9E: ("le", "<=", "setle"),
    0x9F: ("gt", ">", "setg"),
}


def decode_x86_64_two_args_compare(data: bytes, rules: dict[int, tuple[str, str, str]]) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) != 8 or body[:4] != b"\x31\xc0\x39\xf7" or body[4] != 0x0F or body[6:] != b"\xc0\xc3":
        return None
    decoded = rules.get(body[5])
    if decoded is None:
        return None
    suffix, operator, setcc = decoded
    return {
        "suffix": suffix,
        "operator": operator,
        "setcc": setcc,
    }


def decode_x86_64_two_args_compare64(data: bytes, rules: dict[int, tuple[str, str, str]]) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) != 9 or body[:5] != b"\x31\xc0\x48\x39\xf7" or body[5] != 0x0F or body[7:] != b"\xc0\xc3":
        return None
    decoded = rules.get(body[6])
    if decoded is None:
        return None
    suffix, operator, setcc = decoded
    return {
        "suffix": suffix,
        "operator": operator,
        "setcc": setcc,
    }


X86_64_SIGNED_ZERO_COMPARE_SETCC: dict[int, tuple[str, str, str]] = {
    0x9E: ("le", "<=", "setle"),
    0x9F: ("gt", ">", "setg"),
}


def decode_x86_64_arg_signed_zero_compare(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) != 8 or body[:4] != b"\x31\xc0\x85\xff" or body[4] != 0x0F or body[6:] != b"\xc0\xc3":
        return None
    decoded = X86_64_SIGNED_ZERO_COMPARE_SETCC.get(body[5])
    if decoded is None:
        return None
    suffix, operator, setcc = decoded
    return {
        "suffix": suffix,
        "operator": operator,
        "setcc": setcc,
        "pattern": "xor-eax-test-edi-edi-setcc-al-ret",
    }


def decode_x86_64_arg_nonzero_const_select(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) != 15 or body[:4] != b"\x31\xc0\x85\xff" or body[4] != 0x0F or body[6:9] != b"\xc0\x8d\x04" or body[14] != 0xC3:
        return None
    setcc_opcode = body[5]
    if setcc_opcode not in {0x94, 0x95}:
        return None
    sib = body[9]
    if sib & 0x07 != 0x05 or ((sib >> 3) & 0x07) != 0x00:
        return None
    scale = 1 << ((sib >> 6) & 0x03)
    if scale not in {2, 4, 8}:
        return None
    base_value = int.from_bytes(body[10:14], "little", signed=False)
    scaled_value = base_value + scale
    if setcc_opcode == 0x95:
        false_value = base_value
        true_value = scaled_value
        setcc = "setne"
    else:
        false_value = scaled_value
        true_value = base_value
        setcc = "sete"
    return {
        "trueValue": true_value,
        "falseValue": false_value,
        "baseValue": base_value,
        "scale": scale,
        "setcc": setcc,
        "pattern": f"xor-eax-test-edi-edi-{setcc}-al-lea-eax-rax{scale}-disp32-ret",
    }


def decode_x86_64_arg_nonzero_cmov_const_select(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if len(body) == 11 and body[:2] == b"\x85\xff" and body[2] == 0xB8 and body[7:10] == b"\x0f\x44\xc7" and body[10] == 0xC3:
        immediate = int.from_bytes(body[3:7], "little", signed=False)
        if immediate == 0:
            return None
        return {
            "trueValue": immediate,
            "falseValue": 0,
            "immediate": immediate,
            "cmov": "cmove",
            "pattern": "test-edi-edi-mov-eax-imm32-cmove-eax-edi-ret",
        }
    if len(body) == 13 and body[:4] == b"\x31\xc9\x85\xff" and body[4] == 0xB8 and body[9:12] == b"\x0f\x45\xc1" and body[12] == 0xC3:
        immediate = int.from_bytes(body[5:9], "little", signed=False)
        if immediate == 0:
            return None
        return {
            "trueValue": 0,
            "falseValue": immediate,
            "immediate": immediate,
            "cmov": "cmovne",
            "pattern": "xor-ecx-ecx-test-edi-edi-mov-eax-imm32-cmovne-eax-ecx-ret",
        }
    return None


def decode_x86_64_arg_mask(data: bytes) -> dict[str, Any] | None:
    body = strip_alignment_padding(data)
    if body == b"\x31\xc0\xf7\xdf\x19\xc0\xc3":
        return {
            "suffix": "nonzero",
            "operator": "!=",
            "immediate": 0,
            "expression": "value != 0",
            "valueType": "unsigned int",
            "returnType": "unsigned int",
            "trueLiteral": "0xffffffffu",
            "falseLiteral": "0u",
            "pattern": "xor-eax-neg-edi-sbb-eax-eax-ret",
        }
    if len(body) == 8 and body[:4] == b"\x31\xc0\x83\xff" and body[6:] == b"\xc0\xc3":
        immediate = body[4]
        opcode = body[5]
        if opcode == 0x19:
            return {
                "suffix": "uint-lt-imm8",
                "operator": "<",
                "immediate": immediate,
                "expression": f"value < 0x{immediate:02x}u",
                "valueType": "unsigned int",
                "returnType": "unsigned int",
                "trueLiteral": "0xffffffffu",
                "falseLiteral": "0u",
                "pattern": "xor-eax-cmp-edi-imm8-sbb-eax-eax-ret",
            }
    if len(body) == 9 and body[:4] == b"\x31\xc0\x83\xff" and body[5:8] == b"\x83\xd0\xff" and body[8] == 0xC3:
        immediate = body[4]
        return {
            "suffix": "uint-ge-imm8",
            "operator": ">=",
            "immediate": immediate,
            "expression": f"value >= 0x{immediate:02x}u",
            "valueType": "unsigned int",
            "returnType": "unsigned int",
            "trueLiteral": "0xffffffffu",
            "falseLiteral": "0u",
            "pattern": "xor-eax-cmp-edi-imm8-adc-eax-minus-one-ret",
        }
    if len(body) == 11 and body[:4] == b"\x31\xc0\x83\xff" and body[5] == 0x0F and body[7:] == b"\xc0\xf7\xd8\xc3":
        raw_immediate = body[4]
        setcc_opcode = body[6]
        if setcc_opcode in {0x94, 0x95}:
            suffix, operator, setcc = X86_64_UNSIGNED_COMPARE_SETCC[setcc_opcode]
            return {
                "suffix": f"uint-{suffix}-imm8",
                "operator": operator,
                "immediate": raw_immediate,
                "expression": f"value {operator} 0x{raw_immediate:02x}u",
                "valueType": "unsigned int",
                "returnType": "unsigned int",
                "trueLiteral": "0xffffffffu",
                "falseLiteral": "0u",
                "setcc": setcc,
                "pattern": f"xor-eax-cmp-edi-imm8-{setcc}-al-neg-eax-ret",
            }
        decoded_signed = X86_64_SIGNED_COMPARE_SETCC.get(setcc_opcode)
        if decoded_signed is not None:
            suffix, operator, setcc = decoded_signed
            signed_immediate = raw_immediate if raw_immediate < 0x80 else raw_immediate - 0x100
            return {
                "suffix": f"int-{suffix}-imm8",
                "operator": operator,
                "immediate": signed_immediate,
                "rawImmediate": raw_immediate,
                "expression": f"value {operator} {signed_immediate}",
                "valueType": "int",
                "returnType": "int",
                "trueLiteral": "-1",
                "falseLiteral": "0",
                "setcc": setcc,
                "pattern": f"xor-eax-cmp-edi-imm8-{setcc}-al-neg-eax-ret",
            }
    return None
