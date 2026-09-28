"""Phase 3 leftover matching: CFG + mnemonic SPP on unmatched islands."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Hashable

from .block_inline import inline_hits
from .cfg_signature import cfg_compatible, md_index_from_adj, md_index_from_counts
from .mnemonic_spp import small_prime_product

Id = Hashable
Fn = Mapping[str, Any]


def _has_mnem_bag(fn: Fn) -> bool:
    raw = fn.get("mnem")
    return isinstance(raw, Mapping) and bool(raw)

def _md(fn: Fn) -> int:
    nodes = fn.get("cfg_nodes")
    edges = fn.get("cfg_edges")
    if isinstance(nodes, Iterable) and isinstance(edges, Iterable):
        try:
            return md_index_from_adj(nodes, edges)
        except (TypeError, ValueError):
            pass
    return md_index_from_counts(fn)


def unique_structural_pairs(
    unmatched_src: Iterable[Fn],
    unmatched_dst: Iterable[Fn],
    *,
    id_of: Callable[[Fn], Id],
) -> list[tuple[Id, Id]]:
    """1-to-1 leftover pairs that share CFG MD-Index (or shape) and SPP."""
    # Cache the expensive arbitrary-precision SPP once per function.  The old
    # fallback recalculated every destination signature for every source and
    # scanned all destinations before applying SPP.  Indexing by SPP first is
    # equivalent: structural_candidates(src, dests) followed by
    # spp_candidates(src, pool) retains exactly the compatible destinations
    # with the source SPP.
    dests = [fn for fn in unmatched_dst if _has_mnem_bag(fn)]
    by_md: dict[int, list[Fn]] = defaultdict(list)
    by_md_spp: dict[tuple[int, int], list[Fn]] = defaultdict(list)
    by_spp: dict[int, list[Fn]] = defaultdict(list)
    for dst in dests:
        signature = small_prime_product(dst["mnem"])
        md = _md(dst)
        by_md[md].append(dst)
        by_md_spp[(md, signature)].append(dst)
        by_spp[signature].append(dst)

    proposals: list[tuple[Id, Id]] = []
    for src in unmatched_src:
        if not _has_mnem_bag(src):
            continue
        signature = small_prime_product(src["mnem"])
        md = _md(src)
        if md in by_md:
            pool = by_md_spp.get((md, signature), ())
        else:
            pool = (dst for dst in by_spp.get(signature, ()) if cfg_compatible(src, dst))
        pool = list(pool)
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
    same_md = _md(src) == _md(dst)
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
