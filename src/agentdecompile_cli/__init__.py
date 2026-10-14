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

# Lazy re-exports (PEP 562). Importing bridge/executor pulls in the MCP SDK
# (~0.7 s), which CLI startup must not pay. ``from agentdecompile_cli import X``
# keeps working: the attribute is resolved on first access.
_LAZY_EXPORTS: dict[str, str] = {
    "AgentDecompileMcpClient": "agentdecompile_cli.bridge",
    "ClientError": "agentdecompile_cli.bridge",
    "NotFoundError": "agentdecompile_cli.bridge",
    "ServerNotRunningError": "agentdecompile_cli.bridge",
    "RESOURCE_URI_CAPABILITIES": "agentdecompile_cli.registry",
    "RESOURCE_URI_DEBUG_INFO": "agentdecompile_cli.registry",
    "RESOURCE_URI_PROGRAMS": "agentdecompile_cli.registry",
    "RESOURCE_URI_STATIC_ANALYSIS": "agentdecompile_cli.registry",
    "RESOURCE_URIS": "agentdecompile_cli.registry",
    "ResourceUri": "agentdecompile_cli.registry",
    "Tool": "agentdecompile_cli.registry",
    "ToolName": "agentdecompile_cli.registry",
    "TOOLS": "agentdecompile_cli.registry",
    "TOOL_PARAMS": "agentdecompile_cli.registry",
    "build_tool_payload": "agentdecompile_cli.registry",
    "get_tool_params": "agentdecompile_cli.registry",
    "resolve_tool_name_enum": "agentdecompile_cli.registry",
    "to_camel_case_key": "agentdecompile_cli.registry",
    "get_client": "agentdecompile_cli.executor",
    "get_server_start_message": "agentdecompile_cli.executor",
    "handle_command_error": "agentdecompile_cli.executor",
    "handle_noisy_mcp_errors": "agentdecompile_cli.executor",
    "run_async": "agentdecompile_cli.executor",
    "show_connection_error": "agentdecompile_cli.executor",
}


def __getattr__(name: str):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


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
