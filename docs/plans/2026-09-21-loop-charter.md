---
title: Loop charter — how planning converges, when building starts by itself, when we go back
date: 2026-09-21
applies-to: the portable-signatures plan, the design docs, STRATEGY.md, the risk register, the autonomous loop
status: living; the loop follows this file, and edits it when the process itself is found wanting
---

# Loop charter

One authoritative plan (`2026-09-21-portable-signatures-codecaves-generic-plan.md`), one design
authority (`docs/dashboard-design/2026-09-21-consolidated-design-plan.md` + `docs/FRONTEND_INTENT.md`),
one program policy (`STRATEGY.md`), one risk register, one loop. No parallel "current" plans.

## 1. Modes

| Mode | What runs | Leaves when |
|---|---|---|
| **PLAN** | grill rounds (the saved `plan-grill-round` workflow: grill → adversarial refutation → reconcile → apply), attestation of "what exists today" claims on the real corpus, design/diagram regeneration | a **phase** is build-ready (§3) — building of that phase starts while later phases keep being grilled |
| **BUILD** | worktree-isolated units in Recommended order, each with the grill protocol in its packet; integrate → acceptance → attestation per wave; the living-plan delta after every wave | a REPLAN trigger fires (§4), or every unit has landed |
| **REPLAN** | a *targeted* grill round on the affected phase/units only, amendments applied, Recommended order re-derived | the targeted round is dry (§2) — then BUILD resumes where it stopped |

The three modes pipeline: at any moment some phases are build-ready and being built, later phases
are still being planned, and a hindsight finding can pull one phase back into REPLAN without
stopping the others.

## 2. "Addressed as much as realistically possible" — convergence

Planning of an area has converged when all of these hold, measured by the workflow, not by
feel:

1. Two consecutive rounds over that area produce **zero surviving `blocks-goal` or
   `wrong-when-implemented` defects** after three-lens refutation. `stale` and `clarity` findings
   are applied but do not reset the count — grills always find wording to improve; only
   refutation-verified substance counts, otherwise the loop never converges.
2. Every unit in the area names its owned files and its acceptance test.
3. Every open question in the area is a recorded decision (default adopted or user-answered).
4. Every "what exists today" claim the area relies on was attested on the real corpus or
   marked `unverified` in the plan.
5. Every register row touching the area has a unit, an explicit accept, or is closed.
6. The design docs and the diagram carry no amendment for the area.

Whole-plan convergence = every area converged and the risk grill dry for two rounds. Realistic
ceiling: the refutation-verified defect stream is dry, not "no one can think of anything".

## 3. When building starts without a user — phase readiness

A phase is **build-ready** when: (a) its area is converged per §2, (b) every prerequisite unit
in the Recommended order has landed, (c) the anchors its units cite hold at the branch head,
(d) the attestation for the verbs it touches is green, and (e) it does not depend on an
unanswered question. Build-ready phases start automatically; nothing waits for a user.
Phase 0, U7, U22, U1–U3 and U21c were built under exactly this rule (audit 2 converged them);
the rest follow as their phases converge.

## 4. Hindsight — when to go back

BUILD pulls a phase back into REPLAN when any of these appear, from any source (worker report,
attestation diff, risk grill, acceptance test, integration):

- a worker reports a deviation or a plan defect above `clarity`;
- an acceptance test cannot be written as the unit specifies it;
- attestation on the real corpus regresses, refuses, or hangs on a verb the unit touched;
- a "what exists today" claim is refuted by code;
- a risk-grill row is promoted to a unit that changes an existing unit's contract;
- an integration conflict shows two units own one contract.

REPLAN is scoped to the affected phase and its dependents; it runs the workflow with those
areas only; it ends when that round is dry; BUILD resumes at the same Recommended-order step.
Hindsight is expected, not a failure: the plan is rewritten as often as building teaches.

## 5. Living plan — maintenance rules (skill `maintain-living-plan`)

- The dated plan **is** the living plan. Each loop iteration writes a `### Delta Update`
  block at the top of the plan: **Landed** (units + commits), **Partial** (validated but
  uncertain, with what would settle it), **Next** (recommended changes). Minimal churn;
  decision-oriented; the Revision log keeps the audit history.
