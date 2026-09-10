"""Export per-function decompiler savefiles (Ghidra ``DecompileDebug`` format) plus oracle C.

One Java decompile per function. Each call to ``DecompInterface.decompileFunction``
captures every host query the native decompiler made into ``<xml_savefile>`` so a
JVM-free replayer can re-run the same decompile later. ``enableDebug`` is one-shot:
``decompileFunction`` always shuts the debug file and nulls it (also on timeout or
exception), so it is re-armed before every call.

All Ghidra/JPype imports are local to the functions that need them; importing this
module never starts a JVM.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import time
from typing import Any

from agentdecompile_recovery.native_snapshot.manifest import (
    EXPORTER_VERSION,
    FUNCTIONS_DIRNAME,
    MANIFEST_FILENAME,
    OPTIONS_FILENAME,
    ORACLE_DIRNAME,
    SIMPLIFICATION_STYLE,
    SKIP_EXTERNAL,
    SKIP_NO_BODY,
    SKIP_THUNK,
    SKIP_UNSUPPORTED_NAME,
    SLA_FORMAT_VERSION,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_SKIPPED,
    STATUS_TIMED_OUT,
    UNSUPPORTED_LANGUAGES,
    Capabilities,
    Counts,
    EngineInfo,
    FunctionEntry,
    Manifest,
    OptionsInfo,
    Producer,
    ProgramInfo,
    Revision,
    addr16,
    oracle_names,
    partial_name,
    savefile_name,
)

_WARNING_RE = re.compile(r"/\*\s*WARNING:\s*(.*?)\s*\*/")
_MASK64 = (1 << 64) - 1


class SnapshotPreconditionError(RuntimeError):
    """The program or decompiler is not in a state the exporter accepts."""


class UnsupportedStyleError(SnapshotPreconditionError):
    """The configured simplification style is not ``decompile`` (schema v0 records only that)."""


class SnapshotStaleError(RuntimeError):
    """The program changed while the export ran. ``manifest`` was still written with ``revision.stale``."""

    def __init__(self, manifest: Manifest, message: str | None = None):
        super().__init__(message or f"program modification number changed during export ({manifest.revision.modification_number_before} -> {manifest.revision.modification_number_after})")
        self.manifest = manifest


def _has_open_transaction(program: Any) -> bool:
    """Return whether ``program`` has a live caller-owned transaction.

    PyGhidra 3.0.x leaves one historical transaction record on a freshly
    imported program.  Ghidra reports it as either ``""`` or ``"Batch
    Processing"`` depending on the loader path. It has a positive id, but is
    no longer endable and must not make an otherwise read-only export impossible.
    A real transaction is represented as an additional open subtransaction.
    Other bindings do not have that historical record, so any transaction info
    without this exact empty PyGhidra shape remains conservative (open).
    """
    info = program.getCurrentTransactionInfo()
    if info is None:
        return False
    try:
        open_transactions = [str(item) for item in info.getOpenSubTransactions()]
    except Exception:
        return True
    return open_transactions not in ([""], ["Batch Processing"])


@dataclass
class ProgressEvent:
    index: int
    total: int
    addr: str
    name: str
    status: str
    decompile_ms: int | None = None
    skip_reason: str | None = None
    error: str | None = None


ProgressCallback = Callable[[ProgressEvent], None]
Configurer = Callable[[Any, Any], None]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_warnings(c_text: str) -> list[str]:
    """Unique ``/* WARNING: ... */`` comment bodies in order of first appearance."""
    seen: list[str] = []
    for match in _WARNING_RE.finditer(c_text):
        text = match.group(1).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _unsigned_offset(address: Any) -> int:
    try:
        return int(address.getUnsignedOffset()) & _MASK64
    except Exception:
        return int(address.getOffset()) & _MASK64


def _jstr(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def default_configurer() -> Configurer:
    """The shared option configurer (grabFromProgram, 100 MB payload, C code on, syntax tree off, style ``decompile``)."""
    from agentdecompile_cli.mcp_utils.decompiler_util import _configure_decompiler_for_program

    return _configure_decompiler_for_program


def resolve_functions(program: Any, addresses: Iterable[int | str]) -> list[Any]:
    """Map addresses (ints or Ghidra address strings such as ``ram:00401000``) to Function objects.

    Raises ``ValueError`` for an address that does not start or fall inside a function.
    """
    factory = program.getAddressFactory()
    manager = program.getFunctionManager()
    resolved: list[Any] = []
    for raw in addresses:
        if isinstance(raw, int):
            address = factory.getDefaultAddressSpace().getAddress(raw)
        else:
            text = str(raw).strip()
            address = factory.getAddress(text)
            if address is None:
                try:
                    address = factory.getDefaultAddressSpace().getAddress(int(text, 0))
                except ValueError:
                    address = None
        if address is None:
            raise ValueError(f"unparseable address: {raw!r}")
        func = manager.getFunctionAt(address)
        if func is None:
            func = manager.getFunctionContaining(address)
        if func is None:
            raise ValueError(f"no function at {address}")
        if all(f.getEntryPoint() != func.getEntryPoint() for f in resolved):
            resolved.append(func)
    return resolved


def _skip_reason(func: Any, load_name: str) -> str | None:
    if func.isExternal():
        return SKIP_EXTERNAL
    if func.isThunk():
        return SKIP_THUNK
    body = func.getBody()
    if body is None or body.isEmpty():
        return SKIP_NO_BODY
    if any(ch.isspace() for ch in load_name) or not load_name:
        return SKIP_UNSUPPORTED_NAME
    return None


def _encode_options_xml(ifc: Any) -> str:
    """Byte-identical text to what ``DecompileDebug`` embeds in the savefile (``options.encode(new XmlEncode(), ifc)``)."""
    from ghidra.program.model.pcode import XmlEncode

    options = ifc.getOptions()
    if options is None:
        raise SnapshotPreconditionError("DecompInterface has no options set; the configurer must call setOptions")
    encoder = XmlEncode()
    options.encode(encoder, ifc)
    return str(encoder.toString())


def _sla_hashes(program: Any) -> dict[str, str]:
    language = program.getLanguage()
    language_id = str(program.getLanguageID().getIdAsString())
    try:
        description = language.getLanguageDescription()
        sla_file = description.getSlaFile()
    except Exception:
        return {}
    if sla_file is None:
        return {}
    path = Path(str(sla_file.getAbsolutePath()))
    if not path.is_file():
        return {}
    return {language_id: sha256_file(path)}


def _producer() -> Producer:
    import jpype

    from ghidra.framework import Application
    from java.lang import System

    try:
        import pyghidra

        pyghidra_version = str(getattr(pyghidra, "__version__", "") or "")
    except Exception:
        pyghidra_version = ""
    if not pyghidra_version:
        try:
            from importlib.metadata import version as _dist_version

            pyghidra_version = _dist_version("pyghidra")
        except Exception:
            pyghidra_version = "unknown"
    host = {
        "platform": platform.platform(),
        "node": platform.node(),
        "python": platform.python_version(),
        "java": str(System.getProperty("java.version") or ""),
    }
    return Producer(
        ghidra_version=str(Application.getApplicationVersion()),
        pyghidra_version=pyghidra_version,
        jpype_version=str(getattr(jpype, "__version__", "unknown")),
        exporter_version=EXPORTER_VERSION,
        host=host,
    )


def _program_info(program: Any) -> ProgramInfo:
    metadata: dict[str, str] = {}
    try:
        for key, value in program.getMetadata().entrySet():
            metadata[str(key)] = str(value)
    except Exception:
        metadata = {}
    return ProgramInfo(
        name=str(program.getName()),
        language_id=str(program.getLanguageID().getIdAsString()),
        compiler_spec_id=str(program.getCompilerSpec().getCompilerSpecID().getIdAsString()),
        image_base=str(program.getImageBase()),
        executable_path=_jstr(program.getExecutablePath()),
        md5=_jstr(program.getExecutableMD5()),
        sha256=_jstr(program.getExecutableSHA256()),
        metadata=metadata,
    )


def _overlay_spaces(program: Any) -> list[str]:
    names: list[str] = []
    try:
        for space in program.getAddressFactory().getAddressSpaces():
            if space.isOverlaySpace():
                names.append(str(space.getName()))
    except Exception:
        pass
    return sorted(names)


def _dir_bytes(root: Path) -> int:
    total = 0
    if not root.is_dir():
        return 0
    for entry in root.iterdir():
        if entry.is_file():
            total += entry.stat().st_size
    return total


class _Engine:
    """Owns one ``DecompInterface`` bound to a program; can be re-created after a native failure."""

    def __init__(self, program: Any, configurer: Configurer):
        self.program = program
        self.configurer = configurer
        self.ifc: Any = None
        self.respawns = 0

    def open(self) -> None:
        from ghidra.app.decompiler import DecompInterface

        ifc = DecompInterface()
        self.configurer(ifc, self.program)
        style = str(ifc.getSimplificationStyle() or "")
        if style != SIMPLIFICATION_STYLE:
            ifc.dispose()
            raise UnsupportedStyleError(f"simplification style {style!r} is not supported by snapshot schema v0 (only {SIMPLIFICATION_STYLE!r}; the savefile does not record the action name)")
        if not ifc.openProgram(self.program):
            message = str(ifc.getLastMessage() or "")
            ifc.dispose()
            raise SnapshotPreconditionError(f"DecompInterface.openProgram failed: {message}")
        self.ifc = ifc

    def respawn(self) -> None:
        self.close()
        self.respawns += 1
        self.open()

    def close(self) -> None:
        if self.ifc is not None:
            try:
                self.ifc.dispose()
            finally:
                self.ifc = None

    def decompile(self, func: Any, savefile: Path, timeout_s: int) -> tuple[Any, int]:
        """Run one debug-armed decompile under the program's exclusive lock. Returns ``(DecompileResults, ms)``."""
        from ghidra.util.task import TimeoutTaskMonitor
        from java.io import File as JFile
        from java.util.concurrent import TimeUnit

        lock = self.program.getLock()
        monitor = TimeoutTaskMonitor.timeoutIn(int(timeout_s), TimeUnit.SECONDS)
        started = time.perf_counter()
        lock.acquire()
        try:
            self.ifc.enableDebug(JFile(str(savefile)))
            results = self.ifc.decompileFunction(func, int(timeout_s), monitor)
        finally:
            lock.release()
        return results, int(round((time.perf_counter() - started) * 1000))


