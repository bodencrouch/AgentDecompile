"""Tests for identical-image short-circuit (U10)."""

from types import SimpleNamespace

from agentdecompile_recovery.corpus.identical_image import (
    identical_image_mapping,
    images_identical,
    short_circuit_match,
)


def test_same_content_sha256_is_identical():
    a = {"content_sha256": "abc" * 20, "slug": "one"}
    b = {"content_sha256": "abc" * 20, "slug": "two"}
    assert images_identical(a, b)


def test_same_slug_different_digest_is_not_identical():
    a = {"content_sha256": "a" * 64, "slug": "game.exe"}
    b = {"content_sha256": "b" * 64, "slug": "game.exe"}
    assert not images_identical(a, b)


def test_filename_only_without_digest_is_not_identical():
    assert not images_identical({"slug": "x"}, {"slug": "x"})
    assert not images_identical({"repo_path": "/a/x"}, {"repo_path": "/b/x"})


def test_md5_alone_is_not_identical_for_short_circuit():
    digest = "d" * 32
    assert not images_identical({"md5": digest}, {"md5": digest})


def test_mapping_reuses_shared_addrs():
    sa = {0x1000: {"size": 40, "is_thunk": 0}, 0x2000: {"size": 10}}
    sb = {0x1000: {"size": 40, "is_thunk": 0}, 0x2000: {"size": 99}}
    assert identical_image_mapping(sa, sb) == {0x1000: 0x1000}


def test_short_circuit_falls_through_when_address_maps_empty():
    digest = "a" * 64
    sa = SimpleNamespace(
        meta={"content_sha256": digest, "arch": "x86", "bits": 32, "format": "PE"},
        funcs={0x401000: {"size": 40, "is_thunk": 0, "n_instr": 10}},
    )
    sb = SimpleNamespace(
        meta={"content_sha256": digest, "arch": "x86", "bits": 32, "format": "PE"},
        funcs={0x101000: {"size": 40, "is_thunk": 0, "n_instr": 10}},
    )
    assert short_circuit_match(sa, sb) is None


def test_short_circuit_uses_enrich_bands_not_raw_verified():
    digest = "b" * 64
    fa = {"size": 40, "is_thunk": 0, "n_instr": 12}
    sa = SimpleNamespace(
        meta={"content_sha256": digest, "arch": "x86", "bits": 32, "format": "PE"},
        funcs={0x1000: fa},
    )
    sb = SimpleNamespace(
        meta={"content_sha256": digest, "arch": "x86", "bits": 32, "format": "PE"},
        funcs={0x1000: dict(fa)},
    )
    early = short_circuit_match(sa, sb)
    assert early is not None
    row = early["results"][0x1000]
    assert row["status"] == "verify"
    assert row["evidence"]["status_band"] == "verified"
    assert row["evidence"].get("code_equality") != "raw"
    assert row["evidence"]["identity_claim"] is True
