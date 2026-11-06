"""Source-generation task defaults keyed by recovery source language."""
from __future__ import annotations

from typing import Any, Mapping

from .profile import RecoveryLanguageProfile
from .registry import (
    SourceLanguage,
    default_source_language,
    language_spec,
    parse_source_language,
)


def _coerce_language(language: SourceLanguage | str | None) -> SourceLanguage:
    if isinstance(language, SourceLanguage):
        return language
    return parse_source_language(language, default=default_source_language())


def task_source_language_id(language: SourceLanguage | str | None) -> str:
    """Map registry language to legacy generator ``language`` / ``sourceLanguage`` strings."""
    lang = _coerce_language(language)
    verify_id = language_spec(lang).verify_language_id
    if verify_id:
        return verify_id
    return lang.value


def source_quality_for(language: SourceLanguage | str | None) -> str:
    """Classifier tag written to generated tasks as ``sourceQuality``."""
    lang = _coerce_language(language)
    if lang in {SourceLanguage.C, SourceLanguage.CXX}:
        return "high-level-c"
    if lang is SourceLanguage.RUST:
        return "high-level-rust"
    return "high-level-source"


def _export_extension(language: SourceLanguage) -> str:
    ext = language_spec(language).default_export_extension
    return ext.lstrip(".")


def generator_task_fields(language: SourceLanguage | str | None = None) -> dict[str, str]:
    """Default ``extension``, ``sourceLanguage``, and ``sourceQuality`` for generator tasks."""
    lang = _coerce_language(language)
    return {
        "extension": _export_extension(lang),
        "sourceLanguage": task_source_language_id(lang),
        "sourceQuality": source_quality_for(lang),
    }


def active_generator_fields(target: Mapping[str, Any] | None) -> dict[str, str]:
    """Resolve generator defaults from a corpus/target manifest row."""
    merged = RecoveryLanguageProfile.merge_into_target(target)
    profile = merged.get("sourceLanguageProfile")
    explicit = merged.get("defaultSourceLanguage")
    if isinstance(profile, Mapping):
        profile_lang = (
            profile.get("language")
            or profile.get("sourceLanguage")
            or profile.get("id")
            or profile.get("defaultSourceLanguage")
        )
        if profile_lang:
            return generator_task_fields(profile_lang)
    if profile:
        return generator_task_fields(profile)
    return generator_task_fields(explicit)
