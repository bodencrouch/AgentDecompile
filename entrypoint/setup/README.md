# Setup scripts

Two scripts, both safe to run at any time. Neither starts, stops or restarts a process.

## `setup_agent.py`

Proposes client configuration and writes it only with `--apply`.

```bash
python3 entrypoint/setup/setup_agent.py --agent <client> --project <workspace> [--apply]
```

| `--agent` | MCP config written | Instruction file |
|---|---|---|
| `claude-code` | `<workspace>/.mcp.json` (`mcpServers`, `type: http`) | `CLAUDE.md` |
| `codex` | `<workspace>/.codex/config.toml` (`[mcp_servers.agentdecompile]`) | `AGENTS.md` |
| `cursor` | `<workspace>/.cursor/mcp.json` | `.cursor/rules/agentdecompile.mdc` (always applied) |
| `gemini` | `<workspace>/.gemini/settings.json` (`httpUrl`) | `GEMINI.md` |
| `vscode` | `<workspace>/.vscode/mcp.json` (`servers`) | `.github/copilot-instructions.md` |
| `windsurf` | `~/.codeium/windsurf/mcp_config.json` (`serverUrl`) | `<workspace>/.windsurfrules` |
| `opencode` | `<workspace>/opencode.json` (`mcp`, `type: remote`) | `AGENTS.md` |
| `generic` | printed to stdout | printed to stdout |

Options:

- `--server-url` overrides the endpoint (default `$AGENT_DECOMPILE_MCP_SERVER_URL` or
  `http://127.0.0.1:8080/mcp`). It must be an existing listener.
- `--transport stdio` emits the documented compatibility entry
  `agentdecompile-proxy --transport stdio --backend-url <url>` with
  `AGENT_DECOMPILE_WEBUI_ENABLED=false`, for clients that cannot speak HTTP MCP.
- `--no-instructions` skips the instruction block.
- `--json` prints the plan instead of a diff.

The instruction block is fenced by `<!-- agentdecompile-entrypoint:start -->` and
`<!-- agentdecompile-entrypoint:end -->` and is replaced in place on re-runs. When the
workspace is this repository the block is skipped because `AGENTS.md` already governs it.
Every rewritten file is copied to `<file>.bak.<UTC timestamp>` first.

## `doctor.py`

Read-only probe over [../stack.json](../stack.json).

```bash
python3 entrypoint/setup/doctor.py [--json] [--family core|addition|...] [--no-server] [--server-url URL]
```

For each tool it reports `ok` (present), `--` (missing), `??` (missing and the repository
could not be confirmed by the author, locate before installing) or blank (no probe). It
then lists the evidence tiers reachable on this machine and which of the five gaps have at
least one present engine. The only network call is `GET <server>/health`; disable it with
`--no-server`. An unreachable server is reported as a blocker to diagnose, never a reason
to start another one.

Missing tools lower the claim tier an agent may reach. They do not block triage.
