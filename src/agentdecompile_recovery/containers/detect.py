"""Lightweight container format detection helpers."""
from __future__ import annotations

from pathlib import Path

from . import nds as nds_mod
from .registry import detect_container


def is_nds_binary(path: Path, *, head: bytes | None = None) -> bool:
    """Return True when *path* looks like a Nintendo DS (.nds) ROM container."""
    return detect_container(path, head=head) == "nds" or nds_mod.looks_like_nds(path, head=head)
