"""Basic-block hash containment as an inlining failsafe.

When a function disappears on one side of a match and another function grew,
callers can pass per-block hashes (``block_hashes`` or ``blocks``) and ask
whether the missing body's blocks sit inside exactly one survivor. Stored
``func`` rows carry ``block_hashes`` (computed in ``features.py``, persisted
by ``store.py``); rows without them yield an empty set, which never
participates — an empty set is not evidence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

Fn = Mapping[str, Any]


def _fn_id(fn: Fn) -> Any:
    if fn.get("id") is not None:
        return fn["id"]
    return fn.get("addr")


def _as_hash(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip() if not isinstance(value, str) else value
    if not text:
        return None
    return text if isinstance(value, str) else str(value)


def _hashes_from_values(values: Iterable[Any]) -> frozenset[str]:
    hashes: set[str] = set()
    for value in values:
        digest = _as_hash(value)
        if digest is not None:
            hashes.add(digest)
    return frozenset(hashes)


def _hashes_from_blocks(blocks: Iterable[Any]) -> frozenset[str]:
    hashes: set[str] = set()
    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        digest = _as_hash(block.get("hash"))
        if digest is not None:
            hashes.add(digest)
    return frozenset(hashes)


def block_hash_set(fn: Fn) -> frozenset[str]:
    """Unique block hashes from ``block_hashes`` or ``blocks`` (``hash`` key)."""
    if "block_hashes" in fn and fn["block_hashes"] is not None:
        raw = fn["block_hashes"]
        if isinstance(raw, (str, bytes)):
            digest = _as_hash(raw)
            return frozenset({digest} if digest is not None else ())
        try:
            return _hashes_from_values(raw)
        except TypeError:
            return frozenset()
    blocks = fn.get("blocks")
    if blocks is None:
        return frozenset()
    try:
        return _hashes_from_blocks(blocks)
    except TypeError:
        return frozenset()


def blocks_contained(small: Fn, large: Fn) -> bool:
    """True when ``small`` has hashes and they are a subset of ``large``'s."""
    needles = block_hash_set(small)
    if not needles:
        return False
    return needles <= block_hash_set(large)


def _range_end(fn: Fn) -> int | None:
    addr = int(fn.get("addr") or 0)
    size = int(fn.get("size") or 0)
    return (addr + size) or None


def _hit(vanished: Fn, host: Fn, *, kind: str, needles: frozenset[str], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "missing_id": _fn_id(vanished),
        "host_id": _fn_id(host),
        "kind": kind,
        "block_count": len(needles),
        "src_end": _range_end(vanished),
        "dst_end": _range_end(host),
        **(evidence or {}),
    }


