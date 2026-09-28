"""Container formats that wrap one or more analyzable CPU images.

PE/ELF/Mach-O are loadable directly. Cartridges such as Nintendo DS (.nds)
expose ARM9/ARM7 (and overlays) inside a ROM envelope. This package resolves
those envelopes to ``AnalyzableImage`` records the rest of the pipeline can
treat like ordinary binaries once extracted.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field, replace
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


NDS_ARM9_LANGUAGE = "ARM:LE:32:v5t"
NDS_ARM7_LANGUAGE = "ARM:LE:32:v4t"
NDS_PLATFORM = "nds"
_OVERLAY_ENTRY_SIZE = 32


def _read_header(data: bytes) -> dict[str, Any] | None:
    if len(data) < 0x200:
        return None
    title = data[0:12].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
    product_code = data[12:16].decode("ascii", "replace").strip()
    maker_code = data[16:18].decode("ascii", "replace").strip()
    if not title or not product_code or not maker_code:
        return None
    arm9_rom_off, arm9_entry, arm9_ram, arm9_size = struct.unpack_from("<4I", data, 0x20)
    arm7_rom_off, arm7_entry, arm7_ram, arm7_size = struct.unpack_from("<4I", data, 0x30)
    arm9_overlay_off, arm9_overlay_size = struct.unpack_from("<2I", data, 0x68)
    arm7_overlay_off, arm7_overlay_size = struct.unpack_from("<2I", data, 0x70)
    if arm9_size <= 0 or arm9_rom_off <= 0:
        return None
    if arm7_size and arm7_rom_off <= 0:
        return None
    return {
        "title": title,
        "product_code": product_code,
        "maker_code": maker_code,
        "arm9_rom_off": arm9_rom_off,
        "arm9_entry": arm9_entry,
        "arm9_ram": arm9_ram,
        "arm9_size": arm9_size,
        "arm7_rom_off": arm7_rom_off,
        "arm7_entry": arm7_entry,
        "arm7_ram": arm7_ram,
        "arm7_size": arm7_size,
        "arm9_overlay_off": arm9_overlay_off,
        "arm9_overlay_size": arm9_overlay_size,
        "arm7_overlay_off": arm7_overlay_off,
        "arm7_overlay_size": arm7_overlay_size,
    }


def _parse_overlay_table(
    data: bytes,
    *,
    table_offset: int,
    table_size: int,
    file_size: int,
    cpu: str,
    language_id: str,
    architecture_hint: str,
) -> list[AnalyzableImage]:
    if table_offset <= 0 or table_size <= 0:
        return []
    if table_offset + table_size > len(data):
        return []
    if table_size % _OVERLAY_ENTRY_SIZE != 0:
        return []

    overlays: list[AnalyzableImage] = []
    for index in range(0, table_size, _OVERLAY_ENTRY_SIZE):
        (
            overlay_id,
            ram,
            size,
            _bss,
            _static_init_start,
            _static_init_end,
            file_offset,
            _reserved,
        ) = struct.unpack_from("<8I", data, table_offset + index)
        if overlay_id == 0 and ram == 0:
            continue
        if size <= 0 or file_offset <= 0:
            continue
        if file_offset + size > file_size:
            continue
        overlays.append(
            AnalyzableImage(
                role=f"{cpu}-overlay-{overlay_id}",
                load_address=ram,
                entry_point=ram,
                file_offset=file_offset,
                size=size,
                language_id=language_id,
                platform=NDS_PLATFORM,
                architecture_hint=architecture_hint,
                overlay_id=overlay_id,
            )
        )
    return overlays


def looks_like_nds(path: Path, *, head: bytes | None = None) -> bool:
    if path.suffix.lower() != ".nds":
        return False
    blob = head if head is not None else path.read_bytes()[:0x200]
    header = _read_header(blob)
    if header is None:
        return False
    size = path.stat().st_size if path.is_file() else len(blob)
    if header["arm9_rom_off"] + header["arm9_size"] > size:
        return False
    if header["arm7_size"] and header["arm7_rom_off"] + header["arm7_size"] > size:
        return False
    return True


def parse_nds(path: Path) -> ContainerResolution | None:
    path = path.expanduser().resolve()
    if not path.is_file():
        return None
    file_size = path.stat().st_size
    header = _read_header(path.read_bytes()[:0x200])
    if header is None:
        return None
    if header["arm9_rom_off"] + header["arm9_size"] > file_size:
        return None

    table_end = max(
        header["arm9_overlay_off"] + header["arm9_overlay_size"],
        header["arm7_overlay_off"] + header["arm7_overlay_size"],
    )
    read_size = max(0x200, table_end)
    blob = path.read_bytes()[:read_size] if read_size <= file_size else path.read_bytes()

    images: list[AnalyzableImage] = [
        AnalyzableImage(
            role="arm9",
            load_address=header["arm9_ram"] or 0x02000000,
            entry_point=header["arm9_entry"],
            file_offset=header["arm9_rom_off"],
            size=header["arm9_size"],
            language_id=NDS_ARM9_LANGUAGE,
            platform=NDS_PLATFORM,
            architecture_hint="armv5te",
        )
    ]
    if header["arm7_size"] > 0 and header["arm7_rom_off"] + header["arm7_size"] <= file_size:
        images.append(
            AnalyzableImage(
                role="arm7",
                load_address=header["arm7_ram"] or 0x02380000,
                entry_point=header["arm7_entry"],
                file_offset=header["arm7_rom_off"],
                size=header["arm7_size"],
                language_id=NDS_ARM7_LANGUAGE,
                platform=NDS_PLATFORM,
                architecture_hint="arm7tdmi",
            )
        )

    images.extend(
        _parse_overlay_table(
            blob,
            table_offset=header["arm9_overlay_off"],
            table_size=header["arm9_overlay_size"],
            file_size=file_size,
            cpu="arm9",
            language_id=NDS_ARM9_LANGUAGE,
            architecture_hint="armv5te",
        )
    )
    images.extend(
        _parse_overlay_table(
            blob,
            table_offset=header["arm7_overlay_off"],
            table_size=header["arm7_overlay_size"],
            file_size=file_size,
            cpu="arm7",
            language_id=NDS_ARM7_LANGUAGE,
            architecture_hint="arm7tdmi",
        )
    )

    overlay_count = sum(1 for image in images if image.overlay_id is not None)
    return ContainerResolution(
        format="nds",
        container_path=path,
        title=header["title"],
        product_code=header["product_code"],
        primary=images[0],
        images=tuple(images),
        detail={"makerCode": header["maker_code"], "overlayCount": overlay_count},
    )


def extract_image(path: Path, image: AnalyzableImage, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem.replace(" ", "_")
    if image.overlay_id is not None:
        dest = out_dir / f"{stem}.overlay{image.overlay_id}.bin"
    else:
        dest = out_dir / f"{stem}.{image.role}.bin"
    with path.open("rb") as src, dest.open("wb") as dst:
        src.seek(image.file_offset)
        dst.write(src.read(image.size))
    return dest


def extract_all_images(path: Path, resolution: ContainerResolution, out_dir: Path) -> list[AnalyzableImage]:
    extracted: list[AnalyzableImage] = []
    for image in resolution.images:
        extract_path = extract_image(path, image, out_dir)
        extracted.append(replace(image, extract_path=extract_path))
    return extracted


_PARSERS = {
    "nds": parse_nds,
}


def detect_container(path: Path, *, head: bytes | None = None) -> str | None:
    path = Path(path)
    if looks_like_nds(path, head=head):
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
        extract_path = extract_image(resolution.container_path, resolution.primary, out_dir)
        return replace(resolution.primary, extract_path=extract_path)
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
        extracted = extract_all_images(resolution.container_path, resolution, out_dir)
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


def is_nds_binary(path: Path, *, head: bytes | None = None) -> bool:
    """Return True when *path* looks like a Nintendo DS (.nds) ROM container."""
    return detect_container(path, head=head) == "nds" or looks_like_nds(path, head=head)


__all__ = [
    "AnalyzableImage",
    "ContainerResolution",
    "detect_container",
    "extract_primary_image",
    "is_nds_binary",
    "prepare_container_for_analysis",
    "resolve_container",
]
