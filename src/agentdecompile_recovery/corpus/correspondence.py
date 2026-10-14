"""Correspondence evidence model for cross-build relations.

Stores relation kind, status band, alternatives, and separate claims for
cross-build identity, code equality, and behavioral checks — never a lone
addr→addr confidence float.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

RELATION_KINDS = frozenset({"one_to_one", "clone", "inline", "thunk", "split", "fold", "region", "unroll"})
# Only these relations have concrete producers in the current corpus facts.
# The wider vocabulary remains a storage contract for future extractors; it
# must not silently turn an unsupported relation into an identity edge.
OPERATIONAL_RELATION_KINDS = frozenset({"one_to_one", "inline", "clone", "split", "fold", "unroll"})
STATUS_BANDS = frozenset({"verified", "strongly_supported", "tentative", "ambiguous", "unresolved", "quarantined"})

KIND_TO_RELATION = {
    "anchor": "one_to_one",
    "callgraph": "one_to_one",
    "structural": "one_to_one",
    "inline": "inline",
    "clone": "clone",
    "split": "split",
    "fold": "fold",
    "unroll": "unroll",
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
    behavior_checked: bool | None = None,
    quarantine: bool = False,
    src_end: int | None = None,
    dst_end: int | None = None,
    stage: str | None = None,
    dependencies: list | None = None,
) -> dict[str, Any]:
    ev = dict(evidence or {})
    rel = relation or KIND_TO_RELATION.get(kind or "", "one_to_one")
    if rel not in OPERATIONAL_RELATION_KINDS:
        raise ValueError(f"unsupported correspondence relation without extracted facts: {rel}")
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
        # Producer-ranked (best first); the order is a value, keep it.
        ev["alternatives"] = list(alternatives)
    elif "alternatives" not in ev:
        ev["alternatives"] = []
    if code_equality is not None:
        ev["code_equality"] = code_equality
    if identity_claim is None:
        identity_claim = status in {"auto", "verify"} and rel == "one_to_one"
    ev["identity_claim"] = bool(identity_claim)
    ev["behavior_checked"] = bool(ev.get("behavior_checked")) if behavior_checked is None else bool(behavior_checked)
    if quarantine:
        ev["quarantine"] = True
    if src_end is not None or dst_end is not None:
        ev["range"] = {"src_end": src_end, "dst_end": dst_end}
    if stage:
        ev["stage"] = stage
    if dependencies is not None:
        # Persisted into ``match.evidence`` and consumed as a set: sort so the
        # stored row does not inherit the producer's iteration order.
        ev["dependencies"] = sorted(dependencies, key=str)
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


def has_identity_contradiction(evidence):
    """Recorded actionable exclusions, independent of candidate review status."""
    ev = evidence or {}
    # Recorded contradictions are exclusions, not weaker positive evidence.
    # Inspect the selected destination's actionable contract. Disabled shadow
    # inference is not applicability-qualified across platforms and cannot
    # become a new hard veto here. A vetoed original best does not veto a
    # compatible promoted destination; unknown ABI facts do not imply conflict.
    if ev.get("reason") == "authentic_name_conflict":
        return True
    shadow = ev.get("contract_shadow")
    actionable = not isinstance(shadow, Mapping) or shadow.get("enabled") is True
    contract = ev.get("contract")
    if actionable and isinstance(contract, Mapping):
        if contract.get("veto") or contract.get("verdict") == "incompatible":
            return True
    if isinstance(shadow, Mapping) and shadow.get("enabled") is True:
        contract = shadow.get("contract")
        if isinstance(contract, Mapping):
            if contract.get("veto") or contract.get("verdict") == "incompatible":
                return True
    return False


def allows_identity_binding(
    evidence: Mapping[str, Any] | None,
    relation: str,
    quarantined_sources: set[Any],
) -> bool:
    """One identity gate shared by direct and dashboard bind paths."""
    ev = evidence or {}
    if has_identity_contradiction(ev):
        return False
    dependencies = set(ev.get("dependencies") or ())
    # Generation-aware propagation stores direct parents. Walk stored ancestry
    # too, so quarantining an intermediate invalidates every descendant.
    ancestry = ev.get("dependency_ancestry") or ()
    dependencies.update(ancestry)
    return (
        relation == "one_to_one"
        and not ev.get("quarantine")
        and ev.get("identity_claim") is not False
        and not quarantined_sources.intersection(dependencies)
    )


def dumps_evidence(evidence: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(evidence or {}), separators=(",", ":"))


__all__ = [
    "KIND_TO_RELATION",
    "OPERATIONAL_RELATION_KINDS",
    "RELATION_KINDS",
    "STATUS_BANDS",
    "ambiguity_group",
    "allows_identity_binding",
    "dumps_evidence",
    "enrich_evidence",
]
