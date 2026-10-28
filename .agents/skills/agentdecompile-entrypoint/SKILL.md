---
name: agentdecompile-entrypoint
description: "Use this skill when an agent is new to AgentDecompile, needs to be set up against the MCP server, asks where to start reversing, wants the tool stack or environment checked, or asks what to export and when recovery counts as done. Apply even if they only say set me up, point me at the binaries, or what tools do we have."
license: AGPL-3.0-or-later
metadata:
  author: AgentDecompile
  version: "1.0"
---

# AgentDecompile entrypoint

Read [AGENTS](../../../AGENTS.md) and [STRATEGY](../../../STRATEGY.md) first; they own
operations and acceptance. This skill routes a new agent through the
[entrypoint](../../../entrypoint/README.md) folder and nothing more.

1. Read [AGENT_BOOTSTRAP.md](../../../entrypoint/AGENT_BOOTSTRAP.md) top to bottom.
2. Attach to the existing `http://127.0.0.1:8080/mcp`; never start, restart or re-port it.
   Client configuration, when asked for, comes from
   `python3 entrypoint/setup/setup_agent.py --agent <client> --project <workspace>`
   (dry run; `--apply` writes with backups).
3. Probe the stack read-only with `python3 entrypoint/setup/doctor.py` and report which
   evidence tiers and named gaps are reachable. Missing tools lower the claim tier; they do
   not block triage.
4. Work the [recovery loop](../../../entrypoint/RECOVERY_LOOP.md): ingest, provenance,
   joint analysis, layered matching, transfer with provenance, per-function recovery with
   the `.S` fallback ladder, bundle and exports, feedback, whole-image finish line.
5. Report in claim tiers. "Insufficient evidence" is a valid result.

Hand off to `tiered-re-analysis` before opening anything, `source-recovery` for C and
objdiff, `bsim-corpus` for cross-build names, the `re-*` roles for multi-agent work and
`lfg` to continue authorized work. The [stack registry](../../../entrypoint/STACK.md) and
[coordinator design](../../../entrypoint/COORDINATOR.md) are reference; the coordinator is
proposed, not implemented.

Validation reference (do not run during the current mission):

```bash
python3 entrypoint/setup/setup_agent.py --agent generic
python3 entrypoint/setup/doctor.py --no-server --json
```
