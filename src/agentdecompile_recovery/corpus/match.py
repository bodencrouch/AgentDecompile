"""Identity matcher surface, API-compatible with the ``kx.match`` toolkit module.

List snapshots use :mod:`match_engine`. Store-backed runs use :mod:`match_store`.
"""

from __future__ import annotations

from .match_engine import (  # noqa: F401
    CONTENT_CHANNELS,
    CONTENT_FLOOR,
    CONTENT_FLOORS,
    PAIR_POLICY,
    WEIGHTS,
    classify_pair,
    cosine,
    decomp_similarity,
    jaccard,
    relsim,
    score_features,
    shape_key,
    status_for,
)
from .callgraph_propagate import propagate_call_graph, unique_neighbor_matches
from .match_store import Binary, candidate_pairs, match_binaries

__all__ = [
    "Binary",
    "PAIR_POLICY",
    "candidate_pairs",
    "classify_pair",
    "cosine",
    "decomp_similarity",
    "jaccard",
    "match_binaries",
    "propagate_call_graph",
    "relsim",
    "unique_neighbor_matches",
    "score_features",
    "shape_key",
    "status_for",
]
