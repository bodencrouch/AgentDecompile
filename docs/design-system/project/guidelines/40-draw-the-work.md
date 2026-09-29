# Draw the work

The primary feedback is a live, inspectable picture of the actual work. Counts, timestamps, logs and measured ETAs are secondary detail. A spinner and the word "Running" alone are not an acceptable status.

## Work verbs

| Work | Primary picture | Inspectable truth | Component |
|---|---|---|---|
| Extract / parse / unpack | Container tree expands with discovered members; section map resolves into regions | Member offsets, parser, content identity; protected regions stay marked | ContainerTree |
| Candidate comparison | Counterpart blocks align across build lanes; matching strings, refs and anchors highlight | Evidence channel, alternatives, uniqueness and margin, rejection | CandidateAlignment |
| Identity acceptance | Edge changes from candidate to accepted; split and merged regions stay explicit | Decision and supporting witnesses | IdentityEdge |
| Name / type / comment propagation | Exact field before and after, donor → eligible recipient; blocked recipients keep the conflicting field | Per-field origin, precedence, compatibility gate | PropagationTransfer |
| Source repair | Source diff beside the diagnostic that motivated it | Candidate revision, compiler, flags, ABI, retry history | SourceRepairDiff |
| Object verification | Original and generated instructions align; changed operands, registers, bytes, relocations highlight | Exact object pair and comparison receipt | ObjectDiff |
| Whole-image rebuild | Image/section map shows remaining deltas in headers, layout, imports, relocations, resources or functions | Fresh build identity, hashes, differing ranges | ImageDeltaMap |
| Derive / backfill | Row → derived column → receipt; the column changes only after its receipt exists | `{stable_key, build, operation, member, outcome}` | ActivityRecord |
| Runtime reuse | Call and event trace with arguments, returns and state changes linked to the entity | Target build, preflight, observed behavior; never a recovery badge | RuntimeCapabilities |
| Waiting / failover | The affected branch stops at its real unmet dependency while others continue | Named owner or provider failure, last evidence, fallback, retry eligibility | FailureRecord |

## Motion rules

- Motion follows observed events only. No simulated packet travel, random graph motion or timer-driven "compiling" decoration.
- An animated edge or transfer appears only after its accepted or rejected event exists, on both surfaces.
- When a provider exposes only start and finish, show exactly that. Unknown internals are drawn as unobserved.
- Every animated view has freeze, step and history controls (WorkTimeline). Never auto-pan away from the operator.
- Code panes never follow active work. The work view keeps its own freeze, step and history. Its header chip names the job and where it is ("Job a3f9 is at build-b · ResourceRef::Resolve · Go") and updates silently. Go is an explicit move that pushes one history stop, with build-switch and checked-set words when they apply. Work-view events link to the evidence they drew.
- Reduced-motion and keyboard presentations convey the same change as a static before/after.
- The static 8080 surface draws a truthful lighter form (inline row changes, stage details, expandable causes). The full workspace draws the rich animated form. Both replay the same accepted-event receipts.

## Activity readouts

Keep three readouts apart: **liveness** (heartbeat and last event), **execution progress** (durable units completed) and **goal progress** (accepted outcomes). A job record names its owner (managed or external), operation, source and target builds, measured units, last observation, blocking prerequisites and receipt freshness. If progress is not instrumented, write "Progress unknown" and the last event time.

## The one control

WorkflowControl is **pause/resume plus its scope**. There is no Start button and no per-stage Run button. Opening a project, adding binaries or resuming admits eligible missing work by itself; reopening admits nothing that already has a receipt. Pause stops admitting and drains what this scope accepted. It is not cancel, never reports "safe-paused" falsely, and claims nothing over lanes it does not own (runtime reuse, distributed workers, read-only indexing). Those lanes are surfaced beside it.

## Starvation

Draw starvation beside the work (StarvationMeter): the age of the oldest unreviewed review row, the oldest waiting lane, and the longest-running job against its deadline. A job past its deadline is drawn as a named failover, never a spinner.
