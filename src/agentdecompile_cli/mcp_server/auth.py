"""HTTP Basic Auth middleware for AgentDecompile MCP server.

.. warning:: **EXPERIMENTAL** — This auth module is experimental and its API
   may change in future releases.  Auth is disabled by default; set the
   environment variable ``AGENT_DECOMPILE_AUTH_ENABLED=true`` (or pass
   ``--require-auth``) to enable it.

This module provides:
- AuthConfig: server-level auth requirements and default Ghidra credentials
- AuthContext: per-request authenticated credential/server state
- CURRENT_AUTH_CONTEXT: async context variable propagating auth state to tool handlers
- get_current_auth_context(): helper for tool providers to read current auth state
- AuthMiddleware: ASGI middleware that enforces Basic auth before MCP session handling

Auth is all-or-nothing:
- Off (the default): no middleware is installed and requests are anonymous.
- On (``--require-auth`` or ``AGENT_DECOMPILE_AUTH_ENABLED``, HTTP transports
  only): every request needs credentials. The configured Ghidra username and
  password are the MCP credentials; startup fails when either is missing.

The /health endpoint is a FastAPI route mounted separately and is always exempt.

Dynamic Ghidra-host routing (disabled):
  With auth on, a request whose X-Ghidra-Server-Host names a host other than the
  configured one gets HTTP 403 "dynamic Ghidra-host routing is disabled". So does a
  request that names any host when no host is configured. Requests that name the
  configured host (case-insensitive) or no host are checked against the configured
  username and password as before. The old routing code stays in place behind
  DYNAMIC_GHIDRA_HOST_ROUTING_ENABLED for a future implementation.
"""

from __future__ import annotations

import base64
import hmac
import logging

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Dynamic Ghidra-host routing: disabled by user decision 2026-09-27.
# While False, AuthMiddleware answers 403 to a request whose X-Ghidra-Server-Host
# names a host other than the configured one, and validate_credentials rejects it.
# Re-enabling requires a real login check against the target host (not implemented):
# the old path accepted any non-empty username with any password and forwarded them.
# Deliberately a code constant with no env var or CLI flag, so it cannot be turned
# on by accident.
DYNAMIC_GHIDRA_HOST_ROUTING_ENABLED = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AuthConfig:
    """Server-level authentication configuration (created from CLI args)."""

    require_auth: bool = False
    """Explicitly require auth on every MCP request (regardless of other config)."""

    default_server_host: str | None = None
    """Ghidra server host from --server-host (used for credential validation)."""

    default_server_port: int = 13100
    """Ghidra server port from --ghidra-server-port."""

    default_username: str | None = None
    """Username that clients must supply when targeting the default server."""

    default_password: str | None = None
    """Password that clients must supply when targeting the default server."""

    default_repository: str | None = None
    """Repository from --ghidra-server-repository (injected as default path)."""


@dataclass
class AuthContext:
    """Per-request auth state set by AuthMiddleware and consumed by tool providers."""

    username: str
    password: str
    server_host: str | None = None
    server_port: int = 13100
    repository: str | None = None


# ---------------------------------------------------------------------------
# Context variable
# ---------------------------------------------------------------------------

CURRENT_AUTH_CONTEXT: ContextVar[AuthContext | None] = ContextVar(
    "current_auth_context",
    default=None,
)


def get_current_auth_context() -> AuthContext | None:
    """Return the AuthContext for the current request, or None (anonymous)."""
    logger.debug("diag.enter %s", "mcp_server/auth.py:get_current_auth_context")
    return CURRENT_AUTH_CONTEXT.get()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_basic_auth(authorization_header: str) -> tuple[str, str]:
    """Parse ``Authorization: Basic <base64>`` → ``(username, password)``.

    Raises ValueError for malformed input.
    """
    logger.debug("diag.enter %s", "mcp_server/auth.py:parse_basic_auth")
    stripped = authorization_header.strip()
    if not stripped.lower().startswith("basic "):
        raise ValueError("Not a Basic auth header")
    encoded = stripped[6:]  # len("basic ") == 6
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Invalid base64 in Authorization header: {exc}") from exc
    # Split on the *first* colon — passwords may contain colons
    if ":" not in decoded:
        raise ValueError("Basic auth credentials must contain ':'")
    username, password = decoded.split(":", 1)
    return username, password


