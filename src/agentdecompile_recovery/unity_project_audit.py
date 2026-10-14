"""Read-only, local-GUID reference audit for a Unity project's Assets tree.

This is a candidate inventory, not an Editor import or package-resolution check.
"""

from __future__ import annotations

import os
import re
import stat
from bisect import bisect_right
from pathlib import Path


# These extensions contain Unity YAML serialization; media, code, and import
# sources are deliberately excluded. A recognized extension alone is not enough:
# the file must also carry a Unity YAML header.
YAML_EXTENSIONS = frozenset({
    ".anim", ".asset", ".controller", ".cubemap", ".flare", ".giparams",
    ".guiskin", ".lighting", ".mask", ".mat", ".mixer",
    ".overridecontroller", ".physicmaterial", ".physicsmaterial",
    ".physicsmaterial2d", ".playable", ".prefab",
    ".rendertexture", ".spriteatlas", ".terrainlayer", ".unity",
    ".texture2d", ".shadervariants",
})
BUILTIN_GUIDS = frozenset({
    "0000000000000000e000000000000000",
    "0000000000000000f000000000000000",
})
META_GUID = re.compile(r"(?m)^guid:\s*([0-9a-fA-F]{32})\s*$")
REFERENCE_MAP = re.compile(r"\{([^{}]*)\}", re.DOTALL)
REFERENCE_FIELD = re.compile(r"\s*(fileID|guid|type):\s*([0-9a-fA-F-]+)\s*\Z")
BLOCK_FIELD = re.compile(r"^([ \t]*)(?P<dash>-[ \t]+)?(fileID|guid|type):[ \t]*([0-9a-fA-F-]+)[ \t]*$")
BLOCK_SCALAR = re.compile(r"^[ \t]*[^:#\n]+:[ \t]*[|>][+-]?[1-9]?[ \t]*(?:#.*)?$")
HEX_GUID = re.compile(r"[0-9a-fA-F]{32}\Z")
FILE_ID = re.compile(r"-?\d+\Z")
UNITY_DOCUMENT = re.compile(r"(?m)^--- !u!\d+ &-?\d+(?:\s|$)")


def _reference_text(content: str) -> str:
    """Keep YAML structure and offsets while masking quoted/comment/scalar text."""
    output: list[str] = []
    quote: str | None = None
    scalar_indent: int | None = None
    for line in content.splitlines(keepends=True):
        indent = len(line) - len(line.lstrip(" \t"))
        if scalar_indent is not None:
            if not line.strip() or indent > scalar_indent:
                output.append("".join("\n" if char == "\n" else " " for char in line))
                continue
            scalar_indent = None
        masked = list(line)
        index = 0
        while index < len(line):
            char = line[index]
            if quote:
                masked[index] = " " if char != "\n" else "\n"
                if quote == '"' and char == "\\" and index + 1 < len(line):
                    index += 1
                    masked[index] = " " if line[index] != "\n" else "\n"
                elif char == quote:
                    if quote == "'" and index + 1 < len(line) and line[index + 1] == "'":
                        index += 1
                        masked[index] = " "
                    else:
                        quote = None
            elif char in "\"'" and (index == 0 or line[index - 1].isspace() or line[index - 1] in ":[{,"):
                quote = char
                masked[index] = " "
            elif char == "#" and (index == 0 or line[index - 1].isspace()):
                masked[index:] = ["\n" if item == "\n" else " " for item in line[index:]]
                break
            index += 1
        clean = "".join(masked)
        if quote is None and BLOCK_SCALAR.fullmatch(clean.rstrip("\r\n")):
            scalar_indent = indent
        output.append(clean)
    return "".join(output)


def _inline_reference(body: str) -> tuple[str, int, int] | None:
    fields: dict[str, str] = {}
    guid_offset = 0
    offset = 0
    for part in body.split(","):
        match = REFERENCE_FIELD.fullmatch(part)
        if match is None or match.group(1) in fields:
            return None
        fields[match.group(1)] = match.group(2)
        if match.group(1) == "guid":
            guid_offset = offset + match.start(2)
        offset += len(part) + 1
    if not HEX_GUID.fullmatch(fields.get("guid", "")) or not FILE_ID.fullmatch(fields.get("fileID", "")):
        return None
    if "type" in fields and not fields["type"].isdigit():
        return None
    return fields["guid"], int(fields["fileID"]), guid_offset


def _mapping_start(content: str, offset: int) -> bool:
    """Reject braces embedded in plain YAML scalars."""
    prefix = content[content.rfind("\n", 0, offset) + 1:offset].rstrip()
    if not prefix or prefix.endswith((":", "[", "{")) or prefix.lstrip() == "-":
        return True
    return prefix.endswith(",") and "[" in prefix and prefix.rfind("[") > prefix.rfind("]")


