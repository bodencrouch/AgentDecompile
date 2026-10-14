"""Evidence-only audit of Unity package assumptions before Editor import.

The audit compares package declarations in reconstructed project manifests with
package candidates implied by the assemblies shipped in a Unity player. It is a
read-only inventory: assembly presence does not establish a package version or
prove that a package is required by the recovered source.
"""

from __future__ import annotations

import json
import os
import re

from pathlib import Path
from typing import Any

from .unity_probe import discover_managed_assemblies, probe_unity_install

_EDITOR_VERSION_LINE = re.compile(r"^\s*m_EditorVersion\s*:\s*(.*?)\s*$")


def _resolve_project_root(project_root: Path) -> tuple[Path, str | None]:
    """Resolve once; on filesystem resolution failure retain a stable lexical path."""
    candidate = Path(project_root)
    try:
        expanded = candidate.expanduser()
        return expanded.resolve(), None
    except (OSError, RuntimeError) as exc:
        # abspath/normpath do not follow symlinks, so this remains available for
        # deterministic per-root diagnostics even when resolve() cannot proceed.
        lexical = Path(os.path.abspath(os.fspath(candidate)))
        return lexical, f"project root could not be resolved: {exc}"


def _probe_install_safely(install_root: Path) -> dict[str, Any]:
    """Keep install path/probe failures as incomplete report evidence."""
    candidate = Path(install_root)
    try:
        return probe_unity_install(candidate)
    except (OSError, RuntimeError, ValueError) as exc:
        try:
            lexical_root = Path(os.path.abspath(os.fspath(candidate.expanduser())))
        except (OSError, RuntimeError):
            lexical_root = Path(os.path.abspath(os.fspath(candidate)))
        return {
            "schema": "agentdecompile.unity-probe.v1",
            "status": "error",
            "detected": False,
            "reason": f"install root could not be probed: {exc}",
            "installRoot": str(lexical_root),
            "claimBoundary": "install evidence is incomplete because the install root could not be inspected",
        }


def _read_project_version(
    root: Path, shipped_version: str | None, resolution_error: str | None = None
) -> dict[str, Any]:
    """Read the literal m_EditorVersion field and compare it without guessing."""
    version_path = root / "ProjectSettings" / "ProjectVersion.txt"
    result: dict[str, Any] = {
        "projectRoot": str(root),
        "projectVersionPath": str(version_path),
        "status": "error",
        "editorVersion": None,
        "relationToShippedVersion": "unknown",
    }
    if resolution_error is not None:
        result.update(status="unreadable", reason=resolution_error)
        return result
    try:
        content = version_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        result.update(status="missing", reason="ProjectSettings/ProjectVersion.txt does not exist")
        return result
    except (OSError, UnicodeError) as exc:
        result.update(status="unreadable", reason=f"ProjectVersion.txt could not be read: {exc}")
        return result

    versions = [match.group(1) for line in content.splitlines() if (match := _EDITOR_VERSION_LINE.fullmatch(line))]
    if len(versions) != 1 or not versions[0]:
        result.update(
            status="malformed",
            reason="ProjectVersion.txt must contain exactly one non-empty m_EditorVersion field",
        )
        return result
    observed = versions[0]
    relation = "unknown" if shipped_version is None else ("exact" if observed == shipped_version else "mismatch")
    result.update(status="complete", editorVersion=observed, relationToShippedVersion=relation)
    return result


def _read_manifest(root: Path, resolution_error: str | None = None) -> dict[str, Any]:
    """Return one manifest observation while preserving missing/invalid states."""
    manifest_path = root / "Packages" / "manifest.json"
    base: dict[str, Any] = {
        "projectRoot": str(root),
        "manifestPath": str(manifest_path),
        "status": "error",
        "directPackages": {},
    }
    if resolution_error is not None:
        base.update(status="unreadable", reason=resolution_error)
        return base
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        base.update(status="missing", reason="Packages/manifest.json does not exist")
        return base
    except (OSError, UnicodeError) as exc:
        base.update(status="unreadable", reason=f"manifest could not be read: {exc}")
        return base

    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        base.update(status="malformed", reason=f"manifest is not valid JSON: {exc}")
        return base
    if not isinstance(document, dict):
        base.update(status="malformed", reason="manifest JSON root must be an object")
        return base
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, dict):
        base.update(status="malformed", reason="manifest dependencies must be an object")
        return base
    invalid = [key for key, value in dependencies.items() if not isinstance(key, str) or not isinstance(value, str)]
    if invalid:
        base.update(status="malformed", reason="manifest dependencies must map package IDs to string versions")
        return base
    base.update(
        status="complete",
        directPackages={key: dependencies[key] for key in sorted(dependencies)},
    )
    return base


