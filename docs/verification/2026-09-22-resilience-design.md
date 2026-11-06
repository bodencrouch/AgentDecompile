# Resilience design artifact receipt — 2026-09-22

This receipt covers the [failure prevention and recovery refinement](../plans/2026-09-22-failure-prevention-and-recovery-contracts.md)
and synchronized overview, execution and resilience diagrams. It supersedes the
earlier design-package receipt's diagram identities for these updated artifacts;
that earlier receipt remains a historical snapshot.

## Checks actually performed

- 76 local link targets exist across the September 22 plan documents and diagram README.
- Markdown fences pair and trailing whitespace is absent in those documents.
- All six SVG/native draw.io files parse as XML.
- The Documents overview SVG is byte-identical to its canonical copy.
- The diagram author rendered the artifacts; the new resilience view was visually inspected.
- Scoped documentation diff checks passed; no clean-checkout claim is made.
- Independent review challenged provider probe storms, lost wakes, mutable fixture
  races, budget reset and coordinator failure; the author added explicit mechanisms.
- The final specification maps all 11 historical incidents to 25 failure contracts
  and 30 future paired acceptance checks; independent review closed its objections.
- Diagram review corrected opaque-effect and policy-version overclaims.

These are document and diagram checks. No product implementation, workbench probe,
recovery, dependency installation, build or test suite was run. FP acceptance cases
and all real failure-injection demonstrations remain **NOT RUN**. Completion means
reviewed design coverage, not guaranteed runtime reliability or measured optimality.

## Artifact identities

| Artifact | SHA-256 |
|---|---|
| [agentdecompile-recovery-pipeline.drawio](../dashboard-design/pipeline-diagram/agentdecompile-recovery-pipeline.drawio) | `96a5d7b87575e48ab792a81ef27c37bc361b2f939313772d67f96d12eb28780b` |
| [agentdecompile-recovery-pipeline.png](../dashboard-design/pipeline-diagram/agentdecompile-recovery-pipeline.png) | `c6c71566d47a7c28b349a7eae1d39eab43016673b8c69ab9b9f8f5c034fd1358` |
| [agentdecompile-recovery-pipeline.svg](../dashboard-design/pipeline-diagram/agentdecompile-recovery-pipeline.svg) | `a124af582c52c19dc630f25b0b11d8fb0a9411be1ec78725865281e631cf7a3f` |
| [execution-contracts.drawio](../dashboard-design/pipeline-diagram/execution-contracts.drawio) | `83343f28f66cac5f2240d29a2f1818595627bd8d9b3e75d427b96e2ac9ef4114` |
| [execution-contracts.png](../dashboard-design/pipeline-diagram/execution-contracts.png) | `27287e3186e4a570789c80ae1a27b1b98679f0e3caf2ece5a59455070d48635d` |
| [execution-contracts.svg](../dashboard-design/pipeline-diagram/execution-contracts.svg) | `8e2805596632087755d93dd2d577b81932834550f22c777a69f93fb72ee7cbb2` |
| [resilience-contracts.drawio](../dashboard-design/pipeline-diagram/resilience-contracts.drawio) | `7b413a50264fa09845c08800b5b4fadd8916c4372b274daf141600437eabd568` |
| [resilience-contracts.png](../dashboard-design/pipeline-diagram/resilience-contracts.png) | `9705cbb3caf9872a86f8db688b039027ec215d8ab857a6a6396f412fbc4fd607` |
| [resilience-contracts.svg](../dashboard-design/pipeline-diagram/resilience-contracts.svg) | `4355df7bf141cd64c972e47399cef9c8d3b3f99429edc54892e07bc5b24fb1f9` |
