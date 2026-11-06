"""Constants used across MCP server tool providers.

This module contains shared constants to avoid circular import issues.
"""

import os


# Large native functions can take many minutes to simplify. Keep a generous
# default while allowing deployments to tune the bound without editing source.
_BASE_DEFAULT_TIMEOUT_SECONDS = 1800
MAX_CONFIGURED_TIMEOUT_SECONDS = 86400


def _configured_decompile_timeout_seconds() -> int:
    raw = os.environ.get("AGENTDECOMPILE_DECOMPILE_TIMEOUT_SECONDS")
    if raw is None:
        return _BASE_DEFAULT_TIMEOUT_SECONDS
    try:
        configured = int(raw)
    except (TypeError, ValueError):
        return _BASE_DEFAULT_TIMEOUT_SECONDS
    if 1 <= configured <= MAX_CONFIGURED_TIMEOUT_SECONDS:
        return configured
    return _BASE_DEFAULT_TIMEOUT_SECONDS


DEFAULT_TIMEOUT_SECONDS = _configured_decompile_timeout_seconds()
