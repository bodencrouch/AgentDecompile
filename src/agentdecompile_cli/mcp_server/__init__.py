"""Python MCP Server implementation for AgentDecompile.

This module provides a complete Python-based MCP server,
offering the same API while running entirely in Python using PyGhidra for Ghidra integration.
"""

# Lazy re-exports (PEP 562): importing any ``agentdecompile_cli.mcp_server.<sub>``
# must not load the whole server stack (fastapi, FastMCP, tool providers).
_LAZY_EXPORTS: dict[str, str] = {
    "PythonMcpServer": ".server",
    "ServerConfig": ".server",
    "ToolProviderManager": ".tool_providers",
    "ResourceProviderManager": ".resource_providers",
}


def __getattr__(name: str):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "PythonMcpServer",
    "ResourceProviderManager",
    "ServerConfig",
    "ToolProviderManager",
]
