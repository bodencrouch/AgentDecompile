"""CFG shape filter and MD-Index signatures (BinDiff-style Phase 3 topology).

After call-graph propagation, remaining candidates are filtered by control-flow
shape so a 5-block function is not scored against a 50-block one. When a
per-block adjacency list is available, MD-Index hashes each block's in-degree,
out-degree, and a cycle-safe topological layer; otherwise the same idea is
applied to the stored (n_blocks, n_edges, back_edges, cyclomatic) counts.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Hashable

Id = Hashable
Fn = Mapping[str, Any]

DEFAULT_SLACK = 0.25
_MASK64 = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15
_SEED = 0x6A09E667F3BCC908

_PRIMES = [
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
    73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151,
]


def _field(fn: Fn, name: str) -> int:
    value = fn.get(name)
    if value is None:
        return 0
    return int(value)


def cfg_shape(fn: Fn) -> tuple[int, int, int, int]:
    """Return (n_blocks, n_edges, back_edges, cyclomatic); missing fields are 0."""
    return (
        _field(fn, "n_blocks"),
        _field(fn, "n_edges"),
        _field(fn, "back_edges"),
        _field(fn, "cyclomatic"),
    )


def _rel_ok(left: int, right: int, slack: float) -> bool:
    if left == right:
        return True
    scale = max(abs(left), abs(right))
    if scale == 0:
        return True
    return abs(left - right) <= slack * scale


def cfg_compatible(a: Fn, b: Fn, *, slack: float = DEFAULT_SLACK) -> bool:
    """True when block/edge counts are within relative *slack* (default 25%)."""
    a_blocks, a_edges, _, _ = cfg_shape(a)
    b_blocks, b_edges, _, _ = cfg_shape(b)
    return _rel_ok(a_blocks, b_blocks, slack) and _rel_ok(a_edges, b_edges, slack)


def _mix64(values: Iterable[int]) -> int:
    h = _SEED
    for value in values:
        h ^= int(value) & _MASK64
        h = (h * _GOLDEN) & _MASK64
        h ^= h >> 32
    return h


def md_index_from_counts(fn: Fn) -> int:
    """Deterministic 64-bit hash of stored CFG counts."""
    return _mix64(cfg_shape(fn))


def _ensure_primes(n: int) -> None:
    candidate = _PRIMES[-1] + 1 if _PRIMES else 2
    while len(_PRIMES) < n:
        limit = int(candidate ** 0.5) + 1
        if all(candidate % p for p in _PRIMES if p < limit):
            _PRIMES.append(candidate)
        candidate += 1


def _prime(n: int) -> int:
    """1-based nth prime; 0 maps to 1 so a zero coordinate does not wipe a product."""
    if n <= 0:
        return 1
    _ensure_primes(n)
    return _PRIMES[n - 1]


def _kahn_layers(nodes: set[Id], succ: Mapping[Id, list[Id]], indeg: Mapping[Id, int]) -> dict[Id, int]:
    remaining = dict(indeg)
    layer: dict[Id, int] = {}
    wave = 0
    ready = sorted((node for node in nodes if remaining[node] == 0), key=lambda n: (str(type(n).__name__), str(n)))
    seen: set[Id] = set()
    while ready:
        nxt: list[Id] = []
        for node in ready:
            if node in seen:
                continue
            seen.add(node)
            layer[node] = wave
            for dest in succ[node]:
                remaining[dest] -= 1
                if remaining[dest] == 0 and dest not in seen:
                    nxt.append(dest)
        wave += 1
        ready = sorted(nxt, key=lambda n: (str(type(n).__name__), str(n)))
    leftover = [node for node in nodes if node not in layer]
    if leftover:
        for node in _reverse_postorder(leftover, succ):
            layer[node] = wave
    return layer


def _reverse_postorder(nodes: Iterable[Id], succ: Mapping[Id, list[Id]]) -> list[Id]:
    """Cycle-safe reverse postorder; visit order is sorted for stability."""
    wanted = set(nodes)
    post: list[Id] = []
    visited: set[Id] = set()

    def dfs(node: Id) -> None:
        if node in visited or node not in wanted:
            return
        visited.add(node)
        for dest in sorted(succ[node], key=lambda n: (str(type(n).__name__), str(n))):
            dfs(dest)
        post.append(node)

    for node in sorted(wanted, key=lambda n: (str(type(n).__name__), str(n))):
        dfs(node)
    post.reverse()
    return post


def md_index_from_adj(nodes: Iterable[Id], edges: Iterable[tuple[Id, Id]]) -> int:
    """True MD-Index: in-degree, out-degree, and a cycle-safe topological layer."""
    succ: dict[Id, list[Id]] = defaultdict(list)
    indeg: dict[Id, int] = defaultdict(int)
    outdeg: dict[Id, int] = defaultdict(int)
    node_set = set(nodes)
    for src, dst in edges:
        node_set.add(src)
        node_set.add(dst)
        succ[src].append(dst)
        outdeg[src] += 1
        indeg[dst] += 1
    for node in node_set:
        indeg.setdefault(node, 0)
        outdeg.setdefault(node, 0)
        succ.setdefault(node, [])

    layers = _kahn_layers(node_set, succ, indeg)
    triples = sorted((layers[node], indeg[node], outdeg[node]) for node in node_set)
    total = 0
    for rank, (layer, inn, out) in enumerate(triples, start=1):
        total += _prime(rank) * _prime(inn + 1) * _prime(out + 1) * _prime(layer + 1)
    return total


def index_by_md(
    functions: Iterable[Fn],
    key: Callable[[Fn], int] = md_index_from_counts,
) -> dict[int, list[Fn]]:
    """Group *functions* by MD-Index (*key*, default ``md_index_from_counts``)."""
    buckets: dict[int, list[Fn]] = {}
    for fn in functions:
        buckets.setdefault(key(fn), []).append(fn)
    return buckets


def structural_candidates(src: Fn, pool: Iterable[Fn]) -> list[Fn]:
    """Keep CFG-compatible dests; prefer the same count MD-Index, never unfiltered."""
    compatible = [fn for fn in pool if cfg_compatible(src, fn)]
    src_md = md_index_from_counts(src)
    matched = [fn for fn in compatible if md_index_from_counts(fn) == src_md]
    return matched if matched else compatible
