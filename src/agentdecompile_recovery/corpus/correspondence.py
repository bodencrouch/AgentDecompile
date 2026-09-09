"""Correspondence evidence model for cross-build relations.

Stores relation kind, status band, alternatives, and separate claims for
cross-build identity, code equality, and behavioral checks — never a lone
addr→addr confidence float.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

RELATION_KINDS = frozenset({"one_to_one", "clone", "inline", "thunk", "split", "fold", "region"})
STATUS_BANDS = frozenset({"verified", "strongly_supported", "tentative", "ambiguous", "unresolved", "quarantined"})

KIND_TO_RELATION = {
    "anchor": "one_to_one",
    "callgraph": "one_to_one",
    "structural": "one_to_one",
    "inline": "inline",
    "region": "region",
    "hash": "one_to_one",
}


def enrich_evidence(
    evidence: Mapping[str, Any] | None,
    *,
    kind: str | None = None,
    status: str | None = None,
    relation: str | None = None,
    alternatives: list | None = None,
    code_equality: str | None = None,
    identity_claim: bool | None = None,
    behavior_checked: bool = False,
    quarantine: bool = False,
) -> dict[str, Any]:
    ev = dict(evidence or {})
    rel = relation or KIND_TO_RELATION.get(kind or "", "one_to_one")
    if rel not in RELATION_KINDS:
        rel = "one_to_one"
    ev["relation"] = rel
    if quarantine:
        band = "quarantined"
    elif status == "auto":
        band = "strongly_supported"
    elif status == "verify":
        band = "verified"
    elif status == "review":
        band = "tentative"
    elif status == "ambiguous":
        band = "ambiguous"
    else:
        band = "unresolved"
    if band not in STATUS_BANDS:
        band = "unresolved"
    ev["status_band"] = band
    if alternatives is not None:
        ev["alternatives"] = list(alternatives)
    elif "alternatives" not in ev:
        ev["alternatives"] = []
    if code_equality is not None:
        ev["code_equality"] = code_equality
    if identity_claim is None:
        identity_claim = status in {"auto", "verify"} and rel == "one_to_one"
    ev["identity_claim"] = bool(identity_claim)
    ev["behavior_checked"] = bool(behavior_checked)
    if quarantine:
        ev["quarantine"] = True
    return ev


def ambiguity_group(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an unresolved ambiguity Correspondence instead of picking a winner."""
    return enrich_evidence(
        {"candidates": candidates},
        status="ambiguous",
        relation="one_to_one",
        alternatives=candidates,
        identity_claim=False,
    )


def dumps_evidence(evidence: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(evidence or {}), separators=(",", ":"))


__all__ = [
    "KIND_TO_RELATION",
    "RELATION_KINDS",
    "STATUS_BANDS",
    "ambiguity_group",
    "dumps_evidence",
    "enrich_evidence",
]
