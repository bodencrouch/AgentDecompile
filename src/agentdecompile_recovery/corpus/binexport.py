"""Optional BinExport generation helper.

Prep/helper only — never a match-pair hard dependency. BinDiff/Diaphora import
remains in ``second_opinion`` at status=verify.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def binexport_available() -> bool:
    env = os.environ.get("AGENTDECOMPILE_BINEXPORT") or os.environ.get("BINEXPORT_BIN")
    if env and Path(env).exists():
        return True
    return any(shutil.which(name) for name in ("binexport", "BinExport", "binexport2dump"))


def _tool_path() -> str | None:
    env = os.environ.get("AGENTDECOMPILE_BINEXPORT") or os.environ.get("BINEXPORT_BIN")
    if env and Path(env).exists():
        return env
    for name in ("binexport", "BinExport", "binexport2dump"):
        found = shutil.which(name)
        if found:
            return found
    return None


def export_binary(program_path: str | Path, out_path: str | Path, *, timeout: float = 120) -> dict:
    tool = _tool_path()
    if not tool:
        return {"ok": False, "skipped": True, "reason": "missing_tool"}
    program_path = Path(program_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [tool, str(program_path), str(out_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "skipped": False, "reason": str(exc)}
    if proc.returncode != 0:
        return {
            "ok": False,
            "skipped": False,
            "reason": f"exit_{proc.returncode}",
            "stderr": (proc.stderr or "")[:500],
        }
    return {"ok": True, "path": str(out_path), "tool": tool}


__all__ = ["binexport_available", "export_binary"]