def _read_text(path: Path) -> str | None:
    """Return None for binary or invalid UTF-8 without leaking partial results."""
    try:
        with path.open("r", encoding="utf-8", errors="strict") as stream:
            content = stream.read()
    except (OSError, UnicodeError):
        return None
    return None if "\x00" in content else content


def _has_binary_nul_prefix(path: Path) -> bool:
    """Recognize binary serialized payloads without treating read errors as binary."""
    try:
        with path.open("rb") as stream:
            prefix = stream.read(4096)
    except OSError:
        return False
    if b"\x00" not in prefix:
        return False
    text_prefix = prefix.decode("ascii", errors="ignore")
    return UNITY_DOCUMENT.search(text_prefix) is None


def _asset_files(assets: Path) -> tuple[list[Path], list[Path], list[str]]:
    """Inventory regular files/folders and traversal failures without following symlinks."""
    files_found: list[Path] = []
    folders_found: list[Path] = []
    walk_errors: list[str] = []

    def record_walk_error(error: OSError) -> None:
        walk_errors.append(f"{error.filename or assets}: {error.strerror or error}")

    for directory, dirs, files in os.walk(assets, followlinks=False, onerror=record_walk_error):
        base = Path(directory)
        safe_dirs: list[str] = []
        for name in dirs:
            try:
                if not (base / name).is_symlink():
                    safe_dirs.append(name)
            except OSError as error:
                walk_errors.append(f"{base / name}: {error.strerror or error}")
        dirs[:] = sorted(safe_dirs)
        if base != assets:
            folders_found.append(base)
        for name in sorted(files):
            path = base / name
            try:
                if path.is_symlink():
                    continue
                if stat.S_ISREG(path.lstat().st_mode):
                    files_found.append(path)
                else:
                    walk_errors.append(f"{path}: unsupported non-regular asset entry")
            except OSError as error:
                walk_errors.append(f"{path}: {error.strerror or error}")
    return files_found, folders_found, walk_errors


