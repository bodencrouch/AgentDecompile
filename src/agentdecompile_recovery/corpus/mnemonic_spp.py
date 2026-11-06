"""Mnemonic small-prime-product signatures (BinDiff-style Phase 3).

Instruction composition is hashed without regard to operand order: each
mnemonic class gets a fixed prime, and a function's bag of instructions
is the product of those primes. Reordering the same bag does not change
the product. A separate sequence hash keeps order when the caller needs
it. Candidate filtering keeps destinations whose product matches the
source.

Class names follow `mnemonic_class` in `.features` so x86/ARM aliases
(mov/movl/ldr, xor/eor, call/bl) collapse the same way. Keys that are
already classed (as stored on func-row `mnem` maps) are used as-is.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .features import mnemonic_class

# Fixed primes, not drawn at runtime. Order is the classes named in the
# Phase 3 brief, then the rest of the `mnemonic_class` inventory.
CLASS_PRIMES: dict[str, int] = {
    "MOV": 2,
    "STORE": 3,
    "ARITH": 5,
    "CALL": 7,
    "RET": 11,
    "CBRANCH": 13,
    "JMP": 17,
    "LOGIC": 19,
    "SHIFT": 23,
    "CMP": 29,
    "LEA": 31,
    "PUSH": 37,
    "POP": 41,
    "MUL": 43,
    "DIV": 47,
    "FCMP": 53,
    "LEAVE": 59,
    "NOP": 61,
    "FLOAT": 67,
    "FCVT": 71,
    "COND": 73,
    "STRINGOP": 79,
    "OTHER": 83,
}

_OTHER_PRIME = CLASS_PRIMES["OTHER"]
_FUNC_HINTS = frozenset(
    {"id", "addr", "name", "n_instr", "callees", "callee_addrs", "strings"}
)


def _class_key(token: str) -> str:
    text = str(token).strip()
    if not text:
        return "OTHER"
    if text in CLASS_PRIMES:
        return text
    folded = text.upper()
    if folded in CLASS_PRIMES:
        return folded
    return mnemonic_class(text)


def _prime_for(token: str) -> int:
    return CLASS_PRIMES.get(_class_key(token), _OTHER_PRIME)


def _count_of(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _instr_len(mnem: Mapping[str, Any] | None) -> int:
    if not mnem:
        return 0
    return sum(n for n in (_count_of(value) for value in mnem.values()) if n > 0)


def _count_map(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Accept a raw mnemonic->count map or a func row with optional `mnem`."""
    if value is None or not isinstance(value, Mapping):
        return None
    if "mnem" in value:
        nested = value.get("mnem")
        if nested is None:
            return None
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if _FUNC_HINTS.intersection(value.keys()):
        return None
    return dict(value)


def small_prime_product(mnem: dict[str, int] | None) -> int:
    """Product of class primes, once per instruction in the bag.

    Empty or None yields 1. Key order does not matter. Keys may be raw
    mnemonics or already-classed names from func-row `mnem` maps.
    """
    if not mnem:
        return 1
    product = 1
    for token, raw_count in mnem.items():
        count = _count_of(raw_count)
        if count <= 0:
            continue
        product *= _prime_for(token) ** count
    return product


def mnemonic_sequence_hash(mnems: list[str]) -> str:
    """Order-sensitive hex digest of classed mnemonic tokens."""
    blob = "\0".join(mnemonic_class(str(token)) for token in mnems)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def spp_compatible(a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> bool:
    """True when both bags share a product and are empty together or both nonempty."""
    left = _count_map(a)
    right = _count_map(b)
    n_left = _instr_len(left)
    n_right = _instr_len(right)
    if n_left == 0 and n_right == 0:
        return True
    if n_left == 0 or n_right == 0:
        return False
    return small_prime_product(left) == small_prime_product(right)


def spp_candidates(src: Mapping[str, Any], pool: list) -> list:
    """Keep dests whose SPP equals `src`. Missing/empty src `mnem` leaves `pool` as-is."""
    src_map = _count_map(src)
    if _instr_len(src_map) == 0:
        return pool
    want = small_prime_product(src_map)
    return [dest for dest in pool if small_prime_product(_count_map(dest)) == want]
