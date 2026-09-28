"""Small deterministic locality fingerprint for residue matching.

This is intentionally lightweight and dependency-free. If native SSDeep/TLSH
bindings are installed later they can replace this adapter, but the matcher
still needs a cheap local failover that runs after exact/relational/structural
stages and before any neural or human-reviewed channel.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import blake2b
from typing import Any


def _tokens(fn: Mapping[str, Any]) -> list[str]:
    tokens: list[str] = []
    mnem = fn.get("mnem")
    if isinstance(mnem, Mapping):
        for key, count in sorted(mnem.items(), key=lambda item: str(item[0])):
            try:
                repeat = max(1, min(32, int(count)))
            except Exception:
                repeat = 1
            tokens.extend([f"m:{key}"] * repeat)
    for field in ("strings", "consts", "ext_calls"):
        raw = fn.get(field) or ()
        try:
            values = sorted(str(value) for value in raw if str(value))
        except TypeError:
            values = [str(raw)] if str(raw) else []
        tokens.extend(f"{field}:{value}" for value in values[:96])
    for field in ("plate", "signature", "source"):
        value = str(fn.get(field) or "").strip()
        if value:
            tokens.extend(value.replace("(", " ").replace(")", " ").replace(",", " ").split()[:256])
    return tokens


def fuzzy_bits(fn: Mapping[str, Any], *, width: int = 128) -> int:
    """Return a SimHash-style locality fingerprint for available function text."""
    weights = [0] * width
    toks = _tokens(fn)
    if not toks:
        return 0
    for index, token in enumerate(toks):
        digest = blake2b(f"{index % 7}:{token}".encode("utf-8", "replace"), digest_size=16).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(width):
            weights[bit] += 1 if value & (1 << bit) else -1
    out = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            out |= 1 << bit
    return out


def fuzzy_similarity(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    width: int = 128,
    left_bits: int | None = None,
    right_bits: int | None = None,
) -> float:
    """Return 0..1 similarity for the local fuzzy fingerprints."""
    a = fuzzy_bits(left, width=width) if left_bits is None else left_bits
    b = fuzzy_bits(right, width=width) if right_bits is None else right_bits
    if not a and not b:
        return 0.0
    distance = (a ^ b).bit_count()
    return max(0.0, min(1.0, 1.0 - distance / width))


__all__ = ["fuzzy_bits", "fuzzy_similarity"]
