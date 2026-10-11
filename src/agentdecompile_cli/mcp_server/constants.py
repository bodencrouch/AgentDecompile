"""Constants used across MCP server tool providers.

This module contains shared constants to avoid circular import issues.
"""

# Default timeout for decompilation operations (seconds).
# Large native functions can take substantially longer than ordinary functions
# to simplify; keep the default useful for those callers while retaining the
# per-request ``timeout`` override for tighter or longer budgets.
DEFAULT_TIMEOUT_SECONDS = 300
