"""Tests for channel confidence helper (U2)."""

from agentdecompile_recovery.corpus.channel_confidence import (
    allows_auto,
    channel_confidence,
    independent_channels,
)
from agentdecompile_recovery.corpus.propagate import persist_status


def test_correlated_hash_variants_count_as_one_channel():
    ch = independent_channels({"hash_reloc": "x", "hash_instr": "y", "hash_mnemonic": "z"})
    assert ch == {"H"}


def test_tiny_unique_gets_penalty():
    high = channel_confidence(primary="H", evidence={"hash_reloc": "a"}, n_instr=40, unique=True, margin=1.0)
    tiny = channel_confidence(primary="H", evidence={"hash_reloc": "a"}, n_instr=4, unique=True, margin=1.0)
    assert tiny < high


def test_non_unique_refuses_auto_band():
    c = channel_confidence(primary="I", unique=False, margin=1.0, n_instr=20)
    assert not allows_auto(c, unique=False)


def test_structural_persist_stays_verify():
    result = {"kind": "structural", "status": "verify", "score": 0.9, "margin": 1.0, "evidence": {}}
    assert persist_status(result, "same_platform", "a", "a") == "verify"
