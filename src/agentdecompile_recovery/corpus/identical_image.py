"""Identical-image short-circuit before function matching.

Content digests only — never filename, timestamp, or version strings alone.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


def content_digest(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def images_identical(meta_a: Mapping[str, Any], meta_b: Mapping[str, Any]) -> bool:
    """True only when both sides share a non-empty content digest."""
    for key in ("content_sha256", "sha256"):
        a = (meta_a.get(key) or "").strip()
        b = (meta_b.get(key) or "").strip()
        if a and b and a == b:
            return True
    a_md5 = (meta_a.get("md5") or "").strip().lower()
    b_md5 = (meta_b.get("md5") or "").strip().lower()
    if a_md5 and b_md5 and a_md5 == b_md5 and len(a_md5) >= 32:
        return True
    return False


def identical_image_mapping(
    sa_funcs: Mapping[int, Mapping[str, Any]],
    sb_funcs: Mapping[int, Mapping[str, Any]],
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for addr, fa in sa_funcs.items():
        if fa.get("is_thunk"):
            continue
        fb = sb_funcs.get(addr)
        if fb is None or fb.get("is_thunk"):
            continue
        sa_size = fa.get("size")
        sb_size = fb.get("size")
        if sa_size is not None and sb_size is not None and int(sa_size) != int(sb_size):
            continue
        mapping[int(addr)] = int(addr)
    return mapping


def short_circuit_match(sa, sb) -> dict[str, Any] | None:
    """Return a match_binaries-shaped result when images are content-identical."""
    if not images_identical(sa.meta, sb.meta):
        return None
    from .match_engine import classify_pair

    mapping = identical_image_mapping(sa.funcs, sb.funcs)
    results: dict[int, dict] = {}
    for src, dst in mapping.items():
        results[src] = {
            "dst": dst,
            "score": 1.0,
            "margin": 1.0,
            "evidence": {
                "identical_image": 1.0,
                "code_equality": "raw",
                "relation": "one_to_one",
                "status_band": "verified",
                "identity_claim": True,
                "behavior_checked": False,
                "alternatives": [],
            },
            "round": "identical_image",
            "kind": "anchor",
            "status": "auto",
        }
    return {
        "mapping": mapping,
        "results": results,
        "src": sa,
        "dst": sb,
        "pair_class": classify_pair(sa.meta, sb.meta),
        "inlines": [],
        "short_circuit": "identical_image",
    }


__all__ = [
    "content_digest",
    "identical_image_mapping",
    "images_identical",
    "short_circuit_match",
]
