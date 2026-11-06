# Prototypes

Operator start: [README.md](../../README.md). Workbench feel north star is long on purpose. These files are **design records**, not how-to.

The prototype also includes corpus-wide recovery and original-engine runtime reuse.
[Unfinished outcomes](../PROTOTYPE_OUTCOMES.md) records requested results, current
evidence and next actions, including the KotorXID design obligations. Pipeline
policy remains [STRATEGY.md](../../STRATEGY.md); operations follow [AGENTS.md](../../AGENTS.md).

```mermaid
flowchart TD
  feel[dashboard-operator-feel] --> workbench[/dashboard]
  flow[dashboard-flow-evolution] --> feel
```

| Folder | What it is |
|--------|------------|
| [dashboard-operator-feel/](./dashboard-operator-feel/feel.md) | Experiential north star + [decisions](./dashboard-operator-feel/decisions.md) + HTML mocks |
| [dashboard-flow-evolution/](./dashboard-flow-evolution/decisions.md) | Palette / jobs-dock decisions + [mock](./dashboard-flow-evolution/mock.html) |

Do not rewrite `feel.md` to match a later CSS pass. New feel work gets a new dated note. Current workbench skill: `skills/workbench-operator`.
