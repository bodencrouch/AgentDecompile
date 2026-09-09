"""Shared types for binary container resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AnalyzableImage:
    """One CPU image Ghidra (or Tier 0 tools) can analyze."""

    role: str
    load_address: int
    entry_point: int
    file_offset: int
    size: int
    language_id: str
    platform: str
    architecture_hint: str
    extract_path: Path | None = None
    overlay_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": self.role,
            "loadAddress": f"0x{self.load_address:08x}",
            "entryPoint": f"0x{self.entry_point:08x}",
            "fileOffset": self.file_offset,
            "size": self.size,
            "languageId": self.language_id,
            "platform": self.platform,
            "architectureHint": self.architecture_hint,
            "extractPath": str(self.extract_path) if self.extract_path else None,
        }
        if self.overlay_id is not None:
            payload["overlayId"] = self.overlay_id
        return payload


@dataclass(frozen=True)
class ContainerResolution:
    """Parsed container with a primary gameplay CPU image and optional siblings."""

    format: str
    container_path: Path
    title: str
    product_code: str
    primary: AnalyzableImage
    images: tuple[AnalyzableImage, ...] = field(default_factory=tuple)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "containerPath": str(self.container_path),
            "title": self.title,
            "productCode": self.product_code,
            "primary": self.primary.to_dict(),
            "images": [image.to_dict() for image in self.images],
            "detail": dict(self.detail),
        }
