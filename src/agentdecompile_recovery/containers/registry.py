"""Container format registry and analysis prep."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .models import AnalyzableImage, ContainerResolution
from . import nds as nds_mod

_PARSERS = {
    "nds": nds_mod.parse_nds,
}


def detect_container(path: Path, *, head: bytes | None = None) -> str | None:
    path = Path(path)
    if nds_mod.looks_like_nds(path, head=head):
        return "nds"
    return None


def resolve_container(path: Path) -> ContainerResolution | None:
    path = Path(path).expanduser().resolve()
    kind = detect_container(path)
    if kind is None:
        return None
    parser = _PARSERS.get(kind)
    return parser(path) if parser else None


def extract_primary_image(resolution: ContainerResolution, out_dir: Path) -> AnalyzableImage:
    if resolution.format == "nds":
        extract_path = nds_mod.extract_image(resolution.container_path, resolution.primary, out_dir)
        primary = resolution.primary
        return AnalyzableImage(
            role=primary.role,
            load_address=primary.load_address,
            entry_point=primary.entry_point,
            file_offset=primary.file_offset,
            size=primary.size,
            language_id=primary.language_id,
            platform=primary.platform,
            architecture_hint=primary.architecture_hint,
            extract_path=extract_path,
            overlay_id=primary.overlay_id,
        )
    raise ValueError(f"unsupported container format: {resolution.format}")


def _container_cache_key(resolution: ContainerResolution) -> str:
    parts = [
        str(resolution.container_path),
        str(resolution.container_path.stat().st_mtime_ns),
    ]
    for image in resolution.images:
        parts.append(f"{image.role}:{image.file_offset}:{image.size}")
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def prepare_container_for_analysis(
    path: Path,
    work_dir: Path,
    *,
    extract_overlays: bool = True,
) -> dict[str, Any] | None:
    """Extract the primary CPU image when *path* is a known container."""
    resolution = resolve_container(path)
    if resolution is None:
        return None
    cache_key = _container_cache_key(resolution)
    out_dir = work_dir / "container-extract" / cache_key
    overlays: list[dict[str, Any]] = []
    if extract_overlays and resolution.format == "nds":
        extracted = nds_mod.extract_all_images(resolution.container_path, resolution, out_dir)
        primary = next(image for image in extracted if image.role == resolution.primary.role)
        overlays = [image.to_dict() for image in extracted if image.overlay_id is not None]
    else:
        primary = extract_primary_image(resolution, out_dir)
    return {
        "handling": "container-extract",
        "container": resolution.to_dict(),
        "analysisPath": str(primary.extract_path),
        "languageId": primary.language_id,
        "loadAddress": primary.load_address,
        "entryPoint": primary.entry_point,
        "platform": primary.platform,
        "architectureHint": primary.architecture_hint,
        "overlays": overlays,
        "reason": f"Extracted {primary.role} image from {resolution.format} container for Ghidra raw import.",
    }
