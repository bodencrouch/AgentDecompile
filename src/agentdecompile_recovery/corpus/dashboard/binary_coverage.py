"""Honest per-binary capability and evidence status for the workbench library."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agentdecompile_recovery.inventory import supports_binary_format
from agentdecompile_recovery.targets import inspect_magic
_FORMAT_NAMES = {
    "portable executable (pe)": "pe",
    "executable and linking format (elf)": "elf",
    "mac os x mach-o": "macho",
    "nds": "nds",
}


# Keep discovery compatible with actions/matching.py without importing its native dependencies.
_PRESET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_FUNCTION = re.compile(r"[A-Za-z_][A-Za-z0-9_@$?]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _public_text(value: Any, fallback: str) -> str:
    # Display metadata must not accidentally expose configured filesystem paths.
    return value.strip() if isinstance(value, str) and value.strip() and len(value) <= 256 and value.isprintable() and "/" not in value and "\\" not in value else fallback


def _matching_presets(sha256: str) -> list[dict[str, Any]]:
    configured = os.environ.get("AGENT_DECOMPILE_MATCHING_PRESET_ROOT", "").strip()
    sha256 = sha256.strip().lower()
    if not _SHA256.fullmatch(sha256) or not configured:
        return []
    try:
        root = Path(configured).expanduser().resolve()
        paths = sorted(root.glob("*.json")) if root.is_dir() else []
    except (OSError, RuntimeError, ValueError):
        return []
    found: list[dict[str, Any]] = []
    for candidate in paths:
        try:
            preset_id = candidate.stem
            if not _PRESET_ID.fullmatch(preset_id):
                continue
            path = candidate.resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or str(payload.get("artifactHash") or "").strip().lower() != sha256:
                continue
            # The action opens <requested ID>.json, then resolves symlinks before loading.
            if str(payload.get("id") or path.stem) != preset_id:
                continue
            script = payload.get("compilerScript")
            if not isinstance(script, str) or not script.strip():
                continue
            project_root = Path(str(payload.get("projectRoot") or path.parent)).expanduser().resolve()
            if not project_root.is_dir():
                continue
            int(payload.get("timeoutSeconds", 300))
            context = payload.get("contextPath")
            if context:
                context_path = Path(str(context)).expanduser()
                if not context_path.is_absolute():
                    context_path = path.parent / context_path
                context_path = context_path.resolve()
                if not context_path.is_relative_to(project_root) or not context_path.is_file() or context_path.stat().st_size > 2 * 1024 * 1024:
                    continue
            bindings = payload.get("targets")
            if not isinstance(bindings, dict):
                continue
            targets = []
            for function, target in sorted(bindings.items()):
                if not _FUNCTION.fullmatch(function) or not isinstance(target, dict):
                    continue
                revision = str(target.get("sha256") or "").strip().lower()
                symbol = str(target.get("symbol") or function).strip()
                if not _SHA256.fullmatch(revision) or not symbol or _public_text(symbol, "") != symbol:
                    continue
                try:
                    target_path = Path(str(target.get("path") or "")).expanduser()
                    if not target_path.is_absolute():
                        target_path = project_root / target_path
                    target_path = target_path.resolve()
                    if not target_path.is_relative_to(project_root) or not target_path.is_file():
                        continue
                except (OSError, RuntimeError, ValueError):
                    continue
                targets.append({"function": function, "symbol": symbol, "targetRevision": revision})
            if targets:
                found.append({"id": preset_id, "label": _public_text(payload.get("label"), preset_id),
                              "platform": _public_text(payload.get("platform"), "unknown"), "targets": targets})
        except (OSError, UnicodeError, ValueError, TypeError, RuntimeError, OverflowError):
            continue
    return found


def annotate_binary_coverage(
    rows: list[dict[str, Any]], recorded_identities: dict[str, str]
) -> list[dict[str, Any]]:
    """Attach status facts without converting analysis or matching into proof."""
    for row in rows:
        sha256 = str(row.get("sha256") or "")
        source_paths = [str(path) for path in row.get("sourcePaths") or [row.get("repo") or ""]]
        exact = bool(sha256 and any(recorded_identities.get(path) == sha256 for path in source_paths))
        recorded_format = str(row.get("format") or "").strip().lower()
        fmt = _FORMAT_NAMES.get(recorded_format, recorded_format)
        if fmt in {"", "unknown"} and row.get("kind") == "binary" and row.get("repo"):
            try:
                fmt, _ = inspect_magic(Path(str(row["repo"])))
            except OSError:
                pass
        parser_supported = supports_binary_format(fmt)
        bindings = row.get("projectBindings") or []
        source_count = int((row.get("decomp") or {}).get("files") or 0)
        function_count = int(row.get("funcs") or 0)
        presets = _matching_presets(sha256)
        row["coverage"] = {
            "exactHashRegistration": {
                "status": "confirmed" if exact else "unconfirmed",
                "sha256": sha256 or None,
            },
            "parser": {
                "status": "supported" if parser_supported else "unsupported",
                "format": fmt,
                "provider": "agentdecompile.binary-inventory.v1" if parser_supported else None,
            },
            "projectProvider": {
                "status": "available" if bindings else "not-bound",
                "bindings": len(bindings),
            },
            "evidence": {
                "status": "available" if function_count or source_count else "not-produced",
                "functions": function_count,
                "sourceFiles": source_count,
            },
            "matchingPreset": {
                "status": "available" if presets else "unavailable",
                "ids": [preset["id"] for preset in presets],
                "presets": presets,
            },
            "proof": {
                "phase": "comparison-pending",
                "reason": "Independent objdiff starts when a candidate object is available; no accepted receipt is recorded yet.",
            },
            "claimBoundary": "Registration, parser support, evidence, and matching presets do not prove a byte match.",
        }
    return rows
