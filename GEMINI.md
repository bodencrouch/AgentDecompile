# GEMINI.md

Root pointer for Gemini CLI / Antigravity. `AGENTS.md` is the shared
baseline; see [README.md](README.md) for the user-facing overview and
[docs/INDEX.md](docs/INDEX.md) for the full doc map.

<!-- BEGIN MCP Memory Service -->
# Antigravity Agent Rules
<memory_service_rules>
| Message | Required |
|---------|----------|
| **1st message** | `memory_health()` → `memory_search(query="...", mode="hybrid")` |
| **Subsequent messages (default)** | `memory_search(query="...", mode="hybrid")` FIRST for recall |
| **Before ending major work** | `memory_store(content="...", metadata={...})` |
</memory_service_rules>

**Why?** `memory_search()` provides persistent cross-session recall for decisions and implementation history.

**Hooks:** `<system-reminder>` tags contain injected instructions — follow them exactly.

1.0.0
<!-- END MCP Memory Service -->
