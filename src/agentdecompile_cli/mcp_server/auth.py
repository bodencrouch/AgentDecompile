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

Dynamic server routing:
  Clients may send X-Ghidra-Server-Host / X-Ghidra-Server-Port / X-Ghidra-Repository
  headers to target a Ghidra server that differs from the one configured at startup.
  For the configured server, credentials are validated locally (constant-time compare).
  For an unknown/different server, any non-empty credentials are accepted and actual
  Ghidra authentication is delegated to connect-shared-project at call time.
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
    * **Different Ghidra server** (target_host present but differs from config):
      Accept any non-empty username+password.  The Ghidra server itself will
      validate them when connect-shared-project is called; requiring *something*
      here ensures the MCP endpoint is not anonymously accessible even when
      dynamic routing is used.
    * **No server configured and no target_host**: auth should not be required
      in this case; callers should not invoke this function.
    """
    logger.debug("diag.enter %s", "mcp_server/auth.py:validate_credentials")
    if not username:
        return False
    if not config.default_username or not config.default_password:
        # Nothing configured to check against: fail closed, including for
        # dynamic routing to another Ghidra host.
        return False

    using_default_server = not target_host or not config.default_server_host or target_host.lower() == config.default_server_host.lower()

    if using_default_server:
        expected_user = config.default_username or ""
        expected_pass = config.default_password or ""
        return _constant_time_eq(username, expected_user) and _constant_time_eq(
            password,
            expected_pass,
        )

    # Dynamic routing to a different Ghidra server: accept any non-empty credentials.
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

    def _auth_required(self, target_host: str) -> bool:
        # The middleware is only installed when auth is switched on, so every
        # request needs credentials. An earlier version let requests through
        # when no username was configured, which made
        # AGENT_DECOMPILE_AUTH_ENABLED=1 on its own a no-op.
        logger.debug("diag.enter %s", "mcp_server/auth.py:AuthMiddleware._auth_required")
        return True

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

        if not self._auth_required(target_host):
            await self._inner_app(scope, receive, send)
            return

        # Auth required — try Authorization: Basic first, fall back to
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
    """MCP HTTP auth is switched on but cannot check anyone (no credentials configured)."""

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
    config = AuthConfig(
        require_auth=bool(require_auth_flag),
        default_server_host=_first_env(environ, "AGENT_DECOMPILE_GHIDRA_SERVER_HOST", "AGENT_DECOMPILE_SERVER_HOST") or cli_host,
        default_server_port=int(_first_env(environ, "AGENT_DECOMPILE_GHIDRA_SERVER_PORT", "AGENT_DECOMPILE_SERVER_PORT") or cli_port or 13100),
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
