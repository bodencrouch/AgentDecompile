from __future__ import annotations

from pathlib import Path

import pytest

from agentdecompile_recovery.containers import (
    detect_container,
    prepare_container_for_analysis,
    resolve_container,
)
from agentdecompile_recovery.discovery import sniff_path
from agentdecompile_recovery.targets import identify_binary, inspect_magic, looks_executable

SONIC_NDS = Path(
    "/run/media/brunner56/MyBook/Games/2794 - Sonic Chronicles - The Dark Brotherhood (U)(XenoPhobia)/"
    "2794 - Sonic Chronicles - The Dark Brotherhood (U)(XenoPhobia).nds"
)

pytestmark = pytest.mark.unit


@pytest.mark.skipif(not SONIC_NDS.is_file(), reason="Sonic NDS fixture not available on this machine")
def test_detect_and_resolve_sonic_nds() -> None:
    assert detect_container(SONIC_NDS) == "nds"
    resolution = resolve_container(SONIC_NDS)
    assert resolution is not None
    assert resolution.format == "nds"
    assert resolution.title == "SONICCHRON"
    assert resolution.product_code == "YWSE"
    assert resolution.primary.role == "arm9"
    assert resolution.primary.load_address == 0x02000000
    assert resolution.primary.entry_point == 0x02000800
    assert resolution.primary.language_id == "ARM:LE:32:v5t:default"
    assert len(resolution.images) == 2


@pytest.mark.skipif(not SONIC_NDS.is_file(), reason="Sonic NDS fixture not available on this machine")
def test_extract_primary_image_for_analysis(tmp_path: Path) -> None:
    prepared = prepare_container_for_analysis(SONIC_NDS, tmp_path)
    assert prepared is not None
    assert prepared["handling"] == "container-extract"
    extract_path = Path(prepared["analysisPath"])
    assert extract_path.is_file()
    assert extract_path.stat().st_size == 0x110F18


@pytest.mark.skipif(not SONIC_NDS.is_file(), reason="Sonic NDS fixture not available on this machine")
def test_discovery_and_targets_recognize_nds() -> None:
    sniff = sniff_path(SONIC_NDS)
    assert sniff.kind == "binary"
    assert sniff.detail.get("containerFormat") == "nds"
    assert looks_executable(SONIC_NDS)
    assert inspect_magic(SONIC_NDS) == ("nds", "armv5te")
    identity = identify_binary(SONIC_NDS)
    assert identity.format == "nds"
    assert identity.architecture_hint == "armv5te"
