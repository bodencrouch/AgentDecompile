---
name: agentdecompile-server-env
description: "Use this skill when starting the AgentDecompile MCP server, setting GHIDRA_INSTALL_DIR, auto-match, auto-checkin, analysis-tier, or debugging session-id or proxy forwarding, including on Cursor Cloud."
license: AGPL-3.0-or-later
compatibility: Requires GHIDRA_INSTALL_DIR, Python 3.10+, Java 21, and uv
metadata:
  author: AgentDecompile
  version: "1.0"
---

# AgentDecompile server environment

Start paths: `README.md`. Full env-var and HTTP-header catalog: `USAGE.md`. Bind and MCP HTTP auth: `docs/MCP_CONFIGURATION_SECURITY.md`. Session ids: `docs/session-handling.md`.

## First run

1. Set `GHIDRA_INSTALL_DIR` to the real Ghidra install folder name.
2. Stdio: `uv run mcp-agentdecompile`. HTTP: `uv run agentdecompile-server -t streamable-http` then `http://127.0.0.1:8080/mcp`.
3. Do not set `AGENT_DECOMPILE_HOST=0.0.0.0` without `AGENT_DECOMPILE_AUTH_ENABLED` plus firewall/TLS.
4. `AGENT_DECOMPILE_GHIDRA_SERVER_*` authenticates Ghidra Server, not the MCP listener.

## Session and proxy

Session IDs are not authentication. Send `mcp-session-id` on HTTP follow-ups. Use `tool-seq` when state must survive. Details: `docs/session-handling.md`.

## Analysis tier

`AGENT_DECOMPILE_TOOL_SURFACE` is `full`, `curated`, or `legacy`. See `USAGE.md` and `skills/tiered-re-analysis`.
