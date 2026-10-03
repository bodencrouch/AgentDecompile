# Task15.1 fix round1

Base reviewed HEAD: ccd9b63af57d418cf26842584444e2a471d4348f. Read original task-15-brief.md, adopted next-shared-selection-contract.md, task-15-report.md and task-15-review.md. Fix exactly all three Important findings; preserve captured read/packet/action isolation and original public behavior.

Owned: src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js; src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/StaticSelectionIsolation.test.ts; append task-15-report.md correction receipt. No other source/docs ownership.

1. A->B project opening must survive intervening render without retaining A as pending target; actual later user/open intent still supersedes.
2. Bootstrap identity discovery must not cancel its own session restoration; subsequent user/open intent must win. Author deferred-order regression coverage with effects represented where needed; disclose actual harness limitations, no fake scheduling proof.
3. Create shared refreshed intent before both post-action inventory/detail reads; completed synchronous action must admit updated list without a manual refresh.

Minor M1 focus-index clamp is deferred to whole-branch review under current review policy; do not expand this fix round.

Fresh implementer required because original handle unavailable after interruption. You are not alone; preserve others' edits. No Git/subagents. Source-only: no tests/collection/builds/typechecks/project imports/DB/crypto/checker/runtime/live/provisioning. node --check, source/diff inspection allowed. Return READY_TO_COMMIT with exact owned paths and correction evidence.
