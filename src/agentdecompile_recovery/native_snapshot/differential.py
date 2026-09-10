"""Classify replay output against a snapshot's Java oracle without widening equality."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import difflib
import json
from pathlib import Path

from agentdecompile_recovery.native_snapshot.canonical import canonicalize, layout_collapsed
from agentdecompile_recovery.native_snapshot.manifest import FunctionEntry, Manifest


MATCH = "match"
MISMATCH_LAYOUT = "mismatch-layout-only"
MISMATCH_CONTENT = "mismatch-content"
NATIVE_MISSING_DEPENDENCY = "native-missing-dependency"
NATIVE_ERROR = "native-error"
NATIVE_TIMEOUT = "native-timeout"
NATIVE_CRASH = "native-crash"
ORACLE_ABSENT = "oracle-absent"


@dataclass(frozen=True)
class DifferentialResult:
    addr: str
    name: str
    classification: str
    java_path: str | None
    native_path: str | None
    diff_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def classify(
    entry: FunctionEntry,
    root: Path,
    native_text: str | None,
    *,
    crashed: bool = False,
    timed_out: bool = False,
    native_error: str | None = None,
    missing_dependency: str | None = None,
) -> DifferentialResult:
    """Classify one result. Whitespace-only agreement is intentionally not ``match``."""
    oracle = root / entry.oracle_c if entry.oracle_c else None
    if oracle is None or not oracle.is_file():
        kind = ORACLE_ABSENT
        error = "oracle C absent"
    elif missing_dependency:
        kind = NATIVE_MISSING_DEPENDENCY
        error = missing_dependency
    elif crashed:
        kind = NATIVE_CRASH
        error = native_error
    elif timed_out:
        kind = NATIVE_TIMEOUT
        error = native_error
    elif native_text is None:
        kind = NATIVE_ERROR
        error = native_error or "native output absent"
    else:
        java_text = oracle.read_text(encoding="utf-8", errors="replace")
        if canonicalize(java_text) == canonicalize(native_text):
            kind = MATCH
        elif layout_collapsed(java_text) == layout_collapsed(native_text):
            kind = MISMATCH_LAYOUT
        else:
            kind = MISMATCH_CONTENT
        error = None
    return DifferentialResult(entry.addr, entry.name, kind, entry.oracle_c, None, error=error)


def summary(manifest: Manifest, root: Path, replay: dict[str, str | None], crashed: set[str] | None = None) -> list[DifferentialResult]:
    crashed = crashed or set()
    return [classify(entry, root, replay.get(entry.addr), crashed=entry.addr in crashed) for entry in manifest.ok_entries()]


def _write_diff(path: Path, java_text: str, native_text: str) -> None:
    diff = difflib.unified_diff(
        canonicalize(java_text).splitlines(keepends=True),
        canonicalize(native_text).splitlines(keepends=True),
        fromfile="java-oracle",
        tofile="native",
    )
    path.write_text("".join(diff), encoding="utf-8")


def _markdown_report(results: list[DifferentialResult]) -> str:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.classification] = counts.get(result.classification, 0) + 1
    lines = [
        "# Native Differential Report",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for key in sorted(counts):
        lines.append(f"| {key} | {counts[key]} |")
    lines.extend(["", "| Address | Name | Classification |", "|---|---|---|"])
    for result in results:
        lines.append(f"| `{result.addr}` | `{result.name}` | {result.classification} |")
    lines.append("")
    return "\n".join(lines)


def write_report(root: Path, manifest: Manifest, replay: dict[str, str | None], *,
                 crashed: set[str] | None = None, output: Path | None = None) -> list[DifferentialResult]:
    """Write inspectable native text and a deterministic report JSON.

    ``None`` means missing output, while ``crashed`` distinguishes a console
    process failure. Native files live below the snapshot so a report remains
    self-contained but never overwrites Java oracle artifacts.
    """
    output = output or root / "differential"
    output.mkdir(parents=True, exist_ok=True)
    native_dir = output / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    diff_dir = output / "diff"
    diff_dir.mkdir(parents=True, exist_ok=True)
    results: list[DifferentialResult] = []
    crashed = crashed or set()
    for entry in manifest.ok_entries():
        text = replay.get(entry.addr)
        native_path: str | None = None
        if text is not None:
            native_file = native_dir / f"{entry.addr}.c"
            native_file.write_text(text, encoding="utf-8")
            native_path = str(native_file.relative_to(root))
        classified = classify(entry, root, text, crashed=entry.addr in crashed)
        diff_path: str | None = None
        if classified.classification == MISMATCH_CONTENT and text is not None and entry.oracle_c:
            oracle = root / entry.oracle_c
            if oracle.is_file():
                diff_file = diff_dir / f"{entry.addr}.diff"
                _write_diff(diff_file, oracle.read_text(encoding="utf-8", errors="replace"), text)
                diff_path = str(diff_file.relative_to(root))
        results.append(
            DifferentialResult(
                classified.addr,
                classified.name,
                classified.classification,
                classified.java_path,
                native_path,
                diff_path,
                classified.error,
            )
        )
    report = {
        "schema": "agentdecompile.native-differential/v0",
        "counts": {kind: sum(1 for result in results if result.classification == kind) for kind in sorted({r.classification for r in results})},
        "results": [result.to_dict() for result in results],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "report.md").write_text(_markdown_report(results), encoding="utf-8")
    return results
