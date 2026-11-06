"""Optional Ghidra wrapper bound to the context of one provider call."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import SimpleNamespace

    from agentdecompile_cli.launcher import ProgramInfo


def ghidra_tools_for_program(program_info: ProgramInfo | SimpleNamespace | None) -> Any | None:
    if program_info is None:
        return None
    try:
        from agentdecompile_cli.tools.wrappers import GhidraTools

        return GhidraTools(program_info)
    except Exception:
        # Providers retain their direct API fallback when the wrapper is unavailable.
        return None