# ---------------------------------------------------------------------------
# Credential validation
# ---------------------------------------------------------------------------


def _constant_time_eq(a: str, b: str) -> bool:
    """Constant-time string comparison to resist timing attacks."""
    logger.debug("diag.enter %s", "mcp_server/auth.py:_constant_time_eq")
    return hmac.compare_digest(a.encode(), b.encode())


def names_other_ghidra_host(target_host: str | None, config: AuthConfig) -> bool:
    """Return True when the request names a Ghidra host other than the configured one.

    Naming a host while none is configured also counts: honouring it would switch
    the backend Ghidra host from the header.
    """
    if not target_host:
        return False
    if not config.default_server_host:
        return True
    return target_host.lower() != config.default_server_host.lower()


def validate_credentials(
    username: str,
    password: str,
    config: AuthConfig,
    target_host: str | None,
) -> bool:
    """Return True when the provided credentials are acceptable.

    Validation rules
    ----------------
    * **Matching/default server** (target_host == config.default_server_host or absent):
      Compare username and password against the configured defaults using a
      constant-time comparison to prevent timing-based enumeration.
    * **Different Ghidra server** (target_host present and differs from the
      configured host, or present with no configured host): rejected, because
      dynamic Ghidra-host routing is disabled (DYNAMIC_GHIDRA_HOST_ROUTING_ENABLED).
      AuthMiddleware answers these requests with 403 before calling this.
      The branch kept for a future implementation accepted any non-empty
      username with any password and forwarded them unchecked.
    * **No configured username/password pair**: reject everything.
    """
    logger.debug("diag.enter %s", "mcp_server/auth.py:validate_credentials")
    if not username:
        return False
    if not config.default_username or not config.default_password:
        # Reject when no configured pair exists.
        return False

    if not DYNAMIC_GHIDRA_HOST_ROUTING_ENABLED and names_other_ghidra_host(target_host, config):
        # Dynamic Ghidra-host routing is disabled (user decision 2026-09-27).
        return False

    using_default_server = not target_host or not config.default_server_host or target_host.lower() == config.default_server_host.lower()

    if using_default_server:
        expected_user = config.default_username or ""
        expected_pass = config.default_password or ""
        return _constant_time_eq(username, expected_user) and _constant_time_eq(
            password,
            expected_pass,
        )

    # Kept for a future implementation and unreachable while DYNAMIC_GHIDRA_HOST_ROUTING_ENABLED
    # is False. It accepts any non-empty username and any password (even "") and must not be
    # re-enabled without a real login check against the target host.
    return bool(username) and password is not None


# ---------------------------------------------------------------------------
# 401 response helper
# ---------------------------------------------------------------------------

_401_HEADERS: list[tuple[bytes, bytes]] = [
    (b"content-type", b"text/plain; charset=utf-8"),
    (b"www-authenticate", b'Basic realm="AgentDecompile"'),
    (b"content-length", b"12"),
]
_401_BODY: bytes = b"Unauthorized"


async def _send_401(send: Any) -> None:
    """Emit a minimal HTTP 401 Unauthorized ASGI response."""
    logger.debug("diag.enter %s", "mcp_server/auth.py:_send_401")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": _401_HEADERS,
        },
    )
    await send(
        {
            "type": "http.response.body",
            "body": _401_BODY,
            "more_body": False,
        },
    )


_403_ROUTING_BODY: bytes = (
    b"Forbidden: dynamic Ghidra-host routing is disabled. "
    b"Omit X-Ghidra-Server-Host or send the host this server is configured for."
)
_403_ROUTING_HEADERS: list[tuple[bytes, bytes]] = [
    (b"content-type", b"text/plain; charset=utf-8"),
    (b"content-length", str(len(_403_ROUTING_BODY)).encode("ascii")),
]


async def _send_403_routing_disabled(send: Any) -> None:
    """Emit HTTP 403 for a request that names a Ghidra host other than the configured one."""
    logger.debug("diag.enter %s", "mcp_server/auth.py:_send_403_routing_disabled")
    await send({"type": "http.response.start", "status": 403, "headers": _403_ROUTING_HEADERS})
    await send({"type": "http.response.body", "body": _403_ROUTING_BODY, "more_body": False})


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------


