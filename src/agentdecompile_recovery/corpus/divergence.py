"""Pure multiset graph divergence over explicitly qualified decode evidence.

Analyzer CFG hashes are not a substitute for masked decode-block hashes. Callers
must supply the producing decoder, masking and partition revisions. Thresholds
are input data from the recorded basis; this module invents no default policy.
"""
from __future__ import annotations

from collections import Counter

FORMAT = "agentdecompile.divergence-metric/v1"


def _rational(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"divergence threshold {name} requires [numerator, denominator]")
    num, den = value
    if type(num) is not int or type(den) is not int or not 0 <= num <= den or den <= 0:
        raise ValueError(f"invalid divergence threshold {name}")
    return num, den


def _graph(value):
    if not isinstance(value, dict) or value.get("key_kind") != "masked_block_hash":
        raise ValueError("masked_decode_block_keys_required")
    basis = value.get("decode_basis")
    required = ("decoder_revision", "masking_rule_version", "block_partition_revision")
    if not isinstance(basis, dict) or any(not isinstance(basis.get(k), str) or basis[k] in ("", "unknown", "none") for k in required):
        raise ValueError("qualified_decode_basis_required")
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or not nodes or any(not isinstance(n, str) or not n for n in nodes):
        raise ValueError("nonempty_masked_block_multiset_required")
    edges = value.get("edges")
    if not isinstance(edges, list):
        raise ValueError("decoded_edges_required")
    keys = set(nodes)
    normalized = []
    for edge in edges:
        if not isinstance(edge, (tuple, list)) or len(edge) != 2 or any(n not in keys for n in edge):
            raise ValueError("edge_references_unknown_block")
        normalized.append(tuple(edge))
    neighbors = value.get("neighbors")
    if not isinstance(neighbors, list):
        raise ValueError("neighborhood_evidence_required")
    bound, unbound = [], 0
    for neighbor in neighbors:
        if not isinstance(neighbor, dict) or neighbor.get("role") not in ("caller", "callee"):
            raise ValueError("invalid_neighbor")
        if neighbor.get("library") is True:
            continue
        key = neighbor.get("key")
        if not key:
            unbound += 1
        elif not isinstance(key, str):
            raise ValueError("invalid_neighbor_key")
        else:
            bound.append((key, neighbor["role"]))
    return Counter(sorted(nodes)), Counter(sorted(normalized)), Counter(sorted(bound)), unbound, basis


def compare_graphs(a: dict, b: dict, thresholds: dict, *, containment_hit: bool = False) -> dict:
    """Return integer components and a symmetric three-way classification."""
    if not isinstance(thresholds, dict) or not isinstance(thresholds.get("version"), str) or not thresholds["version"]:
        raise ValueError("versioned_divergence_thresholds_required")
    d_num, d_den = _rational(thresholds.get("d"), "d")
    u_num, u_den = _rational(thresholds.get("u"), "u")
    s_num, s_den = _rational(thresholds.get("s"), "s")
    if type(containment_hit) is not bool:
        raise ValueError("containment_hit_must_be_boolean")
    na, ea, ba, ua, basis_a = _graph(a)
    nb, eb, bb, ub, basis_b = _graph(b)
    if basis_a != basis_b:
        raise ValueError("decode_basis_mismatch")
    components = {
        "nodes_only_in_A": sum((na - nb).values()), "nodes_only_in_B": sum((nb - na).values()),
        "edge_symdiff": sum((ea - eb).values()) + sum((eb - ea).values()),
        "neighborhood_symdiff": sum((ba - bb).values()) + sum((bb - ba).values()),
        "size_A": sum(na.values()), "size_B": sum(nb.values()),
        "nbr_A": sum(ba.values()), "nbr_B": sum(bb.values()), "nbr_unbound_A": ua, "nbr_unbound_B": ub,
    }
    c = components
    same = ((c["nodes_only_in_A"] + c["nodes_only_in_B"]) * d_den <= d_num * (c["size_A"] + c["size_B"])
            and c["neighborhood_symdiff"] * u_den <= u_num * (c["nbr_A"] + c["nbr_B"]))
    split = containment_hit or min(c["nodes_only_in_A"], c["nodes_only_in_B"]) * s_den <= s_num * min(c["size_A"], c["size_B"])
    classification = "1↔1" if same else "split-or-inlined" if split else "diverged"
    direction = None
    if classification == "split-or-inlined":
        direction = "A_into_B" if c["size_A"] < c["size_B"] else "B_into_A" if c["size_B"] < c["size_A"] else "undetermined"
    return {"format": FORMAT, "classification": classification, "direction": direction,
            "components": components, "thresholds": {"version": thresholds["version"],
            "d": [d_num, d_den], "u": [u_num, u_den], "s": [s_num, s_den]},
            "decode_basis": dict(basis_a), "containment_hit": containment_hit}
