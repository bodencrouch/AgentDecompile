"""Tests for donor schedule and lineage accounting (U12)."""

from agentdecompile_recovery.corpus.donor_schedule import (
    independent_channel_bonus,
    lineage_corroboration_count,
    prefer_same_arch_pairs,
    spanning_forest_pairs,
)


def test_forest_has_n_minus_one_edges():
    bins = [
        {"id": 1, "arch": "x86", "bits": 32, "named_count": 100},
        {"id": 2, "arch": "x86", "bits": 32, "named_count": 50},
        {"id": 3, "arch": "x86", "bits": 32, "named_count": 10},
    ]
    edges = spanning_forest_pairs(bins)
    assert len(edges) == 2


def test_prefer_same_arch_first():
    a = {"id": "a", "arch": "x86", "bits": 32}
    b = {"id": "b", "arch": "x86", "bits": 32}
    c = {"id": "c", "arch": "arm", "bits": 32}
    ordered = prefer_same_arch_pairs([(a, c), (a, b)])
    assert ordered[0] == (a, b)


def test_same_lineage_counts_once():
    assert lineage_corroboration_count(["seed1", "seed1", "seed1"]) == 1
    assert lineage_corroboration_count(["a", "b", "a"]) == 2


def test_channel_bonus_capped_by_lineage():
    assert independent_channel_bonus(["I", "H", "G"], lineage_ids=["s", "s", "s"]) == 1
