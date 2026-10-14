---
name: lfg
description: "Use this skill when asked to continue authorized AgentDecompile work from current strategy and evidence."
---

# Continue authorized work

Read [AGENTS](../../../AGENTS.md), [STRATEGY](../../../STRATEGY.md), the
[plans hub](../../../docs/plans/README.md) and
[unfinished outcomes](../../../docs/PROTOTYPE_OUTCOMES.md).

Resume the actual requested outcome from current evidence and ownership, select
the next bounded useful action, and retain unresolved outcomes across handoffs.
Active recovery uses the checkout-pinned `.venv/bin/agentdecompile-cli` from the
repository root; frontends are deferred. Reuse existing local or shared Ghidra
project bytes and analysis when available. Continue safe independent lanes when
one fails; never duplicate writers or bypass the current validation restrictions.

This project-local command does not start the historical live harness or an
automatic shipping pipeline. A request to continue does not authorize publication.
Follow AGENTS for PR approval. General development may use the available planning,
implementation and review skills within the user's authorized scope.

Report the resulting evidence, remaining outcome and next action. A bounded slice
does not complete the wider prototype.
