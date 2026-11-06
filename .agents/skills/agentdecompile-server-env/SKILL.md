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

Read [AGENTS](../../../AGENTS.md) for current operations,
[USAGE](../../../USAGE.md) for environment/session reference and
[MCP security](../../../docs/MCP_CONFIGURATION_SECURITY.md) for authentication.

Attach to the existing `http://127.0.0.1:8080/mcp`. The project plugin uses native
HTTP configuration and starts no proxy, JVM or dashboard. If a client requires
stdio, the existing `agentdecompile-proxy --transport stdio --backend-url
http://127.0.0.1:8080/mcp` with `AGENT_DECOMPILE_WEBUI_ENABLED=false` is the
compatibility option. Source: `src/agentdecompile_cli/server.py:proxy_main` and
`src/agentdecompile_cli/webui.py:launch_webui_sidecar`. Inspection is not a
successful client-connection claim.

Do not start another server, switch ports, clear sessions or restart services
during the current recovery mission. Diagnose an unavailable backend and report
the owner/blocker. No systemctl. Ghidra Server uses RMI/SSL; its credentials and
headers do not authenticate the MCP listener. Session IDs are not authentication.

Global Codex MCP defaults are Hugging Face and Zapier; this project plugin does
not change them. Local JVM setup requires the real Ghidra installation and Java
as documented in USAGE, but those generic startup recipes are reference-only here.
