from __future__ import annotations

import pytest

from agentdecompile_recovery.languages import (
    RecoveryLanguageProfile,
    SourceLanguage,
    default_source_language,
)
from agentdecompile_recovery.languages.sourcegen_defaults import active_generator_fields
from agentdecompile_recovery.source_parity_one_shot import ProfileConfig

pytestmark = pytest.mark.unit


def test_default_profile_uses_cxx() -> None:
    profile = RecoveryLanguageProfile.for_binary_format("pe")
    assert profile.default_source_language is SourceLanguage.CXX
    assert SourceLanguage.C in profile.allowed_languages
    assert SourceLanguage.RUST in profile.allowed_languages


def test_profile_config_carries_language_profile() -> None:
    config = ProfileConfig.for_slug("pe-test")
    assert config.language_profile is not None
    assert config.language_profile.default_source_language is default_source_language()


def test_merge_into_target_adds_profile_fields() -> None:
    merged = RecoveryLanguageProfile.merge_into_target({"format": "elf"})
    assert merged["defaultSourceLanguage"] == "cxx"
    assert "rust" in merged["allowedLanguages"]
    assert merged["sourceLanguageProfile"]["language"] == "cxx"


def test_active_generator_fields_from_explicit_profile() -> None:
    fields = active_generator_fields(
        {
            "defaultSourceLanguage": "rust",
            "allowedLanguages": ["rust", "cxx"],
        }
    )
    assert fields["extension"] == "rs"
    assert fields["sourceLanguage"] == "rust"
    assert fields["sourceQuality"] == "high-level-rust"


def test_profile_allows_language() -> None:
    profile = RecoveryLanguageProfile.from_mapping(
        {"defaultSourceLanguage": "go", "allowedLanguages": ["go", "rust"]}
    )
    assert profile.allows("go")
    assert profile.allows(SourceLanguage.RUST)
    assert not profile.allows("java")
