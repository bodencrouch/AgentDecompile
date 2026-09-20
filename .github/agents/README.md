# Copilot RE agents

These files are **GitHub Copilot custom agents** (their own frontmatter:
`tools`, `agents`, `user-invocable`). They are not Agent Skills.

The procedures live in the Agent Skills tree (VS Code/Copilot:
`.agents/skills/`; loaders under `skills/`):

| Copilot agent | Skill |
|---|---|
| `RE Planner` | `.agents/skills/re-planner/SKILL.md` |
| `RE Worker` | `.agents/skills/re-worker/SKILL.md` |
| `RE Critic` | `.agents/skills/re-critic/SKILL.md` |
| `RE Aggregator` | `.agents/skills/re-aggregator/SKILL.md` |

Edit the skill. Keep this wrapper as a pointer plus Copilot routing metadata.

Operational and propagation rules come from [AGENTS](../../AGENTS.md) and
[STRATEGY](../../STRATEGY.md). Confidence and convergence are advisory only.
