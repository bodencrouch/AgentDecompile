---
name: mcp-debugging
description: "Use this skill when MCP calls time out, tools are missing, schemas mismatch, or the user mentions MCP Inspector, mcptools, mcp-debug, mcp-trace, FastMCP, sandbox, or GUI/coord failures."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
---

# MCP debugging

Read [AGENTS](../../../AGENTS.md), the current product contract
([USER_INTENT](../../../docs/USER_INTENT.md)), and the owning MCP/server docs.
Diagnose the existing 8080 backend without restarting it or switching ports.

Check the configured endpoint/transport, advertised tool schema, session ID,
selected project/binary, authentication boundary, and existing logs. Distinguish
a missing program binding from missing analysis. Corroborate process ownership
before proposing any operational change; a timeout alone does not establish death.
Never retry a mutation blindly after an uncertain response.

The project plugin connects directly to existing 8080 over native HTTP.
Global Codex MCP defaults remain Hugging Face and Zapier. Cursor-local servers
are not global defaults. Historical debug recipes under `references/` are
implementation references, not permission to start, reconnect, mutate or replace
the current recovery environment.
