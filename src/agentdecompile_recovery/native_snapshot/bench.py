"""Strict, inspectable benchmark report construction for native snapshot lanes.

Collection is intentionally separate from report construction: callers supply
the completed addresses and per-function timings they actually observed.  A
table is refused rather than silently comparing different function sets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from typing import Iterable


class CompletionMismatch(ValueError):
    """Lanes did not finish the same function set."""


@dataclass(frozen=True)
class Lane:
    name: str
    completed: tuple[str, ...]
    wall_s: float
    elapsed_ms: tuple[float, ...]
    cpu_s: float | None = None
    rss_hwm_mb: float | None = None
    child_hwm: int | None = None
    includes_analysis: bool = False

    def __post_init__(self) -> None:
        if self.wall_s < 0 or len(self.completed) != len(self.elapsed_ms):
            raise ValueError("lane must have one non-negative timing per completed address")


def _percentile(values: tuple[float, ...], percent: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * percent / 100
    low, high = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _row(lane: Lane) -> dict[str, object]:
    count = len(lane.completed)
    return {
        **asdict(lane),
        "completed": list(lane.completed),
        "elapsed_ms": list(lane.elapsed_ms),
        "completed_count": count,
        "fn_per_s": count / lane.wall_s if lane.wall_s else 0.0,
        "p50_ms": median(lane.elapsed_ms) if lane.elapsed_ms else 0.0,
        "p95_ms": _percentile(lane.elapsed_ms, 95),
        "p99_ms": _percentile(lane.elapsed_ms, 99),
    }


def report(corpus: str, lanes: Iterable[Lane], *, options_sha256: str, timeout_s: float, export_requires_java_decompile: bool = True) -> dict[str, object]:
    """Build a report, refusing completion drift before any rate is calculated."""
    rows = list(lanes)
    if not rows:
        raise ValueError("at least one lane is required")
    expected = set(rows[0].completed)
    mismatched = {lane.name: sorted(set(lane.completed) ^ expected) for lane in rows if set(lane.completed) != expected}
    if mismatched:
        raise CompletionMismatch(f"REFUSED (completion mismatch): {mismatched}")
    by_name = {lane.name: lane for lane in rows}
    java = by_name.get("parallel") or by_name.get("serial")
    native = min((lane for lane in rows if lane.name in {"native-console", "native-batch"}), key=lambda lane: lane.wall_s, default=None)
    export = by_name.get("export")
    k_star: float | str = "never"
    if java and native and export and java.wall_s > native.wall_s:
        k_star = export.wall_s / (java.wall_s - native.wall_s)
    return {
        "schema": "agentdecompile.native-bench/v0",
        "corpus": corpus,
        "held_constant": {"completed_addresses": sorted(expected), "options_sha256": options_sha256, "timeout_s": timeout_s},
        "export_requires_java_decompile": export_requires_java_decompile,
        "k_star": k_star,
        "lanes": [_row(lane) for lane in rows],
    }


def write_report(output_dir: Path, payload: dict[str, object]) -> tuple[Path, Path]:
    """Write machine-readable JSON and a compact human table atomically enough for local runs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "bench.json"
    md_path = output_dir / "bench.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Native SDK benchmark", "", f"Corpus: `{payload['corpus']}`", "", "| Lane | Functions | Wall s | fn/s | p50 ms | p95 ms |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for lane in payload["lanes"]:  # type: ignore[index]
        lines.append("| {name} | {completed_count} | {wall_s:.3f} | {fn_per_s:.3f} | {p50_ms:.1f} | {p95_ms:.1f} |".format(**lane))
    lines += ["", f"`export_requires_java_decompile`: `{payload['export_requires_java_decompile']}`", f"`k_star`: `{payload['k_star']}`", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
