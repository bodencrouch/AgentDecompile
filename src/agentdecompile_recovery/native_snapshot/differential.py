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
PARITY_FAILURE = "parity-failure"


@dataclass(frozen=True)
class DifferentialResult:
    addr: str
    name: str
    classification: str
    java_path: str | None
    native_path: str | None
    diff_path: str | None = None
    error: str | None = None
    space: str = "ram"
    function_id: str = ""

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
    return DifferentialResult(
        entry.addr,
        entry.name,
        kind,
        entry.oracle_c,
        None,
        error=error,
        space=entry.space,
        function_id=entry.stable_id,
    )


def _address_counts(entries: list[FunctionEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.addr] = counts.get(entry.addr, 0) + 1
    return counts


def _entry_value(values: dict[str, object], entry: FunctionEntry, counts: dict[str, int]):
    if entry.stable_id in values:
        return values[entry.stable_id]
    if counts.get(entry.addr) == 1:
        return values.get(entry.addr)
    return None


def _entry_present(values: set[str] | dict[str, object], entry: FunctionEntry, counts: dict[str, int]) -> bool:
    return entry.stable_id in values or (counts.get(entry.addr) == 1 and entry.addr in values)


def summary(manifest: Manifest, root: Path, replay: dict[str, str | None], crashed: set[str] | None = None) -> list[DifferentialResult]:
    crashed = crashed or set()
    entries = list(manifest.ok_entries())
    counts = _address_counts(entries)
    return [
        classify(
            entry,
            root,
            _entry_value(replay, entry, counts),
            crashed=_entry_present(crashed, entry, counts),
        )
        for entry in entries
    ]


def _write_diff(path: Path, java_text: str, native_text: str) -> None:
    diff = difflib.unified_diff(
        canonicalize(java_text).splitlines(keepends=True),
        canonicalize(native_text).splitlines(keepends=True),
        fromfile="java-oracle",
        tofile="native",
    )
    path.write_text("".join(diff), encoding="utf-8")


def _markdown_report(results: list[DifferentialResult], parity: list[str], warnings: list[str]) -> str:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.classification] = counts.get(result.classification, 0) + 1
    lines = [
        "# Native Differential Report",
        "",
        f"- Parity: {'failed' if parity else 'ok'}",
    ]
    if parity:
        lines.extend(f"  - {error}" for error in parity)
    if warnings:
        lines.append("- Parity warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
    lines.extend([
        "",
        "| Classification | Count |",
        "|---|---:|",
    ])
    for key in sorted(counts):
        lines.append(f"| {key} | {counts[key]} |")
    lines.extend(["", "| Function ID | Address | Name | Classification |", "|---|---|---|---|"])
    for result in results:
        lines.append(
            f"| `{result.function_id}` | `{result.addr}` | `{result.name}` | {result.classification} |"
        )
    lines.append("")
    return "\n".join(lines)


def _report_relative(path: Path, root: Path, output: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path.relative_to(output))


def parity_errors(manifest: Manifest, replay_engines: tuple[dict[str, object], ...]) -> list[str]:
    """Return native-vs-snapshot provenance mismatches that invalidate a diff."""
    errors: list[str] = []
    if not replay_engines:
        errors.append("native replay did not report engine metadata")
        return errors
    sources = {str(engine.get("source") or "") for engine in replay_engines}
    ghidra_version = manifest.producer.ghidra_version
    if ghidra_version != "12.1.3":
        errors.append(f"snapshot producer Ghidra version mismatch: expected '12.1.3', got {ghidra_version!r}")
    expected_tag = f"Ghidra_{ghidra_version}_build"
    mismatched_sources = sorted(source for source in sources if not source.startswith(expected_tag))
    if mismatched_sources:
        errors.append(f"native engine source mismatch: expected prefix {expected_tag!r}, got {mismatched_sources!r}")
    sig_pairs = {
        (engine.get("sig_major"), engine.get("sig_minor"))
        for engine in replay_engines
    }
    expected_sig = (manifest.engine.sig_major, manifest.engine.sig_minor)
    if expected_sig not in sig_pairs:
        got = sorted(f"{major}.{minor}" for major, minor in sig_pairs)
        errors.append(f"native engine signature mismatch: expected {expected_sig[0]}.{expected_sig[1]}, got {got!r}")
    return errors


def parity_warnings(manifest: Manifest, replay_engines: tuple[dict[str, object], ...]) -> list[str]:
    warnings: list[str] = []
    expected = manifest.engine.java_sla_sha256
    if not expected:
        return warnings
    observed: dict[str, str] = {}
    for engine in replay_engines:
        hashes = engine.get("sla_sha256")
        if isinstance(hashes, dict):
            observed.update({str(language): str(digest) for language, digest in hashes.items()})
    for language_id, expected_digest in sorted(expected.items()):
        digest = observed.get(language_id)
        if digest is None:
            warnings.append(f"native SLEIGH hash missing for {language_id}")
        elif digest != expected_digest:
            warnings.append(f"native SLEIGH hash mismatch for {language_id}: expected {expected_digest}, got {digest}")
    return warnings


def write_report(root: Path, manifest: Manifest, replay: dict[str, str | None], *,
                 crashed: set[str] | None = None,
                 timed_out: set[str] | None = None,
                 errors: dict[str, str] | None = None,
                 parity: list[str] | None = None,
                 parity_warnings: list[str] | None = None,
                 output: Path | None = None) -> list[DifferentialResult]:
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
    timed_out = timed_out or set()
    errors = errors or {}
    parity = parity or []
    parity_warnings = parity_warnings or []
    entries = list(manifest.ok_entries())
    address_counts = _address_counts(entries)
    for entry in entries:
        text = _entry_value(replay, entry, address_counts)
        native_path: str | None = None
        artifact_stem = entry.stable_stem if address_counts[entry.addr] > 1 else entry.addr
        if text is not None:
            native_file = native_dir / f"{artifact_stem}.c"
            native_file.write_text(text, encoding="utf-8")
            native_path = _report_relative(native_file, root, output)
        classified = classify(
            entry,
            root,
            text,
            crashed=_entry_present(crashed, entry, address_counts),
            timed_out=_entry_present(timed_out, entry, address_counts),
            native_error=_entry_value(errors, entry, address_counts),
        )
        diff_path: str | None = None
        if classified.classification == MISMATCH_CONTENT and text is not None and entry.oracle_c:
            oracle = root / entry.oracle_c
            if oracle.is_file():
                diff_file = diff_dir / f"{artifact_stem}.diff"
                _write_diff(diff_file, oracle.read_text(encoding="utf-8", errors="replace"), text)
                diff_path = _report_relative(diff_file, root, output)
        results.append(
            DifferentialResult(
                classified.addr,
                classified.name,
                classified.classification,
                classified.java_path,
                native_path,
                diff_path,
                classified.error,
                classified.space,
                classified.function_id,
            )
        )
    effective_parity = list(parity)
    if parity_warnings and any(result.classification == MISMATCH_CONTENT for result in results):
        effective_parity.append("native SLEIGH hash drift coincides with mismatch-content results")
    report = {
        "schema": "agentdecompile.native-differential/v0",
        "parity": {"ok": not effective_parity, "errors": effective_parity, "warnings": parity_warnings},
        "counts": {kind: sum(1 for result in results if result.classification == kind) for kind in sorted({r.classification for r in results})},
        "results": [result.to_dict() for result in results],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "report.md").write_text(_markdown_report(results, effective_parity, parity_warnings), encoding="utf-8")
    return results
