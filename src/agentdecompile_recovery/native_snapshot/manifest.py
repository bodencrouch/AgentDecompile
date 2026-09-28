"""Snapshot manifest schema for native decompiler replay (schema v0).

Pure Python. No Ghidra, JPype, or pyghidra imports so that JVM-free jobs
(replayers, differential harnesses, CI unit tests) can read and validate a
snapshot directory produced by :mod:`agentdecompile_recovery.native_snapshot.exporter`.

Layout of a snapshot directory::

    <dir>/manifest.json
    <dir>/options.xml                 DecompileOptions.encode() text, sha256 in manifest.options
    <dir>/functions/<addr16>.xml      DecompileDebug savefile (overlay: <space>__<addr16>.xml)
    <dir>/functions/<addr16>.partial.xml   timed-out / failed decompiles (excluded from replay)
    <dir>/oracle/<addr16>.c           Java DecompiledFunction.getC() from the same decompile
    <dir>/oracle/<addr16>.json        status, error, decompile_ms, warnings, signature
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
from urllib.parse import quote
from typing import Any

SCHEMA = "agentdecompile.native-snapshot/v0"
EXPORTER_VERSION = "0.1.0"
SLA_FORMAT_VERSION = 4
MANIFEST_FILENAME = "manifest.json"
OPTIONS_FILENAME = "options.xml"
FUNCTIONS_DIRNAME = "functions"
ORACLE_DIRNAME = "oracle"

STATUS_OK = "ok"
STATUS_TIMED_OUT = "timed_out"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"
STATUSES: tuple[str, ...] = (STATUS_OK, STATUS_TIMED_OUT, STATUS_ERROR, STATUS_SKIPPED)

SKIP_EXTERNAL = "external"
SKIP_THUNK = "thunk"
SKIP_NO_BODY = "no_body"
SKIP_UNSUPPORTED_NAME = "unsupported_name"
SKIP_REASONS: tuple[str, ...] = (SKIP_EXTERNAL, SKIP_THUNK, SKIP_NO_BODY, SKIP_UNSUPPORTED_NAME)

SUPPORTED_CAPABILITIES: tuple[str, ...] = ("decompile-c",)
UNSUPPORTED_LANGUAGES: tuple[str, ...] = ("JVM", "Dalvik")
SIMPLIFICATION_STYLE = "decompile"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_SPACE = re.compile(r"[^A-Za-z0-9_.-]")


def addr16(offset: int) -> str:
    """Render an address offset as 16 lower-case hex digits."""
    if offset < 0:
        raise ValueError(f"negative address offset: {offset}")
    return f"{offset:016x}"


def safe_space_name(space: str) -> str:
    """Make an address-space name safe for use as a file-name prefix."""
    cleaned = _SAFE_SPACE.sub("_", space.strip())
    return cleaned or "space"


def savefile_name(space: str, offset: int, overlay: bool) -> str:
    """Name of the savefile for a function entry point.

    Non-overlay functions are keyed by address alone (``<addr16>.xml``); functions in
    an overlay space carry the space name so two overlays at the same offset do not
    collide (``<space>__<addr16>.xml``).
    """
    stem = addr16(offset)
    if overlay:
        return f"{safe_space_name(space)}__{stem}.xml"
    return f"{stem}.xml"


def partial_name(savefile: str) -> str:
    """Name a savefile is renamed to when the decompile did not complete."""
    if savefile.endswith(".partial.xml"):
        return savefile
    if savefile.endswith(".xml"):
        return savefile[: -len(".xml")] + ".partial.xml"
    return savefile + ".partial.xml"


def is_partial_name(savefile: str) -> bool:
    return savefile.endswith(".partial.xml")


def savefile_stem(savefile: str) -> str:
    """``<addr16>`` or ``<space>__<addr16>`` without any ``.xml`` / ``.partial.xml`` suffix."""
    if savefile.endswith(".partial.xml"):
        return savefile[: -len(".partial.xml")]
    if savefile.endswith(".xml"):
        return savefile[: -len(".xml")]
    return savefile


def oracle_names(savefile: str) -> tuple[str, str]:
    """``(oracle/<stem>.c, oracle/<stem>.json)`` relative names for a savefile."""
    stem = savefile_stem(savefile)
    return f"{ORACLE_DIRNAME}/{stem}.c", f"{ORACLE_DIRNAME}/{stem}.json"


@dataclass
class Producer:
    ghidra_version: str
    pyghidra_version: str
    jpype_version: str
    exporter_version: str = EXPORTER_VERSION
    host: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Producer:
        return cls(
            ghidra_version=str(data.get("ghidra_version", "")),
            pyghidra_version=str(data.get("pyghidra_version", "")),
            jpype_version=str(data.get("jpype_version", "")),
            exporter_version=str(data.get("exporter_version", "")),
            host=dict(data.get("host") or {}),
        )


@dataclass
class ProgramInfo:
    name: str
    language_id: str
    compiler_spec_id: str
    image_base: str
    executable_path: str | None = None
    md5: str | None = None
    sha256: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgramInfo:
        return cls(
            name=str(data.get("name", "")),
            language_id=str(data.get("language_id", "")),
            compiler_spec_id=str(data.get("compiler_spec_id", "")),
            image_base=str(data.get("image_base", "")),
            executable_path=data.get("executable_path"),
            md5=data.get("md5"),
            sha256=data.get("sha256"),
            metadata={str(k): str(v) for k, v in (data.get("metadata") or {}).items()},
        )


@dataclass
class EngineInfo:
    """Facts about the Java-side decompiler engine that produced the savefiles.

    ``sig_major``/``sig_minor`` are the pair ``DecompInterface.getMajorVersion()`` /
    ``getMinorVersion()`` expose. That is the signature-settings pair, a parity proxy,
    not a build id. ``java_sla_sha256`` maps language id to the sha256 of the compiled
    ``.sla`` file in the Ghidra install used for the export.
    """

    sig_major: int
    sig_minor: int
    sla_format_version: int = SLA_FORMAT_VERSION
    java_sla_sha256: dict[str, str] = field(default_factory=dict)
    respawns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngineInfo:
        return cls(
            sig_major=int(data.get("sig_major", 0)),
            sig_minor=int(data.get("sig_minor", 0)),
            sla_format_version=int(data.get("sla_format_version", 0)),
            java_sla_sha256={str(k): str(v) for k, v in (data.get("java_sla_sha256") or {}).items()},
            respawns=int(data.get("respawns", 0)),
        )


@dataclass
class OptionsInfo:
    sha256: str
    simplification_style: str = SIMPLIFICATION_STYLE
    path: str = OPTIONS_FILENAME

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptionsInfo:
        return cls(
            sha256=str(data.get("sha256", "")),
            simplification_style=str(data.get("simplification_style", "")),
            path=str(data.get("path", OPTIONS_FILENAME)),
        )


@dataclass
class Capabilities:
    supports: list[str] = field(default_factory=lambda: list(SUPPORTED_CAPABILITIES))
    unsupported_languages: list[str] = field(default_factory=lambda: list(UNSUPPORTED_LANGUAGES))
    supported: bool = True
    overlay_spaces: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Capabilities:
        return cls(
            supports=[str(x) for x in (data.get("supports") or [])],
            unsupported_languages=[str(x) for x in (data.get("unsupported_languages") or [])],
            supported=bool(data.get("supported", False)),
            overlay_spaces=[str(x) for x in (data.get("overlay_spaces") or [])],
        )


@dataclass
class Revision:
    """Program modification numbers observed around the export.

    ``stale`` is True when the program changed while the export ran. A stale snapshot
    may mix pre- and post-change state and must not be used as a parity baseline.
    """

    modification_number_before: int
    modification_number_after: int
    stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Revision:
        return cls(
            modification_number_before=int(data.get("modification_number_before", -1)),
            modification_number_after=int(data.get("modification_number_after", -1)),
            stale=bool(data.get("stale", False)),
        )


@dataclass
class Counts:
    total: int = 0
    ok: int = 0
    timed_out: int = 0
    error: int = 0
    skipped: int = 0
    skipped_by_reason: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Counts:
        return cls(
            total=int(data.get("total", 0)),
            ok=int(data.get("ok", 0)),
            timed_out=int(data.get("timed_out", 0)),
            error=int(data.get("error", 0)),
            skipped=int(data.get("skipped", 0)),
            skipped_by_reason={str(k): int(v) for k, v in (data.get("skipped_by_reason") or {}).items()},
        )

    @classmethod
    def from_entries(cls, entries: list[FunctionEntry]) -> Counts:
        counts = cls(total=len(entries))
        for entry in entries:
            if entry.status == STATUS_OK:
                counts.ok += 1
            elif entry.status == STATUS_TIMED_OUT:
                counts.timed_out += 1
            elif entry.status == STATUS_ERROR:
                counts.error += 1
            elif entry.status == STATUS_SKIPPED:
                counts.skipped += 1
                reason = entry.skip_reason or "unknown"
                counts.skipped_by_reason[reason] = counts.skipped_by_reason.get(reason, 0) + 1
        return counts


@dataclass
class FunctionEntry:
    """One function in the snapshot.

    ``addr`` is the 16-digit hex offset; ``space`` the address-space name; ``name`` the
    plain symbol name written into the savefile ``name`` attribute; ``load_name`` the
    ``::``-qualified name for ``load function``. ``savefile`` and the oracle paths are
    relative to the snapshot directory and use ``/`` separators.
    """

    addr: str
    space: str
    name: str
    load_name: str
    size: int
    status: str
    savefile: str | None = None
    sha256: str | None = None
    decompile_ms: int | None = None
    java_c_sha256: str | None = None
    oracle_c: str | None = None
    oracle_json: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    skip_reason: str | None = None
    overlay: bool = False
    load_mode: str = "function"

    @property
    def stable_id(self) -> str:
        """Space-qualified identity used by replay transports and receipts."""
        return f"{self.space}:{self.addr}"

    @property
    def stable_stem(self) -> str:
        """Filesystem-safe form of :attr:`stable_id` for collision-free artifacts."""
        return f"{quote(self.space, safe='')}__{self.addr}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FunctionEntry:
        return cls(
            addr=str(data.get("addr", "")),
            space=str(data.get("space", "")),
            name=str(data.get("name", "")),
            load_name=str(data.get("load_name", "")),
            size=int(data.get("size", 0)),
            status=str(data.get("status", "")),
            savefile=data.get("savefile"),
            sha256=data.get("sha256"),
            decompile_ms=data.get("decompile_ms"),
            java_c_sha256=data.get("java_c_sha256"),
            oracle_c=data.get("oracle_c"),
            oracle_json=data.get("oracle_json"),
            warnings=[str(x) for x in (data.get("warnings") or [])],
            error=data.get("error"),
            skip_reason=data.get("skip_reason"),
            overlay=bool(data.get("overlay", False)),
            load_mode=str(data.get("load_mode", "function")),
        )


@dataclass
class Manifest:
    producer: Producer
    program: ProgramInfo
    engine: EngineInfo
    options: OptionsInfo
    capabilities: Capabilities
    revision: Revision
    counts: Counts = field(default_factory=Counts)
    functions: list[FunctionEntry] = field(default_factory=list)
    total_bytes: int = 0
    timeout_s: int = 60
    created_at: str = ""
    wall_s: float = 0.0
    schema: str = SCHEMA
    export_requires_java_decompile: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "export_requires_java_decompile": self.export_requires_java_decompile,
            "created_at": self.created_at,
            "timeout_s": self.timeout_s,
            "wall_s": self.wall_s,
            "producer": self.producer.to_dict(),
            "program": self.program.to_dict(),
            "engine": self.engine.to_dict(),
            "options": self.options.to_dict(),
            "capabilities": self.capabilities.to_dict(),
            "revision": self.revision.to_dict(),
            "counts": self.counts.to_dict(),
            "total_bytes": self.total_bytes,
            "functions": [f.to_dict() for f in self.functions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        return cls(
            schema=str(data.get("schema", "")),
            export_requires_java_decompile=bool(data.get("export_requires_java_decompile", False)),
            created_at=str(data.get("created_at", "")),
            timeout_s=int(data.get("timeout_s", 0)),
            wall_s=float(data.get("wall_s", 0.0)),
            producer=Producer.from_dict(data.get("producer") or {}),
            program=ProgramInfo.from_dict(data.get("program") or {}),
            engine=EngineInfo.from_dict(data.get("engine") or {}),
            options=OptionsInfo.from_dict(data.get("options") or {}),
            capabilities=Capabilities.from_dict(data.get("capabilities") or {}),
            revision=Revision.from_dict(data.get("revision") or {}),
            counts=Counts.from_dict(data.get("counts") or {}),
            total_bytes=int(data.get("total_bytes", 0)),
            functions=[FunctionEntry.from_dict(f) for f in (data.get("functions") or [])],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    def ok_entries(self) -> list[FunctionEntry]:
        return [f for f in self.functions if f.status == STATUS_OK]

    def recount(self) -> None:
        self.counts = Counts.from_entries(self.functions)

    def write(self, path: Path | str) -> Path:
        """Write the manifest atomically (temp file + ``os.replace``)."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.to_json())
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        return target

    @classmethod
    def load(cls, path: Path | str) -> Manifest:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        errors = validate_manifest(data)
        if errors:
            raise ValueError("invalid snapshot manifest: " + "; ".join(errors))
        return cls.from_dict(data)


