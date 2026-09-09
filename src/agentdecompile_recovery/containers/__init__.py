"""Container formats that wrap one or more analyzable CPU images.

PE/ELF/Mach-O are loadable directly. Cartridges such as Nintendo DS (.nds)
expose ARM9/ARM7 (and overlays) inside a ROM envelope. This package resolves
those envelopes to ``AnalyzableImage`` records the rest of the pipeline can
treat like ordinary binaries once extracted.
"""

from .models import AnalyzableImage, ContainerResolution
from .detect import is_nds_binary
from .registry import (
    detect_container,
    extract_primary_image,
    prepare_container_for_analysis,
    resolve_container,
)

__all__ = [
    "AnalyzableImage",
    "ContainerResolution",
    "detect_container",
    "extract_primary_image",
    "is_nds_binary",
    "prepare_container_for_analysis",
    "resolve_container",
]