def audit_unity_project(project_root: Path) -> dict:
    """Inventory GUID references that lack an indexed local Assets meta asset."""
    root = project_root.resolve(strict=True)
    assets = root / "Assets"
    if assets.is_symlink() or not assets.is_dir():
        raise ValueError(f"Unity project has no regular Assets directory: {assets}")

    paths, folders, walk_errors = _asset_files(assets)
    path_set = set(paths)
    meta_guids: dict[str, list[str]] = {}
    resolvable_guids: set[str] = set()
    skipped: list[dict[str, str]] = []
    orphan_metas: list[str] = []
    asset_meta_paths: set[Path] = set()
    folder_meta_paths: set[Path] = set()
    paired_meta_paths: set[Path] = set()
    for path in paths:
        if path.suffix.lower() != ".meta":
            continue
        relative = path.relative_to(root).as_posix()
        asset_path = path.with_suffix("")
        try:
            asset_is_directory = asset_path.is_dir()
            asset_is_symlink = asset_path.is_symlink()
        except OSError as error:
            skipped.append({"path": relative, "reason": f"counterpart could not be inspected: {error}"})
            walk_errors.append(f"{asset_path}: {error.strerror or error}")
            continue
        paired = asset_path in path_set or (asset_is_directory and not asset_is_symlink)
        if paired:
            paired_meta_paths.add(path)
            if asset_is_directory:
                folder_meta_paths.add(asset_path)
            else:
                asset_meta_paths.add(asset_path)
        content = _read_text(path)
        if content is None:
            skipped.append({"path": relative, "reason": "binary, invalid UTF-8, or unreadable meta"})
            continue
        match = META_GUID.search(content)
        if match is None:
            skipped.append({"path": relative, "reason": "no valid meta GUID"})
            continue
        guid = match.group(1).lower()
        meta_guids.setdefault(guid, []).append(relative)
        if paired:
            resolvable_guids.add(guid)
        else:
            orphan_metas.append(relative)

    missing_asset_metas: list[str] = []
    missing_folder_metas: list[str] = []
    asset_file_count = 0
    for path in paths:
        if path in paired_meta_paths or path.suffix.lower() == ".meta":
            continue
        asset_file_count += 1
        relative = path.relative_to(root).as_posix()
        if path not in asset_meta_paths:
            missing_asset_metas.append(relative)
    folder_count = 0
    for base in folders:
        folder_count += 1
        if base not in folder_meta_paths:
            missing_folder_metas.append(base.relative_to(root).as_posix())

    candidates: list[dict[str, str | int]] = []
    per_scene_counts: dict[str, int] = {}
    scanned_yaml_files = 0
    for path in paths:
        if path.suffix.lower() not in YAML_EXTENSIONS:
            continue
        relative = path.relative_to(root).as_posix()
        content = _read_text(path)
        if content is None:
            reason = (
                "binary serialized asset outside YAML reference scan"
                if _has_binary_nul_prefix(path)
                else "invalid UTF-8 or unreadable YAML"
            )
            skipped.append({"path": relative, "reason": reason})
            continue
        if UNITY_DOCUMENT.search(content[:4096]) is None:
            skipped.append({"path": relative, "reason": "no Unity YAML header"})
            continue
        scanned_yaml_files += 1
        if path.suffix.lower() == ".unity":
            per_scene_counts[relative] = 0
        line_starts = [0]
        line_starts.extend(match.end() for match in re.finditer("\n", content))

        def record(guid: str, file_id: int, offset: int) -> None:
            guid = guid.lower()
            if file_id == 0 or guid in BUILTIN_GUIDS or guid in resolvable_guids:
                return
            line = bisect_right(line_starts, offset)
            candidates.append({"path": relative, "line": line, "fileID": file_id, "guid": guid})
            if relative in per_scene_counts:
                per_scene_counts[relative] += 1

        reference_text = _reference_text(content)
        for mapping in REFERENCE_MAP.finditer(reference_text):
            if not _mapping_start(reference_text, mapping.start()):
                continue
            reference = _inline_reference(mapping.group(1))
            if reference is not None:
                guid, file_id, guid_offset = reference
                record(guid, file_id, mapping.start(1) + guid_offset)

        block_fields: dict[str, str] = {}
        block_indent: int | None = None
        block_guid_offset = 0

        def flush_block() -> None:
            if (HEX_GUID.fullmatch(block_fields.get("guid", ""))
                    and FILE_ID.fullmatch(block_fields.get("fileID", ""))
                    and ("type" not in block_fields or block_fields["type"].isdigit())):
                record(block_fields["guid"], int(block_fields["fileID"]), block_guid_offset)
            block_fields.clear()

        offset = 0
        for line in reference_text.splitlines(keepends=True):
            match = BLOCK_FIELD.fullmatch(line.rstrip("\r\n"))
            if match is None:
                if line.strip():
                    flush_block()
                    block_indent = None
            else:
                indent = len(match.group(1)) + (2 if match.group("dash") else 0)
                field = match.group(3)
                if block_indent != indent or field in block_fields or match.group("dash"):
                    flush_block()
                block_indent = indent
                block_fields[field] = match.group(4)
                if field == "guid":
                    block_guid_offset = offset + match.start(4)
            offset += len(line)
        flush_block()

    candidates.sort(key=lambda item: (item["path"], item["line"], item["guid"], item["fileID"]))

    duplicates = [
        {"guid": guid, "meta_paths": sorted(meta_paths)}
        for guid, meta_paths in sorted(meta_guids.items())
        if len(meta_paths) > 1
    ]
    return {
        "schema": "agentdecompile.unity-project-audit.v1",
        "project_root": str(root),
        "claim": "candidate_external_guid_references",
        "claim_boundary": (
            "A GUID without a local Assets .meta asset is only an unresolved local-reference "
            "candidate. Known Unity built-in GUIDs are excluded; package and external-source "
            "resolution are not covered. "
            "This audit does not establish that an asset is missing or that the Editor can import the project."
        ),
        "scope": (
            "Unity YAML assets and .meta files under Assets; binary serialized assets are "
            "listed as out-of-scope skips; symlinks are ignored"
        ),
        "scanned_yaml_files": scanned_yaml_files,
        "indexed_meta_guids": len(meta_guids),
        "asset_file_count": asset_file_count,
        "asset_files_missing_meta_count": len(missing_asset_metas),
        "asset_files_missing_meta": missing_asset_metas,
        "folder_count_excluding_assets_root": folder_count,
        "folders_missing_meta_count": len(missing_folder_metas),
        "folders_missing_meta": missing_folder_metas,
        "candidate_count": len(candidates),
        "candidate_external_guid_references": candidates,
        "per_scene_candidate_counts": per_scene_counts,
        "duplicate_meta_guids": duplicates,
        "orphan_meta_paths": sorted(orphan_metas),
        "skipped_files": sorted(skipped, key=lambda item: item["path"]),
        "walk_errors": walk_errors,
        "scan_complete": not walk_errors and not any(
            item["reason"] not in {
                "no Unity YAML header",
                "binary serialized asset outside YAML reference scan",
            }
            for item in skipped
        ),
    }
