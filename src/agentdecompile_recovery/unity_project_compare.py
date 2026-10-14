"""Compare unresolved Unity Assets GUIDs with other exported projects.

The result is a merge-planning report only. It never copies assets or rewrites
GUIDs; even byte-identical source matches need a separately reviewed apply step.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from .unity_project_audit import META_GUID, audit_unity_project


def _asset_tree(project_root: Path) -> tuple[Path, Path]:
    root = project_root.resolve(strict=True)
    assets = root / "Assets"
    if assets.is_symlink() or not assets.is_dir():
        raise ValueError(f"Unity project has no regular Assets directory: {assets}")
    return root, assets


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file_beneath(root: Path, relative: str) -> Path | None:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    path = root / relative
    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            return None
    return path if path.is_file() else None


def _reference_index(
    assets: Path, root: Path
) -> tuple[dict[str, list[dict[str, str | int]]], list[dict[str, str]], list[str]]:
    """Index paired sidecar GUIDs and return every input/scan omission."""
    index: dict[str, list[dict[str, str | int]]] = {}
    skipped: list[dict[str, str]] = []
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
            except OSError as exc:
                walk_errors.append(f"{base / name}: {exc.strerror or exc}")
        dirs[:] = sorted(safe_dirs)
        names = set(files)
        for name in sorted(files):
            meta = base / name
            if not name.endswith(".meta"):
                continue
            try:
                if meta.is_symlink():
                    continue
                asset_name = name[:-5]
                asset = base / asset_name
                paired = not asset.is_symlink() and (asset.is_file() or asset.is_dir())
                if not paired:
                    if asset_name in names or asset.exists():
                        skipped.append({"path": meta.relative_to(root).as_posix(), "reason": "counterpart is not a regular file or directory"})
                    continue
                mode = meta.lstat().st_mode
                if not stat.S_ISREG(mode):
                    skipped.append({"path": meta.relative_to(root).as_posix(), "reason": "meta is not a regular file"})
                    continue
                with meta.open("r", encoding="utf-8", errors="strict") as stream:
                    match = META_GUID.search(stream.read())
                asset_is_directory = asset.is_dir()
            except (OSError, UnicodeError) as exc:
                skipped.append({"path": meta.relative_to(root).as_posix(), "reason": f"meta unreadable or invalid UTF-8: {exc}"})
                continue
            if match is None:
                skipped.append({"path": meta.relative_to(root).as_posix(), "reason": "no valid GUID in meta"})
                continue
            relative = asset.relative_to(root).as_posix()
            entry: dict[str, str | int] = {
                "asset_path": relative,
                "meta_path": meta.relative_to(root).as_posix(),
                "is_directory": int(asset_is_directory),
            }
            index.setdefault(match.group(1).lower(), []).append(entry)
    return index, skipped, walk_errors


def compare_unity_projects(project_root: Path, reference_roots: list[Path]) -> dict:
    """Classify local unresolved GUID candidates against reference Assets trees.

    Exact content matches are reported only for same-path ``.cs`` files. Missing
    paths are suggestions, not proof they are safe to add; assemblies, serialized
    assets, package content, and importer settings require separate validation.
    """
    root, assets = _asset_tree(project_root)
    if not reference_roots:
        raise ValueError("at least one --reference-project is required")

    reference_trees: list[tuple[Path, Path]] = []
    for reference_root in reference_roots:
        ref_root, ref_assets = _asset_tree(reference_root)
        if ref_root == root:
            raise ValueError("reference project must differ from the project being audited")
        reference_trees.append((ref_root, ref_assets))

    base_report = audit_unity_project(root)
    references: list[tuple[Path, dict[str, list[dict[str, str | int]]], list[dict[str, str]], list[str]]] = []
    for ref_root, ref_assets in reference_trees:
        index, skipped, walk_errors = _reference_index(ref_assets, ref_root)
        references.append((ref_root, index, skipped, walk_errors))

    occurrences: dict[str, list[dict[str, str | int]]] = {}
    for candidate in base_report["candidate_external_guid_references"]:
        occurrences.setdefault(candidate["guid"], []).append(candidate)

    classified: list[dict] = []
    content_comparison_failures: list[dict[str, str]] = []
    for guid, rows in sorted(occurrences.items()):
        found: list[dict[str, str | int]] = []
        duplicate_in_reference = False
        for ref_root, index, _skipped, _walk_errors in references:
            entries = index.get(guid, [])
            duplicate_in_reference = duplicate_in_reference or len(entries) > 1
            for entry in entries:
                found.append({"project_root": str(ref_root), **entry})

        status = "ambiguous_guid_in_reference_exports" if duplicate_in_reference else "unresolved_in_references"
        evidence: list[dict[str, str | int]] = []
        if found:
            for item in found:
                try:
                    local_path = root / str(item["asset_path"])
                    if item["is_directory"]:
                        comparison = (
                            "directory_path_present"
                            if local_path.is_dir() and not local_path.is_symlink()
                            else "local_path_conflict" if local_path.exists() else "asset_or_folder_path_absent_locally"
                        )
                        evidence.append({**item, "comparison": comparison})
                        continue
                    target = _regular_file_beneath(root, str(item["asset_path"]))
                    source = _regular_file_beneath(Path(str(item["project_root"])), str(item["asset_path"]))
                    if target is None or source is None:
                        evidence.append({
                            **item,
                            "comparison": "local_path_unreadable_or_nonregular" if local_path.exists() else "asset_or_folder_path_absent_locally",
                        })
                        continue
                    source_hash = _sha256(source)
                    target_hash = _sha256(target)
                    source_bytes = source.stat().st_size
                    target_bytes = target.stat().st_size
                except OSError as exc:
                    evidence.append({**item, "comparison": "unreadable", "error": str(exc)})
                    content_comparison_failures.append({
                        "guid": guid,
                        "reference_project": str(item["project_root"]),
                        "asset_path": str(item["asset_path"]),
                        "error": str(exc),
                    })
                    continue
                evidence.append({
                    **item,
                    "comparison": "byte_identical" if source_hash == target_hash else "content_differs",
                    "reference_sha256": source_hash,
                    "project_sha256": target_hash,
                    "reference_bytes": source_bytes,
                    "project_bytes": target_bytes,
                })

            paths = {str(item["asset_path"]) for item in evidence}
            observed_comparisons = {str(item.get("comparison")) for item in evidence}
            reference_types = {int(item["is_directory"]) for item in found}
            csharp_rows = [item for item in evidence if str(item["asset_path"]).lower().endswith(".cs")]
            if duplicate_in_reference:
                status = "ambiguous_guid_in_reference_exports"
            elif len(paths) > 1 or len(reference_types) > 1:
                status = "reference_variants_conflict"
            elif reference_types == {1} and "directory_path_present" in observed_comparisons:
                status = "same_path_directory_candidate"
            elif reference_types == {1} and "local_path_conflict" in observed_comparisons:
                status = "reference_path_conflict"
            elif reference_types == {1} and "asset_or_folder_path_absent_locally" in observed_comparisons:
                status = "asset_or_folder_path_absent_locally"
            elif "content_differs" in observed_comparisons:
                status = "same_path_content_conflict"
            elif "local_path_unreadable_or_nonregular" in observed_comparisons or "unreadable" in observed_comparisons:
                status = "same_path_unreadable_or_nonregular"
            elif "byte_identical" in observed_comparisons and csharp_rows:
                status = "same_path_identical_csharp_candidate"
            elif "byte_identical" in observed_comparisons:
                status = "same_path_identical_non_csharp_candidate"
            elif "asset_or_folder_path_absent_locally" in observed_comparisons:
                status = "asset_or_folder_path_absent_locally"

        incomplete_reference_roots = [
            str(ref_root)
            for ref_root, _index, skipped, walk_errors in references
            if skipped or walk_errors
        ]
        observed_status = status
        if incomplete_reference_roots or not base_report["scan_complete"] or "unreadable" in {
            str(item.get("comparison")) for item in evidence
        }:
            status = "project_or_reference_scan_incomplete"

        classified.append({
            "guid": guid,
            "occurrence_count": len(rows),
            "reference_count": len(found),
            "status": status,
            "observed_status": observed_status,
            "reference_scan_incomplete_roots": incomplete_reference_roots,
            "references": evidence or found,
            "project_references": rows,
        })

    counts: dict[str, int] = {}
    for item in classified:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    reference_scans = [
        {
            "project_root": str(ref_root),
            "complete": not skipped and not walk_errors,
            "skipped_meta_or_counterparts": skipped,
            "walk_errors": walk_errors,
        }
        for ref_root, _index, skipped, walk_errors in references
    ]
    return {
        "schema": "agentdecompile.unity-project-compare.v1",
        "project_root": str(root),
        "reference_project_roots": [str(ref_root) for ref_root, _index, _skipped, _errors in references],
        "claim": "reference_export_guid_classification",
        "claim_boundary": (
            "This is a report-only comparison of paired Assets .meta GUIDs in the named exports. "
            "Project candidates come only from supported Unity-YAML files under Assets; Packages, "
            "ProjectSettings, binary-serialized references, symlinks, and external resolution are outside scope. "
            "It does not establish that reference exports are authoritative or complete, that an asset "
            "is safe to merge, or that Unity resolves/imports it. No files are modified."
        ),
        "reference_scans_complete": all(item["complete"] for item in reference_scans),
        "project_scan_complete": base_report["scan_complete"],
        "project_walk_errors": base_report["walk_errors"],
        "content_comparison_complete": not content_comparison_failures,
        "content_comparison_failures": content_comparison_failures,
        "unresolved_unique_guid_count": len(classified),
        "unresolved_occurrence_count": len(base_report["candidate_external_guid_references"]),
        "scanned_yaml_files": base_report["scanned_yaml_files"],
        "duplicate_meta_guids_in_project": base_report["duplicate_meta_guids"],
        "skipped_project_files": base_report["skipped_files"],
        "reference_scans": reference_scans,
        "scan_complete": (
            base_report["scan_complete"]
            and all(item["complete"] for item in reference_scans)
            and not content_comparison_failures
        ),
        "classification_counts": counts,
        "guid_classifications": classified,
    }