- Unit bullets carry status marks in place (✔ landed `<commit>`, ⏳ in flight, ⛔ blocked
  `<reason>`); "what exists today" sentences are rewritten to "landed at …" when they land.
- **STRATEGY.md** is the program-level authority. It is **not edited while the plan, design and
  diagram are still converging** (user directive 2026-09-21); it is rewritten from them once
  they converge and building has changed the pipeline's policy: the cross-build substrate as a stage-parallel lane, the Autonomy rule,
  the determinism basis, the closed status set, the surfaces rule (no Start; one admission-
  scoped pause/resume). Each such change is one STRATEGY commit citing the plan unit that
  caused it; STRATEGY never contradicts the plan and the plan never restates STRATEGY.
- Superseded plans are marked at their top ("superseded by …") and left in place as history;
  the 2026-09-08 portable-signatures plan is superseded by this plan and is renamed under U21a.
- Companions (audit files, risk register, this charter, the goal) are inputs, not competing
  plans.

## 6. Cadence and limits — grill sparingly

Grilling is a tool with a cost; the default iteration is **build, integrate, attest** — not
grill. A grill round runs only when one of these is true:

- an area has **never** been audited (each area gets one full round, once);
- a **hindsight trigger** (§4) fired for an area → one targeted round on that area only;
- code landed that touches an area's "what exists today" claims → one targeted round, and only
  if attestation or a worker report suggests the claims moved;
- the **sanity cadence**: `risk-hangs` every fourth iteration, `feasibility` every eighth, the
  full set only when the user asks or the plan is about to be declared converged.

Inside a round, three-lens refutation runs only on `blocks-goal` / `wrong-when-implemented`
findings; `stale` and `clarity` findings are applied directly without a refuter panel. A round
with nothing substantive is a no-op tick and does not schedule another.

Per iteration otherwise: integrate → attest (verbs touched since last time) → dispatch. At
most four concurrent agents until the repo leaves the USB drive (register R1/R11). Attestation
runs against a `.backup` copy of the real store, never the live file; slugs hashed; every verb
has a deadline; exceeding it is a finding.

## 6b. Test moratorium (user directive 2026-09-21)

Until the plan, design and diagrams are fully completed **and** built to completion, **no tests
are created and no tests are run** in this session — no pytest, no RED/GREEN, no regression
slices, no fixture-driven gates. Units implement source only; each unit still *names* its
acceptance test in its bullet, and every named test is written and run in one final
verification phase after the build completes. Worker packets carry this rule; a worker that
runs or writes a test is in breach. Verification during the build is by reading the diff,
by the grill protocol on the diff, and by the inline-CLI attestation on a copy of the real
store (the user's explicit instrument), which is not a test suite.

## 6c. Engineering rules for every unit (user directives 2026-09-22)

- **Speculative generality, to the extreme; YAGNI rejected.** Every unit declares its
  abstractions and extension points (Protocols/ABCs, registries, interchangeable adapters,
  configuration) with at least one working implementation and named slots for the others; a
  packet that "keeps it minimal" is in breach.
- **Licensing does not exist** in this program: no unit, gate, role or object policy reasons
  about it.
- **Walking skeleton first.** The default delivery shape is a thin end-to-end path through
  every layer in hours (agents in parallel worktrees), with the full capability arriving as
  adapters behind the declared interfaces — never a 170-day serial build.

## 7. Restart (the loop is session-bound)

If the session ends: read this file, the plan's Delta Update, the register's Resume point;
re-arm the loop with the same prompt. Nothing else is required — all state is committed.

## 8. Meta-problems found and fixed in the loop itself

| Problem | Fix |
|---|---|
| "No amendments for two rounds" could never be reached — grills always find wording | Convergence counts only refutation-verified `blocks-goal`/`wrong-when-implemented` (§2.1) |
| No rule said when to stop planning and build | Phase readiness (§3); phases pipeline |
| No rule said when to go back | Hindsight triggers (§4), scoped REPLAN |
| The dated plan rots as code lands | Living-plan deltas + in-place status marks + STRATEGY maintenance (§5) |
| The goal's scope (substrate) was narrower than the user's one-shot expectation | Autonomy rule recorded; Phase 14 surfaces added; STRATEGY carries the program scope |
| Orchestrator hand-tracked every grill | Grills run as one saved workflow with structured output and adversarial refutation |
| Loop bound to one session | §7 restart from committed state |
