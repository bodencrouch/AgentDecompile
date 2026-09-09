"""Authentic vs matcher-inferred symbol provenance for channel I."""

from __future__ import annotations

from typing import Any, Mapping

AUTHENTIC_ORIGINS = frozenset(
    {
        "debug",
        "dwarf",
        "stabs",
        "pdb",
        "export",
        "mangled",
        "plate",
        "human",
        "human-authored",
        "user",
        "user_defined",
        "manual",
        "imported",
        "analysis",  # Ghidra ANALYSIS from primary import — still linker/export-ish
    }
)
INFERRED_ORIGINS = frozenset(
    {
        "matcher_inferred",
        "matcher",
        "propagated",
        "auto",
        "bsim",
        "default",
        "none",
        "",
    }
)


def normalize_origin(value: str | None) -> str:
    return (value or "").strip().lower()


def is_authentic_symbol(row: Mapping[str, Any]) -> bool:
    """True when the name is trustworthy for channel I seeds."""
    origin = normalize_origin(row.get("name_origin") or row.get("symbol_provenance"))
    if origin in INFERRED_ORIGINS or origin.startswith("matcher"):
        return False
    source = str(row.get("source") or "").upper()
    if origin in AUTHENTIC_ORIGINS:
        return True
    if source in {"USER_DEFINED", "IMPORTED"}:
        return True
    # Default Ghidra FUN_ / untitled analysis names are not authentic identity.
    name = str(row.get("name") or row.get("canon_key") or "")
    if name.startswith("FUN_") or name.startswith("unnamed_function"):
        return False
    if origin in {"analysis"} and name and not name.startswith("FUN_"):
        return True
    return False


def authentic_named_index(funcs: Mapping[Any, Mapping[str, Any]]) -> dict[str, list]:
    """canon_key → addrs, authentic symbols only."""
    from collections import defaultdict

    out: dict[str, list] = defaultdict(list)
    for addr, f in funcs.items():
        key = f.get("canon_key")
        if not key:
            continue
        if not is_authentic_symbol(f):
            continue
        from . import canon

        if canon.is_library(key):
            continue
        out[key].append(addr)
    return out


__all__ = [
    "AUTHENTIC_ORIGINS",
    "INFERRED_ORIGINS",
    "authentic_named_index",
    "is_authentic_symbol",
    "normalize_origin",
]
