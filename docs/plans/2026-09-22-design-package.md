---
title: AgentDecompile complete recovery and runtime design package
type: design
date: 2026-09-22
status: design-complete
execution_scope: design-complete-foundation-implementation-authorized
---

# AgentDecompile design package

Current scope clarification (2026-09-27): this package refines the
[September 18–21 baseline](2026-09-27-weekend-design-scope.md). It does not replace
the full portable-substrate Phases 0–15, distributed-compute design, workstation
requirements or brainstorm/diagram commitments. Omitting a weekend unit from the
tables below does not remove it from the active goal.

This package completes the design requested in the current conversation: recovery
projects, binary/cross-build matching, independently useful original-game memory
modding, and execution that contains failures without weakening evidence. It
incorporates both supplied reviews into the existing design and diagrams. It is
**not an implementation, deployment, test run or recovery result**.

The later explicit request to build authorizes the foundation implementation described in
[the autonomous capability roadmap](2026-09-22-autonomous-capability-product-roadmap.md).
The original design-only delivery above remains a historical boundary; current software
results are recorded separately in [the implementation receipt](../verification/2026-09-22-autonomy-foundation.md).

The governing rule is: **missing evidence blocks its claim; an unhealthy resource
blocks its dependent work; neither automatically blocks the whole project.**
The companion rule is: **recover from the best evidence, reuse only what transfers,
and verify each result at the level where it will be used.**

## Read the package

| Artifact | Authority / purpose |
|---|---|
| [Weekend scope index](2026-09-27-weekend-design-scope.md) | Full September 18–21 design/plan/brainstorm baseline and relationship to later refinements |
| [Current implementation progress and live track](2026-09-27-implementation-progress-and-live-track.md) | Status and ordered todo for the full weekend baseline plus later work; prioritizes useful RE/cross-matching alongside implementation |
| [STRATEGY](../../STRATEGY.md) | Pipeline priorities, claim boundaries and governing policy |
| [Recovery contracts](2026-09-22-recovery-contracts-and-validation-plan.md) | Region reconstruction, compilation units, identity/variant/instance, three binding predicates, scoped facts, early/final verification |
| [Task and acceptance design](2026-09-22-task-acceptance-and-continuation-design.md) | Task/attempt/resource/scenario schemas, admission, progress, retry, fencing, storage, continuation and exhaustive accounting |
| [External validation design](2026-09-22-external-validation-design.md) | Proposed reccmp/ReAgent/AgentDecompile interfaces, report normalization and relocatable recovered-project recipes; isle as reference; the P1.3 execution-actions plan gives its reccmp/ReAgent routes concrete fields, pinned versions and refusal codes |
| [Consolidated product design](../dashboard-design/2026-09-21-consolidated-design-plan.md) | Existing workspace appearance, interaction, two surfaces and observable workflow, with current contract reconciliation |
| [Runtime assessment](../RUNTIME_REUSE.md) | Historical implementation evidence distinguished from the required runtime contract |
| [Autonomous capability roadmap](2026-09-22-autonomous-capability-product-roadmap.md) | Subsequent authorized implementation and M0–M7 ambition, with [companion diagram](../dashboard-design/pipeline-diagram/autonomous-capabilities.svg) |
| [Diagram overview](../dashboard-design/pipeline-diagram/agentdecompile-recovery-pipeline.svg) | Stages 0–8, lanes A–E, bounded locators, serialization and outputs |
| [Execution companion](../dashboard-design/pipeline-diagram/execution-contracts.svg) | Task → evidence → acceptance, independent capability paths, fencing/quarantine and progress |
| [Editable diagrams and generators](../dashboard-design/pipeline-diagram/README.md) | SVG, native draw.io, PNG and artifact-authoring sources |
| [Failure prevention and recovery](2026-09-22-failure-prevention-and-recovery-contracts.md) | Mandatory failure response contracts, control-plane recovery, policy rollout and future acceptance matrix |
| [History-grounded maintainability](2026-09-22-history-grounded-maintainability-design.md) | Eleven historical incidents, current source seams, deterministic continuation and reduced operator intervention |
| [Independent review](2026-09-22-recovery-design-review.md) | Concrete findings, checked referents, concessions and resolution review |
| [Delivery status](../DELIVERY_STATUS.md) | Design delivery distinguished from software and runtime outcomes |

