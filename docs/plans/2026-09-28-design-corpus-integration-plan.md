---
title: Integrate the 2026-09-20..28 design corpus into diagrams, designs and plans
date: 2026-09-28
status: active
---

# Integrate the design corpus

## Goal

Fold the findings from the week's design corpus into the canonical diagrams, design docs and plans. Readers should not have to open the source files to learn what changed.

## Inputs

Four read-only research passes proposed 41 edits:

- R1: plans 09-20..21. 12 sources, 15 edits.
- R2: plans 09-22..27 and JSON ledgers. 15 sources, 13 edits.
- R3: dashboard design 09-20/21 and prototypes. 11 sources, 9 edits.
- R4: pipeline diagram, control briefs, research, residual findings and solutions. 33 sources, 4 edits.

Each proposal names its target, operation (add, amend, supersede), anchor, text and source hash. The proposals live in the session deliverables under `design-integration-20260928/research/R{1..4}.json`.

## Settled decisions

- Static 8080 is the conventional RE GUI. It follows the guide's CodeBrowser arrangement.
- Vite is a different surface: the real-time workstation that draws the work. The two share one backend with field parity.
- Supersede with a dated note that points at the replacement. Do not delete history.
- No product, binary or project names in docs. `scripts/check-anonymization.sh` must not report new hits on touched paths.
- No licensing reasoning in docs.
- Tests come last. This plan edits docs and diagram generators only.

## Units

| ID | Files (disjoint) | Edits |
|---|---|---|
| U1 | docs/plans/2026-09-21-risk-register.md, 2026-09-21-user-requirements-ledger.md, 2026-09-21-portable-signatures-codecaves-generic-plan.md, 2026-09-22-design-package.md, 2026-09-22-external-validation-design.md, 2026-09-22-session-obligation-audit.md, 2026-09-27-implementation-progress-and-live-track.md, 2026-09-27-weekend-design-scope.md, docs/DELIVERY_STATUS.md | 30 |
| U2 | docs/dashboard-design/2026-09-20-ghidra-guide-capability-inventory.md, 2026-09-20-unified-workstation-spec.md, 2026-09-21-consolidated-design-plan.md, 2026-09-21-improvement-recommendations.md, new 2026-09-28-static-codebrowser-guide-redesign.md, new docs/prototypes/dashboard-operator-feel/2026-09-28-static-surface-scope-note.md, docs/FRONTEND_INTENT.md line ~373 scope fix | 10 |
| U3 | docs/dashboard-design/pipeline-diagram/{generate_pipeline_diagram.py, generate_resilience_diagram.py, README.md} and their regenerated SVG, drawio and PNG outputs | 3 + regen |

## Acceptance

- Every `relevant` proposal is applied or has a one-line reason for skipping it in the unit report.
- Superseded sections carry a dated note and a link.
- The anonymization gate reports no hits on touched paths.
- Regenerated diagrams match their generators, as shown by a byte-level rerun.

## Deferred

- The static CodeBrowser redesign build (7 slices) follows this plan.
- Repair of the live store index needs the Ghidra server owner to stop the server first.