def load_manifest(snapshot_dir: Path | str) -> Manifest:
    return Manifest.load(Path(snapshot_dir) / MANIFEST_FILENAME)


_REQUIRED_TOP: tuple[str, ...] = ("schema", "export_requires_java_decompile", "producer", "program", "engine", "options", "capabilities", "revision", "counts", "total_bytes", "functions")
_REQUIRED_PRODUCER: tuple[str, ...] = ("ghidra_version", "pyghidra_version", "jpype_version", "exporter_version", "host")
_REQUIRED_PROGRAM: tuple[str, ...] = ("name", "language_id", "compiler_spec_id", "image_base")
_REQUIRED_ENGINE: tuple[str, ...] = ("sig_major", "sig_minor", "sla_format_version", "java_sla_sha256", "respawns")
_REQUIRED_OPTIONS: tuple[str, ...] = ("sha256", "simplification_style")
_REQUIRED_CAPABILITIES: tuple[str, ...] = ("supports", "unsupported_languages", "supported")
_REQUIRED_REVISION: tuple[str, ...] = ("modification_number_before", "modification_number_after", "stale")
_REQUIRED_COUNTS: tuple[str, ...] = ("total", "ok", "timed_out", "error", "skipped")
_REQUIRED_FUNCTION: tuple[str, ...] = ("addr", "space", "name", "load_name", "size", "status")


