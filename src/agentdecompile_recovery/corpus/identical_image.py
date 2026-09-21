"""Identical-image short-circuit before function matching.

Content digests only — never filename, timestamp, version strings, or MD5 alone.
"""

from __future__ import annotations

import hashlib
import re
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
    """True only when both sides share a non-empty SHA-256 content digest.

    MD5 (including Ghidra ExecutableMD5) is advisory elsewhere — never enough
    alone to short-circuit the cascade.
    """
    # When both artifact paths are still available, bind the decision to their
    # current bytes.  A digest stored during an older ingest is not proof that
    # the file has not since been replaced.
    current_a = content_digest(meta_a.get("repo_path"))
    current_b = content_digest(meta_b.get("repo_path"))
    if current_a is not None or current_b is not None:
        return bool(current_a and current_b and current_a == current_b)
    for key in ("content_sha256", "sha256"):
        a = (meta_a.get(key) or "").strip().lower()
        b = (meta_b.get(key) or "").strip().lower()
        if a == b and re.fullmatch(r"[0-9a-f]{64}", a or ""):
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


def _eligible_non_thunk(funcs: Mapping[int, Mapping[str, Any]]) -> set[int]:
    return {int(a) for a, f in funcs.items() if not f.get("is_thunk")}


def short_circuit_match(sa, sb) -> dict[str, Any] | None:
    """Return a match_binaries-shaped result when images are content-identical.

    Falls through (None) when digests match but the address map is empty or
    incomplete — reloc/hash cascade must still run for residuals / rebases.
    Identity claim only: status=verify via enrich_evidence, never code_equality=raw
    without per-function byte proof / objdiff 0.
    """
    if not images_identical(sa.meta, sb.meta):
        return None
    from .correspondence import enrich_evidence
    from .match_engine import classify_pair

    mapping = identical_image_mapping(sa.funcs, sb.funcs)
    eligible = _eligible_non_thunk(sa.funcs)
    if not mapping or (eligible and len(mapping) < len(eligible)):
        return None
    results: dict[int, dict] = {}
    for src, dst in mapping.items():
        results[src] = {
            "dst": dst,
            "score": 1.0,
            "margin": 1.0,
            "evidence": enrich_evidence(
                {"identical_image": 1.0, "channel": "I"},
                kind="anchor",
                status="verify",
                identity_claim=True,
                behavior_checked=False,
            ),
            "round": "identical_image",
            "kind": "anchor",
            "status": "verify",
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
