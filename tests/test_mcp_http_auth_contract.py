"""MCP HTTP auth contract for agentdecompile-server / agentdecompile-proxy.

Unit level only: ``resolve_auth_config`` (the startup decision shared by both
entry points) and ``AuthMiddleware`` driven with a hand-built ASGI scope.
Nothing binds a port.
"""

from __future__ import annotations

import asyncio
import base64

from typing import Any

import pytest

from agentdecompile_cli.mcp_server.auth import (
    AuthConfig,
    AuthConfigError,
    AuthMiddleware,
    auth_env_enabled,
    resolve_auth_config,
)

ENV_ON = {"AGENT_DECOMPILE_AUTH_ENABLED": "1"}
CREDS = {
    "AGENT_DECOMPILE_GHIDRA_SERVER_USERNAME": "alice",
    "AGENT_DECOMPILE_GHIDRA_SERVER_PASSWORD": "s3cret",
}


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def _call(config: AuthConfig, headers: dict[str, str] | None = None, path: str = "/mcp") -> int:
    """Run one HTTP request through AuthMiddleware; return the status (200 = reached inner app)."""
    reached: list[bool] = []

    async def inner(scope: dict[str, Any], receive: Any, send: Any) -> None:
        reached.append(True)

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "path": path,
        "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()],
    }
    asyncio.run(AuthMiddleware(inner, config)(scope, receive, send))
    if reached:
        return 200
    return int(sent[0]["status"])


# ---------------------------------------------------------------------------
# When is auth on at all?
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_env_truthy_values_enable(value: str) -> None:
    assert auth_env_enabled({"AGENT_DECOMPILE_AUTH_ENABLED": value})


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "enabled"])
def test_env_other_values_do_not_enable(value: str) -> None:
    assert not auth_env_enabled({"AGENT_DECOMPILE_AUTH_ENABLED": value})


@pytest.mark.parametrize("flag", [None, False])
def test_off_without_flag_or_env(flag: bool | None) -> None:
    assert resolve_auth_config(is_http=True, require_auth_flag=flag, environ=dict(CREDS)) is None


@pytest.mark.parametrize("flag", [None, True, False])
def test_stdio_never_gets_auth(flag: bool | None) -> None:
    env = {**ENV_ON, **CREDS}
    assert resolve_auth_config(is_http=False, require_auth_flag=flag, environ=env) is None


def test_no_require_auth_cannot_switch_off_the_env_var() -> None:
    # Fail-closed by design: an explicit off flag resolves the same as omitting it.
    config = resolve_auth_config(is_http=True, require_auth_flag=False, environ={**ENV_ON, **CREDS})
    assert config is not None
    assert _call(config) == 401
    assert _call(config, {"Authorization": _basic("alice", "s3cret")}) == 200


# ---------------------------------------------------------------------------
# Credentials and precedence
# ---------------------------------------------------------------------------


def test_env_with_credentials_enforces_on_every_request() -> None:
    config = resolve_auth_config(is_http=True, require_auth_flag=None, environ={**ENV_ON, **CREDS})
    assert config is not None
    assert _call(config) == 401
    assert _call(config, {"Authorization": _basic("alice", "wrong")}) == 401
    assert _call(config, {"Authorization": _basic("alice", "s3cret")}) == 200
    assert _call(config, {"X-Agent-Server-Username": "alice", "X-Agent-Server-Password": "s3cret"}) == 200


def test_health_is_always_exempt() -> None:
    config = resolve_auth_config(is_http=True, require_auth_flag=True, environ=dict(CREDS))
    assert config is not None
    assert _call(config, path="/health") == 200


def test_env_credentials_win_over_cli_values() -> None:
    config = resolve_auth_config(
        is_http=True,
        require_auth_flag=True,
        environ=dict(CREDS),
        cli_username="bob",
        cli_password="other",
        cli_port=9999,
    )
    assert config is not None
    assert (config.default_username, config.default_password) == ("alice", "s3cret")
    assert config.default_server_port == 9999


def test_cli_credentials_used_when_env_has_none() -> None:
    config = resolve_auth_config(
        is_http=True,
        require_auth_flag=True,
        environ={},
        cli_host="ghidra.local",
        cli_username="bob",
        cli_password="pw",
        cli_repository="repo",
    )
    assert config is not None
    assert (config.default_server_host, config.default_username, config.default_password, config.default_repository) == (
        "ghidra.local",
        "bob",
        "pw",
        "repo",
    )
    assert config.default_server_port == 13100


# ---------------------------------------------------------------------------
# Auth switched on with nothing to check against: refuse, never pass through
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "env"),
    [
        (None, ENV_ON),  # the reported case: AGENT_DECOMPILE_AUTH_ENABLED=1 alone
        (False, ENV_ON),  # --no-require-auth does not turn the env var off
        (True, {}),  # --require-auth alone
    ],
)
def test_auth_on_without_credentials_refuses_to_start(flag: bool | None, env: dict[str, str]) -> None:
    with pytest.raises(AuthConfigError) as excinfo:
        resolve_auth_config(is_http=True, require_auth_flag=flag, environ=dict(env))
    message = str(excinfo.value)
    assert "AGENT_DECOMPILE_GHIDRA_SERVER_USERNAME" in message
    assert "AGENT_DECOMPILE_GHIDRA_SERVER_PASSWORD" in message


@pytest.mark.parametrize(
    "partial",
    [
        {"AGENT_DECOMPILE_GHIDRA_SERVER_USERNAME": "alice"},
        {"AGENT_DECOMPILE_GHIDRA_SERVER_PASSWORD": "s3cret"},
    ],
)
def test_auth_on_with_half_the_credentials_refuses_to_start(partial: dict[str, str]) -> None:
    # A username with an empty password would let anyone who knows the name in.
    with pytest.raises(AuthConfigError):
        resolve_auth_config(is_http=True, require_auth_flag=None, environ={**ENV_ON, **partial})


def test_stdio_with_env_on_and_no_credentials_still_starts() -> None:
    assert resolve_auth_config(is_http=False, require_auth_flag=None, environ=dict(ENV_ON)) is None


@pytest.mark.parametrize("require_auth", [False, True])
def test_installed_middleware_without_credentials_rejects_everything(require_auth: bool) -> None:
    # Defence in depth for code that builds AuthConfig directly: installing the
    # middleware means auth is on, so an empty config must not pass requests.
    config = AuthConfig(require_auth=require_auth)
    assert _call(config) == 401
    assert _call(config, {"Authorization": _basic("anyone", "anything")}) == 401
    # 24ae019c ("disable dynamic Ghidra-host routing") made AuthMiddleware
    # check X-Ghidra-Server-Host before credentials: naming any host while
    # none is configured gets 403 "dynamic Ghidra-host routing is disabled",
    # not 401, even with credentials attached.
    assert _call(config, {"X-Ghidra-Server-Host": "elsewhere", "Authorization": _basic("anyone", "x")}) == 403
