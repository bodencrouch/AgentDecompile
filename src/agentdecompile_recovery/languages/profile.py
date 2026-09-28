"""Corpus profile language settings for recovery pipelines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .registry import SourceLanguage, default_source_language, parse_source_language


@dataclass(frozen=True)
class RecoveryLanguageProfile:
    """Per-corpus recovery source-language policy."""

    default_source_language: SourceLanguage
    allowed_languages: tuple[SourceLanguage, ...]

    @staticmethod
    def default_allowed() -> tuple[SourceLanguage, ...]:
        return (
            SourceLanguage.C,
            SourceLanguage.CXX,
            SourceLanguage.RUST,
            SourceLanguage.GO,
            SourceLanguage.CSHARP,
            SourceLanguage.JAVA,
        )

    @classmethod
    def for_binary_format(cls, binary_format: str) -> RecoveryLanguageProfile:
        """Derive sensible defaults from PE vs ELF profile shape."""
        default = default_source_language()
        allowed = cls.default_allowed()
        if binary_format in {"elf", "nds"}:
            return cls(default_source_language=default, allowed_languages=allowed)
        return cls(default_source_language=default, allowed_languages=allowed)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> RecoveryLanguageProfile:
        data = data or {}
        default = parse_source_language(
            data.get("defaultSourceLanguage")
            or data.get("default_source_language")
            or data.get("language"),
            default=default_source_language(),
        )
        raw_allowed = data.get("allowedLanguages") or data.get("allowed_languages") or ()
        allowed: list[SourceLanguage] = []
        for item in raw_allowed:
            lang = parse_source_language(item, default=None)
            if lang is not SourceLanguage.UNKNOWN and lang not in allowed:
                allowed.append(lang)
        if not allowed:
            allowed = list(cls.default_allowed())
        if default not in allowed:
            allowed = [default, *allowed]
        return cls(default_source_language=default, allowed_languages=tuple(allowed))

    def allows(self, language: SourceLanguage | str | None) -> bool:
        lang = (
            language
            if isinstance(language, SourceLanguage)
            else parse_source_language(language, default=SourceLanguage.UNKNOWN)
        )
        if lang is SourceLanguage.UNKNOWN:
            return False
        return lang in self.allowed_languages

    def to_dict(self) -> dict[str, Any]:
        return {
            "defaultSourceLanguage": self.default_source_language.value,
            "allowedLanguages": [lang.value for lang in self.allowed_languages],
        }

    def to_target_fields(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload["sourceLanguageProfile"] = {
            "language": self.default_source_language.value,
            "defaultSourceLanguage": self.default_source_language.value,
            "allowedLanguages": payload["allowedLanguages"],
        }
        return payload

    @classmethod
    def merge_into_target(cls, target: Mapping[str, Any] | None) -> dict[str, Any]:
        """Return target dict with explicit or format-derived language profile."""
        base = dict(target or {})
        if base.get("sourceLanguageProfile") or base.get("defaultSourceLanguage"):
            profile = cls.from_mapping(base)
        else:
            profile = cls.for_binary_format(str(base.get("format") or base.get("binaryFormat") or "pe"))
        base.update(profile.to_target_fields())
        return base
