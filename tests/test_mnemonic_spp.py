from __future__ import annotations

from agentdecompile_recovery.corpus.features import mnemonic_class
from agentdecompile_recovery.corpus.mnemonic_spp import (
    CLASS_PRIMES,
    mnemonic_sequence_hash,
    small_prime_product,
    spp_candidates,
    spp_compatible,
)


def test_reordered_bag_has_same_spp() -> None:
    left = {"xor": 1, "add": 2, "mov": 3}
    right = {"mov": 3, "add": 2, "xor": 1}
    assert small_prime_product(left) == small_prime_product(right)
    assert small_prime_product(left) != 1


def test_xor_vs_add_changes_spp() -> None:
    assert small_prime_product({"xor": 2}) != small_prime_product({"add": 2})


def test_mov_movl_ldr_collapse_to_same_spp() -> None:
    assert mnemonic_class("mov") == mnemonic_class("movl") == mnemonic_class("ldr") == "MOV"
    assert small_prime_product({"mov": 4}) == small_prime_product({"movl": 4})
    assert small_prime_product({"movl": 4}) == small_prime_product({"ldr": 4})
    assert small_prime_product({"mov": 4}) == small_prime_product({"MOV": 4})


def test_sequence_hash_differs_when_order_differs() -> None:
    bag = {"mov": 1, "add": 1, "xor": 1}
    assert small_prime_product(bag) == small_prime_product({"xor": 1, "add": 1, "mov": 1})
    forward = mnemonic_sequence_hash(["mov", "add", "xor"])
    reverse = mnemonic_sequence_hash(["xor", "add", "mov"])
    assert forward != reverse
    assert len(forward) == 64
    assert forward == mnemonic_sequence_hash(["mov", "add", "xor"])


def test_spp_candidates_filters_the_pool() -> None:
    src = {"id": "src", "mnem": {"mov": 2, "call": 1}}
    keep_raw = {"id": "keep-raw", "mnem": {"movl": 2, "bl": 1}}
    keep_classed = {"id": "keep-classed", "mnem": {"MOV": 2, "CALL": 1}}
    drop = {"id": "drop", "mnem": {"xor": 3}}
    pool = [keep_raw, drop, keep_classed]
    assert spp_candidates(src, pool) == [keep_raw, keep_classed]


def test_empty_src_leaves_pool_unchanged() -> None:
    pool = [{"id": "a", "mnem": {"xor": 1}}, {"id": "b"}]
    assert spp_candidates({"id": "empty"}, pool) is pool
    assert spp_candidates({"id": "empty", "mnem": {}}, pool) is pool
    assert spp_candidates({"id": "empty", "mnem": None}, pool) is pool
    assert spp_candidates({"id": 16, "n_instr": 20}, pool) is pool


def test_empty_or_none_product_is_one() -> None:
    assert small_prime_product(None) == 1
    assert small_prime_product({}) == 1


def test_spp_compatible_empty_and_mismatch() -> None:
    assert spp_compatible({}, {})
    assert spp_compatible(None, None)
    assert spp_compatible({"mov": 1, "add": 2}, {"ldr": 1, "sub": 2})
    assert not spp_compatible({"xor": 1}, {"add": 1})
    assert not spp_compatible({}, {"mov": 1})


def test_class_primes_are_fixed_and_unique() -> None:
    primes = list(CLASS_PRIMES.values())
    assert len(primes) == len(set(primes))
    assert all(n > 1 for n in primes)
    for n in primes:
        assert all(n % k for k in range(2, int(n**0.5) + 1))
