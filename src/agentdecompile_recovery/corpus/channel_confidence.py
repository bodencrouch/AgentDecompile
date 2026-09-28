"""Channel confidence helper for evidence-fusion matching.

Maps primary evidence kinds onto a 0–99 band with independent corroboration
bonuses and tiny/non-unique penalties. Correlated hash variants (H_*) count as
one channel. This is identity evidence only — not objdiff-0 or behavioral proof.
"""

from __future__ import annotations

from typing import Any, Mapping

# Primary base scores by kind / channel letter.
BASE = {
    "I": 88,
    "anchor": 88,
    "H": 86,
    "hash": 86,
    "X": 78,
    "G": 72,
    "callgraph": 74,
    "structural": 70,
    "S": 68,
    "bsim": 68,
    "T": 55,
    "abi": 55,
    "K": 70,
    "pcode": 70,
    "M": 66,
    "bindiff": 66,
    "D": 64,
    "emulate": 64,
    "inline": 50,
    "region": 50,
    "fuzzy_hash": 58,
    "F": 58,
}

HASH_KEYS = frozenset({"hash_reloc", "hash_instr", "hash_mnemonic", "hash_raw", "H_reloc", "H_instr", "H_mnemonic", "H_raw"})
TINY_INSTR = 8
TINY_PENALTY = 18
NONUNIQUE_PENALTY = 25
TIGHT_MARGIN_PENALTY = 12
CHANNEL_BONUS = 6


def _channel_letter(token: str) -> str:
    t = (token or "").strip().lower()
    if t in HASH_KEYS or t.startswith("h_") or t == "hash":
        return "H"
    if t in {"i", "symbol", "debug", "anchor", "name"}:
        return "I"
    if t in {"x", "string", "const", "ref", "rtti", "vtable"}:
        return "X"
    if t in {"g", "cfg", "callgraph", "spp", "structural"}:
        return "G"
    if t in {"s", "bsim"}:
        return "S"
    if t in {"t", "abi", "arity", "cc"}:
        return "T"
    if t in {"k", "pcode", "pcode_fingerprint", "pcode_il_ast", "skeleton"}:
        return "K"
    if t in {"m", "bindiff", "binexport", "diaphora"}:
        return "M"
    if t in {"d", "emulate", "unicorn", "qemu"}:
        return "D"
    if t in {"f", "fuzzy", "fuzzy_hash", "ssdeep", "tlsh"}:
        return "F"
    if len(t) == 1 and t.upper() in BASE:
        return t.upper()
    return t[:1].upper() if t else "?"


def independent_channels(evidence: Mapping[str, Any] | None) -> set[str]:
    """Collapse correlated hash variants into a single H channel."""
    if not evidence:
        return set()
    letters: set[str] = set()
    for key, val in evidence.items():
        if key.startswith("_") or val in (None, 0, 0.0, False, ""):
            continue
        if key in HASH_KEYS or key.startswith("hash_"):
            letters.add("H")
            continue
        if key in {"channel", "primary_channel"} and isinstance(val, str):
            letters.add(_channel_letter(val))
            continue
        if key in BASE or key in {"strings", "consts", "ext", "neighbors", "compunit", "decomp", "fuzzy_hash", "bsim", "abi"}:
            letters.add(_channel_letter(key))
    letters.update(_channel_letter(str(channel)) for channel in evidence.get("channels", []) if isinstance(channel, str))
    kind = evidence.get("kind") or evidence.get("propagation_kind")
    if isinstance(kind, str) and not (evidence.get("primary_channel") or evidence.get("channel") or evidence.get("channels")):
        letters.add(_channel_letter(kind))
    return {c for c in letters if c and c != "?"}


def channel_confidence(
    *,
    primary: str,
    evidence: Mapping[str, Any] | None = None,
    n_instr: int | None = None,
    unique: bool = True,
    margin: float | None = None,
    margin_floor: float = 0.06,
) -> int:
    """Return a 0–99 confidence; refuse stacking correlated H_* as many channels."""
    base = BASE.get(primary, BASE.get(_channel_letter(primary), 60))
    channels = independent_channels(evidence)
    channels.add(_channel_letter(primary))
    bonus = max(0, len(channels) - 1) * CHANNEL_BONUS
    score = base + bonus
    if n_instr is not None and int(n_instr or 0) < TINY_INSTR:
        score -= TINY_PENALTY
    if not unique:
        score -= NONUNIQUE_PENALTY
    if margin is not None and margin < margin_floor:
        score -= TIGHT_MARGIN_PENALTY
    return int(max(0, min(99, score)))


def high_band(pair_class: str = "same_platform") -> int:
    """Static band required before optional emulation (aligned to auto floors)."""
    from .match_engine import PAIR_POLICY

    auto = PAIR_POLICY.get(pair_class, PAIR_POLICY["same_platform"])["auto"]
    # Map 0.70 score floor ≈ mid-80s confidence helper band.
    return 80 if auto[0] >= 0.70 else 75


def allows_auto(confidence: int, *, unique: bool) -> bool:
    return unique and confidence >= 86


def allows_verify(confidence: int, *, unique: bool) -> bool:
    return unique and confidence >= 72


__all__ = [
    "allows_auto",
    "allows_verify",
    "channel_confidence",
    "high_band",
    "independent_channels",
]
