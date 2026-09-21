# `/capabilities` — capability discovery

Follow [AGENTS](../../AGENTS.md) and [STRATEGY](../../STRATEGY.md).
Use the existing 8080 `GET /api/v1/actions` for current recovery actions and
parameters. Its `corpus.export-hookpack` action is implemented; listing a verb
is not runtime-workflow proof.

MCP capabilities are described by `agentdecompile://capabilities`, the advertised
`tools/list` and [TOOLS_LIST](../../TOOLS_LIST.md). Counts and names can change;
inspect the current surface instead of trusting a copied inventory.
See [runtime reuse](../../docs/RUNTIME_REUSE.md) and
[unfinished outcomes](../../docs/PROTOTYPE_OUTCOMES.md) for claim limits.