This index and its traceability table are the later contract part of the active
living plan; the weekend scope index retains the complete original unit set. The September 8
plans retain historical implementation decisions under their new reconciliation
notes. This package does not rewrite unrelated historical records or grant the
execution permissions described in old recipes.

## Design decisions and why these options win

| Decision | Deciding criterion | Selected mechanism | Rejected alternative / falsifier |
|---|---|---|---|
| Evidence before more throughput | Prevent wrong semantic bindings from multiplying | Presence + independent target identity + operation-specific predicates | Same signature/label lineage cannot prove identity; Foo/Bar RC-08 |
| Keep named stages, remove global barriers | Reach useful capability without waiting for unrelated work | Prerequisite DAG with identity/calibration feedback, early reconstruction and continuous parity | One missing target must not stop an eligible other target; A01/A05 |
| Region-based scaffold | Preserve real link/reference/metadata semantics | Explicit region/fixup/data manifest and independent linked-image oracle | Broken reconstructed addend must fail RC-01 |
| Separate three units | Match actual compiler scope | Recovery fragment, TU/LTCG group and emitted comparison region | Isolated compile cannot stand in for required final LTCG output |
| Typed relationships in existing catalog | Express variants/inline/folded instances without a new silo | Logical entity → implementation variant → physical instance | One address is not one entity; RC-03/04 |
| Original-code runtime as separate branch | Deliver usable vanilla features before reconstruction completes | Independent identity/ABI/layout/lifetime capabilities | Source-floor status cannot block valid original-code call; RC-09 |
| External tool adapters | Reuse established diagnostics without coupling server internals | Immutable input/report envelopes, capability checks, centralized acceptance | Vendor/import engine only if a measured missing contract justifies it |
| One task and acceptance contract | Reuse containment across providers and future hosts | Private attempts, immutable outputs, durable per-unit results and short acceptance commits | Independent per-launcher retry loops fail A04/A08 |
| Generation plus resource quarantine | Reject stale authority without pretending access stopped | Separate publication and access state; disjoint-resource continuation | Expired owner with byte-perfect result fails A07/A14 |
| Complete staged closure | Continue after device failure only when dependencies really independent | Verified manifests including indirect libraries/prefix/assets; durable outputs | Executable moved but library on failed drive fails A06 |
| Same-run scenario evidence | Prevent mismatched proof packages | Separate behavior/video receipts correlated to command/run/action interval | Old oracle plus new unrelated video fails A11 |
| Portable recipe and resolver | Another supported host can follow the exported project | Logical inputs by digest, relative paths, scoped build/compare operations | Absolute author-machine path fails portability preparation |

These are design choices backed by mechanisms and counterexamples. They are not
measured claims that a chosen implementation is fastest or universally optimal.
Versioned policies hold empirical thresholds; no benchmark number is invented.

## Requirement traceability

A = supplied architecture review; H = supplied hindsight review. Section references
use their headings, not inferred machine state. R = recovery contracts; T = task
and acceptance design; X = external validation design. RC and A identifiers refer
to **future acceptance specifications, all NOT RUN**. Explicit applicability and
unknown/unsupported outcomes complete the contract without inventing universal support.