def export_snapshot(
    program: Any,
    out_dir: Path | str,
    *,
    functions: Iterable[Any] | None = None,
    timeout_s: int = 60,
    configurer: Configurer | None = None,
    on_progress: ProgressCallback | None = None,
    allow_stale: bool = False,
) -> Manifest:
    """Export savefiles, oracle C, options and a manifest for ``program`` into ``out_dir``.

    Args:
        program: An open ``ghidra.program.model.listing.Program`` with no active transaction.
        out_dir: Snapshot directory (created). Existing savefiles for the same functions are replaced.
        functions: Iterable of Ghidra ``Function`` objects; ``None`` exports every function in address order.
        timeout_s: Per-function decompile timeout in seconds (``TimeoutTaskMonitor`` and the native command timeout).
        configurer: ``(DecompInterface, Program) -> None``; defaults to the shared MCP configurer.
        on_progress: Called with a ``ProgressEvent`` after each function.
        allow_stale: When False, a changed modification number stops the export early and raises ``SnapshotStaleError``
            after the manifest (flagged ``revision.stale``) is written. When True the export completes and the flag is set.

    Raises:
        SnapshotPreconditionError: transaction open, ``openProgram`` failed, or options missing.
        UnsupportedStyleError: configurer selected a style other than ``decompile``.
        SnapshotStaleError: program changed during export and ``allow_stale`` is False.
    """
    out = Path(out_dir)
    functions_dir = out / FUNCTIONS_DIRNAME
    oracle_dir = out / ORACLE_DIRNAME
    functions_dir.mkdir(parents=True, exist_ok=True)
    oracle_dir.mkdir(parents=True, exist_ok=True)

    if _has_open_transaction(program):
        raise SnapshotPreconditionError("program has an open transaction; end it before exporting a snapshot")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    wall_started = time.perf_counter()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mod_before = int(program.getModificationNumber())

    engine = _Engine(program, configurer or default_configurer())
    engine.open()
    try:
        options_xml = _encode_options_xml(engine.ifc)
        options_bytes = options_xml.encode("utf-8")
        (out / OPTIONS_FILENAME).write_bytes(options_bytes)
        options_info = OptionsInfo(sha256=sha256_bytes(options_bytes), simplification_style=str(engine.ifc.getSimplificationStyle()))
        sig_major = int(engine.ifc.getMajorVersion())
        sig_minor = int(engine.ifc.getMinorVersion())

        processor = str(program.getLanguage().getProcessor())
        capabilities = Capabilities(supported=processor not in UNSUPPORTED_LANGUAGES, overlay_spaces=_overlay_spaces(program))

        candidates = list(functions) if functions is not None else list(program.getFunctionManager().getFunctions(True))
        total = len(candidates)
        entries: list[FunctionEntry] = []
        stale = False
        mod_after = mod_before

        for index, func in enumerate(candidates):
            entry = _export_one(engine, func, functions_dir, oracle_dir, timeout_s)
            entries.append(entry)
            if on_progress is not None:
                on_progress(ProgressEvent(index=index + 1, total=total, addr=entry.addr, name=entry.name, status=entry.status, decompile_ms=entry.decompile_ms, skip_reason=entry.skip_reason, error=entry.error))
            mod_after = int(program.getModificationNumber())
            if mod_after != mod_before:
                stale = True
                if not allow_stale:
                    break

        mod_after = int(program.getModificationNumber())
        stale = stale or (mod_after != mod_before)
        engine_info = EngineInfo(sig_major=sig_major, sig_minor=sig_minor, sla_format_version=SLA_FORMAT_VERSION, java_sla_sha256=_sla_hashes(program), respawns=engine.respawns)
        manifest = Manifest(
            producer=_producer(),
            program=_program_info(program),
            engine=engine_info,
            options=options_info,
            capabilities=capabilities,
            revision=Revision(modification_number_before=mod_before, modification_number_after=mod_after, stale=stale),
            counts=Counts.from_entries(entries),
            functions=entries,
            total_bytes=_dir_bytes(functions_dir) + _dir_bytes(oracle_dir) + len(options_bytes),
            timeout_s=int(timeout_s),
            created_at=created_at,
            wall_s=round(time.perf_counter() - wall_started, 3),
        )
    finally:
        engine.close()

    manifest.write(out / MANIFEST_FILENAME)
    if stale and not allow_stale:
        raise SnapshotStaleError(manifest)
    return manifest


