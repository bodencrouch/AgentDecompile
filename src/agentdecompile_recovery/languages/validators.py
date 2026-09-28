"""Language-specific readable high-level source validators."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from agentdecompile_recovery.languages.registry import (
    SourceLanguage,
    language_spec,
    parse_source_language,
)

if TYPE_CHECKING:
    pass

ValidatorFn = Callable[[str], bool]
ReasonFn = Callable[[str], str | None]

RUST_SHIM_RE = re.compile(
    r"""
      \basm!\s*\(
    | \bglobal_asm!\s*\(
    | \bcore::arch::
    | \bnaked\b
    """,
    re.X,
)

GENERIC_ASM_RE = re.compile(
    r"""
      \b__asm__?\b
    | \binline\s+asm\b
    """,
    re.I | re.X,
)

_VALIDATORS: dict[str, ValidatorFn] = {}
_REASONS: dict[str, ReasonFn] = {}


def _register(key: str, validator: ValidatorFn, reason: ReasonFn) -> None:
    _VALIDATORS[key] = validator
    _REASONS[key] = reason


def _c_readable_ok(source: str) -> bool:
    from agentdecompile_recovery.corpus.source_claims import _c_readable_ok as check

    return check(source)


def _c_shim_match(source: str) -> str | None:
    from agentdecompile_recovery.corpus.source_claims import _c_shim_match as match

    return match(source)


def _validate_rust(source: str) -> bool:
    return RUST_SHIM_RE.search(source) is None


def _reason_rust(source: str) -> str | None:
    match = RUST_SHIM_RE.search(source)
    return match.group(0) if match else None


def _validate_generic_asm(source: str) -> bool:
    return GENERIC_ASM_RE.search(source) is None


def _reason_generic_asm(source: str) -> str | None:
    match = GENERIC_ASM_RE.search(source)
    return match.group(0) if match else None


_register("c", _c_readable_ok, _c_shim_match)
_register("cxx", _c_readable_ok, _c_shim_match)
_register("rust", _validate_rust, _reason_rust)
_register("go", _validate_generic_asm, _reason_generic_asm)
_register("java", _validate_generic_asm, _reason_generic_asm)
_register("csharp", _validate_generic_asm, _reason_generic_asm)


def _normalize_language(language: SourceLanguage | str | None) -> SourceLanguage:
    if isinstance(language, SourceLanguage):
        return language
    if language is None:
        return SourceLanguage.UNKNOWN
    return parse_source_language(language, default=SourceLanguage.UNKNOWN)


def _validator_key(language: SourceLanguage) -> str | None:
    return language_spec(language).readable_validator


def _validate_unknown(source: str) -> bool:
    body = source.strip()
    if not body:
        return False
    return _c_readable_ok(source)


def _reason_unknown(source: str) -> str | None:
    return _c_shim_match(source)


def is_readable_high_level_source(
    source: str | None,
    language: SourceLanguage | str | None = None,
) -> bool:
    text = source or ""
    if not text.strip():
        return False
    lang = _normalize_language(language)
    key = _validator_key(lang)
    if key and key in _VALIDATORS:
        return _VALIDATORS[key](text)
    return _validate_unknown(text)


def shim_reason_for(
    source: str | None,
    language: SourceLanguage | str | None = None,
) -> str | None:
    text = source or ""
    if not text.strip():
        return None
    lang = _normalize_language(language)
    key = _validator_key(lang)
    if key and key in _REASONS:
        return _REASONS[key](text)
    return _reason_unknown(text)