| ID | Source requirement | Design location | Concrete future check |
|---|---|---|---|
| D01 | A1 reconstruct trustworthy linkable regions, independent oracle | R region record + reconstruction mechanism | RC-01 wrong addend rejected after placement |
| D02 | A2 separate recovery/compilation/comparison | R units + scoped toolchain; X recipe groups | Required grouped/LTCG output compared |
| D03 | A2 incremental calibration and legacy flags | R stages 1–2, environment/group records | Unsupported toolchain switch blocks only that profile |
| D04 | A2 diagnose before permutation/AI | STRATEGY cross-match; R stage 6 | Wrong type/ABI/context cannot be masked by source search |
| D05 | A3 architecture-specific floor with metadata | R scaffold + reconstruction | Instruction-only region missing required metadata refused |
| D06 | A3 early unchanged round trip | R RC-01 | Real extract/emit/place path, not copied output |
| D07 | A3 source contribution and rebuild methods | R reconstruction axes | RC-02 discarded compiled replacement earns zero credit |
| D08 | A4 compile is candidate admission | R facts and candidate state | Wrong constant compiles but remains unaccepted |
| D09 | A4 separate facts and bounded equivalence | R fact outcomes/assumptions | RC-05 reports each observed scope separately |
| D10 | A4 behavior-preserving repair, actual C++ | R source contract; X language/FP/group recipe | FP/NaN and exception-sensitive negative cases |
| D11 | A5 entity/variant/physical multiplicity | R data + worked reuse counterexamples | RC-03 changed behavior; RC-04 inline/folded/split |
| D12 | A5 compatible recipient candidate reuse | R propagation and recipient gates | Donor x+1 cannot replace recipient x+2 on identity alone |
| D13 | A5/A7 unchanged-work reuse, better evidence | R invalidation; T acceptance versions | RC-06 changed type invalidates only dependents |
| D14 | A5 per-build layout, no pointer scaling | R layouts + counterexample | Unknown spans stay opaque; exact offset evidence required |
| D15 | A5 naming preference vs facts | STRATEGY fusion; R lane A | Renaming cannot overwrite measured layout |
| D16 | A6 known-build RVA first | R runtime contract; overview B/C | Build+bytes pass still cannot replace identity evidence |
| D17 | A6 located/readable/callable/detourable/writable | R binding predicates; T scenario contract | RC-09 valid original use independent of source |
| D18 | A6 executable policy/caves | R runtime contract | Policy denial stays unsupported; zeros/slack alone refused |
| D19 | A6 install/remove/quiescence/lifetime | R runtime contract; T resource bundle | In-flight trampoline return prevents reclamation |
| D20 | A6 rollback limits | R operation contract; T teardown | Restored bytes never claim undone side effects |
| D21 | A7 stable snapshots, relevant dependencies and cache sync | R invalidation; T short acceptance commit | RC-06/A17 stale proposal rejected |
| D22 | A7 corpus/local keys and replay | R cache projections; T immutable proposals | Unrelated build preserves local compile; RC-07/A20 stable replay |
| D23 | A7 shared compiler, isolated mutable outputs | R toolchains; T ownership | No shared PDB/temp/Wine writer collision |
| D24 | A outcomes and regressing coverage | R named outcomes; T accounting | Ambiguous/absent/inlined/unsupported stay explicit; RC-10 |
| D25 | A agent roles and central acceptance | R acceptance owner; T contract | Producer cannot revise policy or self-promote |
| D26 | A first demonstrations, reccmp scope | R RC-01–10; X normalized tools | Held-out builds + representative replacement matrix |
| D27 | H1A noncircular target binding | R three predicates, T1–T3/Foo-Bar | RC-08/A01 right bytes under wrong label refused |
| D28 | H1A automatic withdrawal, no platform ban | R lineage; T coverage withdrawal | A02 seed withdrawal; repaired input version reevaluated |
| D29 | H1B original-code use without full recovery | R operation predicate; T original-code example | RC-09 supported read/call proceeds with source floor |
| D30 | H1C task-specific capacity, shared nested budget | T admission | A15 no-swap/swap-occupied small work vs overloaded class |
| D31 | H1D liveness/execution/goal and persistent attempts | T state/progress/retry schemas | A04 PID churn not progress; A08 restart keeps budget |
| D32 | H1E exhaustive accounting and proof scopes | T accounting | 24,242 inventory reconciles; unexplained two not invented |
| D33 | H2 local dependency failures, capability priority/aging | T admission/priorities | A05 independent cached task; A16 aged capacity reservation |
| D34 | H2 no spin, exact wake sets, objective preserved | T task completion/wake conditions | Exhausted attempt never marks objective achieved |
| D35 | H3 actual resources, scenario bundles, short transactions | T ownership and acceptance | Compile/LLM/game work outside writer transaction |
| D36 | H3 atomic ownership/fencing, quarantine/external jobs | T two ownership states and late-worker example | A07/A14 stale result and unsafe resource remain separated |
| D37 | H4 one retry owner, negative cache, bounded recovery | T failure table | A04/A08 finite retries, changed basis required for deterministic repeat |
| D38 | H4 checkpoint/exit and resource enforcement capability | T admission/cancellation | Pause does not claim memory reclaimed; unsupported enforcement routed |
| D39 | H5 input closure, persistent storage, tmpfs limits | T staging | A06 incomplete bundle never launchable; complete cached work continues |
| D40 | H5 publication, SQLite snapshots and bounded probes | T storage | A05/A13 interrupted copy cannot publish partial manifest |
| D41 | H6 fixture/driver/recording prerequisites | T scenario | A10 missing fixture distinct from behavior failure |
| D42 | H6 observation/mutation and unknown command outcome | T scenario/command IDs | A09/A12 status available, no blind duplicate mutation |
| D43 | H6 same-run oracle/video and local authentication limits | T scenario | A11 failed recorder retains scoped behavior; other scenarios continue |
| D44 | H7 namespaces/config and honest scanner limits | T adapter constraints | A18 bad args/log prefix/config owner rejected |
| D45 | H8 paired rejection/continuation cases and useful metrics | T A01–A20 | Every bad case has unaffected-ready-work control |
| D46 | H implementation order and conditional guarantees | T delivery order/guarantees | Containment → restart → explicit replica-dependent host failover |
| D47 | User reccmp/ReAgent/AgentDecompile testing preference | X routes, raw reports, unknown outcomes | Later tools consume actual candidate; no GREEN/exit-code promotion |
| D48 | User many isle-like projects and universal-use matching | X exported layout, recipe/input resolver; R variants | Held-out builds + clean-host relocation, explicit unsupported limits |
| D49 | User design-only correction | Package scope, delivery ledger, historical reconciliation | No product edits, installs, runtime probes or tests for this goal |
| D50 | User collaborative grill/prove-the-effort completion | Independent review and closure log | Review a specific counterexample, amend, independently recheck |

