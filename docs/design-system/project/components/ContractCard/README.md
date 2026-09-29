# ContractCard

A contract box from the execution and resilience companions: a role-colored title and plain rows.

**Consumer provides** the title ("BYTES · Are these bytes here?"), the role (`step`, `bytes`, `operation`, `acceptance`, `gate`, `contain`) and the rows.

- `pane`, `line-node` stroke, `radius-contract`; title `dia-box-title` in the role color (`role-*`); rows `dia-box-row` in `ink`. Step boxes join with `role-step` arrows at `stroke-contract-arrow`.
- Roles: step (numbered process), bytes (bytes, recovered source, resume), operation (operation, original code), acceptance, gate (the identity question, continue, policy), contain (fence, quarantine, control plane, data/provider).
- The title's words carry the role; the role color is never the only carrier.

**Linking**

- **Publishes:** nothing. Diagram-only.
- **Follows:** nothing; the content is `pipeline-model.json`.
- **Targets rendered:** in app renderings (RuntimeCapabilities predicate rows, TaskLifecycle and FailureRecord crosswalks, Explain) the title links to its pipeline node: `?node=contract-bytes`, `contract-identity`, `contract-operation`, `fence`, `quarantine`, `continue`, `exec-step-1`…, `resil-step-1`…; in docs to the outline anchor (`execution-contracts.outline.md#contract-bytes`, `resilience-contracts.outline.md#resil-step-1`).
- **Absent copy:** none in the diagram. A live predicate row with no receipt says "no receipt · not run".

**Accessibility**

- Each box is a list item with a heading; in the SVG a `<g id>` in reading order, with the outline as the primary accessible form.
