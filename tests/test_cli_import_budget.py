"""Guard CLI startup cost: importing the CLI must not load server-side stacks.

``agentdecompile-cli --help`` and plain HTTP client calls used to spend ~1 s
importing the MCP server SDK, FastAPI/FastMCP and ghidrecomp/pyghidra. Those
modules load lazily now; this test fails if a top-level import brings them back.
It asserts on the imported module list, not on wall-clock time.
"""

from __future__ import annotations

import os
import subprocess
import sys

FORBIDDEN_PREFIXES = ("fastapi", "mcp.server.fastmcp", "ghidrecomp", "pyghidra")


def _imported_modules(code: str) -> set[str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    modules: set[str] = set()
    for line in proc.stderr.splitlines():
        if line.startswith("import time:") and line.count("|") >= 2:
            name = line.rsplit("|", 1)[1].strip()
            if name and name != "imported package":
                modules.add(name)
    return modules


def _offenders(modules: set[str]) -> list[str]:
    return sorted(m for m in modules if any(m == p or m.startswith(p + ".") for p in FORBIDDEN_PREFIXES))


def test_cli_import_does_not_load_server_stacks() -> None:
    modules = _imported_modules("import agentdecompile_cli.cli")
    assert "agentdecompile_cli.cli" in modules
    assert _offenders(modules) == []


def test_cli_import_does_not_load_mcp_sdk() -> None:
    modules = _imported_modules("import agentdecompile_cli.cli")
    assert "mcp" not in modules
    assert "agentdecompile_cli.bridge" not in modules


def test_lazy_package_reexports_still_resolve() -> None:
    from agentdecompile_cli import AgentDecompileMcpClient, ClientError, Tool, run_async  # noqa: F401
    from agentdecompile_cli.bridge import ServerNotRunningError

    assert issubclass(ServerNotRunningError, ClientError)