## Implementation dependency order (authorized by the later user build request)

1. Type evidence, separate binding predicates and withdrawal, and derive exhaustive
   coverage from receipts. Reject the false-label case before increasing throughput.
2. Wrap one existing verifier/compiler path with the common task/acceptance protocol:
   immutable inputs, private outputs, durable units, version/generation checks and
   independent acceptance. Include the failure-response contract: atomic command/budget
   intent, retry circuits, durable wakes, resource quarantine and control-plane
   outage handling. Require interruption/resume proof before more concurrency.
3. Establish validated region extraction/emission/placement and contribution checks;
   refine compilation groups/toolchain evidence. Feed results into per-recipient
   candidates and independent local/linked checks.
4. Add planned external-tool adapters and portable project recipes behind the same
   contracts. Unsupported providers do not stop other eligible verification routes.
5. Add common admission/retry/storage/scenario mechanisms for the remaining providers,
   then supported original-code bindings and complete combined demonstrations.
6. Expand concurrency and remote providers only after containment and resume gates;
   final source claims still require fresh current-source whole-image evidence.

Implementation status and the ongoing completion gate are tracked in the
[session obligation audit](2026-09-22-session-obligation-audit.md). The numbered
requirements remain open until their actual software and acceptance evidence exists.

A feature requiring only valid original-code identity/interface/runtime evidence
can proceed as soon as those prerequisites exist. The sequence above is an
implementation dependency plan, not a new barrier forcing runtime use to wait for
all source/reconstruction tooling.

## Design completion gate

The design goal is complete only when all of these are checked on the artifacts:

- Both reviews have requirement-to-contract and future-falsifier coverage.
- Mechanisms specify inputs, outputs, ownership, state changes and failure continuation;
  no known cross-document contradiction is left as an implementation decision.
- Every external integration is a proposal with input/output/claim boundaries;
  no installable dependency change is substituted for a design contract.
- The overview and companion remain readable, editable and synchronized with their
  authoring source; the Documents overview matches the canonical SVG.
- Independent reviewers inspect the actual revised text/diagrams and resolve concrete
  objections; author declarations alone do not close review findings.
- Link/source/XML/diff checks and visual inspection establish artifact quality only.
  Every runtime demonstration and performance/fairness hypothesis remains NOT RUN.

Unknown empirical results (target toolchain behavior, delinker correctness,
performance, runtime support, real cross-host reproducibility) remain **future
verification obligations with decisive tests**, not unresolved architecture choices.
No server, game or compiler is required to complete this design gate.

