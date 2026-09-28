# ContractCard

A contract box from the execution and resilience companions: a role-colored title and plain rows.

**Consumer provides** the title ("BYTES · Are these bytes here?"), the role (`step`, `bytes`, `operation`, `acceptance`, `gate`, `contain`) and the rows.

- `pane`, `line-node` stroke, `radius-contract`; title `dia-box-title` in the role color (`role-*`); rows `dia-box-row` in `ink`. Step boxes join with `role-step` arrows at `stroke-contract-arrow`.
- Roles: step (numbered process), bytes (bytes, recovered source, resume), operation (operation, original code), acceptance, gate (the identity question, continue, policy), contain (fence, quarantine, control plane, data/provider).