def audit_unity_packages(
    install_root: Path, project_roots: list[Path] | tuple[Path, ...] = ()
) -> dict[str, Any]:
    """Build a deterministic, read-only package evidence report.

    ``project_roots`` may include reconstructed and reference projects. A
    manifest's literal dependency values are reported as direct observations;
    ``*`` and other values are preserved exactly and never resolved or guessed.
    """
    probe = _probe_install_safely(Path(install_root))
    resolved_roots = [_resolve_project_root(Path(root)) for root in project_roots]
    manifests = [_read_manifest(root, error) for root, error in resolved_roots]
    manifests.sort(key=lambda item: item["projectRoot"])
    project_versions = [
        _read_project_version(root, probe.get("unityVersion"), error)
        for root, error in resolved_roots
    ]
    project_versions.sort(key=lambda item: item["projectRoot"])

    # Keep each assembly as its own evidence record, while grouping mapped
    # assembly names by package for convenient review.
    assembly_evidence: dict[str, list[dict[str, Any]]] = {}
    data_dir = probe.get("dataDir")
    if data_dir:
        try:
            shipped_assemblies = discover_managed_assemblies(Path(data_dir))
            assembly_scan = {
                "status": "complete",
                "dataDir": str(data_dir),
                "assemblyCount": len(shipped_assemblies),
            }
        except (OSError, RuntimeError, ValueError) as exc:
            shipped_assemblies = []
            assembly_scan = {
                "status": "error",
                "dataDir": str(data_dir),
                "assemblyCount": 0,
                "reason": f"shipped assemblies could not be discovered: {exc}",
            }
    else:
        shipped_assemblies = []
        assembly_scan = {
            "status": "unavailable",
            "dataDir": None,
            "assemblyCount": 0,
            "reason": "install probe did not provide a Unity data directory",
        }
    for assembly in sorted(shipped_assemblies, key=lambda item: item.get("name", "")):
        package = assembly.get("package")
        if package:
            assembly_evidence.setdefault(str(package), []).append(
                {
                    "assembly": str(assembly.get("name", "")),
                    "sizeBytes": int(assembly.get("sizeBytes") or 0),
                    "evidence": "shipped-managed-assembly",
                }
            )

    manifest_versions: dict[str, dict[str, str]] = {
        item["projectRoot"]: item["directPackages"]
        for item in manifests
        if item["status"] == "complete"
    }
    package_ids = set(assembly_evidence)
    for versions in manifest_versions.values():
        package_ids.update(versions)

    packages: list[dict[str, Any]] = []
    for package_id in sorted(package_ids):
        direct = {
            root: versions[package_id]
            for root, versions in sorted(manifest_versions.items())
            if package_id in versions
        }
        shipped = assembly_evidence.get(package_id, [])
        labels = []
        if direct:
            labels.append("direct-manifest-version")
        if shipped:
            labels.append("shipped-assembly-mapping")
        packages.append(
            {
                "packageId": package_id,
                "mappedAssemblies": [item["assembly"] for item in shipped],
                "shippedAssemblyEvidence": shipped,
                "directManifestVersions": direct,
                "evidence": labels,
                "versionConclusion": None,
            }
        )

    install_detected = bool(probe.get("detected"))
    manifest_observations_complete = bool(manifests) and all(
        item["status"] == "complete" for item in manifests
    )
    editor_version_observations_complete = bool(project_versions) and all(
        item["status"] == "complete" for item in project_versions
    )
    assembly_evidence_complete = assembly_scan["status"] == "complete"
    manifest_comparison_complete = (
        install_detected and manifest_observations_complete and assembly_evidence_complete
    )
    project_version_comparison_complete = (
        install_detected
        and bool(probe.get("unityVersion"))
        and editor_version_observations_complete
    )
    package_evidence_complete = manifest_comparison_complete
    report_complete = package_evidence_complete and project_version_comparison_complete
    return {
        "schema": "agentdecompile.unity-package-audit.v1",
        "status": "complete" if report_complete else "incomplete",
        "installRoot": probe.get("installRoot", str(Path(os.path.abspath(os.fspath(install_root))))),
        "unityVersion": probe.get("unityVersion"),
        "shippedInstallDetected": install_detected,
        "projectManifests": manifests,
        "projectEditorVersions": project_versions,
        "directManifestVersionsByProjectRoot": manifest_versions,
        "shippedAssemblyScan": assembly_scan,
        "packages": packages,
        "scanCompleteness": {
            "complete": report_complete,
            "packageEvidenceComplete": package_evidence_complete,
            "assemblyEvidenceComplete": assembly_evidence_complete,
            "projectManifestComparisonComplete": manifest_comparison_complete,
            "projectEditorVersionComparisonComplete": project_version_comparison_complete,
            "installProbeDetected": install_detected,
            "allProjectManifestsReadableAndValid": manifest_observations_complete,
            "projectManifestCount": len(manifests),
            "incompleteProjectRoots": [
                item["projectRoot"] for item in manifests if item["status"] != "complete"
            ],
            "allProjectEditorVersionsReadableAndValid": editor_version_observations_complete,
            "projectVersionObservationCount": len(project_versions),
            "unknownProjectVersionRoots": [
                item["projectRoot"] for item in project_versions if item["status"] != "complete"
            ],
        },
        "claimBoundaries": [
            "Unity version is read from shipped player data by unity_probe; it is not inferred from package evidence.",
            "A mapped shipped assembly is evidence of an assembly-to-package mapping, not proof that recovered source requires that package.",
            "Manifest versions are literal direct observations keyed by project root; no registry resolution or version inference is performed.",
            "A '*' manifest value remains '*'; differing project observations are reported without selecting a final version.",
            "Project Editor versions are literal m_EditorVersion fields; exact/mismatch compares strings only, and missing or unreadable values have unknown relation and make overall coverage incomplete.",
            "A project version mismatch is an observed difference, not evidence that either version is incorrect or that the project cannot import.",
            "This report does not establish Unity Editor import, package resolution, compilation, or runtime compatibility.",
        ],
    }
