# MCP Configuration Security Guide

Current operations follow [AGENTS](../AGENTS.md): attach to existing 8080; do not
start another JVM/dashboard or alter global Codex MCP defaults (Hugging Face and
Zapier). The project plugin connects directly with `type: http` and
`url: http://127.0.0.1:8080/mcp`, spawning no process. Native HTTP plugin
configuration is supported by the [official plugin integration reference](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/mcp-integration/SKILL.md).
For stdio-only clients, the existing `agentdecompile-proxy` compatibility option
requires `AGENT_DECOMPILE_WEBUI_ENABLED=false` to suppress its web UI sidecar.
This is configuration/source inspection, not a live connection claim.

The remaining client-specific configuration examples are reference material.
Recovery actions still use the 8080 dashboard/catalog; MCP attachment is not a
direct recovery bypass. Confirm the client's input-substitution syntax; it is not
part of the MCP protocol itself.

## Bind and MCP HTTP auth

The MCP HTTP listener defaults to `127.0.0.1`. That is localhost only.

- Do not set `AGENT_DECOMPILE_HOST=0.0.0.0` unless `AGENT_DECOMPILE_AUTH_ENABLED` is on **and** you have a firewall (and TLS when the listener leaves the host).
- `AGENT_DECOMPILE_GHIDRA_SERVER_*` and `X-Agent-Server-*` authenticate **Ghidra Server**, not the MCP listener.
- Session IDs are not authentication. See [session-handling.md](./session-handling.md).

Full env-var catalog: [USAGE.md](../USAGE.md). Vulnerability reports: [SECURITY.md](../SECURITY.md).

## Overview

This guide explains how to configure the MCP (Model Context Protocol) client for AgentDecompile without hardcoding credentials or sensitive server details.

## Security Best Practices

**❌ NEVER hardcode credentials in your `mcp.json` configuration file**

Instead, use dynamic input prompts that request credentials at runtime.

## Configuration Approach

### Using Input Prompts (Recommended)

Clients that support dynamic input prompts can keep secrets out of configuration. This allows you to:
- Keep credentials out of configuration files
- Prompt users securely at connection time
- Mark password inputs as sensitive

### Example: Secure Configuration

See [`mcp.example.json`](./mcp.example.json) for one project-local connection to existing 8080. Add shared-server headers only when needed, using the client-specific examples below.

#### Key Features:

1. **Dynamic Inputs Definition**:
   ```json
   "inputs": [
     {
       "id": "ghidra-username",
       "type": "promptString",
       "description": "Ghidra shared server username"
     },
     {
       "id": "ghidra-password",
       "type": "promptString",
       "description": "Ghidra shared server password",
       "password": true
     }
   ]
   ```

2. **Input References in Server Config**:
   ```json
   "agdec-http-mcp-shared": {
     "type": "http",
     "url": "http://{input:ad-http-host}:{input:ad-http-port}",
     "headers": {
       "X-Agent-Server-Password": "{input:ghidra-password}",
       "X-Agent-Server-Username": "{input:ghidra-username}"
     }
   }
   ```

3. **Environment Variable Passthrough**:
   ```json
   "agdec-stdio-mcp-shared": {
     "type": "stdio",
     "env": {
       "AGENTDECOMPILE_GHIDRA_SERVER_HOST": "{input:ad-http-ghidra-server-host}",
       "AGENTDECOMPILE_GHIDRA_SERVER_PASSWORD": "{input:ghidra-password}",
       "AGENTDECOMPILE_GHIDRA_SERVER_USERNAME": "{input:ghidra-username}"
     }
   }
   ```

## Available Input Parameters

| Input ID | Description | Default | Required |
|----------|-------------|---------|----------|
| `ghidra-username` | Ghidra server username | - | Yes |
| `ghidra-password` | Ghidra server password | - | Yes |
| `ghidra-repository` | Repository name | `MyRepository` | No |
| `ad-http-host` | AgentDecompile HTTP host | `localhost` | No |
| `ad-http-port` | AgentDecompile HTTP port | `8080` | No |
| `ad-http-ghidra-server-host` | Ghidra server host | `localhost` | No |
| `ad-http-ghidra-server-port` | Ghidra server port | `13100` | No |

## Setup Instructions

### 1. Inspect the project-local example

The example contains one native HTTP connection. Shared-server authentication
can be added to that connection; do not configure duplicate server aliases. Do not copy it over global
configuration. Preserve the existing 8080 server and client settings.

### 2. Customize Defaults (Optional)

Edit the `inputs` section to set appropriate defaults for your environment:

```json
{
  "id": "ad-http-host",
  "type": "promptString",
  "description": "AgentDecompile HTTP server host",
  "default": "your-server.example.com"
}
```

### 3. Start MCP Client

The MCP client will prompt you for required inputs when connecting to AgentDecompile servers.

## Alternative: Environment Variables Only

If you prefer pure environment variable configuration without prompts, use the CLI directly:

```bash
export AGENT_DECOMPILE_GHIDRA_SERVER_HOST="your-host"
export AGENT_DECOMPILE_GHIDRA_SERVER_PORT="13100"
export AGENT_DECOMPILE_GHIDRA_SERVER_USERNAME="your-username"
export AGENT_DECOMPILE_GHIDRA_SERVER_PASSWORD="your-password"
export AGENT_DECOMPILE_GHIDRA_SERVER_REPOSITORY="your-repo"

AGENT_DECOMPILE_WEBUI_ENABLED=false agentdecompile-proxy --transport stdio --backend-url http://127.0.0.1:8080/mcp
```

See [USAGE.md](../USAGE.md) for complete CLI documentation.

## Migration from Hardcoded Credentials

If you have an existing `mcp.json` with hardcoded credentials:

1. **Backup your current config**:
   ```bash
   cp mcp.json mcp.json.backup
   ```

2. **Replace hardcoded values** with `{input:...}` references:
   - IP addresses → `{input:ad-http-host}` or `{input:ad-http-ghidra-server-host}`
   - Usernames → `{input:ghidra-username}`
   - Passwords → `{input:ghidra-password}`
   - Repository names → `{input:ghidra-repository}`
   - Port numbers → `{input:ad-http-port}` or `{input:ad-http-ghidra-server-port}`

3. **Add input definitions** to the `inputs` array (see example above)

4. **Test the configuration** by reconnecting your MCP client

## Security Checklist

- [ ] No hardcoded passwords in `mcp.json`
- [ ] No hardcoded usernames in `mcp.json`
- [ ] No hardcoded IP addresses or hostnames in `mcp.json` (unless public/localhost)
- [ ] Password inputs marked with `"password": true`
- [ ] Configuration file not committed to version control
- [ ] Default values are generic (localhost, MyRepository, etc.)

## Related Documentation

- [USAGE.md](../USAGE.md)
- [SECURITY.md](../SECURITY.md)
- [session-handling.md](./session-handling.md)
- [QUICKSTART_IMPORT_EXPORT.md](./QUICKSTART_IMPORT_EXPORT.md)
