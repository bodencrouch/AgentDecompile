"""Tests for fingerprint hash family (U1)."""

from agentdecompile_recovery.corpus.fingerprint_hashes import attach_hashes, hash_reloc


def test_identical_reloc_bodies_share_digest():
    a = attach_hashes({"mnem": {"MOV": 3, "RET": 1}, "consts": [7, 42], "block_hashes": ["aa"]})
    b = attach_hashes({"mnem": {"MOV": 3, "RET": 1}, "consts": [42, 7], "block_hashes": ["aa"]})
    assert a["hash_reloc"] and a["hash_reloc"] == b["hash_reloc"]


def test_different_consts_change_reloc_hash():
    a = hash_reloc({"MOV": 1}, [1])
    b = hash_reloc({"MOV": 1}, [2])
    assert a != b


def test_empty_features_yield_empty_hashes():
    row = attach_hashes({})
    assert row["hash_reloc"] == ""
    assert row["hash_mnemonic"] == ""