def inline_hits(missing: list[Fn], survivors: list[Fn]) -> list[dict[str, Any]]:
    """Likely non-1:1 block correspondences after normal function matching.

    The order remains cheap and deterministic:

    1. exact block-set containment in one host => ``inline``;
    2. exact containment in multiple hosts => ``clone`` ambiguity evidence;
    3. multiple vanished functions in one host => ``fold``;
    4. union of several host fragments covers a vanished body => ``split``;
    5. one high-overlap larger host without exact containment => ``unroll``.

    All emitted relations are review evidence. They must not become logical
    identity bindings unless a later stage proves a real one-to-one function.

    Output does not depend on the order of ``missing`` or ``survivors``:
    every host/fragment pick uses a total key and the hit list is emitted
    sorted by (missing id, host id, kind).
    """
    # This used to evaluate ``blocks_contained`` against every surviving
    # function for every missing function.  A large cross-build comparison can
    # leave tens of thousands on both sides, turning an advisory residue check
    # into a multi-hour quadratic pass.  An inverted block index preserves the
    # same containment rule: a valid host must appear in every needle bucket.
    # Empty block sets are deliberately omitted, as before.
    indexed_survivors: list[tuple[Fn, frozenset[str]]] = []
    by_block: dict[str, set[int]] = defaultdict(set)
    for host in survivors:
        hashes = block_hash_set(host)
        if not hashes:
            continue
        index = len(indexed_survivors)
        indexed_survivors.append((host, hashes))
        for digest in hashes:
            by_block[digest].add(index)

    candidates_by_missing: dict[Any, list[tuple[Fn, frozenset[str]]]] = {}
    exact_by_host: dict[Any, list[Any]] = defaultdict(list)
    needles_by_missing: dict[Any, frozenset[str]] = {}
    missing_by_id: dict[Any, Fn] = {}
    for vanished in missing:
        missing_id = _fn_id(vanished)
        missing_by_id[missing_id] = vanished
        missing_size = int(vanished.get("n_instr") or vanished.get("size") or 0)
        needles = block_hash_set(vanished)
        if not needles:
            continue
        needles_by_missing[missing_id] = needles
        candidates: set[int] | None = None
        for digest in needles:
            bucket = by_block.get(digest, set())
            candidates = set(bucket) if candidates is None else candidates & bucket
            if not candidates:
                break
        hosts = [
            indexed_survivors[index][0]
            for index in (candidates or ())
            if _fn_id(indexed_survivors[index][0]) != missing_id
            and int(indexed_survivors[index][0].get("n_instr") or indexed_survivors[index][0].get("size") or 0) > missing_size
        ]
        candidates_by_missing[missing_id] = [(host, block_hash_set(host)) for host in hosts]
        for host in hosts:
            exact_by_host[_fn_id(host)].append(missing_id)

    hits: list[dict[str, Any]] = []
    handled: set[Any] = set()
    for missing_id, hosts_with_hashes in candidates_by_missing.items():
        vanished = missing_by_id[missing_id]
        needles = needles_by_missing[missing_id]
        hosts = [host for host, _hashes in hosts_with_hashes]
        if len(hosts) != 1:
            if len(hosts) > 1:
                ordered = sorted(hosts, key=lambda fn: str(_fn_id(fn)))
                hits.append(_hit(
                    vanished,
                    ordered[0],
                    kind="clone",
                    needles=needles,
                    evidence={
                        "host_unique": False,
                        "alternatives": [{"host_id": _fn_id(host)} for host in ordered],
                    },
                ))
                handled.add(missing_id)
            continue
        host = hosts[0]
        host_id = _fn_id(host)
        if len(exact_by_host.get(host_id, ())) > 1:
            hits.append(_hit(
                vanished,
                host,
                kind="fold",
                needles=needles,
                evidence={
                    "host_unique": True,
                    "folded_missing_ids": sorted(exact_by_host[host_id], key=str),
                },
            ))
        else:
            hits.append(_hit(vanished, host, kind="inline", needles=needles, evidence={"host_unique": True}))
        handled.add(missing_id)

    # Fragmented bodies: choose a small deterministic set of survivors whose
    # block union covers the vanished function. This catches split/fission
    # cases without comparing every src/dst pair.
    for vanished in missing:
        missing_id = _fn_id(vanished)
        if missing_id in handled:
            continue
        needles = needles_by_missing.get(missing_id) or block_hash_set(vanished)
        if len(needles) < 2:
            continue
        fragment_indexes: set[int] = set()
        for digest in needles:
            fragment_indexes.update(by_block.get(digest, ()))
        fragments: list[tuple[int, Fn, frozenset[str]]] = []
        for index in fragment_indexes:
            host, host_hashes = indexed_survivors[index]
            overlap = needles & host_hashes
            if overlap and _fn_id(host) != missing_id:
                fragments.append((len(overlap), host, overlap))
        fragments.sort(key=lambda item: (-item[0], str(_fn_id(item[1]))))
        covered: set[str] = set()
        chosen: list[tuple[Fn, frozenset[str]]] = []
        for _count, host, overlap in fragments:
            new_bits = overlap - covered
            if not new_bits:
                continue
            chosen.append((host, new_bits))
            covered.update(new_bits)
            if covered >= needles or len(chosen) >= 4:
                break
        if covered >= needles and len(chosen) > 1:
            primary = chosen[0][0]
            hits.append(_hit(
                vanished,
                primary,
                kind="split",
                needles=needles,
                evidence={
                    "host_unique": False,
                    "fragments": [
                        {"host_id": _fn_id(host), "block_count": len(bits)}
                        for host, bits in chosen
                    ],
                },
            ))
            handled.add(missing_id)
            continue

        if fragments:
            best_count, best_host, _overlap = fragments[0]
            coverage = best_count / max(1, len(needles))
            if coverage >= 0.75:
                hits.append(_hit(
                    vanished,
                    best_host,
                    kind="unroll",
                    needles=needles,
                    evidence={"coverage": round(coverage, 4), "host_unique": True},
                ))
                handled.add(missing_id)
    hits.sort(key=lambda hit: (str(hit["missing_id"]), str(hit["host_id"]), hit["kind"]))
    return hits


def likely_inlined(missing: list[Fn], survivors: list[Fn]) -> list[dict[str, Any]]:
    """Alias of :func:`inline_hits`."""
    return inline_hits(missing, survivors)
