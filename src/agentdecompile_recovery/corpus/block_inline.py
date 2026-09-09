"""Basic-block hash containment as an inlining failsafe.

When a function disappears on one side of a match and another function grew,
callers can pass optional per-block hashes (``block_hashes`` or ``blocks``)
and ask whether the missing body's blocks sit inside exactly one survivor.
Empty hash sets never participate — stored ``func`` rows today have
``n_blocks`` but not per-block hashes, and an empty set is not evidence.
"""

from __future__ import annotations

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


def inline_hits(missing: list[Fn], survivors: list[Fn]) -> list[dict[str, Any]]:
    """Likely inlines: missing body contained in exactly one survivor."""
    hits: list[dict[str, Any]] = []
    for vanished in missing:
        hosts = [host for host in survivors if blocks_contained(vanished, host)]
        if len(hosts) != 1:
            continue
        needles = block_hash_set(vanished)
        hits.append(
            {
                "missing_id": _fn_id(vanished),
                "host_id": _fn_id(hosts[0]),
                "kind": "inline",
                "block_count": len(needles),
            }
        )
    return hits


def likely_inlined(missing: list[Fn], survivors: list[Fn]) -> list[dict[str, Any]]:
    """Alias of :func:`inline_hits`."""
    return inline_hits(missing, survivors)