class AuthMiddleware:
    """ASGI middleware enforcing HTTP Basic Auth on MCP requests.

    .. warning:: **EXPERIMENTAL** — Disabled by default.  Enable via
       ``AGENT_DECOMPILE_AUTH_ENABLED=true`` or ``--require-auth``.

    Middleware chain (innermost last):
        AuthMiddleware → _SessionContextASGI → StreamableHTTPSessionManager

    The ``/health`` FastAPI route is mounted separately and never reaches this
    middleware.

    Once installed, every request except ``/health`` needs credentials. The
    server and proxy only install it when auth is on, and refuse to start
    when no username/password is configured (see :func:`resolve_auth_config`).
    """

    def __init__(self, inner_app: Any, auth_config: AuthConfig) -> None:
        logger.debug("diag.enter %s", "mcp_server/auth.py:AuthMiddleware.__init__")
        self._inner_app = inner_app
        self._config = auth_config

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        # Non-HTTP scopes (lifespan, websocket) pass straight through
        logger.debug("diag.enter %s", "mcp_server/auth.py:AuthMiddleware.__call__")
        if scope.get("type") != "http":
            await self._inner_app(scope, receive, send)
            return

        path = (scope.get("path") or "").rstrip("/") or "/"
        if path == "/health":
            await self._inner_app(scope, receive, send)
            return

        # Decode relevant request headers
        auth_header = ""
        target_host = ""
        target_port_str = ""
        target_repo = ""
        agent_username = ""
        agent_password = ""
        agent_repo = ""
        key_b: bytes
        value_b: bytes
        for key_b, value_b in scope.get("headers", []):
            key = key_b.decode("latin1").lower()
            val = value_b.decode("latin1").strip()
            if key == "authorization":
                auth_header = val
            elif key == "x-ghidra-server-host":
                target_host = val
            elif key == "x-ghidra-server-port":
                target_port_str = val
            elif key == "x-ghidra-repository":
                target_repo = val
            elif key == "x-agent-server-username":
                agent_username = val
            elif key == "x-agent-server-password":
                agent_password = val
            elif key == "x-agent-server-repository":
                agent_repo = val

        # Use X-Agent-Server-Repository as fallback for X-Ghidra-Repository
        if not target_repo and agent_repo:
            target_repo = agent_repo

        if not DYNAMIC_GHIDRA_HOST_ROUTING_ENABLED and names_other_ghidra_host(target_host, self._config):
            logger.warning("mcp_auth_rejected reason=dynamic_host_routing_disabled")
            await _send_403_routing_disabled(send)
            return

        # The middleware is only installed when auth is switched on, so every
        # request needs credentials. An earlier version let requests through
        # when no username was configured, which made
        # AGENT_DECOMPILE_AUTH_ENABLED=1 on its own a no-op.
        # Try Authorization: Basic first, fall back to
        # X-Agent-Server-Username / X-Agent-Server-Password headers.
        username: str = ""
        password: str = ""
        if auth_header.lower().startswith("basic "):
            try:
                username, password = parse_basic_auth(auth_header)
            except ValueError:
                logger.warning("mcp_auth_rejected reason=malformed_basic")
        if not username and agent_username:
            username = agent_username
            password = agent_password

        if not username:
            logger.warning("mcp_auth_rejected reason=no_credentials")
            await _send_401(send)
            return

        if not validate_credentials(username, password, self._config, target_host):
            logger.warning(
                "mcp_auth_rejected reason=invalid_credentials username_len=%s dynamic_target_host=%s",
                len(username),
                bool(target_host),
            )
            await _send_401(send)
            return

        # Build per-request AuthContext and propagate via ContextVar
        try:
            port = int(target_port_str)
        except (ValueError, TypeError):
            port = self._config.default_server_port

        auth_ctx = AuthContext(
            username=username,
            password=password,
            server_host=target_host or self._config.default_server_host,
            server_port=port,
            repository=target_repo or self._config.default_repository,
        )
        token = CURRENT_AUTH_CONTEXT.set(auth_ctx)
        try:
            await self._inner_app(scope, receive, send)
        finally:
            CURRENT_AUTH_CONTEXT.reset(token)


