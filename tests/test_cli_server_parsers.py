"""Parser-level tests for agentdecompile-server, agentdecompile-proxy and mcp-agentdecompile.

Only the extracted builder functions are called. No server main() runs and
nothing binds a port.
"""

from __future__ import annotations

import argparse

from pathlib import Path

import pytest

from agentdecompile_cli.__main__ import _setup_main_argument_parser
from agentdecompile_cli.server import build_proxy_parser, build_server_parser

TRANSPORTS = ["stdio", "streamable-http", "sse", "http"]


def _action(parser: argparse.ArgumentParser, option: str) -> argparse.Action:
    for action in parser._actions:
        if option in action.option_strings:
            return action
    raise AssertionError(f"{option} not defined")


# ---------------------------------------------------------------------------
# agentdecompile-server
# ---------------------------------------------------------------------------


def test_server_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_DECOMPILE_PROJECT_NAME", raising=False)
    args = build_server_parser().parse_args([])
    assert args.transport == "stdio"
    assert args.port is None and args.host is None
    assert args.require_auth is None
    assert args.tls_certfile is None and args.tls_keyfile is None
    assert args.project_path == Path("agentdecompile_projects")
    assert args.project_name == "my_project"
    assert args.threaded is True
    assert args.max_workers == 0
    assert args.wait_for_analysis is False
    assert args.force_analysis is False
    assert args.verbose_analysis is False
    assert args.no_symbols is False
    assert args.gdt == []
    assert args.input_paths == []
    assert args.config is None


def test_server_transport_choices() -> None:
    assert _action(build_server_parser(), "--transport").choices == TRANSPORTS


def test_server_project_name_reads_env_at_build_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DECOMPILE_PROJECT_NAME", "from_env")
    assert build_server_parser().parse_args([]).project_name == "from_env"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], None),
        (["--require-auth"], True),
        (["--no-require-auth"], False),
        (["--require-auth", "--no-require-auth"], False),
        (["--no-require-auth", "--require-auth"], True),
    ],
)
@pytest.mark.parametrize("builder", [build_server_parser, build_proxy_parser])
def test_require_auth_tristate(builder, argv: list[str], expected: bool | None) -> None:
    assert builder().parse_args(argv).require_auth is expected


def test_server_port_aliases() -> None:
    parser = build_server_parser()
    assert parser.parse_args(["--mcp-server-port", "9001"]).port == 9001
    assert parser.parse_args(["-p", "9002"]).port == 9002


# ---------------------------------------------------------------------------
# agentdecompile-proxy
# ---------------------------------------------------------------------------


def test_proxy_defaults() -> None:
    args = build_proxy_parser().parse_args([])
    assert args.transport == "stdio"
    assert args.backend_url is None and args.mcp_server_url is None
    assert args.port is None and args.host is None
    assert args.require_auth is None
    assert args.enable_exchange is None


def test_proxy_transport_choices() -> None:
    assert _action(build_proxy_parser(), "--transport").choices == TRANSPORTS


def test_proxy_backend_url_alias() -> None:
    assert build_proxy_parser().parse_args(["--server-url", "http://h:1"]).backend_url == "http://h:1"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [([], None), (["--enable-exchange"], True), (["--no-enable-exchange"], False)],
)
def test_proxy_exchange_tristate(argv: list[str], expected: bool | None) -> None:
    assert build_proxy_parser().parse_args(argv).enable_exchange is expected


# ---------------------------------------------------------------------------
# mcp-agentdecompile
# ---------------------------------------------------------------------------


def test_mcp_defaults() -> None:
    args = _setup_main_argument_parser().parse_args([])
    assert args.config is None
    assert args.server_url is None
    assert args.host is None and args.port is None
    assert args.output_format == "text"
    assert args.verbose is False


def test_mcp_format_choices() -> None:
    assert _action(_setup_main_argument_parser(), "--format").choices == ["json", "table", "text"]


def test_mcp_server_url_alias() -> None:
    assert _setup_main_argument_parser().parse_args(["--mcp-server-url", "http://h:1"]).server_url == "http://h:1"
