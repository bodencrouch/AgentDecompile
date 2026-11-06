"""Native decompiler snapshot tooling: export Ghidra ``DecompileDebug`` savefiles for JVM-free replay.

Schema and pure-Python helpers live in :mod:`agentdecompile_recovery.native_snapshot.manifest`.
The exporter (needs a running PyGhidra JVM) lives in :mod:`agentdecompile_recovery.native_snapshot.exporter`.
Nothing here imports pyghidra or JPype at import time.
"""

from __future__ import annotations

from agentdecompile_recovery.native_snapshot.manifest import (
    EXPORTER_VERSION,
    SCHEMA,
    Manifest,
    load_manifest,
    partial_name,
    savefile_name,
    validate_manifest,
)

__all__ = [
    "EXPORTER_VERSION",
    "SCHEMA",
    "Manifest",
    "load_manifest",
    "partial_name",
    "savefile_name",
    "validate_manifest",
]