# ---------------------------------------------------------------------------
# Startup resolution (shared by agentdecompile-server and agentdecompile-proxy)
# ---------------------------------------------------------------------------

AUTH_ENABLED_ENV = "AGENT_DECOMPILE_AUTH_ENABLED"


class AuthConfigError(ValueError):
    """MCP HTTP auth configuration is invalid."""


_TRUTHY = frozenset({"true", "1", "yes", "on"})


def auth_env_enabled(environ: Mapping[str, str]) -> bool:
    """Return True when ``AGENT_DECOMPILE_AUTH_ENABLED`` is set to a truthy value."""
    return (environ.get(AUTH_ENABLED_ENV) or "").strip().lower() in _TRUTHY


def _first_env(environ: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = environ.get(key)
        if value:
            return value
    return None


def resolve_auth_config(
    *,
    is_http: bool,
    require_auth_flag: bool | None,
    environ: Mapping[str, str],
    cli_host: str | None = None,
    cli_port: int | None = None,
    cli_username: str | None = None,
    cli_password: str | None = None,
    cli_repository: str | None = None,
) -> AuthConfig | None:
    """Build the MCP HTTP auth config for a server/proxy start, or None when auth is off.

    Auth is on when the transport is HTTP and either ``--require-auth`` was
    passed or ``AGENT_DECOMPILE_AUTH_ENABLED`` is truthy. ``--no-require-auth``
    cannot switch off the env var: it resolves the same as omitting the flag.
    stdio never gets auth (the internal HTTP server only serves the in-process
    bridge). Environment credentials win over the ``cli_*`` values.

    Fails closed: when auth is on but the username or password is missing,
    raise :class:`AuthConfigError` instead of starting a listener that either
    lets everyone in or can never let anyone in.
    """
    if not is_http or not (require_auth_flag or auth_env_enabled(environ)):
        return None
    port_value = (
        _first_env(environ, "AGENT_DECOMPILE_GHIDRA_SERVER_PORT", "AGENT_DECOMPILE_SERVER_PORT")
        or cli_port
        or 13100
    )
    try:
        default_server_port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise AuthConfigError("Ghidra server port must be an integer") from exc

    config = AuthConfig(
        require_auth=True,
        default_server_host=_first_env(environ, "AGENT_DECOMPILE_GHIDRA_SERVER_HOST", "AGENT_DECOMPILE_SERVER_HOST") or cli_host,
        default_server_port=default_server_port,
        default_username=_first_env(environ, "AGENT_DECOMPILE_GHIDRA_SERVER_USERNAME", "AGENT_DECOMPILE_SERVER_USERNAME") or cli_username,
        default_password=_first_env(environ, "AGENT_DECOMPILE_GHIDRA_SERVER_PASSWORD", "AGENT_DECOMPILE_SERVER_PASSWORD") or cli_password,
        default_repository=_first_env(
            environ,
            "AGENT_DECOMPILE_GHIDRA_SERVER_REPOSITORY",
            "AGENTDECOMPILE_GHIDRA_SERVER_REPOSITORY",
            "AGENT_DECOMPILE_REPOSITORY",
        )
        or cli_repository,
    )
    missing = [
        name
        for name, value in (
            ("AGENT_DECOMPILE_GHIDRA_SERVER_USERNAME", config.default_username),
            ("AGENT_DECOMPILE_GHIDRA_SERVER_PASSWORD", config.default_password),
        )
        if not value
    ]
    if missing:
        switch = "--require-auth" if require_auth_flag else AUTH_ENABLED_ENV
        raise AuthConfigError(
            f"MCP HTTP auth is on ({switch}) but {' and '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not set, so no request could be checked. "
            "Set AGENT_DECOMPILE_GHIDRA_SERVER_USERNAME and AGENT_DECOMPILE_GHIDRA_SERVER_PASSWORD "
            "(or --ghidra-server-username / --ghidra-server-password); clients send the same pair "
            "as HTTP Basic auth. To run without auth, unset AGENT_DECOMPILE_AUTH_ENABLED and drop --require-auth.",
        )
    return config
