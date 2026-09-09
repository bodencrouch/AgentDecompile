"""Fingerprint hash family for exact / reloc-normalized identity seeds.

Equal under a named normalization means body equality under that mask — not
proven logical identity. Candidate generation (hash lookup) is not acceptance.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_mnemonic(mnem: Mapping[str, Any] | None) -> str:
    """H_mnemonic — classed mnemonic histogram."""
    if not mnem:
        return ""
    blob = json.dumps({str(k): int(v) for k, v in sorted(mnem.items())}, separators=(",", ":"))
    return _digest("H_mnem|" + blob)


def hash_reloc(mnem: Mapping[str, Any] | None, consts: list | None) -> str:
    """H_reloc — mnemonic profile + preserved non-address-ish constants.

    Address-like immediates should already be filtered at extract; remaining
    consts are treated as meaningful.
    """
    if not mnem and not consts:
        return ""
    payload = {
        "m": {str(k): int(v) for k, v in sorted((mnem or {}).items())},
        "c": sorted(int(x) for x in (consts or [])),
    }
    return _digest("H_reloc|" + json.dumps(payload, separators=(",", ":")))


def hash_instr(block_hashes: list[str] | None) -> str:
    """H_instr — ordered block mnemonic digests (relocation-agnostic blocks)."""
    if not block_hashes:
        return ""
    return _digest("H_instr|" + "\0".join(str(h) for h in block_hashes))


def hash_raw(n_instr: int | None, size: int | None, mnem: Mapping[str, Any] | None) -> str:
    """Optional weak H_raw stand-in when true bytes are unavailable in the store."""
    if not n_instr and not size:
        return ""
    payload = {"n": int(n_instr or 0), "s": int(size or 0), "m": hash_mnemonic(mnem)}
    return _digest("H_raw|" + json.dumps(payload, separators=(",", ":")))


def attach_hashes(row: dict[str, Any]) -> dict[str, Any]:
    """Fill hash_* fields on a function feature row (extract or in-memory)."""
    mnem = row.get("mnem") or row.get("mnemonic_counts") or {}
    if isinstance(mnem, str):
        try:
            mnem = json.loads(mnem) or {}
        except Exception:
            mnem = {}
    consts = row.get("consts") or []
    if isinstance(consts, str):
        try:
            consts = json.loads(consts) or []
        except Exception:
            consts = []
    blocks = row.get("block_hashes") or []
    if isinstance(blocks, str):
        try:
            blocks = json.loads(blocks) or []
        except Exception:
            blocks = []
    row = dict(row)
    row["hash_mnemonic"] = hash_mnemonic(mnem)
    row["hash_reloc"] = hash_reloc(mnem, list(consts))
    row["hash_instr"] = hash_instr(list(blocks))
    row["hash_raw"] = hash_raw(row.get("n_instr"), row.get("size"), mnem)
    return row


__all__ = [
    "attach_hashes",
    "hash_instr",
    "hash_mnemonic",
    "hash_raw",
    "hash_reloc",
]
