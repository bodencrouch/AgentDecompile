# ContractCard

A contract box from the execution and resilience companions: a role-colored title and plain rows.

**Consumer provides** the title ("BYTES · Are these bytes here?"), the role (`step`, `bytes`, `operation`, `acceptance`, `gate`, `contain`) and the rows.

- `pane`, `line-node` stroke, `radius-contract`; title `dia-box-title` in the role color (`role-*`); rows `dia-box-row` in `ink`. Step boxes join with `role-step` arrows at `stroke-contract-arrow`.
- Roles: step (numbered process), bytes (bytes, recovered source, resume), operation (operation, original code), acceptance, gate (the identity question, continue, policy), contain (fence, quarantine, control plane, data/provider).
- The title's words carry the role; the role color is never the only carrier.

**Linking:** none (print diagram). Its nodes keep their pipeline-model ids (`contract-bytes`, `contract-identity`, `contract-operation`, `fence`, `quarantine`, `continue`, `exec-step-1`…, `resil-step-1`…): where the app renders the same node (RuntimeCapabilities predicate rows, or a crosswalk line inside TaskLifecycle's and FailureRecord's Explain, which ends "(interpretation)" because the crosswalks are design interpretations, never recorded facts), that rendering links it to `?node=` with that id, and in docs the name links to the outline anchor (`execution-contracts.outline.md#…`). The print canvas itself carries no links and no live data.

**Accessibility**

- Each box is a list item with a heading; in the SVG a `<g id>` in reading order, with the outline as the primary accessible form.
