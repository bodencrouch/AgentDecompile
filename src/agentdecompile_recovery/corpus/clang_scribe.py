"""Local dialect cleanup after Ghidra emit.

No Clang AST rewrites are implemented here. Do not launch Clang for every
function merely to traverse its AST without changing the source. Keep the
existing entry point and report that AST recovery was not performed.
"""

from __future__ import annotations

import re
import shutil
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .normalize_pipeline import NormalizeMode


def clang_binary() -> str | None:
    for name in ("clang", "clang-15", "clang-18", "clang-17"):
        path = shutil.which(name)
        if path:
            return path
    return None


def run_clang_passes(code: str, *, mode: NormalizeMode | str) -> tuple[str, dict[str, Any]]:
    from .normalize_pipeline import NormalizeMode

    resolved = NormalizeMode(mode)
    text = _local_dialect_passes(code, resolved)
    clang = clang_binary()
    if clang is None:
        return text, {"used": False, "reason": "clang not on PATH"}
    return text, {"used": False, "reason": "no AST rewrites implemented", "clang": clang}


def _local_dialect_passes(code: str, mode: NormalizeMode) -> str:
    """Compiler-level spelling that does not invent layout.

    Boolean width follows SCRIBE: one byte, not a host ``_Bool``.
    """
    text = re.sub(r"\b_Bool\b", "unsigned char", code)
    text = re.sub(r"\bbool\b", "unsigned char", text)
    return text
