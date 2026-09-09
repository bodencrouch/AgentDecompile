"""Raw binary import helpers for container-extracted CPU images."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ghidra.program.model.listing import (  # pyright: ignore[reportMissingImports]
        Program as GhidraProgram,
    )


def normalize_language_id(language_id: str) -> str:
    """Strip a trailing ``:default`` compiler suffix from Ghidra language ids."""
    normalized = language_id.strip()
    if normalized.endswith(":default"):
        return normalized[: -len(":default")]
    return normalized


def _resolve_ghidra_project(ghidra_project: Any) -> Any:
    if hasattr(ghidra_project, "getProject"):
        return ghidra_project.getProject()
    return ghidra_project


def _program_from_load_results(load_results: Any, consumer: Any) -> Any:
    """Return an open Program registered against *consumer*.

    Ghidra ``LoadResults.close()`` releases the loader's internal consumer.
    Callers must obtain the program via ``getPrimaryDomainObject(consumer)``
    so the project handle keeps the domain object alive after ``release()``.
    """
    get_primary = getattr(load_results, "getPrimaryDomainObject", None)
    if callable(get_primary):
        return get_primary(consumer)

    raise RuntimeError("LoadResults did not yield a Program")


def finalize_raw_binary_load(
    program: Any,
    *,
    base_address: int,
    entry_point: int | None = None,
    block_name: str | None = None,
) -> dict[str, Any]:
    """Relocate a BinaryLoader import to its real load address and optional entry."""

    result: dict[str, Any] = {
        "baseAddress": f"0x{base_address:08x}",
        "imageBaseBefore": str(program.getImageBase()),
    }
    if base_address <= 0:
        return result

    memory = program.getMemory()
    addr_factory = program.getAddressFactory()
    space = addr_factory.getDefaultAddressSpace()
    target = space.getAddress(base_address)
    tx = program.startTransaction("container-load-model")
    try:
        current_base = int(program.getImageBase().getOffset())
        if current_base != base_address:
            program.setImageBase(target, True)
        if block_name:
            block = memory.getBlock(target)
            if block is None and memory.getNumBlocks() == 1:
                block = memory.getBlock(space.getAddress(0))
            if block is not None and block.getName() != block_name:
                block.setName(block_name)
        if entry_point is not None and entry_point > 0:
            entry_addr = space.getAddress(int(entry_point))
            program.getSymbolTable().addExternalEntryPoint(entry_addr)
            result["entryPoint"] = f"0x{int(entry_point):08x}"
    finally:
        program.endTransaction(tx, True)

    result["imageBaseAfter"] = str(program.getImageBase())
    return result


def import_raw_binary_slice(
    ghidra_project: Any,
    file_path: Path,
    *,
    language_id: str,
    compiler_id: str = "default",
    base_address: int,
    block_name: str,
    program_name: str,
    dest_folder_path: str = "/",
    entry_point: int | None = None,
) -> GhidraProgram:
    """Import a raw binary slice with Ghidra's BinaryLoader and loader options."""
    import pyghidra
    from ghidra.app.util.opinion import BinaryLoader  # pyright: ignore[reportMissingImports]
    from ghidra.util.task import TaskMonitor  # pyright: ignore[reportMissingImports]
    from java.io import File as JavaFile  # pyright: ignore[reportMissingImports]

    resolved_path = Path(file_path).expanduser().resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Binary slice not found: {resolved_path}")

    project = _resolve_ghidra_project(ghidra_project)
    normalized_language = normalize_language_id(language_id)
    if not normalized_language:
        raise ValueError("language_id is required for raw binary import")

    loader = (
        pyghidra.program_loader()
        .project(project)
        .projectFolderPath(dest_folder_path)
        .source(JavaFile(str(resolved_path)))
        .loaders("BinaryLoader")
        .language(normalized_language)
        .compiler(compiler_id)
        .name(program_name)
        .addLoaderArg(BinaryLoader.OPTION_NAME_BASE_ADDR, f"0x{base_address:08x}")
        .addLoaderArg(BinaryLoader.OPTION_NAME_BLOCK_NAME, block_name)
    )

    load_results = loader.load()
    try:
        program = _program_from_load_results(load_results, ghidra_project)
        if program is None:
            raise RuntimeError("BinaryLoader import returned no program")
        load_results.save(TaskMonitor.DUMMY)
        is_closed = getattr(program, "isClosed", None)
        if callable(is_closed) and is_closed():
            raise RuntimeError("BinaryLoader import closed the program before it could be used")
        finalize_raw_binary_load(
            program,
            base_address=int(base_address),
            entry_point=entry_point,
            block_name=block_name,
        )
        return program
    finally:
        release = getattr(load_results, "release", None)
        if callable(release):
            release(ghidra_project)
        else:
            load_results.close()


def _parse_address_value(value: object) -> int:
    if isinstance(value, str):
        return int(value, 0)
    if isinstance(value, int):
        return value
    raise ValueError(f"invalid address value: {value!r}")


def apply_extracted_overlays(program: Any, overlays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map extracted overlay binaries into an already-imported program."""
    from ghidra.util.task import TaskMonitor  # pyright: ignore[reportMissingImports]

    if not overlays:
        return []

    memory = program.getMemory()
    monitor = TaskMonitor.DUMMY
    applied: list[dict[str, Any]] = []
    for overlay in overlays:
        extract_path = overlay.get("extractPath")
        if not extract_path:
            continue
        path = Path(str(extract_path))
        if not path.is_file():
            continue
        load_address = _parse_address_value(overlay.get("loadAddress"))
        size = int(overlay.get("size") or path.stat().st_size)
        role = str(overlay.get("role") or "overlay")
        payload = path.read_bytes()[:size]
        if not payload:
            continue
        addr = program.getAddressFactory().getDefaultAddressSpace().getAddress(load_address)
        block_name = role.replace("/", "_")
        try:
            block = memory.getBlock(addr)
            if block is None:
                block = memory.createInitializedBlock(
                    block_name,
                    addr,
                    len(payload),
                    0,
                    monitor,
                    False,
                )
            block.putBytes(addr, payload)
            applied.append(
                {
                    "role": role,
                    "loadAddress": f"0x{load_address:08x}",
                    "size": len(payload),
                    "extractPath": str(path),
                }
            )
        except Exception as exc:
            applied.append(
                {
                    "role": role,
                    "loadAddress": f"0x{load_address:08x}",
                    "error": str(exc),
                    "extractPath": str(path),
                }
            )
    return applied
