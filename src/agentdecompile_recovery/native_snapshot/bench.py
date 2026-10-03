"""Strict, inspectable benchmark report construction for native snapshot lanes.

Collection is intentionally separate from report construction: callers supply
the completed addresses and per-function timings they actually observed.  A
table is refused rather than silently comparing different function sets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Iterable

from .manifest import Manifest, addr16


class CompletionMismatch(ValueError):
    """Lanes did not finish the same function set."""


class CorpusMismatch(ValueError):
    """A benchmark input no longer matches its recorded corpus manifest."""


class CompletionIdentityError(ValueError):
    """A lane completion ID cannot be resolved unambiguously in the manifest."""


def verify_corpus(manifest_path: Path, corpus: str, *, repo_root: Path) -> dict[str, object]:
    """Return one corpus spec after checking every repository-local SHA-256."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "agentdecompile.native-bench-corpora/v0":
        raise CorpusMismatch("unsupported corpus manifest schema")
    spec = payload.get("corpora", {}).get(corpus)
    if not isinstance(spec, dict):
        raise CorpusMismatch(f"unknown corpus: {corpus}")
    for relative, expected in spec.get("sha256", {}).items():
        # Installed Ghidra tools have short names in the hash map and are
        # validated by their installer separately; only repo-relative paths
        # are safe and meaningful to resolve here.
        if not str(relative).startswith("tests/"):
            continue
        actual = hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise CorpusMismatch(f"corpus hash mismatch: {relative}")
    return spec


@dataclass(frozen=True)
class Lane:
    name: str
    completed: tuple[str, ...]
    wall_s: float
    elapsed_ms: tuple[float, ...]
    cpu_s: float | None = None
    rss_hwm_mb: float | None = None
    jvm_heap_max_mb: float | None = None
    child_hwm: int | None = None
    named_child_hwm: int | None = None
    includes_analysis: bool = False

    def __post_init__(self) -> None:
        if self.wall_s < 0 or len(self.completed) != len(self.elapsed_ms):
            raise ValueError("lane must have one non-negative timing per completed address")


def normalize_lanes(lanes: Iterable[Lane], manifest: Manifest) -> list[Lane]:
    """Resolve every lane completion to the manifest's space-qualified identity.

    Current producers emit ``<space>:<addr>``. Historical lane JSONL emitted a
    numeric address alone; that form remains usable only when one successful
    manifest entry has the address. Unknown and ambiguous identities are
    rejected so address-space collisions cannot be hidden by set comparison.
    """
    stable_ids: set[str] = set()
    by_addr: dict[str, list[str]] = {}
    for entry in manifest.ok_entries():
        if entry.stable_id in stable_ids:
            raise CompletionIdentityError(f"duplicate stable manifest ID: {entry.stable_id}")
        stable_ids.add(entry.stable_id)
        by_addr.setdefault(entry.addr.lower(), []).append(entry.stable_id)

    normalized: list[Lane] = []
    for lane in lanes:
        completed: list[str] = []
        for raw_id in lane.completed:
            identity = raw_id.strip()
            if identity in stable_ids:
                stable_id = identity
            else:
                try:
                    numeric = identity[2:] if identity.lower().startswith("0x") else identity
                    canonical_addr = addr16(int(numeric, 16))
                except (ValueError, OverflowError):
                    candidates: list[str] = []
                else:
                    candidates = by_addr.get(canonical_addr, [])
                if len(candidates) == 1:
                    stable_id = candidates[0]
                elif len(candidates) > 1:
                    raise CompletionIdentityError(
                        f"lane {lane.name!r} has ambiguous legacy completion ID {raw_id!r}: {sorted(candidates)}"
                    )
                else:
                    raise CompletionIdentityError(
                        f"lane {lane.name!r} completion ID {raw_id!r} is missing from the manifest"
                    )
            if stable_id in completed:
                raise CompletionIdentityError(
                    f"lane {lane.name!r} completion ID {raw_id!r} duplicates normalized ID {stable_id!r}"
                )
            completed.append(stable_id)
        normalized.append(replace(lane, completed=tuple(completed)))
    return normalized


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


def _is_parallel_lane(name: str) -> bool:
    return name == "parallel" or name.startswith("parallel-")


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
    parallel = min((lane for lane in rows if _is_parallel_lane(lane.name)), key=lambda lane: lane.wall_s, default=None)
    java = parallel or by_name.get("serial")
    native = min((lane for lane in rows if lane.name in {"native-console", "native-batch"}), key=lambda lane: lane.wall_s, default=None)
    export = by_name.get("export")
    k_star: float | str = "never"
    if java and native and export and java.wall_s > native.wall_s:
        k_star = export.wall_s / (java.wall_s - native.wall_s)
    return {
        "schema": "agentdecompile.native-bench/v0",
        "corpus": corpus,
        "held_constant": {"completed_addresses": sorted(expected), "function_count": len(expected), "options_sha256": options_sha256, "timeout_s": timeout_s},
        "export_requires_java_decompile": export_requires_java_decompile,
        "best_java_lane": java.name if java else None,
        "best_native_lane": native.name if native else None,
        "k_star": k_star,
        "lanes": [_row(lane) for lane in rows],
    }


def write_report(output_dir: Path, payload: dict[str, object]) -> tuple[Path, Path]:
    """Write machine-readable JSON and a compact human table atomically enough for local runs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "bench.json"
    md_path = output_dir / "bench.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    held = payload["held_constant"]  # type: ignore[index]
    lines = [
        "# Native SDK benchmark",
        "",
        f"Corpus: `{payload['corpus']}`",
        "",
        "## Held constant",
        "",
        f"- Function count: `{held['function_count']}`",  # type: ignore[index]
        f"- Options SHA-256: `{held['options_sha256']}`",  # type: ignore[index]
        f"- Timeout: `{held['timeout_s']}` seconds",  # type: ignore[index]
        "",
        "| Lane | Functions | Wall s | fn/s | CPU s | RSS HWM MB | Child HWM | p50 ms | p95 ms | p99 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for lane in payload["lanes"]:  # type: ignore[index]
        row = {**lane}
        for key in ("cpu_s", "rss_hwm_mb", "child_hwm"):
            row[key] = "n/a" if row.get(key) is None else row[key]
        lines.append("| {name} | {completed_count} | {wall_s:.3f} | {fn_per_s:.3f} | {cpu_s} | {rss_hwm_mb} | {child_hwm} | {p50_ms:.1f} | {p95_ms:.1f} | {p99_ms:.1f} |".format(**row))
    lines += [
        "",
        f"`best_java_lane`: `{payload['best_java_lane']}`",
        f"`best_native_lane`: `{payload['best_native_lane']}`",
        f"`export_requires_java_decompile`: `{payload['export_requires_java_decompile']}`",
        f"`k_star`: `{payload['k_star']}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
