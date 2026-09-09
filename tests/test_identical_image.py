"""Tests for identical-image short-circuit (U10)."""

from agentdecompile_recovery.corpus.identical_image import (
    identical_image_mapping,
    images_identical,
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


def test_mapping_reuses_shared_addrs():
    sa = {0x1000: {"size": 40, "is_thunk": 0}, 0x2000: {"size": 10}}
    sb = {0x1000: {"size": 40, "is_thunk": 0}, 0x2000: {"size": 99}}
    assert identical_image_mapping(sa, sb) == {0x1000: 0x1000}
