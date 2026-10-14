"""Read-only original FileBytes extraction; never import or analyze a program."""

from __future__ import annotations

from pathlib import Path


def extract(source: str, program_path: str, output: Path, *, shared: bool = False) -> dict:
    from agentdecompile_recovery.corpus import ghidra_env as ge
    from agentdecompile_recovery.corpus.export_bytes import export

    output = output.expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing to overwrite {output}")
    if shared:
        if not ge.start():
            raise RuntimeError("Original FileBytes extraction requires PyGhidra and GHIDRA_INSTALL_DIR.")
        # Shared source is a repository folder, not an HTTP backend URL.
        path = "/" + "/".join((source.strip("/"), program_path.strip("/"))).strip("/")
        with ge.open_program(path) as program:
            if program is None:
                raise FileNotFoundError(path)
            return _extract_program(program, output, source, path, export)

    project_file = Path(source).expanduser().resolve()
    if project_file.is_dir():
        candidates = sorted(project_file.glob("*.gpr"))
        if len(candidates) != 1:
            raise ValueError("Project folder must contain exactly one .gpr; pass a specific .gpr instead.")
        project_file = candidates[0]
    if project_file.suffix.lower() != ".gpr" or not project_file.is_file():
        raise FileNotFoundError(f"Expected an existing .gpr or project folder: {source}")
    if not ge.start():
        raise RuntimeError("Original FileBytes extraction requires PyGhidra and GHIDRA_INSTALL_DIR.")
    from ghidra.base.project import GhidraProject

    project = GhidraProject.openProject(str(project_file.parent), project_file.stem, False)
    try:
        path = "/" + program_path.strip("/")
        domain_file = project.getProjectData().getFile(path)
        if domain_file is None:
            raise FileNotFoundError(f"Program {path} is absent from {project_file}")
        consumer = ge.consumer()
        program = domain_file.getImmutableDomainObject(consumer, -1, ge.monitor())
        try:
            return _extract_program(program, output, str(project_file), path, export)
        finally:
            program.release(consumer)
    finally:
        project.close()


def _extract_program(program, output: Path, source: str, path: str, export) -> dict:
    entries = export(program, output)
    imported_sha256 = str(program.getExecutableSHA256() or "")
    if len(entries) == 1 and imported_sha256:
        entries[0]["whole_original_file_verified"] = (
            entries[0]["file_offset"] == 0
            and entries[0]["sha256"].lower() == imported_sha256.lower()
        )
    return {
        "success": True,
        "project": source,
        "programPath": path,
        "programName": str(program.getName()),
        "executablePath": str(program.getExecutablePath() or ""),
        "importedExecutableSha256": imported_sha256,
        "entries": entries,
        "claimBoundary": "Original stored FileBytes only; no reconstructed memory export. Multiple blobs are separate imports, not a reassembled image.",
    }
