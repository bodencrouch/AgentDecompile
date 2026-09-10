"""Classify replay output against a snapshot's Java oracle without widening equality."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
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


def write_report(root: Path, manifest: Manifest, replay: dict[str, str | None], *,
                 crashed: set[str] | None = None, output: Path | None = None) -> list[DifferentialResult]:
    """Write inspectable native text and a deterministic report JSON.

    ``None`` means missing output, while ``crashed`` distinguishes a console
    process failure. Native files live below the snapshot so a report remains
    self-contained but never overwrites Java oracle artifacts.
    """
    output = output or root / "native"
    output.mkdir(parents=True, exist_ok=True)
    results: list[DifferentialResult] = []
    crashed = crashed or set()
    for entry in manifest.ok_entries():
        text = replay.get(entry.addr)
        native_path: str | None = None
        if text is not None:
            native_file = output / f"{entry.addr}.c"
            native_file.write_text(text, encoding="utf-8")
            native_path = str(native_file.relative_to(root))
        classified = classify(entry, root, text, crashed=entry.addr in crashed)
        results.append(DifferentialResult(classified.addr, classified.name, classified.classification, classified.java_path, native_path))
    report = {"schema": "agentdecompile.native-differential/v0", "results": [result.to_dict() for result in results]}
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return results