def _check_keys(section: dict[str, Any] | None, required: tuple[str, ...], label: str, errors: list[str]) -> bool:
    if not isinstance(section, dict):
        errors.append(f"{label}: expected object")
        return False
    for key in required:
        if key not in section:
            errors.append(f"{label}.{key}: missing")
    return True


def validate_manifest(data: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems; empty means the manifest is valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest: expected a JSON object"]
    for key in _REQUIRED_TOP:
        if key not in data:
            errors.append(f"{key}: missing")
    if errors:
        return errors

    if data["schema"] != SCHEMA:
        errors.append(f"schema: expected {SCHEMA!r}, got {data['schema']!r}")
    if data["export_requires_java_decompile"] is not True:
        errors.append("export_requires_java_decompile: must be true for schema v0")
    if not isinstance(data["total_bytes"], int) or data["total_bytes"] < 0:
        errors.append("total_bytes: expected non-negative integer")

    _check_keys(data.get("producer"), _REQUIRED_PRODUCER, "producer", errors)
    _check_keys(data.get("program"), _REQUIRED_PROGRAM, "program", errors)

    engine = data.get("engine")
    if _check_keys(engine, _REQUIRED_ENGINE, "engine", errors):
        if not isinstance(engine.get("sla_format_version"), int):
            errors.append("engine.sla_format_version: expected integer")
        if not isinstance(engine.get("java_sla_sha256"), dict):
            errors.append("engine.java_sla_sha256: expected object")
        else:
            for lang, digest in engine["java_sla_sha256"].items():
                if not isinstance(digest, str) or not _HEX64.match(digest):
                    errors.append(f"engine.java_sla_sha256[{lang!r}]: expected 64 hex digits")

    options = data.get("options")
    if _check_keys(options, _REQUIRED_OPTIONS, "options", errors):
        if not isinstance(options.get("sha256"), str) or not _HEX64.match(options["sha256"]):
            errors.append("options.sha256: expected 64 hex digits")
        if options.get("simplification_style") != SIMPLIFICATION_STYLE:
            errors.append(f"options.simplification_style: schema v0 only records {SIMPLIFICATION_STYLE!r}")
        if options.get("path", OPTIONS_FILENAME) != OPTIONS_FILENAME:
            errors.append(f"options.path: schema v0 requires {OPTIONS_FILENAME!r}")

    caps = data.get("capabilities")
    if _check_keys(caps, _REQUIRED_CAPABILITIES, "capabilities", errors):
        supports = caps.get("supports")
        if not isinstance(supports, list) or "decompile-c" not in supports:
            errors.append("capabilities.supports: must list 'decompile-c'")
        if not isinstance(caps.get("supported"), bool):
            errors.append("capabilities.supported: expected boolean")

    revision = data.get("revision")
    if _check_keys(revision, _REQUIRED_REVISION, "revision", errors):
        before = revision.get("modification_number_before")
        after = revision.get("modification_number_after")
        stale = revision.get("stale")
        if not isinstance(stale, bool):
            errors.append("revision.stale: expected boolean")
        elif isinstance(before, int) and isinstance(after, int) and (before != after) != stale:
            errors.append("revision.stale: inconsistent with modification numbers")

    functions = data.get("functions")
    counts = data.get("counts")
    counts_ok = _check_keys(counts, _REQUIRED_COUNTS, "counts", errors)
    if not isinstance(functions, list):
        errors.append("functions: expected list")
        return errors

    seen_savefiles: set[str] = set()
    tally = {STATUS_OK: 0, STATUS_TIMED_OUT: 0, STATUS_ERROR: 0, STATUS_SKIPPED: 0}
    for index, entry in enumerate(functions):
        label = f"functions[{index}]"
        if not _check_keys(entry, _REQUIRED_FUNCTION, label, errors):
            continue
        status = entry.get("status")
        if status not in STATUSES:
            errors.append(f"{label}.status: unknown status {status!r}")
            continue
        tally[status] += 1
        addr = entry.get("addr")
        addr_valid = isinstance(addr, str) and len(addr) == 16 and not any(c not in "0123456789abcdef" for c in addr)
        if not addr_valid:
            errors.append(f"{label}.addr: expected 16 lower-case hex digits")
        space = entry.get("space")
        overlay = entry.get("overlay", False)
        if not isinstance(space, str) or not space:
            errors.append(f"{label}.space: expected non-empty string")
        if not isinstance(overlay, bool):
            errors.append(f"{label}.overlay: expected boolean")
        load_name = entry.get("load_name")
        if not isinstance(load_name, str) or not load_name or any(ch in load_name for ch in "\r\n\0"):
            errors.append(f"{label}.load_name: expected non-empty single-line string")
        expected_savefile = None
        if addr_valid and isinstance(space, str) and isinstance(overlay, bool):
            expected_savefile = f"{FUNCTIONS_DIRNAME}/{savefile_name(space, int(addr, 16), overlay)}"
        savefile = entry.get("savefile")
        if status == STATUS_OK:
            if not isinstance(savefile, str) or not savefile.endswith(".xml") or is_partial_name(savefile):
                errors.append(f"{label}.savefile: ok entries need a '.xml' savefile that is not '.partial.xml'")
            elif expected_savefile is not None and savefile != expected_savefile:
                errors.append(f"{label}.savefile: expected snapshot-relative path {expected_savefile!r}")
            digest = entry.get("sha256")
            if not isinstance(digest, str) or not _HEX64.match(digest):
                errors.append(f"{label}.sha256: expected 64 hex digits for ok entry")
            if expected_savefile is not None:
                expected_oracle_c, expected_oracle_json = oracle_names(expected_savefile.rsplit("/", 1)[-1])
                if entry.get("oracle_c") != expected_oracle_c:
                    errors.append(f"{label}.oracle_c: expected snapshot-relative path {expected_oracle_c!r}")
                if entry.get("oracle_json") != expected_oracle_json:
                    errors.append(f"{label}.oracle_json: expected snapshot-relative path {expected_oracle_json!r}")
        elif status == STATUS_TIMED_OUT:
            if savefile is not None and not is_partial_name(savefile):
                errors.append(f"{label}.savefile: timed_out entries must reference a '.partial.xml' savefile or null")
            elif savefile is not None and expected_savefile is not None and savefile != f"{FUNCTIONS_DIRNAME}/{partial_name(expected_savefile.rsplit('/', 1)[-1])}":
                errors.append(f"{label}.savefile: timed_out path does not match its address and space")
        elif status == STATUS_SKIPPED:
            if entry.get("skip_reason") not in SKIP_REASONS:
                errors.append(f"{label}.skip_reason: expected one of {SKIP_REASONS}")
        if isinstance(savefile, str):
            if savefile in seen_savefiles:
                errors.append(f"{label}.savefile: duplicate {savefile!r}")
            seen_savefiles.add(savefile)
        warnings_value = entry.get("warnings", [])
        if not isinstance(warnings_value, list):
            errors.append(f"{label}.warnings: expected list")

    if counts_ok:
        expected = {"total": len(functions), **tally}
        for key, value in expected.items():
            if counts.get(key) != value:
                errors.append(f"counts.{key}: expected {value}, got {counts.get(key)!r}")
    return errors
