# AgentDecompile – Copilot/Claude Instructions

Read [AGENTS.md](../AGENTS.md) for operational authority and canonical naming;
[STRATEGY.md](../STRATEGY.md) owns pipeline, matching and acceptance policy.
[Runtime reuse](../docs/RUNTIME_REUSE.md) separates original-binary calls from
source recovery. Use the [plans hub](../docs/plans/README.md) for current work.

Verify the actual behavior affected by an authorized code change; tool listing,
startup, job success and screenshots alone are insufficient. State the evidence
and limits. For the current recovery mission, do not run filesystem tests/builds,
restart processes, use systemctl or create alternate ports. Use the existing
8080 catalog; manually corroborate ownership before admitting work. General
development test recipes elsewhere do not override these constraints.

Keep changes narrow and preserve user-owned state. Naming conventions are
centralized in AGENTS.md; tool naming and parameter contracts are in USAGE.md.
Optional multi-agent artifact notes remain advisory under the
[RE artifact protocol](instructions/re-artifact-protocol.instructions.md).
Use diagrams when they explain a relationship; do not create duplicate policy.