def _export_one(engine: _Engine, func: Any, functions_dir: Path, oracle_dir: Path, timeout_s: int) -> FunctionEntry:
    entry_point = func.getEntryPoint()
    space = entry_point.getAddressSpace()
    space_name = str(space.getName())
    overlay = bool(space.isOverlaySpace())
    offset = _unsigned_offset(entry_point)
    name = str(func.getName())
    load_name = str(func.getName(True))
    size = int(func.getBody().getNumAddresses()) if func.getBody() is not None else 0
    entry = FunctionEntry(addr=addr16(offset), space=space_name, name=name, load_name=load_name, size=size, status=STATUS_SKIPPED, overlay=overlay)

    reason = _skip_reason(func, load_name)
    if reason is not None:
        entry.skip_reason = reason
        return entry

    file_name = savefile_name(space_name, offset, overlay)
    savefile = functions_dir / file_name
    partial = functions_dir / partial_name(file_name)
    for stale_path in (savefile, partial):
        if stale_path.exists():
            stale_path.unlink()
    oracle_c_rel, oracle_json_rel = oracle_names(file_name)
    oracle_c_path = oracle_dir / Path(oracle_c_rel).name
    oracle_json_path = oracle_dir / Path(oracle_json_rel).name
    for stale_path in (oracle_c_path, oracle_json_path):
        if stale_path.exists():
            stale_path.unlink()

    results, ms = engine.decompile(func, savefile, timeout_s)
    if results.failedToStart():
        engine.respawn()
        results, ms = engine.decompile(func, savefile, timeout_s)

    entry.decompile_ms = ms
    error_message = _jstr(results.getErrorMessage())
    error_message = error_message.strip() if error_message else None
    c_text = ""
    signature = None

    if results.isTimedOut() or results.isCancelled():
        entry.status = STATUS_TIMED_OUT
        entry.error = error_message or f"timed out after {timeout_s}s"
        engine.respawns += 1  # the native process was disposed on timeout; DecompInterface respawns it on the next call
    elif results.decompileCompleted():
        decompiled = results.getDecompiledFunction()
        c_text = str(decompiled.getC()) if decompiled is not None and decompiled.getC() is not None else ""
        signature = _jstr(decompiled.getSignature()) if decompiled is not None else None
        if c_text.strip():
            entry.status = STATUS_OK
        else:
            entry.status = STATUS_ERROR
            entry.error = error_message or "decompile completed with empty C output"
    else:
        entry.status = STATUS_ERROR
        entry.error = error_message or "decompile did not complete"

    if entry.status == STATUS_OK:
        if not savefile.is_file():
            entry.status = STATUS_ERROR
            entry.error = "decompile completed but no savefile was written"
        else:
            entry.savefile = f"{FUNCTIONS_DIRNAME}/{file_name}"
            entry.sha256 = sha256_file(savefile)
            entry.warnings = extract_warnings(c_text)
            c_bytes = c_text.encode("utf-8")
            oracle_c_path.write_bytes(c_bytes)
            entry.java_c_sha256 = sha256_bytes(c_bytes)
            entry.oracle_c = oracle_c_rel
            entry.oracle_json = oracle_json_rel
    if entry.status != STATUS_OK and savefile.is_file():
        os.replace(savefile, partial)
    if entry.status != STATUS_OK and partial.is_file():
        entry.savefile = f"{FUNCTIONS_DIRNAME}/{partial.name}"

    if entry.status != STATUS_SKIPPED:
        record = {
            "addr": entry.addr,
            "space": entry.space,
            "name": entry.name,
            "load_name": entry.load_name,
            "status": entry.status,
            "error": entry.error,
            "decompile_ms": entry.decompile_ms,
            "warnings": entry.warnings,
            "signature": signature,
            "c_sha256": entry.java_c_sha256,
            "savefile": entry.savefile,
        }
        oracle_json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        entry.oracle_json = oracle_json_rel
    return entry
