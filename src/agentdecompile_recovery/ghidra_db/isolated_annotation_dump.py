"""Read operator annotations from a local Ghidra project in an isolated JVM.

This is intentionally a tiny process boundary: an embedded MCP JVM cannot safely
open both a preserved checkout and its replacement at once on every supported
Ghidra build.  The output is JSON-only and contains no mutation instructions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agentdecompile_recovery.corpus.ghidra_env import start


def _items(iterator: Any) -> list[Any]:
    values: list[Any] = []
    try:
        while iterator.hasNext():
            values.append(iterator.next())
    except Exception:
        pass
    return values


def _comment_addresses(listing: Any, program: Any, kind: int) -> list[Any]:
    for args in ((kind, program.getMemory(), True), (kind, True), (kind, program.getMemory())):
        try:
            return _items(listing.getCommentAddressIterator(*args))
        except Exception:
            continue
    return []


def _domain_file_folder_path_and_name(domain: Any) -> tuple[str, str]:
    """Match the provider's proven ``openProgram(String,String,boolean)`` split."""
    pathname = str(domain.getPathname() or "").replace("\\", "/").strip()
    name = str(domain.getName() or "").strip()
    if not name and pathname:
        name = Path(pathname).name
    body = pathname.strip("/")
    if not body or "/" not in body:
        return "", name or body
    parent_body, basename = body.rsplit("/", 1)
    return f"/{parent_body}" if parent_body else "", name or basename


def dump(project_file: Path, only_program: str = "") -> dict[str, Any]:
    if not start(project_path=project_file):
        raise RuntimeError("PyGhidra is unavailable for isolated annotation reconciliation")
    from ghidra.base.project import GhidraProject
    from ghidra.program.model.listing import CodeUnit

    project = GhidraProject.openProject(str(project_file.parent), project_file.stem, False)
    programs: dict[str, Any] = {}
    try:
        data = project.getProject().getProjectData()
        def walk(folder: Any) -> list[Any]:
            found = list(folder.getFiles())
            for child in folder.getFolders():
                found.extend(walk(child))
            return found
        for domain in walk(data.getRootFolder()):
            path = str(domain.getPathname())
            if only_program and path != only_program:
                continue
            row: dict[str, Any] = {"names": [], "comments": [], "bookmarks": [], "unsupportedTypes": 0, "unsupportedStructures": 0, "conflicts": []}
            program = None
            try:
                folder_path, program_name = _domain_file_folder_path_and_name(domain)
                program = project.openProgram(folder_path, program_name, False)
                if program is None:
                    raise RuntimeError("openProgram returned no program")
                symbols, listing = program.getSymbolTable(), program.getListing()
                for symbol in _items(symbols.getAllSymbols(True)):
                    if "USER_DEFINED" in str(symbol.getSource()):
                        row["names"].append([str(symbol.getAddress()), str(symbol.getName())])
                for kind in (CodeUnit.PLATE_COMMENT, CodeUnit.PRE_COMMENT, CodeUnit.POST_COMMENT, CodeUnit.EOL_COMMENT, CodeUnit.REPEATABLE_COMMENT):
                    for address in _comment_addresses(listing, program, kind):
                        text = listing.getComment(kind, address)
                        if text:
                            row["comments"].append([str(address), int(kind), str(text)])
                bookmarks = program.getBookmarkManager()
                for mark in _items(bookmarks.getBookmarksIterator()):
                    row["bookmarks"].append([str(mark.getAddress()), str(mark.getTypeString()), str(mark.getCategory()), str(mark.getComment())])
                row["unsupportedTypes"] = int(program.getDataTypeManager().getDataTypeCount(True))
                row["conflicts"].append({"kind": "structure-inventory-deferred", "detail": "Types and structures remain in the preserved project."})
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if program is not None:
                    try:
                        project.close(program)
                    except Exception:
                        try:
                            program.release(None)
                        except Exception:
                            pass
            programs[path] = row
    finally:
        project.close()
    return {"version": 1, "previousProject": str(project_file), "programs": programs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("output")
    parser.add_argument("--program", default="")
    args = parser.parse_args()
    result = dump(Path(args.project).resolve(), args.program)
    output = Path(args.output)
    output.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
