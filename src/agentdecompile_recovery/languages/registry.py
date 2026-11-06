"""Canonical recovery source-language registry.

Ghidra *processor* language (ISA/endian) is separate from recovery *source*
language (readable output target).  Use ``SourceLanguage`` for the latter.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class SourceLanguage(str, Enum):
    C = "c"
    CXX = "cxx"
    RUST = "rust"
    GO = "go"
    CSHARP = "csharp"
    JAVA = "java"
    GAS = "gas"
    MASM = "masm"
    ASM = "asm"
    TEXT = "text"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LanguageSpec:
    id: SourceLanguage
    display_name: str
    file_extensions: tuple[str, ...]
    monaco_id: str | None
    markdown_fence: str
    default_export_extension: str
    compiler_lane: str | None  # c | cxx when verify applies
    verify_language_id: str | None  # clang/msvc dialect id
    discovery_label: str | None
    readable_validator: str | None = None  # key into languages.validators registry


def _register(spec: LanguageSpec) -> LanguageSpec:
    _REGISTRY[spec.id] = spec
    for ext in spec.file_extensions:
        _SUFFIX_INDEX[ext.lower()] = spec.id
    for alias in (spec.id.value, *spec.file_extensions):
        _ALIAS[alias.lower()] = spec.id
    return spec


_REGISTRY: dict[SourceLanguage, LanguageSpec] = {}
_SUFFIX_INDEX: dict[str, SourceLanguage] = {}
_ALIAS: dict[str, SourceLanguage] = {}

C = _register(
    LanguageSpec(
        id=SourceLanguage.C,
        display_name="C",
        file_extensions=(".c", ".h"),
        monaco_id="c",
        markdown_fence="c",
        default_export_extension=".c",
        compiler_lane="c",
        verify_language_id="c",
        discovery_label="C source",
        readable_validator="c",
    )
)
CXX = _register(
    LanguageSpec(
        id=SourceLanguage.CXX,
        display_name="C++",
        file_extensions=(".cpp", ".cxx", ".cc", ".hpp", ".hh", ".hxx"),
        monaco_id="cpp",
        markdown_fence="cpp",
        default_export_extension=".cpp",
        compiler_lane="cxx",
        verify_language_id="c++",
        discovery_label="C++ source",
        readable_validator="cxx",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.RUST,
        display_name="Rust",
        file_extensions=(".rs",),
        monaco_id="rust",
        markdown_fence="rust",
        default_export_extension=".rs",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="Rust source",
        readable_validator="rust",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.GO,
        display_name="Go",
        file_extensions=(".go",),
        monaco_id="go",
        markdown_fence="go",
        default_export_extension=".go",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="Go source",
        readable_validator="go",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.CSHARP,
        display_name="C#",
        file_extensions=(".cs",),
        monaco_id="csharp",
        markdown_fence="csharp",
        default_export_extension=".cs",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="C# source",
        readable_validator="csharp",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.JAVA,
        display_name="Java",
        file_extensions=(".java",),
        monaco_id="java",
        markdown_fence="java",
        default_export_extension=".java",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="Java source",
        readable_validator="java",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.GAS,
        display_name="GNU assembly",
        file_extensions=(".s",),
        monaco_id="agentdecompile-asm",
        markdown_fence="gas",
        default_export_extension=".s",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="GNU assembly",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.MASM,
        display_name="MASM assembly",
        file_extensions=(".asm",),
        monaco_id="agentdecompile-asm",
        markdown_fence="masm",
        default_export_extension=".asm",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="MASM assembly",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.ASM,
        display_name="Assembly",
        file_extensions=(),
        monaco_id="agentdecompile-asm",
        markdown_fence="asm",
        default_export_extension=".asm",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="Assembly listing",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.TEXT,
        display_name="Plain text",
        file_extensions=(".txt",),
        monaco_id="plaintext",
        markdown_fence="text",
        default_export_extension=".txt",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label="Text artifact",
    )
)
_register(
    LanguageSpec(
        id=SourceLanguage.UNKNOWN,
        display_name="Unknown",
        file_extensions=(),
        monaco_id="plaintext",
        markdown_fence="text",
        default_export_extension=".txt",
        compiler_lane=None,
        verify_language_id=None,
        discovery_label=None,
    )
)

# Common aliases not covered by extensions alone.
for alias, target in {
    "c++": SourceLanguage.CXX,
    "cpp": SourceLanguage.CXX,
    "cxx": SourceLanguage.CXX,
    "c#": SourceLanguage.CSHARP,
    "cs": SourceLanguage.CSHARP,
    "csharp": SourceLanguage.CSHARP,
    "rs": SourceLanguage.RUST,
    "rust": SourceLanguage.RUST,
    "go": SourceLanguage.GO,
    "java": SourceLanguage.JAVA,
    "masm": SourceLanguage.MASM,
    "gas": SourceLanguage.GAS,
    "asm": SourceLanguage.ASM,
    "assembly": SourceLanguage.ASM,
    "text": SourceLanguage.TEXT,
}.items():
    _ALIAS[alias] = target


def default_source_language() -> SourceLanguage:
    return SourceLanguage.CXX


def language_spec(language: SourceLanguage) -> LanguageSpec:
    return _REGISTRY.get(language, _REGISTRY[SourceLanguage.UNKNOWN])


def parse_source_language(value: object, *, default: SourceLanguage | None = None) -> SourceLanguage:
    text = str(value or "").strip().lower()
    if not text:
        return default or default_source_language()
    if text in _ALIAS:
        return _ALIAS[text]
    try:
        return SourceLanguage(text)
    except ValueError:
        return default or SourceLanguage.UNKNOWN


def language_from_path(path: Path | str, *, default: SourceLanguage | None = None) -> SourceLanguage:
    suffix = Path(path).suffix.lower()
    if suffix in _SUFFIX_INDEX:
        return _SUFFIX_INDEX[suffix]
    return default or SourceLanguage.UNKNOWN


def language_from_metadata(meta: Mapping[str, Any] | None, path: Path | str | None = None) -> SourceLanguage:
    meta = meta or {}
    explicit = parse_source_language(
        meta.get("sourceLanguage") or meta.get("source_language") or meta.get("recoveryLanguage"),
        default=None,
    )
    if explicit is not SourceLanguage.UNKNOWN:
        return explicit
    lane = str(meta.get("compilerLane") or meta.get("compiler_lane") or "").lower()
    if lane in {"cxx", "c++", "cpp"}:
        return SourceLanguage.CXX
    if lane == "c":
        return SourceLanguage.C
    if path is not None:
        guessed = language_from_path(path, default=None)
        if guessed is not SourceLanguage.UNKNOWN:
            return guessed
    return default_source_language()


def source_file_suffixes() -> frozenset[str]:
    return frozenset(_SUFFIX_INDEX)


def compiler_lane_for(language: SourceLanguage) -> str | None:
    return language_spec(language).compiler_lane


def verify_language_id(language: SourceLanguage) -> str | None:
    return language_spec(language).verify_language_id


def discovery_label_for(language: SourceLanguage) -> str:
    spec = language_spec(language)
    return spec.discovery_label or f"{spec.display_name} source"


def source_dump_kind_label() -> str:
    """Human label for mixed high-level source dumps."""
    return "high-level source dump"
