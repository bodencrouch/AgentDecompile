"""Recovery source-language registry — C/C++ is one supported target among many."""

from .profile import RecoveryLanguageProfile
from .registry import (
    LanguageSpec,
    SourceLanguage,
    compiler_lane_for,
    default_source_language,
    language_from_metadata,
    language_from_path,
    language_spec,
    parse_source_language,
    source_file_suffixes,
    verify_language_id,
)

__all__ = [
    "LanguageSpec",
    "RecoveryLanguageProfile",
    "SourceLanguage",
    "compiler_lane_for",
    "default_source_language",
    "language_from_metadata",
    "language_from_path",
    "language_spec",
    "parse_source_language",
    "source_file_suffixes",
    "verify_language_id",
]
