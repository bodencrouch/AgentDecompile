#!/usr/bin/env python3
"""Propose and apply AI-agent client configuration for AgentDecompile.

The script does exactly two things, both reversible and both shown as a diff first:

1. Add an ``agentdecompile`` MCP server entry to the chosen client's config file,
   pointing at the EXISTING listener (default ``http://127.0.0.1:8080/mcp``).
2. Insert or replace one fenced instruction block in the client's instruction file that
   tells the agent to read ``entrypoint/AGENT_BOOTSTRAP.md`` before reversing.

It never starts a server, opens a port, restarts anything or edits files it did not
name. Nothing is written without ``--apply``; every file it rewrites is first copied to
``<file>.bak.<UTC timestamp>``.

Examples::

    python3 entrypoint/setup/setup_agent.py --agent claude-code --project ~/work
    python3 entrypoint/setup/setup_agent.py --agent cursor --project ~/work --apply
    python3 entrypoint/setup/setup_agent.py --agent generic
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ENTRYPOINT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = ENTRYPOINT_DIR.parent
BOOTSTRAP = ENTRYPOINT_DIR / "AGENT_BOOTSTRAP.md"
SERVER_NAME = "agentdecompile"
DEFAULT_URL = os.environ.get("AGENT_DECOMPILE_MCP_SERVER_URL") or os.environ.get(
    "AGENTDECOMPILE_MCP_SERVER_URL", "http://127.0.0.1:8080/mcp"
)
BLOCK_START = "<!-- agentdecompile-entrypoint:start -->"
BLOCK_END = "<!-- agentdecompile-entrypoint:end -->"

# Per-client layout. ``config`` is relative to the project unless ``home`` is true.
# ``shape`` names how the MCP entry is written; ``instructions`` is the instruction file.
CLIENTS: dict[str, dict[str, object]] = {
    "claude-code": {"config": ".mcp.json", "shape": "mcpServers-type-url", "instructions": "CLAUDE.md"},
    "codex": {"config": ".codex/config.toml", "shape": "toml", "instructions": "AGENTS.md"},
    "cursor": {"config": ".cursor/mcp.json", "shape": "mcpServers-url", "instructions": ".cursor/rules/agentdecompile.mdc"},
    "gemini": {"config": ".gemini/settings.json", "shape": "mcpServers-httpUrl", "instructions": "GEMINI.md"},
    "vscode": {"config": ".vscode/mcp.json", "shape": "servers-type-url", "instructions": ".github/copilot-instructions.md"},
    "windsurf": {"config": ".codeium/windsurf/mcp_config.json", "shape": "mcpServers-serverUrl", "instructions": ".windsurfrules", "home": True},
    "opencode": {"config": "opencode.json", "shape": "opencode", "instructions": "AGENTS.md"},
    "generic": {"config": None, "shape": "mcpServers-type-url", "instructions": None},
}


def _stdio_entry(url: str) -> dict[str, object]:
    # Documented compatibility route: the stdio proxy forwards to the existing backend.
    return {
        "command": "agentdecompile-proxy",
        "args": ["--transport", "stdio", "--backend-url", url],
        "env": {"AGENT_DECOMPILE_WEBUI_ENABLED": "false"},
    }


def mcp_entry(shape: str, url: str, transport: str) -> dict[str, object]:
    if transport == "stdio":
        return _stdio_entry(url)
    if shape in ("mcpServers-type-url", "servers-type-url"):
        return {"type": "http", "url": url}
    if shape == "mcpServers-url":
        return {"url": url}
    if shape == "mcpServers-httpUrl":
        return {"httpUrl": url}
    if shape == "mcpServers-serverUrl":
        return {"serverUrl": url}
    if shape == "opencode":
        return {"type": "remote", "url": url, "enabled": True}
    return {"type": "http", "url": url}


def _top_key(shape: str) -> str:
    if shape == "servers-type-url":
        return "servers"
    if shape == "opencode":
        return "mcp"
    return "mcpServers"


def _strip_json_comments(text: str) -> str:
    # Some clients tolerate comments and trailing commas; we only need to read.
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    return re.sub(r",(\s*[}\]])", r"\1", text)


def render_json_config(existing: str, shape: str, entry: dict[str, object]) -> str:
    data: dict[str, object] = {}
    if existing.strip():
        try:
            data = json.loads(_strip_json_comments(existing))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"cannot parse existing JSON config: {exc}") from exc
        if not isinstance(data, dict):
            raise SystemExit("existing config is not a JSON object")
    key = _top_key(shape)
    servers = data.get(key)
    if not isinstance(servers, dict):
        servers = {}
    servers[SERVER_NAME] = entry
    data[key] = servers
    if shape == "opencode" and "$schema" not in data:
        data = {"$schema": "https://opencode.ai/config.json", **data}
    return json.dumps(data, indent=2) + "\n"


def render_toml_config(existing: str, entry: dict[str, object], url: str, transport: str) -> str:
    header = f"[mcp_servers.{SERVER_NAME}]"
    if transport == "stdio":
        args = ", ".join(json.dumps(a) for a in entry["args"])  # type: ignore[index]
        block = (
            f"{header}\n"
            f'command = "{entry["command"]}"\n'
            f"args = [{args}]\n"
            f"env = {{ AGENT_DECOMPILE_WEBUI_ENABLED = \"false\" }}\n"
        )
    else:
        block = f'{header}\nurl = "{url}"\n'
    pattern = re.compile(rf"^\[mcp_servers\.{re.escape(SERVER_NAME)}\]\n(?:(?!\[).*\n?)*", re.MULTILINE)
    if pattern.search(existing):
        return pattern.sub(block, existing, count=1)
    sep = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + block


def instruction_block(client: str, bootstrap: Path) -> str:
    body = (
        f"{BLOCK_START}\n"
        "## AgentDecompile\n\n"
        f"Before any reverse-engineering, decompilation, binary matching or source-recovery work, read\n"
        f"`{bootstrap}` and follow it. Recovery runs through the existing AgentDecompile MCP server\n"
        f"(`{SERVER_NAME}`) and its 8080 action catalog; do not start servers, switch ports or re-run\n"
        "analysis that already exists. Report results in claim tiers (verified, readable/compiling,\n"
        "advisory, context hint, byte-authoritative, insufficient evidence) and never let a weaker\n"
        "claim read as a stronger one.\n"
        f"{BLOCK_END}\n"
    )
    if client == "cursor":
        return "---\ndescription: AgentDecompile entrypoint for reverse-engineering work\nalwaysApply: true\n---\n\n" + body
    return body


def render_instructions(existing: str, block: str) -> str:
    pattern = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?", re.DOTALL)
    core = block
    front = ""
    if block.startswith("---\n"):
        # Cursor rule frontmatter is only emitted when the file is new.
        end = block.find("\n---\n", 4)
        front, core = block[: end + 5] + "\n", block[end + 5 :].lstrip("\n")
    if pattern.search(existing):
        return pattern.sub(core, existing, count=1)
    if not existing.strip():
        return front + core
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + core


def unified(path: Path, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{path} (current)",
            tofile=f"{path} (proposed)",
        )
    )


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = path.with_name(f"{path.name}.bak.{stamp}")
    shutil.copy2(path, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent", choices=sorted(CLIENTS), required=True, help="client to configure")
    parser.add_argument("--project", default=".", help="workspace the agent runs in (default: cwd)")
    parser.add_argument("--server-url", default=DEFAULT_URL, help=f"existing MCP endpoint (default {DEFAULT_URL})")
    parser.add_argument("--transport", choices=("http", "stdio"), default="http", help="stdio emits the documented proxy entry")
    parser.add_argument("--no-instructions", action="store_true", help="skip the instruction-file block")
    parser.add_argument("--apply", action="store_true", help="write the proposed changes (default: dry run)")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON instead of a diff")
    args = parser.parse_args(argv)

    client = CLIENTS[args.agent]
    project = Path(args.project).expanduser().resolve()
    entry = mcp_entry(str(client["shape"]), args.server_url, args.transport)

    if args.agent == "generic":
        print(json.dumps({"mcpServers": {SERVER_NAME: entry}}, indent=2))
        print(f"\nInstruction file block (append to your agent's instructions):\n\n{instruction_block('generic', BOOTSTRAP)}")
        return 0

    base = Path.home() if client.get("home") else project
    config_path = base / str(client["config"])
    existing_config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if str(client["shape"]) == "toml":
        new_config = render_toml_config(existing_config, entry, args.server_url, args.transport)
    else:
        new_config = render_json_config(existing_config, str(client["shape"]), entry)

    plan: list[tuple[Path, str, str]] = [(config_path, existing_config, new_config)]
    notes: list[str] = []

    if not args.no_instructions:
        if project == REPO_ROOT:
            notes.append("workspace is the AgentDecompile repository: AGENTS.md already governs it; no instruction block added")
        else:
            instr_path = project / str(client["instructions"])
            existing_instr = instr_path.read_text(encoding="utf-8") if instr_path.exists() else ""
            new_instr = render_instructions(existing_instr, instruction_block(args.agent, BOOTSTRAP))
            plan.append((instr_path, existing_instr, new_instr))

    changes = [(p, b, a) for (p, b, a) in plan if b != a]

    if args.json:
        print(json.dumps({
            "agent": args.agent,
            "project": str(project),
            "server_url": args.server_url,
            "transport": args.transport,
            "apply": args.apply,
            "changes": [{"path": str(p), "new_file": not p.exists()} for p, _, _ in changes],
            "notes": notes,
        }, indent=2))
    else:
        for note in notes:
            print(f"note: {note}")
        if not changes:
            print("nothing to change: configuration already matches")
        for path, before, after in changes:
            print(unified(path, before, after))

    if not args.apply:
        if changes and not args.json:
            print("dry run: re-run with --apply to write these changes")
        return 0

    for path, _before, after in changes:
        path.parent.mkdir(parents=True, exist_ok=True)
        saved = backup(path)
        path.write_text(after, encoding="utf-8")
        print(f"wrote {path}" + (f" (backup: {saved})" if saved else " (new file)"))
    if changes:
        print("restart the agent or reload its MCP servers; then run entrypoint/setup/doctor.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
