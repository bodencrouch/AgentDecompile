"""Unique call-graph neighbor matching (BinDiff-style Phase 2).

Phase 1 of the cascade plants high-confidence anchors (unique symbols and
unique string/constant xrefs). This module then walks the call graph: if an
already-matched pair has exactly one unmatched callee (or caller) on each
side, those neighbors are the same function. That is an O(1) relational
lookup, not another all-pairs score.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Hashable

Id = Hashable

PROPAGATION_SCORE = 1.0
PROPAGATION_MARGIN = 1.0
MIN_UNIQUE_STRING = 4


def _pending(nodes: Iterable[Id], claimed: Mapping[Id, Any] | set[Id], eligible: set[Id]) -> set[Id]:
    claimed_set = claimed if isinstance(claimed, set) else set(claimed)
    return {node for node in nodes if node in eligible and node not in claimed_set}


def unique_index_anchors(
    src_index: Mapping[Any, Iterable[Id]],
    dst_index: Mapping[Any, Iterable[Id]],
    *,
    src_eligible: set[Id],
    dst_eligible: set[Id],
    key_ok: Callable[[Any], bool] | None = None,
) -> dict[Id, Id]:
    """1-to-1 keys that appear on exactly one eligible function per side."""
    proposals: list[tuple[Id, Id, str]] = []
    for key, src_hits in src_index.items():
        if key_ok is not None and not key_ok(key):
            continue
        dst_hits = dst_index.get(key)
        if not dst_hits:
            continue
        src_ids = [fid for fid in src_hits if fid in src_eligible]
        dst_ids = [fid for fid in dst_hits if fid in dst_eligible]
        if len(src_ids) != 1 or len(dst_ids) != 1:
            continue
        proposals.append((src_ids[0], dst_ids[0], "anchor"))
    return {src: dst for src, dst, _ in _consistent(proposals)}


def unique_neighbor_matches(
    src_callees: Mapping[Id, Iterable[Id]],
    src_callers: Mapping[Id, Iterable[Id]],
    dst_callees: Mapping[Id, Iterable[Id]],
    dst_callers: Mapping[Id, Iterable[Id]],
    mapping: Mapping[Id, Id],
    *,
    src_eligible: set[Id],
    dst_eligible: set[Id],
) -> list[tuple[Id, Id, str]]:
    """Unique unmatched callee/caller pairs implied by current anchors."""
    taken = set(mapping.values())
    proposals: list[tuple[Id, Id, str]] = []
    for src, dst in mapping.items():
        src_cal = _pending(src_callees.get(src, ()), mapping, src_eligible)
        dst_cal = _pending(dst_callees.get(dst, ()), taken, dst_eligible)
        if len(src_cal) == 1 and len(dst_cal) == 1:
            proposals.append((next(iter(src_cal)), next(iter(dst_cal)), "callee"))
        src_cr = _pending(src_callers.get(src, ()), mapping, src_eligible)
        dst_cr = _pending(dst_callers.get(dst, ()), taken, dst_eligible)
        if len(src_cr) == 1 and len(dst_cr) == 1:
            proposals.append((next(iter(src_cr)), next(iter(dst_cr)), "caller"))
    return _consistent(proposals)


def _consistent(proposals: list[tuple[Id, Id, str]]) -> list[tuple[Id, Id, str]]:
    by_src: dict[Id, set[Id]] = defaultdict(set)
    by_dst: dict[Id, set[Id]] = defaultdict(set)
    kinds: dict[tuple[Id, Id], str] = {}
    for src, dst, kind in proposals:
        by_src[src].add(dst)
        by_dst[dst].add(src)
        kinds.setdefault((src, dst), kind)
    accepted: list[tuple[Id, Id, str]] = []
    for src, dests in by_src.items():
        if len(dests) != 1:
            continue
        dst = next(iter(dests))
        if len(by_dst[dst]) != 1:
            continue
        accepted.append((src, dst, kinds[(src, dst)]))
    return accepted


def propagate_call_graph(
    src_callees: Mapping[Id, Iterable[Id]],
    src_callers: Mapping[Id, Iterable[Id]],
    dst_callees: Mapping[Id, Iterable[Id]],
    dst_callers: Mapping[Id, Iterable[Id]],
    mapping: dict[Id, Id],
    *,
    src_eligible: set[Id],
    dst_eligible: set[Id],
) -> list[tuple[Id, Id, str]]:
    """Grow *mapping* to a unique-neighbor fixpoint. Returns newly added pairs."""
    added: list[tuple[Id, Id, str]] = []
    while True:
        step = unique_neighbor_matches(
            src_callees,
            src_callers,
            dst_callees,
            dst_callers,
            mapping,
            src_eligible=src_eligible,
            dst_eligible=dst_eligible,
        )
        grew = False
        taken = set(mapping.values())
        for src, dst, kind in step:
            if src in mapping or dst in taken:
                continue
            mapping[src] = dst
            taken.add(dst)
            added.append((src, dst, kind))
            grew = True
        if not grew:
            return added


def absorb_anchors(base: dict[Id, Id], extra: Mapping[Id, Id]) -> dict[Id, Id]:
    """Add *extra* only when it does not contradict an existing 1-1 mapping."""
    taken = set(base.values())
    for src, dst in extra.items():
        if src in base or dst in taken:
            continue
        base[src] = dst
        taken.add(dst)
    return base


def interesting_string(value: Any) -> bool:
    text = str(value)
    return len(text) >= MIN_UNIQUE_STRING


def interesting_const(value: Any) -> bool:
    try:
        return abs(int(value)) > 255
    except (TypeError, ValueError):
        return bool(value)


def propagation_evidence(kind: str, *, channel: str = "neighbors") -> dict[str, Any]:
    return {
        channel: 1.0,
        "propagation": 1.0,
        "propagation_kind": kind,
        "_content": 99,
    }


def record_pairs(
    results: dict[Id, dict[str, Any]],
    pairs: Iterable[tuple[Id, Id, str]],
    *,
    id_field: str = "id",
    left_lookup: Mapping[Id, Mapping[str, Any]] | None = None,
    right_lookup: Mapping[Id, Mapping[str, Any]] | None = None,
    round_label: int | str = "propagate",
    pair_class: str | None = None,
) -> int:
    """Write result rows for already-accepted pairs. Returns how many were new."""
    added = 0
    for src, dst, kind in pairs:
        existing = results.get(src)
        if existing is not None and existing.get("kind") in {"callgraph", "anchor"}:
            continue
        left = (left_lookup or {}).get(src) or {}
        right = (right_lookup or {}).get(dst) or {}
        ev = propagation_evidence(kind)
        results[src] = {
            "left_id": left.get(id_field, src),
            "right_id": right.get(id_field, dst),
            "dst": dst,
            "score": PROPAGATION_SCORE,
            "margin": PROPAGATION_MARGIN,
            "evidence": ev,
            "signals": {k: v for k, v in ev.items() if not str(k).startswith("_")},
            "content": 99,
            "pair_class": pair_class,
            "status": "auto",
            "kind": "callgraph" if kind in {"callee", "caller"} else "anchor",
            "round": round_label,
            "method": f"callgraph-{kind}",
        }
        added += 1
    return added
