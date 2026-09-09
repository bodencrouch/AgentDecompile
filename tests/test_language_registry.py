from __future__ import annotations

from pathlib import Path

import pytest

from agentdecompile_recovery.languages import (
    SourceLanguage,
    compiler_lane_for,
    language_from_metadata,
    language_from_path,
    language_spec,
    parse_source_language,
    source_file_suffixes,
    verify_language_id,
)

pytestmark = pytest.mark.unit


def test_parse_aliases() -> None:
    assert parse_source_language("C++") is SourceLanguage.CXX
    assert parse_source_language("cpp") is SourceLanguage.CXX
    assert parse_source_language("rust") is SourceLanguage.RUST
    assert parse_source_language("unknown-thing") is SourceLanguage.UNKNOWN


def test_language_from_path() -> None:
    assert language_from_path("foo.c") is SourceLanguage.C
    assert language_from_path("bar.cpp") is SourceLanguage.CXX
    assert language_from_path("main.rs") is SourceLanguage.RUST
    assert language_from_path("readme.md") is SourceLanguage.UNKNOWN


def test_language_from_metadata_prefers_explicit() -> None:
    assert language_from_metadata({"sourceLanguage": "go"}, "x.c") is SourceLanguage.GO
    assert language_from_metadata({"compilerLane": "cxx"}, "x.c") is SourceLanguage.CXX


def test_compiler_and_verify_ids() -> None:
    assert compiler_lane_for(SourceLanguage.C) == "c"
    assert compiler_lane_for(SourceLanguage.CXX) == "cxx"
    assert compiler_lane_for(SourceLanguage.RUST) is None
    assert verify_language_id(SourceLanguage.C) == "c"
    assert verify_language_id(SourceLanguage.CXX) == "c++"


def test_source_suffixes_include_new_languages() -> None:
    suffixes = source_file_suffixes()
    assert ".rs" in suffixes
    assert ".go" in suffixes
    assert ".cs" in suffixes


def test_language_spec_monaco_ids() -> None:
    assert language_spec(SourceLanguage.RUST).monaco_id == "rust"
    assert language_spec(SourceLanguage.CXX).monaco_id == "cpp"
