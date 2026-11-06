"""AgentDecompile CLI - stdio MCP bridge for AgentDecompile Ghidra extension.

This package provides a command-line interface that bridges stdio MCP transport
to AgentDecompile's StreamableHTTP server, enabling seamless integration with Claude CLI.
Programmatic use: AgentDecompileMcpClient for async HTTP access to an existing server.

Package layout:
  - bridge: HTTP client (AgentDecompileMcpClient), stdio bridge, MCP session fix.
  - registry: Tool names (Tool enum), normalization, TOOLS, TOOL_PARAMS, resource URIs.
  - executor: run_async(), get_client(), error handling, backend URL resolution.
  - launcher: PyGhidra init, ProjectManager, AgentDecompileLauncher (see launcher.py).
  - mcp_server: FastMCP server, ToolProviderManager, providers/*, resources, prompts.

Tool and resource names: use agentdecompile_cli.registry (TOOLS, RESOURCE_URIS,
build_tool_payload, get_tool_params, resolve_tool_name_enum).
"""

try:
    from ._version import version as __version__
except ImportError:
    # Fallback version if not installed or in development without git tags
    __version__ = "0.0.0.dev0"

from agentdecompile_cli.env_compat import sync_agentdecompile_env_aliases

# Keep compact and canonical env prefixes in lockstep for all submodules.
sync_agentdecompile_env_aliases()

from importlib import import_module
from typing import Any

# Keep the package facade stable without importing MCP's bridge/server stack for
# every submodule import. In particular, CLI help and metadata queries should
# not pay the startup cost of FastMCP, Pydantic, and the bridge transport.
_EXPORT_MODULES = {
    "AgentDecompileMcpClient": "bridge",
    "ClientError": "bridge",
    "NotFoundError": "bridge",
    "ServerNotRunningError": "bridge",
    "RESOURCE_URI_CAPABILITIES": "registry",
    "RESOURCE_URI_DEBUG_INFO": "registry",
    "RESOURCE_URI_PROGRAMS": "registry",
    "RESOURCE_URI_STATIC_ANALYSIS": "registry",
    "RESOURCE_URIS": "registry",
    "ResourceUri": "registry",
    "Tool": "registry",
    "ToolName": "registry",
    "TOOLS": "registry",
    "TOOL_PARAMS": "registry",
    "build_tool_payload": "registry",
    "get_tool_params": "registry",
    "resolve_tool_name_enum": "registry",
    "to_camel_case_key": "registry",
    "get_client": "executor",
    "get_server_start_message": "executor",
    "handle_command_error": "executor",
    "handle_noisy_mcp_errors": "executor",
    "run_async": "executor",
    "show_connection_error": "executor",
}

__all__ = [
    "RESOURCE_URIS",
    "RESOURCE_URI_CAPABILITIES",
    "RESOURCE_URI_DEBUG_INFO",
    "RESOURCE_URI_PROGRAMS",
    "RESOURCE_URI_STATIC_ANALYSIS",
    "TOOLS",
    "TOOL_PARAMS",
    "AgentDecompileMcpClient",
    "ClientError",
    "NotFoundError",
    "ResourceUri",
    "ServerNotRunningError",
    "Tool",
    "ToolName",
    "__version__",
    "build_tool_payload",
    "get_client",
    "get_server_start_message",
    "get_tool_params",
    "handle_command_error",
    "handle_noisy_mcp_errors",
    "resolve_tool_name_enum",
    "run_async",
    "show_connection_error",
    "to_camel_case_key",
]


def __getattr__(name: str) -> Any:
    """Load a public facade export only when the caller requests it."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORT_MODULES})
