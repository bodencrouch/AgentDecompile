"""Donor pair scheduling and corroboration lineage accounting.

A spanning forest is the default schedule, not a ban on direct pairs.
Transitive edges from one seed count as one evidential lineage.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Hashable, Mapping


def group_by_arch(binaries: list[Mapping[str, Any]]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in binaries:
        key = (row.get("arch"), row.get("bits"))
        groups[key].append(dict(row))
    return dict(groups)


def _node_id(row: Mapping[str, Any]) -> Hashable:
    if row.get("id") is not None:
        return row["id"]
    return row.get("slug") or row.get("repo_path")


def spanning_forest_pairs(
    binaries: list[Mapping[str, Any]],
    *,
    overlap_key: str = "named_count",
) -> list[tuple[Hashable, Hashable]]:
    """Connect each arch group into a tree (n-1 edges), preferring high overlap hubs."""
    edges: list[tuple[Hashable, Hashable]] = []
    for _arch, members in group_by_arch(list(binaries)).items():
        if len(members) < 2:
            continue
        ranked = sorted(
            members,
            key=lambda m: (-int(m.get(overlap_key) or m.get("func_count") or 0), str(_node_id(m))),
        )
        hub = ranked[0]
        hub_id = _node_id(hub)
        for other in ranked[1:]:
            oid = _node_id(other)
            if oid is None or hub_id is None or oid == hub_id:
                continue
            edges.append((hub_id, oid))
    return edges


def prefer_same_arch_pairs(
    candidates: list[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    def key(pair):
        a, b = pair
        same = (a.get("arch"), a.get("bits")) == (b.get("arch"), b.get("bits"))
        return (0 if same else 1, str(_node_id(a)), str(_node_id(b)))

    return sorted(candidates, key=key)


def lineage_corroboration_count(edge_lineages: list[str]) -> int:
    return len({str(x) for x in edge_lineages if x})


def independent_channel_bonus(
    channels: list[str],
    *,
    lineage_ids: list[str] | None = None,
) -> int:
    """Unique channel letters; chain-derived lineages do not multiply the bonus."""
    unique_channels = len({c for c in channels if c})
    if lineage_ids is None:
        return unique_channels
    lineages = lineage_corroboration_count(lineage_ids)
    return min(unique_channels, max(lineages, 1) if channels else 0)


__all__ = [
    "group_by_arch",
    "independent_channel_bonus",
    "lineage_corroboration_count",
    "prefer_same_arch_pairs",
    "spanning_forest_pairs",
]
