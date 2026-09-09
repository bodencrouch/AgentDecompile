"""Phase 3 leftover matching: CFG + mnemonic SPP on unmatched islands."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Hashable

from .block_inline import inline_hits
from .cfg_signature import md_index_from_counts, structural_candidates
from .mnemonic_spp import small_prime_product, spp_candidates

Id = Hashable
Fn = Mapping[str, Any]


def _has_mnem_bag(fn: Fn) -> bool:
    raw = fn.get("mnem")
    return isinstance(raw, Mapping) and bool(raw)


def unique_structural_pairs(
    unmatched_src: Iterable[Fn],
    unmatched_dst: Iterable[Fn],
    *,
    id_of: Callable[[Fn], Id],
) -> list[tuple[Id, Id]]:
    """1-to-1 leftover pairs that share CFG MD-Index (or shape) and SPP."""
    dests = list(unmatched_dst)
    proposals: list[tuple[Id, Id]] = []
    for src in unmatched_src:
        if not _has_mnem_bag(src):
            continue
        pool = structural_candidates(src, dests)
        pool = spp_candidates(src, pool)
        if len(pool) != 1:
            continue
        proposals.append((id_of(src), id_of(pool[0])))
    by_src: dict[Id, set[Id]] = defaultdict(set)
    by_dst: dict[Id, set[Id]] = defaultdict(set)
    for src, dst in proposals:
        by_src[src].add(dst)
        by_dst[dst].add(src)
    accepted: list[tuple[Id, Id]] = []
    for src, dests_for in by_src.items():
        if len(dests_for) != 1:
            continue
        dst = next(iter(dests_for))
        if len(by_dst[dst]) != 1:
            continue
        accepted.append((src, dst))
    return accepted


def island_evidence(src: Fn, dst: Fn) -> dict[str, Any]:
    same_md = md_index_from_counts(src) == md_index_from_counts(dst)
    src_mnem = src.get("mnem") if isinstance(src.get("mnem"), Mapping) else None
    dst_mnem = dst.get("mnem") if isinstance(dst.get("mnem"), Mapping) else None
    same_spp = bool(src_mnem) and bool(dst_mnem) and small_prime_product(src_mnem) == small_prime_product(dst_mnem)
    return {
        "struct": 1.0 if same_md else 0.75,
        "mnem": 1.0 if same_spp else 0.0,
        "propagation": 0.0,
        "propagation_kind": "structural",
        "_content": 2 if same_md and same_spp else 1,
    }


def leftover_inlines(unmatched_src: list[Fn], matched_dst: list[Fn]) -> list[dict[str, Any]]:
    return inline_hits(unmatched_src, matched_dst)
