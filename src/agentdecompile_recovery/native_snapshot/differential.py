"""Classify replay output against a snapshot's Java oracle without widening equality."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from agentdecompile_recovery.native_snapshot.canonical import canonicalize, layout_collapsed
from agentdecompile_recovery.native_snapshot.manifest import FunctionEntry, Manifest


MATCH = "match"
MISMATCH_LAYOUT = "mismatch-layout-only"
MISMATCH_CONTENT = "mismatch-content"
NATIVE_CRASH = "native-crash"
MISSING_OUTPUT = "missing-output"


@dataclass(frozen=True)
class DifferentialResult:
    addr: str
    name: str
    classification: str
    java_path: str | None
    native_path: str | None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def classify(entry: FunctionEntry, root: Path, native_text: str | None, *, crashed: bool = False) -> DifferentialResult:
    """Classify one result. Whitespace-only agreement is intentionally not ``match``."""
    oracle = root / entry.oracle_c if entry.oracle_c else None
    if crashed:
        kind = NATIVE_CRASH
    elif native_text is None or oracle is None or not oracle.is_file():
        kind = MISSING_OUTPUT
    else:
        java_text = oracle.read_text(encoding="utf-8", errors="replace")
        if canonicalize(java_text) == canonicalize(native_text):
            kind = MATCH
        elif layout_collapsed(java_text) == layout_collapsed(native_text):
            kind = MISMATCH_LAYOUT
        else:
            kind = MISMATCH_CONTENT
    return DifferentialResult(entry.addr, entry.name, kind, entry.oracle_c, None)


def summary(manifest: Manifest, root: Path, replay: dict[str, str | None], crashed: set[str] | None = None) -> list[DifferentialResult]:
    crashed = crashed or set()
    return [classify(entry, root, replay.get(entry.addr), crashed=entry.addr in crashed) for entry in manifest.ok_entries()]