## Collaboration and resolved challenges

`grill-me` explicitly defers technical critique to `prove-the-effort`; both were read.
The team used concrete claim/referent/check/verdict exchanges, not repeated requests
for user confirmation. The user already specified scope and desired tools.

| Challenge | Decision / concrete correction | Independent reviewer |
|---|---|---|
| Correct bytes can prove the wrong function | Explicit presence/identity/operation predicates; lineage exclusion; Foo/Bar walkthrough | Recovery review |
| Lease expiry is not safe reuse | Separate publication authority/resource access; late matching result does not clear quarantine | Diagram and execution reviewers |
| Representation vs evidence totals | Disjoint representation buckets, overlapping fact/capability axes | Execution reviewer |
| Durable publication vs short DB commit | Filesystem staging/flush/rename outside transaction; short version/fence/manifest commit | Execution reviewer |
| Partial accepted fact vs complete task | All mandatory contracts + required predicates; objective acceptance separate | Root challenged execution author |
| Priority order may defeat aging | Capped same-class reservation, explicit urgent override and no age reset | Root challenged execution author |
| Export may retain author-machine paths | Declarative recipe, content-ID input resolver, clean-host negative acceptance | Diagram reviewer |
| Inconclusive check has no fact state | Explicit unknown/not_run/unsupported/stale distinctions | Diagram reviewer |
| Workbench availability as design blocker | Removed; prior dependency file converted to documentation only | User correction and recovery reviewer |

Final review closes all concrete findings at the design level. Artifact checks are
recorded in the [documentation-only acceptance receipt](../verification/2026-09-22-design-package.md). None of these review concessions asserts
implemented runtime behavior.

## Source provenance and interpretation

| Input | Identity | Use |
|---|---|---|
| H hindsight review | Attachment `a7bcfa80-8844-4a5f-bd88-1e7f31bf2bda/pasted-text.txt`, 27,540 bytes, SHA-256 `4e940239b9656a62229021eb5649b1ac1f22c44fc088023c97ca0d3479dc29d3` | Historical failures → local continuation, ownership, progress, storage and scenarios |
| A architecture review | Attachment `1964612c-8fb0-44de-ab59-da1e53f8833f/pasted-text.txt`, 33,752 bytes, SHA-256 `6f64fb0ca0f7caae1a622b780bf704a8a3458402514fe0142b3b87fd85576182` | Reconstruction, compiler scope, claim separation and runtime capabilities |
| Existing plan and diagram | STRATEGY, consolidated product design, living-plan reconciliation, overview generator | Preserve existing scope and newer lane E rather than reverting to older attached SVG |
| Earlier design-phase correction | Design/diagrams/plan exclusively | Controlled the original design delivery; superseded for subsequent implementation by the explicit build request |
| Later build request and ongoing goal | Build according to the design, then finish all applicable directives | Authorizes current implementation; full obligations remain in the session audit |
| Skills | `/home/brunner56/.agents/skills/grill-me/SKILL.md`; `prove-the-effort/SKILL.md` and `EVOLUTION.md` | Concrete evidence-driven design review and explicit concessions |

The hindsight attachment links an additional sandbox download whose contents are
not separately present. This package implements the recommendations actually
supplied in its text; it does not claim to have read an unavailable extra file.
Historical counts, process/resource observations and prior runtime successes are
not treated as current host measurements. Upstream projects are references, not
AgentDecompile acceptance evidence.


## Failure prevention and recovery refinement

The [complete failure-response specification](2026-09-22-failure-prevention-and-recovery-contracts.md)
refines the eleven historical incident remedies into prevention, detection,
containment, bounded recovery and wake contracts. It also covers the coordinator,
metadata/artifact storage, ambiguous commands, fixture drift, missed wakeups,
policy/schema compatibility and unknown failures. Its linked resilience diagram
complements the overview and execution diagram. Implementation must satisfy these
contracts alongside RC01–10 and A01–20; a fallback cannot weaken the objective or
change acceptance silently. Completion here is design completion only.

Current resilience artifacts and static checks are recorded in the
[resilience design receipt](../verification/2026-09-22-resilience-design.md).
