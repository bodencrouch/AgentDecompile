# Operating Contract

## Original request
/mission-resume /intent-runtime please implement the vite design plan(s)
thoroughly fan out subagents and utilize numerous subagents for this. three
layers, first layer creates subagents based on what the plan requires and what
the current implementation is, the second layer of subagents should be created
with expert roles in the scope they're targetting, and should be responsible
for spawning numerous tiny subagents for each small scope. May even need a
fourth layer. Do this until all of the plan(s) stuff for the vite frontend is
completely implemented.

## Mission
Deliver the documented Vite workbench design in the React frontend with the
same dependable operator workflows as its dashboard integration, without
discarding in-flight work already present in the checkout.

## Outcome model
1. Every applicable, unimplemented Vite requirement in the current workbench
   plans has a traceable implementation or a recorded, evidence-backed reason
   it is already satisfied [stated]; check: plan-to-source completion matrix.
2. Frontend behavior keeps selections, projects, evidence, actions, and
   recovery state coherent across the documented workspace surfaces
   [entailed]; check: focused Vitest coverage and browser interaction.
3. Vite production assets build and are served by the dashboard integration
   without TypeScript errors [repo: frontend/README.md]; check: `npm run build`
   and a live dashboard/Vite browser pass.
4. The operator path stays usable by keyboard and pointer at responsive sizes,
   with stacked layers and activity feedback remaining reachable [repo:
   infer-intent.instructions.md]; check: browser interaction and an
   independent review.
5. Existing user and in-flight changes are preserved rather than reverted or
   overwritten [stated]; check: diff review and file ownership ledger.
6. No commit, push, deployment, or changes to the static legacy workbench are
   made [default]; check: final diff and git history.

## Scope
`src/agentdecompile_recovery/corpus/dashboard/frontend/`, its focused tests,
the server/build integration directly required to deliver it, and mission
ledgers. Applicable plans include the local-first workbench plan and
predecessor Vite/workbench design plans that remain unsatisfied.

The end-to-end `corpus.match-pair` / cross-match action path, its live API/MCP
surface, and development-server hot reload are also in scope where required
to make the mounted Vite workflows genuinely functional.

## Non-goals / drift boundaries
No backend redesign unrelated to a proven frontend integration need. No
rewriting or deleting the legacy static workbench. No unrelated corpus,
recovery, CLI, documentation, dependency, or design-system work. No commit,
push, external deployment, or destructive reset. Do not claim recovery proof
from UI state.

## Authority
- Autonomous: inspect repository and plans; run local frontend and focused
  integration checks; make reversible, in-scope frontend changes; add focused
  tests; delegate independent investigations and reviews.
- Execute-and-report: minimal backend or build wiring strictly required by a
  proven frontend design requirement; update related frontend documentation.
- Prepare-but-do-not-execute: commit, push, PR, deployment, public
  communication, destructive operations.
- Human authority: accepting a data-loss, privacy, security, or incompatible
  workflow tradeoff.
- Action boundary: this is an implementation request, not a plan-only review.

## Quality bar
Production-ready correctness, workflow continuity, accessibility,
responsiveness, maintainability, and evidence-based browser validation.

## Evidence standard
Each requirement has a plan file:line and source/test/browser evidence. Run
the narrow Vitest and TypeScript/Vite build checks, then exercise the live Vite
and served dashboard paths with browser automation. A fresh independent review
must find no material unaddressed plan gap before completion.

## Communication
Asynchronous, declarative updates; no user check-ins for routine engineering
choices; silence means continue.

## Amendments
- 2026-09-09: the separate Vite workbench implementation directive supersedes
  the prior quiescent portable-identity mission. The prior mission is preserved
  in `.mission/notes/2026-09-09-portable-identity-closeout.md`.
- 2026-09-09: prioritize parallel, evidence-backed discovery and promptly
  commission the expert and tiny-scope layers requested by the user. This does
  not relax exclusive writer ownership or the completion evidence standard.
- 2026-09-09: "$mission-resume $intent-runtime please implement the vite
  design plan(s) thoroughly fan out subagents and utilize numerous subagents
  for this. three layers, first layer creates subagents based on what the plan
  requires and what the current implementation is, the second layer of
  subagents should be created with expert roles in the scope they're
  targetting, and should be responsible for spawning numerous tiny subagents
  for each small scope. May even need a fourth layer. Do this until all of the
  plan(s) stuff for the vite frontend is completely implemented." The supplied
  RE-dashboard research is product-direction evidence; apply it through the
  existing local-first plan and capability boundaries, without copying
  unlicensed source or silently expanding into every external engine.
- 2026-09-09: preserve the standing constraint for this task: do not write,
  run, or rely on saved filesystem test suites. Use live browser/API checks
  and inline validation. Do not restart 8080 or 5174 while hot reload works.
- 2026-09-09: "entirety of the vite frontend tested with inline terminal
  commands/playwright/curl/devtools/chromium driven, entirety of the cross-
  match pipeline functional, hotloading fully functional without requiring
  restarts of either server, and all the tasks implemented according to the
  most optimal and expert level strategies we've previously mentioned
  especially with cross-match(es)."
- 2026-09-09: cross-matching must follow the supplied cascading failover:
  exact/image/hash and authentic-symbol anchors; unique reference evidence;
  call-graph propagation; CFG topology; mnemonic/SPP filtering; IL/AST and
  fuzzy comparison only on the residue; AI last; basic-block containment for
  inline/split/fold/clone cases. Preserve uniqueness, margin, provenance,
  quarantine, and non-1-to-1 Correspondence safeguards from the evidence-
  fusion plan.
- 2026-09-09: multiple simultaneous browser clients must keep navigation,
  selection, drafts, layout, and transient workflow state isolated per client
  while observing the same shared backend data and jobs. Source-heavy work
  must execute outside the request-serving process with bounded concurrency so
  it cannot stall the workbench. Provide an accessible Open in VS Code action;
  expose an embedded browser VS Code surface only when a compatible local
  service is available at low idle cost, with an honest non-embedded fallback.

## Stopping rules
All high-value applicable plan requirements are implemented and evidenced,
validation and an independent completion review pass, and any remaining work is
explicitly deferred as low-value or externally blocked.
