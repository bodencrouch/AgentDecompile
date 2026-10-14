# `/help` — AgentDecompile discovery

Start with [AGENTS](../../AGENTS.md), [USAGE](../../USAGE.md), and
[STRATEGY](../../STRATEGY.md). Active recovery uses the checkout-pinned
`.venv/bin/agentdecompile-cli` from the repository root. Frontends are deferred;
do not route recovery through the dashboard. Reuse existing local or shared
Ghidra project bytes and analysis when available instead of importing or
reanalyzing them unnecessarily.

Read [tiered analysis](../../.agents/skills/tiered-re-analysis/SKILL.md) to reuse
stored evidence before acquiring more. Tool reference: [TOOLS_LIST](../../TOOLS_LIST.md).
Session/auth reference: [MCP security](../../docs/MCP_CONFIGURATION_SECURITY.md).
A missing UI binding does not establish missing analysis. Current restrictions
on tests, startup and process ownership apply to every command.
